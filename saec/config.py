"""Lectura y escritura de config/settings.ini."""
from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def base_dir() -> Path:
    """Carpeta raíz del programa (funciona también empaquetado con PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


CONFIG_PATH = Path(os.environ.get("SAEC_CONFIG", base_dir() / "config" / "settings.ini"))


@dataclass
class DBConfig:
    host: str = "localhost"
    port: int = 5432
    dbname: str = "saec"
    user: str = "postgres"
    password: str = ""
    admin_db: str = "postgres"

    def url(self, dbname: str | None = None) -> str:
        from urllib.parse import quote_plus
        return (f"postgresql+psycopg2://{quote_plus(self.user)}:{quote_plus(self.password)}"
                f"@{self.host}:{self.port}/{dbname or self.dbname}")


@dataclass
class PoblacionConfig:
    edad_min: int = 18
    edad_max: int = 59
    anio_min: int = 2020
    anio_max: int = 2026
    estratos: tuple = (1, 2, 3)
    localidades: tuple = ("CHAPINERO",)
    incluir_quinquenio_parcial: bool = False


@dataclass
class Settings:
    db: DBConfig = field(default_factory=DBConfig)
    poblacion: PoblacionConfig = field(default_factory=PoblacionConfig)
    poligono: list = field(default_factory=list)
    carpeta_datos: Path = Path("datos")
    carpeta_rechazos: Path = Path("datos/rechazados")
    tamano_lote: int = 5000
    tema: str = "clam"
    registros_por_pagina: int = 50
    portable_modo: str = "auto"
    portable_puerto: int = 54329


def _lista(texto: str) -> list[str]:
    return [t.strip() for t in texto.split(",") if t.strip()]


def cargar(path: Path | None = None) -> Settings:
    path = Path(path or CONFIG_PATH)
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")
    s = Settings()
    if cp.has_section("database"):
        d = cp["database"]
        s.db = DBConfig(d.get("host", "localhost"), d.getint("port", 5432), d.get("dbname", "saec"),
                        d.get("user", "postgres"), d.get("password", ""), d.get("admin_db", "postgres"))
    # variables de entorno tienen prioridad (útil para pruebas / servidores)
    for attr, env in [("host", "SAEC_DB_HOST"), ("dbname", "SAEC_DB_NAME"), ("user", "SAEC_DB_USER"),
                      ("password", "SAEC_DB_PASSWORD")]:
        if os.environ.get(env):
            setattr(s.db, attr, os.environ[env])
    if os.environ.get("SAEC_DB_PORT"):
        s.db.port = int(os.environ["SAEC_DB_PORT"])
    if cp.has_section("poblacion"):
        p = cp["poblacion"]
        s.poblacion = PoblacionConfig(
            p.getint("edad_min", 18), p.getint("edad_max", 59), p.getint("anio_min", 2020),
            p.getint("anio_max", 2026), tuple(int(x) for x in _lista(p.get("estratos", "1,2,3"))),
            tuple(x.upper() for x in _lista(p.get("localidades", "CHAPINERO"))),
            p.getboolean("incluir_quinquenio_parcial", False))
    if cp.has_section("area_estudio"):
        pts = []
        for par in cp["area_estudio"].get("poligono", "").split(";"):
            if par.strip():
                lat, lon = (float(v) for v in par.split(","))
                pts.append((lat, lon))
        s.poligono = pts
    if cp.has_section("etl"):
        e = cp["etl"]
        s.carpeta_datos = base_dir() / e.get("carpeta_datos", "datos")
        s.carpeta_rechazos = base_dir() / e.get("carpeta_rechazos", "datos/rechazados")
        s.tamano_lote = e.getint("tamano_lote", 5000)
    if cp.has_section("portable"):
        s.portable_modo = cp["portable"].get("modo", "auto").strip().lower()
        s.portable_puerto = cp["portable"].getint("puerto", 54329)
    if cp.has_section("ui"):
        s.tema = cp["ui"].get("tema", "clam")
        s.registros_por_pagina = cp["ui"].getint("registros_por_pagina", 50)
    return s


def guardar_db(db: DBConfig, path: Path | None = None) -> None:
    """Actualiza solo la sección [database] conservando el resto del archivo."""
    path = Path(path or CONFIG_PATH)
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")
    if not cp.has_section("database"):
        cp.add_section("database")
    for k, v in [("host", db.host), ("port", db.port), ("dbname", db.dbname), ("user", db.user),
                 ("password", db.password), ("admin_db", db.admin_db)]:
        cp["database"][k] = str(v)
    with open(path, "w", encoding="utf-8") as f:
        cp.write(f)


SETTINGS = cargar()
