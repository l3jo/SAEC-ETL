"""Capa de acceso a datos: todas las consultas SQL del sistema están aquí."""
from __future__ import annotations

import json
import zlib

import pandas as pd
from sqlalchemy import text

from .db import Database
from .models import Filtro


def _where_resumen(f: Filtro) -> tuple[str, dict]:
    """Condiciones comunes sobre mv_casos_resumen / v_casos (parámetros enlazados)."""
    cond = ["grupo_edad = ANY(:grupos)"]
    p: dict = {"grupos": f.grupos_incluidos()}
    if f.estrato:
        cond.append("estrato = :estrato"); p["estrato"] = f.estrato
    else:  # los datos agregados (RIPS público) no traen estrato: se conservan como "sin estrato"
        cond.append("(estrato IS NULL OR estrato IN (1, 2, 3))")
    if f.enfermedad:
        cond.append("enfermedad = :enf"); p["enf"] = f.enfermedad
    if f.anio:
        cond.append("anio = :anio"); p["anio"] = f.anio
    else:
        cond.append("anio BETWEEN 2020 AND 2026")
    if f.id_ips:
        cond.append("id_institucion = :ips"); p["ips"] = f.id_ips
    if f.localidad:
        cond.append("localidad = :loc"); p["loc"] = f.localidad
    if f.origen:
        cond.append("origen = :origen"); p["origen"] = f.origen
    return " AND ".join(cond), p


class AtencionRepository:
    def __init__(self, db: Database | None = None):
        self.db = db or Database.get()

    def resumen(self, f: Filtro) -> pd.DataFrame:
        """Filas agregadas (anio, enfermedad, grupo_edad, sexo, estrato, localidad, institucion, casos)."""
        where, p = _where_resumen(f)
        sql = f"""SELECT anio, enfermedad, grupo_edad, sexo, estrato, localidad, id_institucion,
                         institucion, origen, casos
                  FROM mv_casos_resumen WHERE {where}"""
        df = self.db.consultar(sql, **p)
        if not df.empty:
            df["casos"] = df["casos"].astype(int)
            df["estrato"] = df["estrato"].astype("Int64")
        return df

    def atenciones_paginadas(self, f: Filtro, pagina: int, limite: int) -> tuple[pd.DataFrame, int]:
        where, p = _where_resumen(f)
        # en la vista detallada la edad exacta se filtra cuando existe
        where += " AND (edad IS NULL OR edad BETWEEN :emin AND :emax)"
        p.update(emin=f.edad_min, emax=f.edad_max)
        total = self.db.escalar(f"SELECT COUNT(*) FROM v_casos WHERE {where}", **p) or 0
        p.update(lim=limite, off=(max(pagina, 1) - 1) * limite)
        df = self.db.consultar(
            f"""SELECT id_atencion, anio, enfermedad, codigo_cie10, sexo,
                       COALESCE(edad::text, grupo_edad) AS edad, estrato, localidad,
                       COALESCE(institucion, '—') AS institucion, cantidad, origen
                FROM v_casos WHERE {where}
                ORDER BY anio DESC, id_atencion LIMIT :lim OFFSET :off""", **p)
        return df, int(total)

    def personas_unicas(self, f: Filtro) -> int:
        where, p = _where_resumen(f)
        return int(self.db.escalar(f"SELECT COUNT(DISTINCT paciente_hash) FROM v_casos WHERE {where}", **p) or 0)

    def usa_datos_demo(self, origen: str | None) -> bool:
        """True si alguna fila viene de un archivo de demostración (nombre con 'demo')."""
        return bool(self.db.escalar("""SELECT bool_or(e.fuente ILIKE '%demo%') FROM atencion a
                                       JOIN etl_ejecucion e ON e.id_ejecucion = a.id_ejecucion
                                       WHERE (:o IS NULL OR a.origen = :o)""", o=origen))

    def origenes(self) -> dict[str, int]:
        df = self.db.consultar("SELECT origen, SUM(cantidad)::bigint AS n FROM atencion GROUP BY origen")
        return dict(zip(df["origen"], df["n"].astype(int))) if not df.empty else {}

    def total_atenciones(self) -> int:
        return int(self.db.escalar("SELECT COALESCE(SUM(cantidad),0) FROM atencion") or 0)

    def calidad(self) -> dict:
        df = self.db.consultar("""
            SELECT origen, COUNT(*) AS filas, SUM(cantidad) AS atenciones,
                   SUM(CASE WHEN id_estrato IS NULL THEN cantidad ELSE 0 END) AS sin_estrato,
                   SUM(CASE WHEN id_institucion IS NULL THEN cantidad ELSE 0 END) AS sin_ips
            FROM atencion GROUP BY origen""")
        return {r["origen"]: {k: int(r[k] or 0) for k in ("filas", "atenciones", "sin_estrato", "sin_ips")}
                for _, r in df.iterrows()}


class CatalogoRepository:
    def __init__(self, db: Database | None = None):
        self.db = db or Database.get()

    def enfermedades(self) -> pd.DataFrame:
        return self.db.consultar("SELECT id_enfermedad AS id, nombre, codigo_cie10, categoria FROM enfermedad ORDER BY id_enfermedad")

    def anios(self) -> list[int]:
        df = self.db.consultar("SELECT DISTINCT anio FROM atencion ORDER BY anio")
        return [int(a) for a in df["anio"]] if not df.empty else []

    def localidades_area(self) -> list[str]:
        df = self.db.consultar("SELECT nombre FROM localidad WHERE en_area_estudio ORDER BY nombre")
        return list(df["nombre"])


class LocalidadRepository:
    def __init__(self, db: Database | None = None):
        self.db = db or Database.get()

    def mapa(self) -> dict[str, int]:
        df = self.db.consultar("SELECT nombre, id_localidad FROM localidad")
        return dict(zip(df["nombre"], df["id_localidad"]))

    def asegurar(self, codigo: str | None, nombre: str) -> int:
        """Devuelve el id de la localidad, creándola si no existe."""
        with self.db.engine.begin() as con:
            r = con.execute(text("SELECT id_localidad FROM localidad WHERE nombre = :n"), {"n": nombre}).scalar()
            if r:
                return r
            cod = (codigo or "").strip() or f"X{zlib.crc32(nombre.encode()) % 999:03d}"
            return con.execute(text("""INSERT INTO localidad (codigo, nombre) VALUES (:c, :n)
                                       ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre
                                       RETURNING id_localidad"""), {"c": cod[:4], "n": nombre}).scalar()

    def marcar_area_estudio(self, nombres) -> None:
        self.db.ejecutar("UPDATE localidad SET en_area_estudio = (nombre = ANY(:n))", n=list(nombres))

    def asignar_estrato(self, estratos: dict[str, int]) -> int:
        n = 0
        with self.db.engine.begin() as con:
            for nombre, est in estratos.items():
                n += con.execute(text("""UPDATE localidad SET id_estrato_predominante =
                                         (SELECT id_estrato FROM estrato WHERE numero_estrato = :e)
                                         WHERE nombre = :n"""), {"e": int(est), "n": nombre}).rowcount
        return n

    def estrato_predominante(self) -> dict[str, int]:
        df = self.db.consultar("""SELECT l.nombre, e.numero_estrato FROM localidad l
                                  JOIN estrato e ON e.id_estrato = l.id_estrato_predominante""")
        return dict(zip(df["nombre"], df["numero_estrato"].astype(int)))


class IPSRepository:
    def __init__(self, db: Database | None = None):
        self.db = db or Database.get()

    def listar(self, f: Filtro) -> pd.DataFrame:
        where, p = _where_resumen(f)
        return self.db.consultar(f"""
            SELECT i.id_institucion AS id, i.nombre, i.direccion,
                   i.latitud::float AS latitud, i.longitud::float AS longitud,
                   COALESCE(c.total, 0)::int AS total_casos
            FROM institucion i
            LEFT JOIN (SELECT id_institucion, SUM(casos) AS total FROM mv_casos_resumen
                       WHERE {where} GROUP BY id_institucion) c ON c.id_institucion = i.id_institucion
            WHERE i.en_area_estudio
            ORDER BY total_casos DESC, i.nombre""", **p)

    def detalle(self, id_ips: int, f: Filtro) -> pd.DataFrame:
        f2 = Filtro(**{**f.__dict__, "id_ips": id_ips})
        where, p = _where_resumen(f2)
        return self.db.consultar(f"""SELECT enfermedad, SUM(casos)::int AS casos FROM mv_casos_resumen
                                     WHERE {where} GROUP BY enfermedad ORDER BY casos DESC""", **p)

    def mapa_codigos(self) -> dict[str, int]:
        df = self.db.consultar("SELECT codigo_habilitacion, id_institucion FROM institucion WHERE codigo_habilitacion IS NOT NULL")
        return dict(zip(df["codigo_habilitacion"], df["id_institucion"]))

    def upsert(self, filas: list[dict]) -> int:
        sql = text("""INSERT INTO institucion (codigo_habilitacion, nombre, direccion, latitud, longitud,
                                               id_localidad, en_area_estudio)
                      VALUES (:codigo, :nombre, :direccion, :latitud, :longitud, :id_localidad, :en_area)
                      ON CONFLICT (codigo_habilitacion) DO UPDATE SET
                        nombre = EXCLUDED.nombre, direccion = EXCLUDED.direccion,
                        latitud = EXCLUDED.latitud, longitud = EXCLUDED.longitud,
                        id_localidad = EXCLUDED.id_localidad, en_area_estudio = EXCLUDED.en_area_estudio""")
        with self.db.engine.begin() as con:
            for f in filas:
                con.execute(sql, f)
        return len(filas)


class UsuarioRepository:
    def __init__(self, db: Database | None = None):
        self.db = db or Database.get()

    def por_correo(self, correo: str) -> dict | None:
        df = self.db.consultar("SELECT * FROM usuario WHERE lower(correo) = lower(:c)", c=correo)
        return None if df.empty else df.iloc[0].to_dict()

    def listar(self) -> pd.DataFrame:
        return self.db.consultar("""SELECT id_usuario, nombre, correo, rol, activo,
                                           to_char(fecha_creacion, 'YYYY-MM-DD') AS creado
                                    FROM usuario ORDER BY id_usuario""")

    def crear(self, nombre: str, correo: str, contrasena_hash: str, rol: str) -> int:
        with self.db.engine.begin() as con:
            return con.execute(text("""INSERT INTO usuario (nombre, correo, contrasena_hash, rol)
                                       VALUES (:n, :c, :h, :r) RETURNING id_usuario"""),
                               {"n": nombre, "c": correo, "h": contrasena_hash, "r": rol}).scalar()

    def actualizar(self, id_usuario: int, nombre: str, rol: str, activo: bool, contrasena_hash: str | None) -> None:
        sql = "UPDATE usuario SET nombre=:n, rol=:r, activo=:a" + (", contrasena_hash=:h" if contrasena_hash else "") + " WHERE id_usuario=:id"
        self.db.ejecutar(sql, n=nombre, r=rol, a=activo, h=contrasena_hash, id=id_usuario)

    def contar(self) -> int:
        return int(self.db.escalar("SELECT COUNT(*) FROM usuario") or 0)


class ETLRepository:
    def __init__(self, db: Database | None = None):
        self.db = db or Database.get()

    def iniciar(self, fuente: str, id_usuario: int | None, tipo: str = "", archivo_hash: str = "") -> int:
        with self.db.engine.begin() as con:
            return con.execute(text("""INSERT INTO etl_ejecucion (fuente, tipo_archivo, archivo_hash, id_usuario)
                                       VALUES (:f, :t, :h, :u) RETURNING id_ejecucion"""),
                               {"f": fuente[:250], "t": tipo, "h": archivo_hash or None, "u": id_usuario}).scalar()

    def ejecuciones_previas(self, archivo_hash: str, excluir: int) -> list[int]:
        df = self.db.consultar("""SELECT id_ejecucion FROM etl_ejecucion
                                  WHERE archivo_hash = :h AND id_ejecucion <> :e AND estado = 'EXITOSO'""", h=archivo_hash, e=excluir)
        return [int(x) for x in df["id_ejecucion"]] if not df.empty else []

    def cerrar(self, id_ejec: int, estado: str, leidos: int, cargados: int, rechazados: int, mensaje: str = "") -> None:
        self.db.ejecutar("""UPDATE etl_ejecucion SET fecha_fin = now(), estado = :e, registros_leidos = :l,
                            registros_cargados = :c, registros_rechazados = :r, mensaje = :m
                            WHERE id_ejecucion = :id""",
                         e=estado, l=leidos, c=cargados, r=rechazados, m=mensaje[:4000], id=id_ejec)

    def historial(self, limite: int = 30) -> pd.DataFrame:
        return self.db.consultar("""
            SELECT id_ejecucion AS id, to_char(fecha_inicio, 'YYYY-MM-DD HH24:MI') AS inicio,
                   fuente, registros_leidos AS leidos, registros_cargados AS cargados,
                   registros_rechazados AS rechazados, estado
            FROM etl_ejecucion ORDER BY id_ejecucion DESC LIMIT :l""", l=limite)

    def rechazos(self, id_ejec: int, limite: int = 500) -> pd.DataFrame:
        return self.db.consultar("""SELECT motivo, registro_original::text AS registro FROM etl_rechazo
                                    WHERE id_ejecucion = :id LIMIT :l""", id=id_ejec, l=limite)

    def ultima_exitosa(self) -> dict | None:
        df = self.db.consultar("""SELECT * FROM etl_ejecucion WHERE estado = 'EXITOSO'
                                  ORDER BY id_ejecucion DESC LIMIT 1""")
        return None if df.empty else df.iloc[0].to_dict()


class SalidaRepository:
    """Reportes y diagnósticos generados."""

    def __init__(self, db: Database | None = None):
        self.db = db or Database.get()

    def registrar_reporte(self, id_usuario, tipo, formato, filtros: dict, ruta: str) -> None:
        self.db.ejecutar("""INSERT INTO reporte (id_usuario, tipo, formato, filtros, ruta_archivo)
                            VALUES (:u, :t, :f, CAST(:fi AS JSONB), :r)""",
                         u=id_usuario, t=tipo, f=formato, fi=json.dumps(filtros), r=ruta)

    def registrar_diagnostico(self, id_usuario, filtros: dict, resumen: str, resultado: dict) -> int:
        with self.db.engine.begin() as con:
            return con.execute(text("""INSERT INTO diagnostico (id_usuario, filtros, resumen, resultado)
                                       VALUES (:u, CAST(:f AS JSONB), :r, CAST(:res AS JSONB))
                                       RETURNING id_diagnostico"""),
                               {"u": id_usuario, "f": json.dumps(filtros), "r": resumen,
                                "res": json.dumps(resultado, default=str)}).scalar()
