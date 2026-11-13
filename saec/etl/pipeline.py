"""Orquestador del proceso ETL."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable


from ..config import SETTINGS, Settings
from ..db import refrescar_vistas
from ..models import ResultadoETL
from ..repositories import ETLRepository
from .extract import DESCRIPCION_TIPO, detectar_tipo, hash_archivo, leer_tabla
from .load import Loader
from .transform import (moda_estrato, transformar_estrato, transformar_individual, transformar_ips,
                        transformar_rips_agregado)

log = logging.getLogger(__name__)
ORDEN = {"ESTRATO": 0, "IPS": 1, "INDIVIDUAL": 2, "RIPS_AGREGADO": 3}
MAX_RECHAZOS_GUARDADOS = 20_000


class Cancelado(Exception):
    pass


def _contar_lineas(path: Path) -> int:
    if path.suffix.lower() not in (".csv", ".txt"):
        return 0
    n = 0
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            n += bloque.count(b"\n")
    return max(n - 1, 1)


class ETLPipeline:
    """Ejecuta Extracción -> Transformación -> Carga para una lista de archivos.

    notificar(mensaje: str, porcentaje: float | None) se llama para informar progreso a la UI o a la consola.
    """

    def __init__(self, archivos: list[Path], id_usuario: int | None = None,
                 notificar: Callable[[str, float | None], None] | None = None,
                 cancelar: threading.Event | None = None, settings: Settings | None = None,
                 guardar_staging: bool = True):
        self.archivos = [Path(a) for a in archivos]
        self.id_usuario = id_usuario
        self.notificar = notificar or (lambda m, p=None: log.info(m))
        self.cancelar = cancelar or threading.Event()
        self.s = settings or SETTINGS
        self.guardar_staging = guardar_staging
        self.repo = ETLRepository()

    def _msg(self, texto: str, pct: float | None = None) -> None:
        self.notificar(f"[{time.strftime('%H:%M:%S')}] {texto}", pct)

    def run(self) -> list[ResultadoETL]:
        tipos = []
        for a in self.archivos:
            if not a.exists():
                raise FileNotFoundError(a)
            t = detectar_tipo(a)
            if t is None:
                raise ValueError(f"No se reconoce el formato de {a.name}. Revise las columnas (ver manual).")
            tipos.append((ORDEN[t], t, a))
        tipos.sort()
        resultados = []
        total = len(tipos)
        for i, (_, tipo, archivo) in enumerate(tipos):
            base, ancho = 100 * i / total, 100 / total
            resultados.append(self._procesar(archivo, tipo, base, ancho))
        self._msg("Actualizando vista materializada mv_casos_resumen ...", 98)
        refrescar_vistas()
        self._msg("ETL finalizado.", 100)
        return resultados

    def _procesar(self, archivo: Path, tipo: str, base: float, ancho: float) -> ResultadoETL:
        r = ResultadoETL()
        h = hash_archivo(archivo)
        r.id_ejecucion = self.repo.iniciar(archivo.name, self.id_usuario, tipo, h)
        self._msg(f"Ejecución #{r.id_ejecucion}: {archivo.name} → {DESCRIPCION_TIPO[tipo]}", base)
        estimado = _contar_lineas(archivo)
        conteos_estrato = []
        try:
            with Loader() as ld:
                previas = self.repo.ejecuciones_previas(h, r.id_ejecucion)
                if previas and tipo in ("RIPS_AGREGADO", "INDIVIDUAL"):
                    n = ld.borrar_ejecuciones(previas)
                    if n:
                        self._msg(f"El archivo ya se había cargado: se reemplazan {n:,} filas anteriores."
                                  .replace(",", "."))
                ips_area: set[str] = set()
                if tipo == "INDIVIDUAL":
                    ld.cur.execute("SELECT codigo_habilitacion FROM institucion WHERE en_area_estudio")
                    ips_area = {row[0] for row in ld.cur.fetchall()}
                for bloque in leer_tabla(archivo, chunksize=50_000):
                    if self.cancelar.is_set():
                        raise Cancelado("Proceso cancelado por el usuario")
                    r.leidos += len(bloque)
                    if self.guardar_staging:
                        ld.staging(bloque, tipo)
                    if tipo == "RIPS_AGREGADO":
                        ok, rech, fuera = transformar_rips_agregado(bloque, self.s.poblacion)
                        r.cargados += ld.atenciones(ok, r.id_ejecucion)
                        r.atenciones += int(ok["cantidad"].sum()) if not ok.empty else 0
                    elif tipo == "INDIVIDUAL":
                        ok, rech, fuera = transformar_individual(bloque, self.s.poblacion, ips_area)
                        r.cargados += ld.atenciones(ok, r.id_ejecucion)
                        r.atenciones += len(ok)
                    elif tipo == "IPS":
                        filas, rech, fuera = transformar_ips(bloque, self.s.poligono)
                        r.cargados += ld.instituciones(filas)
                        dentro = sum(1 for f in filas if f["en_area"])
                        self._msg(f"IPS cargadas: {len(filas)} ({dentro} dentro del área de estudio)")
                    else:
                        conteo, rech, fuera = transformar_estrato(bloque)
                        conteos_estrato.append(conteo)
                    ld.rechazos(rech, r.id_ejecucion, MAX_RECHAZOS_GUARDADOS - r.rechazados)
                    r.rechazados += len(rech)
                    r.fuera_poblacion += fuera
                    pct = base + ancho * min(0.95, r.leidos / estimado) if estimado else base + ancho * 0.5
                    self._msg(f"  {r.leidos:,} leídos · {r.cargados:,} cargados · {r.rechazados:,} rechazados · "
                              f"{r.fuera_poblacion:,} fuera de la población".replace(",", "."), pct)
                if tipo == "ESTRATO":
                    mapa = moda_estrato(conteos_estrato)
                    r.cargados = ld.estratos_localidad(mapa)
                    self._msg(f"Estrato predominante asignado a {r.cargados} localidades")
            r.estado = "EXITOSO"
            self.repo.cerrar(r.id_ejecucion, "EXITOSO", r.leidos, r.cargados, r.rechazados,
                             f"fuera_poblacion={r.fuera_poblacion}; atenciones={r.atenciones}")
            self._msg(f"✔ {archivo.name}: {r.cargados:,} registros cargados ({r.atenciones:,} atenciones)".replace(",", "."),
                      base + ancho)
        except Exception as exc:
            r.estado = "FALLIDO"
            self.repo.cerrar(r.id_ejecucion, "FALLIDO", r.leidos, 0, r.rechazados, str(exc))
            self._msg(f"✖ {archivo.name}: {exc} (se hizo ROLLBACK, la base de datos no cambió)")
            raise
        return r


def ejecutar(archivos, id_usuario=None, notificar=None) -> list[ResultadoETL]:
    return ETLPipeline(archivos, id_usuario, notificar).run()
