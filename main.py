"""SAEC - Sistema de Análisis de Enfermedades Crónicas (software de escritorio).

Uso:
    python main.py                      -> abre la aplicación (interfaz Tkinter)
    python main.py instalar             -> crea la base de datos, tablas, vistas y el usuario administrador
    python main.py demo                 -> instala + genera datos de demostración + ETL + diagnóstico PDF
    python main.py etl ARCHIVO [...]    -> ejecuta el ETL sobre uno o varios archivos (CSV, XLSX, GeoJSON)
    python main.py diagnostico [--pdf RUTA] [--excel RUTA] [--fuente INDIVIDUAL|AGREGADO]
                                        -> genera el diagnóstico sin abrir la interfaz
    python main.py usuario CORREO NOMBRE ROL   -> crea un usuario (pide la contraseña)

En la versión portable (carpeta runtime/ presente) PostgreSQL se inicia y se detiene automáticamente.
"""
from __future__ import annotations

import argparse
import getpass
import logging
import sys
from pathlib import Path

import os

from saec.config import SETTINGS, base_dir

LOG_DIR = base_dir() / "logs"
# caché de Matplotlib dentro de la carpeta (no escribe en el perfil del usuario en la versión portable)
if (base_dir() / "runtime").exists():
    os.environ.setdefault("MPLCONFIGDIR", str(base_dir() / "runtime" / "cache" / "matplotlib"))


def configurar_logs() -> None:
    # La consola de Windows usa cp1252/cp850: se fuerza UTF-8 para que tildes y símbolos no detengan el programa.
    for flujo in (sys.stdout, sys.stderr):
        if flujo is not None and hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    LOG_DIR.mkdir(exist_ok=True)
    manejadores = [logging.FileHandler(LOG_DIR / "saec.log", encoding="utf-8")]
    if sys.stdout is not None:  # con pythonw.exe no hay consola
        manejadores.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=manejadores)


def cmd_instalar(_args=None) -> None:
    from saec.db import instalar_esquema
    from saec.services.auth import AuthService
    print(f"Instalando esquema en {SETTINGS.db.host}:{SETTINGS.db.port}/{SETTINGS.db.dbname} ...")
    instalar_esquema()
    if AuthService().asegurar_admin():
        print("Usuario administrador creado:  admin@saec.local  /  Admin2026  (cámbielo al ingresar)")
    print("Instalación completa.")


def _imprimir(msg, pct=None):
    print(msg if pct is None else f"{msg}  [{pct:5.1f} %]")


def cmd_etl(args) -> None:
    from saec.etl.pipeline import ETLPipeline
    res = ETLPipeline([Path(a) for a in args.archivos], notificar=_imprimir).run()
    for r in res:
        print(f"Ejecución #{r.id_ejecucion}: {r.estado} · leídos {r.leidos} · cargados {r.cargados} · "
              f"rechazados {r.rechazados} · fuera de población {r.fuera_poblacion}")


def cmd_diagnostico(args) -> None:
    from saec.models import Filtro
    from saec.services import reportes
    from saec.services.diagnostico import DiagnosticoService
    svc = DiagnosticoService()
    fuente = args.fuente or svc.fuente_por_defecto()
    dx = svc.generar(Filtro(origen=fuente))
    print(dx.texto())
    carpeta = base_dir() / "reportes"
    if args.pdf is not None:
        ruta = reportes.diagnostico_pdf(dx, Path(args.pdf) if args.pdf else reportes.nombre_archivo("diagnostico", "pdf", carpeta))
        print(f"\nPDF generado: {ruta}")
    if args.excel is not None:
        ruta = reportes.diagnostico_excel(dx, Path(args.excel) if args.excel else reportes.nombre_archivo("diagnostico", "xlsx", carpeta))
        print(f"Excel generado: {ruta}")


def cmd_demo(_args) -> None:
    from saec.etl import demo_data
    from saec.etl.pipeline import ETLPipeline
    cmd_instalar()
    carpeta = base_dir() / "datos_demo"
    print(f"Generando datos de demostración en {carpeta} ...")
    archivos = demo_data.generar(carpeta)
    # Para la demo se cargan los registros individuales (traen estrato e IPS).
    # El archivo rips_agregado_demo.csv queda como ejemplo del formato de Datos Abiertos.
    ETLPipeline([a for a in archivos if "rips_agregado" not in a.name], notificar=_imprimir).run()
    ns = argparse.Namespace(pdf="", excel="", fuente="INDIVIDUAL")
    cmd_diagnostico(ns)


def cmd_usuario(args) -> None:
    from saec.services.auth import AuthService
    clave = getpass.getpass("Contraseña: ")
    uid = AuthService().crear(args.nombre, args.correo, clave, args.rol.upper())
    print(f"Usuario creado con id {uid}")


def cmd_gui(_args=None) -> None:
    from saec.ui.app import App
    App().mainloop()


def main(argv=None) -> None:
    configurar_logs()
    p = argparse.ArgumentParser(prog="saec", description="Sistema de Análisis de Enfermedades Crónicas")
    sp = p.add_subparsers(dest="cmd")
    sp.add_parser("gui", help="Abrir la interfaz gráfica").set_defaults(func=cmd_gui)
    sp.add_parser("instalar", help="Crear base de datos y tablas").set_defaults(func=cmd_instalar)
    sp.add_parser("demo", help="Instalar, cargar datos de demostración y generar diagnóstico").set_defaults(func=cmd_demo)
    e = sp.add_parser("etl", help="Ejecutar ETL"); e.add_argument("archivos", nargs="+"); e.set_defaults(func=cmd_etl)
    d = sp.add_parser("diagnostico", help="Generar diagnóstico")
    d.add_argument("--pdf", nargs="?", const="", default=None, help="Ruta del PDF (opcional)")
    d.add_argument("--excel", nargs="?", const="", default=None, help="Ruta del Excel (opcional)")
    d.add_argument("--fuente", choices=["INDIVIDUAL", "AGREGADO"], default=None)
    d.set_defaults(func=cmd_diagnostico)
    u = sp.add_parser("usuario", help="Crear usuario")
    u.add_argument("correo"); u.add_argument("nombre"); u.add_argument("rol", choices=["ANALISTA", "ADMINISTRADOR", "analista", "administrador"])
    u.set_defaults(func=cmd_usuario)
    args = p.parse_args(argv)
    funcion = getattr(args, "func", None) or cmd_gui
    if funcion is not cmd_gui:  # la interfaz arranca la base portable en la pantalla de inicio
        from saec import portable
        info = portable.asegurar_servidor(print)
        if info:
            print(info)
    try:
        funcion(args)
    finally:
        from saec import portable
        portable.detener()


if __name__ == "__main__":
    main()
