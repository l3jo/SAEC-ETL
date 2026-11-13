"""TRANSFORMACIÓN: limpieza, estandarización, filtro de población objetivo y validación.

Cada función recibe un bloque crudo (todas las columnas como texto) y devuelve:
    validos   -> DataFrame con columnas estándar listo para cargar
    rechazos  -> DataFrame (motivo, registro) con filas de la población objetivo que no pasan validación
    fuera     -> número de filas que no pertenecen a la población objetivo (otra enfermedad, edad, etc.)
"""
from __future__ import annotations

import hashlib
import zlib

import pandas as pd

from ..config import PoblacionConfig
from ..models import grupo_de_quinquenio, grupo_edad
from .reglas import (ALIAS_ESTRATO, ALIAS_INDIVIDUAL, ALIAS_IPS, ALIAS_RIPS_AGREGADO, clasificar_enfermedad,
                     mapear_columnas, norm_localidad, norm_texto, normalizar_sexo, punto_en_poligono,
                     rango_quinquenio)

COLUMNAS_SALIDA = ["anio", "mes", "sexo", "edad", "grupo_edad", "estrato", "localidad", "ips_codigo",
                   "enfermedad", "tipo_atencion", "regimen", "paciente_hash", "cantidad", "origen"]
SAL = "SAEC-BI-2026"


def _col(df: pd.DataFrame, mapa: dict, campo: str) -> pd.Series:
    if campo in mapa:
        return df[mapa[campo]]
    return pd.Series([None] * len(df), index=df.index, dtype=object)


def _mapear_unicos(serie: pd.Series, funcion) -> pd.Series:
    """Aplica una función costosa solo sobre los valores distintos (rápido en archivos grandes)."""
    unicos = {v: funcion(v) for v in serie.dropna().unique()}
    return serie.map(unicos)


def _numero(serie: pd.Series) -> pd.Series:
    limpio = serie.astype(str).str.replace(r"[^\d,.\-]", "", regex=True).str.replace(",", ".", regex=False)
    return pd.to_numeric(limpio, errors="coerce")


def _rechazos(df: pd.DataFrame, mascara: pd.Series, motivo: str) -> pd.DataFrame:
    if not mascara.any():
        return pd.DataFrame(columns=["motivo", "registro"])
    sub = df.loc[mascara]
    return pd.DataFrame({"motivo": motivo, "registro": sub.to_dict(orient="records")})


def _salida(d: pd.DataFrame) -> pd.DataFrame:
    for c in COLUMNAS_SALIDA:
        if c not in d:
            d[c] = None
    return d[COLUMNAS_SALIDA].reset_index(drop=True)


# ---------------------------------------------------------------------------
def transformar_rips_agregado(df: pd.DataFrame, pob: PoblacionConfig):
    m = mapear_columnas(df.columns, ALIAS_RIPS_AGREGADO)
    texto_dx = (_col(df, m, "dx1").fillna("") + " " + _col(df, m, "dx2").fillna("")).str.strip()
    enf = _mapear_unicos(texto_dx, clasificar_enfermedad)
    objetivo = enf.notna()
    fuera = int((~objetivo).sum())
    df, enf = df.loc[objetivo], enf.loc[objetivo]
    if df.empty:
        return _salida(pd.DataFrame()), pd.DataFrame(columns=["motivo", "registro"]), fuera

    anio = _numero(_col(df, m, "anio"))
    rango = _mapear_unicos(_col(df, m, "quinquenio"), rango_quinquenio)
    cantidad = _numero(_col(df, m, "cantidad"))
    sexo = _mapear_unicos(_col(df, m, "sexo"), normalizar_sexo).fillna("I")
    loc = pd.Series([norm_localidad(n, c) for n, c in zip(_col(df, m, "localidad"), _col(df, m, "cod_localidad"))],
                    index=df.index)

    rech = []
    malo = anio.isna(); rech.append(_rechazos(df, malo, "Año no válido"))
    malo2 = ~malo & rango.isna(); rech.append(_rechazos(df, malo2, "Quinquenio de edad no válido"))
    malo3 = ~malo & ~malo2 & (cantidad.isna() | (cantidad <= 0)); rech.append(_rechazos(df, malo3, "Número de atenciones no válido"))
    malo4 = ~malo & ~malo2 & ~malo3 & (loc == ""); rech.append(_rechazos(df, malo4, "Localidad vacía"))
    valido = ~(malo | malo2 | malo3 | malo4)

    def dentro_edad(r):
        if not isinstance(r, tuple):
            return False
        lo, hi = r
        if pob.incluir_quinquenio_parcial:
            return hi >= pob.edad_min and lo <= pob.edad_max
        return lo >= pob.edad_min and hi <= pob.edad_max

    en_edad = rango.map(dentro_edad).fillna(False).astype(bool)
    en_anio = anio.between(pob.anio_min, pob.anio_max)
    en_loc = loc.isin(pob.localidades)
    poblacion = valido & en_edad & en_anio & en_loc
    fuera += int((valido & ~poblacion).sum())

    idx = poblacion[poblacion].index
    d = pd.DataFrame(index=idx)
    d["anio"] = anio.loc[idx].astype(int)
    d["mes"] = None
    d["sexo"] = sexo.loc[idx]
    d["edad"] = None
    d["grupo_edad"] = rango.loc[idx].map(lambda r: grupo_de_quinquenio(*r))
    d["estrato"] = None  # el RIPS público no trae estrato
    d["localidad"] = loc.loc[idx]
    d["ips_codigo"] = None
    d["enfermedad"] = enf.loc[idx]
    d["tipo_atencion"] = _col(df, m, "tipo_atencion").loc[idx].map(norm_texto).str.slice(0, 60)
    d["regimen"] = _col(df, m, "regimen").loc[idx].map(norm_texto).str.slice(0, 60)
    d["paciente_hash"] = None
    d["cantidad"] = cantidad.loc[idx].astype(int)
    d["origen"] = "AGREGADO"
    rech_df = pd.concat([r for r in rech if not r.empty], ignore_index=True) if any(not r.empty for r in rech) \
        else pd.DataFrame(columns=["motivo", "registro"])
    return _salida(d), rech_df, fuera


# ---------------------------------------------------------------------------
def transformar_individual(df: pd.DataFrame, pob: PoblacionConfig, ips_en_area: set[str] | None = None):
    ips_en_area = ips_en_area or set()
    m = mapear_columnas(df.columns, ALIAS_INDIVIDUAL)
    enf = _mapear_unicos(_col(df, m, "dx").fillna(""), clasificar_enfermedad)
    objetivo = enf.notna()
    fuera = int((~objetivo).sum())
    df, enf = df.loc[objetivo], enf.loc[objetivo]
    duplicado = df.duplicated(keep="first")
    rech_dup = _rechazos(df, duplicado, "Registro duplicado")
    df, enf = df.loc[~duplicado], enf.loc[~duplicado]
    if df.empty:
        return _salida(pd.DataFrame()), rech_dup, fuera

    fecha_txt = _col(df, m, "fecha")
    fecha = pd.to_datetime(fecha_txt, format="%Y-%m-%d", errors="coerce")
    falta = fecha.isna() & fecha_txt.notna()
    if falta.any():
        fecha.loc[falta] = pd.to_datetime(fecha_txt.loc[falta], dayfirst=True, errors="coerce", format="mixed")
    anio = fecha.dt.year.astype("Float64")
    if "anio" in m:
        anio = anio.fillna(_numero(_col(df, m, "anio")))
    edad = _numero(_col(df, m, "edad"))
    sexo = _mapear_unicos(_col(df, m, "sexo"), normalizar_sexo)
    estrato = _numero(_col(df, m, "estrato"))
    loc = pd.Series([norm_localidad(n, c) for n, c in zip(_col(df, m, "localidad"), _col(df, m, "cod_localidad"))],
                    index=df.index)
    ips = _col(df, m, "ips").fillna("").astype(str).str.strip()

    rech = [rech_dup]
    reglas = [
        (anio.isna(), "Fecha de atención no válida"),
        (edad.isna() | (edad < 0) | (edad > 120), "Edad no válida"),
        (sexo.isna(), "Sexo no válido"),
        (estrato.isna() | ~estrato.isin([1, 2, 3, 4, 5, 6]), "Estrato no válido"),
        ((loc == "") & (ips == ""), "Sin localidad ni IPS"),
    ]
    acumulado = pd.Series(False, index=df.index)
    for mascara, motivo in reglas:
        mascara = mascara.fillna(True).astype(bool) & ~acumulado
        rech.append(_rechazos(df, mascara, motivo))
        acumulado |= mascara
    valido = ~acumulado

    en_area = ips.isin(ips_en_area) | loc.isin(pob.localidades)
    poblacion = (valido & edad.between(pob.edad_min, pob.edad_max) & anio.between(pob.anio_min, pob.anio_max)
                 & estrato.isin(pob.estratos) & en_area).fillna(False).astype(bool)
    fuera += int((valido & ~poblacion).sum())

    idx = poblacion[poblacion].index
    d = pd.DataFrame(index=idx)
    d["anio"] = anio.loc[idx].astype(int)
    d["mes"] = fecha.loc[idx].dt.month.astype("Int64")
    d["sexo"] = sexo.loc[idx]
    d["edad"] = edad.loc[idx].astype(int)
    d["grupo_edad"] = d["edad"].map(grupo_edad)
    d["estrato"] = estrato.loc[idx].astype(int)
    d["localidad"] = loc.loc[idx].replace("", None)
    d["ips_codigo"] = ips.loc[idx].replace("", None)
    d["enfermedad"] = enf.loc[idx]
    d["tipo_atencion"] = _col(df, m, "tipo_atencion").loc[idx].map(norm_texto).str.slice(0, 60)
    d["regimen"] = _col(df, m, "regimen").loc[idx].map(norm_texto).str.slice(0, 60)
    doc = (_col(df, m, "tipo_documento").fillna("").astype(str) + ":" + _col(df, m, "documento").fillna("").astype(str)).loc[idx]
    d["paciente_hash"] = doc.map(lambda s: hashlib.sha256((SAL + s).encode()).hexdigest() if s.strip(":") else None)
    d["cantidad"] = 1
    d["origen"] = "INDIVIDUAL"
    nonempty = [r for r in rech if not r.empty]
    rech_df = pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame(columns=["motivo", "registro"])
    return _salida(d), rech_df, fuera


# ---------------------------------------------------------------------------
def transformar_ips(df: pd.DataFrame, poligono: list):
    m = mapear_columnas(df.columns, ALIAS_IPS)
    lat, lon = _numero(_col(df, m, "latitud")), _numero(_col(df, m, "longitud"))
    nombre = _col(df, m, "nombre").map(norm_texto)
    malo = lat.isna() | lon.isna() | ~lat.between(-5, 15) | ~lon.between(-80, -66) | (nombre == "")
    rech = _rechazos(df, malo, "IPS sin nombre o coordenadas válidas")
    filas = []
    for i in df.index[~malo]:
        cod = str(_col(df, m, "codigo").loc[i] or "").strip()
        if not cod or cod.lower() in ("none", "nan"):
            cod = f"SC{zlib.crc32(nombre.loc[i].encode()):010d}"
        loc = norm_localidad(_col(df, m, "localidad").loc[i], _col(df, m, "cod_localidad").loc[i])
        filas.append({"codigo": cod[:20], "nombre": nombre.loc[i][:200],
                      "direccion": norm_texto(_col(df, m, "direccion").loc[i])[:200] or None,
                      "latitud": round(float(lat.loc[i]), 6), "longitud": round(float(lon.loc[i]), 6),
                      "localidad": loc or None,
                      "en_area": punto_en_poligono(float(lat.loc[i]), float(lon.loc[i]), poligono)})
    return filas, rech, 0


# ---------------------------------------------------------------------------
def transformar_estrato(df: pd.DataFrame):
    """Estrato predominante (moda) por localidad. Sirve tanto para un archivo de manzanas como para
    una tabla localidad-estrato."""
    m = mapear_columnas(df.columns, ALIAS_ESTRATO)
    est = _numero(_col(df, m, "estrato"))
    loc = pd.Series([norm_localidad(n, c) for n, c in zip(_col(df, m, "localidad"), _col(df, m, "cod_localidad"))],
                    index=df.index)
    ok = est.between(1, 6) & (loc != "")
    rech = _rechazos(df, ~ok, "Estrato o localidad no válidos")
    conteo = pd.DataFrame({"loc": loc[ok], "est": est[ok].astype(int)}).value_counts().reset_index(name="n")
    return conteo, rech, 0


def moda_estrato(conteos: list[pd.DataFrame]) -> dict[str, int]:
    if not conteos:
        return {}
    c = pd.concat(conteos).groupby(["loc", "est"], as_index=False)["n"].sum()
    c = c.sort_values(["loc", "n", "est"], ascending=[True, False, True])
    return dict(zip(c.drop_duplicates("loc")["loc"], c.drop_duplicates("loc")["est"].astype(int)))
