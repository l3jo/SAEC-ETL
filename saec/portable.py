"""MODO PORTABLE: PostgreSQL incluido dentro de la carpeta del programa.

Estructura esperada (la crea tools/construir_portable.py):
    SAEC_Portable/
        runtime/python/   Python 3.12 con todas las librerías
        runtime/pgsql/    binarios de PostgreSQL (bin/, lib/, share/)
        datos_pg/         base de datos (se crea sola en el primer arranque)

Al abrir SAEC:   inicializa el clúster si no existe (initdb), lo arranca en un puerto local
                 (solo 127.0.0.1), crea las tablas y el usuario administrador.
Al cerrar SAEC:  detiene el servidor (pg_ctl stop), de modo que la carpeta se puede copiar o
                 llevar en una memoria USB a otro equipo.
"""
from __future__ import annotations

import atexit
import logging
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from typing import Callable

from .config import SETTINGS, DBConfig, base_dir, guardar_db

log = logging.getLogger(__name__)
WINDOWS = sys.platform.startswith("win")
EXE = ".exe" if WINDOWS else ""
RUNTIME = base_dir() / "runtime"
PG_HOME = RUNTIME / "pgsql"
PG_BIN = PG_HOME / "bin"
PG_DATA = base_dir() / "datos_pg"
PG_LOG = base_dir() / "logs" / "postgresql.log"
_iniciado_por_saec = False


class ErrorPortable(Exception):
    pass


def es_portable() -> bool:
    modo = os.environ.get("SAEC_PORTABLE", SETTINGS.portable_modo).lower()
    return modo != "desactivado" and (PG_BIN / f"pg_ctl{EXE}").exists()


def _run(args: list, timeout: int = 180, check: bool = True) -> subprocess.CompletedProcess:
    """Ejecuta un binario de PostgreSQL sin ventana de consola.

    La salida va a un archivo temporal y no a tuberías: en Windows el proceso postgres que deja
    `pg_ctl start` hereda los manejadores y una tubería haría esperar a Python indefinidamente."""
    flags = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW
    env = dict(os.environ)
    env["PATH"] = str(PG_BIN) + os.pathsep + env.get("PATH", "")
    env.pop("PGDATA", None)
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as salida:
        r = subprocess.run([str(a) for a in args], stdout=salida, stderr=subprocess.STDOUT, timeout=timeout,
                           creationflags=flags, env=env, stdin=subprocess.DEVNULL, close_fds=True)
        salida.seek(0)
        texto = salida.read()
    r.stdout, r.stderr = texto, ""
    if check and r.returncode != 0:
        raise ErrorPortable((texto or f"código {r.returncode}").strip()[-800:])
    return r


def _puerto_libre(preferido: int) -> int:
    for p in [preferido, *range(54329, 54400)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise ErrorPortable("No hay puertos libres entre 54329 y 54399.")


def inicializado() -> bool:
    return (PG_DATA / "PG_VERSION").exists()


def corriendo() -> int | None:
    """Puerto del servidor si está en ejecución (según pg_ctl status y postmaster.pid)."""
    if not inicializado():
        return None
    r = _run([PG_BIN / f"pg_ctl{EXE}", "status", "-D", PG_DATA], check=False, timeout=30)
    if r.returncode != 0:
        return None
    try:
        lineas = (PG_DATA / "postmaster.pid").read_text().splitlines()
        return int(lineas[3])
    except (OSError, IndexError, ValueError):
        return None


def inicializar(notificar: Callable[[str], None]) -> None:
    notificar("Creando la base de datos portable (solo la primera vez, puede tardar un minuto)…")
    PG_DATA.mkdir(parents=True, exist_ok=True)
    clave = secrets.token_urlsafe(18)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pw", encoding="utf-8") as f:
        f.write(clave)
        pwfile = f.name
    try:
        _run([PG_BIN / f"initdb{EXE}", "-D", PG_DATA, "-U", "postgres", "--pwfile", pwfile,
              "-A", "scram-sha-256", "-E", "UTF8", "--no-locale", "--no-instructions"], timeout=600)
    finally:
        os.unlink(pwfile)
    # configuración mínima: solo conexiones locales y poca memoria
    with open(PG_DATA / "postgresql.conf", "a", encoding="utf-8") as f:
        f.write("\n# --- SAEC portable ---\nlisten_addresses = '127.0.0.1'\nshared_buffers = 128MB\n"
                "max_connections = 30\nlogging_collector = off\n")
    cfg = DBConfig("127.0.0.1", SETTINGS.portable_puerto, SETTINGS.db.dbname or "saec", "postgres", clave, "postgres")
    guardar_db(cfg)
    SETTINGS.db = cfg


def iniciar(notificar: Callable[[str], None]) -> int:
    global _iniciado_por_saec
    puerto = corriendo()
    if puerto:
        return puerto
    puerto = _puerto_libre(SETTINGS.portable_puerto)
    notificar(f"Iniciando PostgreSQL portable en el puerto {puerto}…")
    PG_LOG.parent.mkdir(parents=True, exist_ok=True)
    _run([PG_BIN / f"pg_ctl{EXE}", "start", "-D", PG_DATA, "-l", PG_LOG, "-w", "-t", "120",
          "-o", f"-p {puerto}"], timeout=180)
    _iniciado_por_saec = True
    atexit.register(detener)
    return puerto


def detener() -> None:
    """Detiene el servidor si lo inició este proceso (se llama al cerrar SAEC)."""
    global _iniciado_por_saec
    if _iniciado_por_saec and inicializado():
        try:
            from .db import Database
            Database.get().engine.dispose()
        except Exception:  # noqa: BLE001
            pass
        _run([PG_BIN / f"pg_ctl{EXE}", "stop", "-D", PG_DATA, "-m", "fast", "-w", "-t", "60"], check=False, timeout=90)
        _iniciado_por_saec = False
        log.info("PostgreSQL portable detenido")


def asegurar_servidor(notificar: Callable[[str], None] | None = None) -> str:
    """Deja la base portable lista para usar. Devuelve un mensaje para la interfaz ('' si no es portable)."""
    if not es_portable():
        return ""
    notificar = notificar or (lambda m: log.info(m))
    if not inicializado():
        inicializar(notificar)
    puerto = iniciar(notificar)
    if SETTINGS.db.port != puerto or SETTINGS.db.host not in ("127.0.0.1", "localhost"):
        SETTINGS.db.host, SETTINGS.db.port = "127.0.0.1", puerto
        guardar_db(SETTINGS.db)
    from .db import Database, instalar_esquema
    Database.reiniciar(SETTINGS.db)
    try:
        n = Database.get().escalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'atencion'")
    except Exception:  # noqa: BLE001  (la base 'saec' aún no existe)
        n = 0
    if not n:
        notificar("Creando tablas de SAEC…")
        instalar_esquema(SETTINGS.db)
        from .services.auth import AuthService
        AuthService().asegurar_admin()
    return f"PostgreSQL portable · puerto {puerto} · {PG_DATA}"
