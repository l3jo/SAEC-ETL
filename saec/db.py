"""Conexión a PostgreSQL (SQLAlchemy) e instalación del esquema."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import SETTINGS, DBConfig, base_dir

log = logging.getLogger(__name__)
SQL_DIR = base_dir() / "db"


class Database:
    """Singleton con el engine de SQLAlchemy (pool de conexiones)."""

    _instancia: "Database | None" = None
    _lock = threading.Lock()

    def __init__(self, cfg: DBConfig):
        self.cfg = cfg
        self.engine: Engine = create_engine(cfg.url(), pool_pre_ping=True, future=True)

    @classmethod
    def get(cls) -> "Database":
        with cls._lock:
            if cls._instancia is None:
                cls._instancia = Database(SETTINGS.db)
            return cls._instancia

    @classmethod
    def reiniciar(cls, cfg: DBConfig | None = None) -> None:
        with cls._lock:
            if cls._instancia is not None:
                cls._instancia.engine.dispose()
            cls._instancia = Database(cfg or SETTINGS.db)

    # -- utilidades --
    def consultar(self, sql: str, **params) -> pd.DataFrame:
        with self.engine.connect() as con:
            res = con.execute(text(sql), params)
            return pd.DataFrame(res.fetchall(), columns=list(res.keys()))

    def escalar(self, sql: str, **params):
        with self.engine.connect() as con:
            return con.execute(text(sql), params).scalar()

    def ejecutar(self, sql: str, **params) -> None:
        with self.engine.begin() as con:
            con.execute(text(sql), params)


def probar_conexion(cfg: DBConfig) -> tuple[bool, str]:
    try:
        eng = create_engine(cfg.url(), future=True)
        with eng.connect() as con:
            v = con.execute(text("SELECT version()")).scalar()
        eng.dispose()
        return True, v.split(",")[0]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc).splitlines()[0]


def crear_base_si_no_existe(cfg: DBConfig) -> bool:
    """Crea la base de datos (p. ej. 'saec') si no existe. Devuelve True si la creó."""
    eng = create_engine(cfg.url(cfg.admin_db), isolation_level="AUTOCOMMIT", future=True)
    with eng.connect() as con:
        existe = con.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": cfg.dbname}).scalar()
        if not existe:
            con.execute(text(f'CREATE DATABASE "{cfg.dbname}" ENCODING \'UTF8\' TEMPLATE template0'))
    eng.dispose()
    return not existe


def ejecutar_script(engine: Engine, ruta: Path) -> None:
    sql = Path(ruta).read_text(encoding="utf-8")
    with engine.begin() as con:
        con.exec_driver_sql(sql)


def instalar_esquema(cfg: DBConfig | None = None) -> None:
    """Crea la base, tablas, vistas y catálogos. Es idempotente (se puede repetir)."""
    cfg = cfg or SETTINGS.db
    if crear_base_si_no_existe(cfg):
        log.info("Base de datos %s creada", cfg.dbname)
    Database.reiniciar(cfg)
    eng = Database.get().engine
    for nombre in ("01_schema.sql", "02_vistas.sql", "03_semillas.sql"):
        ejecutar_script(eng, SQL_DIR / nombre)
        log.info("Ejecutado %s", nombre)
    from .repositories import LocalidadRepository
    LocalidadRepository().marcar_area_estudio(SETTINGS.poblacion.localidades)


def refrescar_vistas() -> None:
    Database.get().ejecutar("REFRESH MATERIALIZED VIEW mv_casos_resumen")
