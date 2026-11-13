"""EXTRACCIÓN: lectura de CSV, XLSX y GeoJSON, y detección automática del tipo de archivo."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterator

import pandas as pd

from .reglas import (ALIAS_ESTRATO, ALIAS_INDIVIDUAL, ALIAS_IPS, ALIAS_RIPS_AGREGADO, mapear_columnas)

TIPOS = ("RIPS_AGREGADO", "INDIVIDUAL", "IPS", "ESTRATO")
DESCRIPCION_TIPO = {
    "RIPS_AGREGADO": "Morbilidad RIPS (Datos Abiertos, agregada)",
    "INDIVIDUAL": "Registros individuales de atención",
    "IPS": "Instituciones Prestadoras de Salud",
    "ESTRATO": "Estrato socioeconómico por localidad / manzana",
}


def hash_archivo(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _codificacion(path: Path) -> str:
    with open(path, "rb") as f:
        muestra = f.read(200_000)
    for enc in ("utf-8-sig", "utf-8"):
        try:
            muestra.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _separador(path: Path, enc: str) -> str:
    with open(path, encoding=enc, errors="replace") as f:
        cabecera = f.readline()
    try:
        return csv.Sniffer().sniff(cabecera, delimiters=",;|\t").delimiter
    except csv.Error:
        return max([",", ";", "|", "\t"], key=cabecera.count)


def leer_geojson(path: Path) -> pd.DataFrame:
    datos = json.loads(Path(path).read_text(encoding=_codificacion(path)))
    filas = []
    for feat in datos.get("features", []):
        props = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if geom.get("type") == "Point" and coords:
            props.setdefault("longitud", coords[0]); props.setdefault("latitud", coords[1])
        elif coords:  # polígono: se usa el promedio de vértices como punto representativo
            plano = []
            def aplanar(c):
                if isinstance(c[0], (int, float)):
                    plano.append(c)
                else:
                    for x in c:
                        aplanar(x)
            aplanar(coords)
            if plano:
                props.setdefault("longitud", sum(p[0] for p in plano) / len(plano))
                props.setdefault("latitud", sum(p[1] for p in plano) / len(plano))
        filas.append(props)
    return pd.DataFrame(filas).astype(str).replace({"None": None, "nan": None})


def leer_tabla(path: Path, chunksize: int = 50_000) -> Iterator[pd.DataFrame]:
    """Itera el archivo en bloques; todas las columnas como texto (la conversión es tarea de la transformación)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".geojson", ".json"):
        yield leer_geojson(path)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
        for i in range(0, len(df), chunksize):
            yield df.iloc[i:i + chunksize].copy()
    else:
        enc = _codificacion(path)
        sep = _separador(path, enc)
        yield from pd.read_csv(path, sep=sep, dtype=str, encoding=enc, chunksize=chunksize,
                               keep_default_na=False, na_values=["", "NA", "NULL", "null", "None"],
                               on_bad_lines="warn")


def columnas(path: Path) -> list[str]:
    primero = next(iter(leer_tabla(path, chunksize=5)))
    return list(primero.columns)


def detectar_tipo(path: Path) -> str | None:
    """Clasifica el archivo según sus columnas."""
    cols = columnas(path)
    m_agr = mapear_columnas(cols, ALIAS_RIPS_AGREGADO)
    m_ind = mapear_columnas(cols, ALIAS_INDIVIDUAL)
    m_ips = mapear_columnas(cols, ALIAS_IPS)
    m_est = mapear_columnas(cols, ALIAS_ESTRATO)
    if {"anio", "quinquenio", "cantidad"} <= m_agr.keys() and ("dx1" in m_agr or "dx2" in m_agr):
        return "RIPS_AGREGADO"
    if "dx" in m_ind and "edad" in m_ind and ("fecha" in m_ind or "anio" in m_ind):
        return "INDIVIDUAL"
    if "nombre" in m_ips and "latitud" in m_ips and "longitud" in m_ips:
        return "IPS"
    if "estrato" in m_est and ("localidad" in m_est or "cod_localidad" in m_est):
        return "ESTRATO"
    return None
