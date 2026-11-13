"""Reglas de negocio del ETL: alias de columnas, códigos CIE-10 y normalización."""
from __future__ import annotations

import re
import unicodedata

# --- Enfermedades objetivo: patrón sobre código CIE-10 o texto del diagnóstico ---
ENFERMEDAD_PATRONES = {
    "EPOC": re.compile(r"\bJ44\d?\b|PULMONAR(ES)?\s+OBSTRUCTIVA", re.I),
    "ASMA": re.compile(r"\bJ4[56][0-9X]?\b|\bASMA\b", re.I),
    "DIABETES": re.compile(r"\bE11\d?\b|NO\s+INSULINODEPENDIENTE|TIPO\s*2|\bDIABETES\b", re.I),
}
# Otros tipos de diabetes (E10, E12, E13, E14) se excluyen: el proyecto analiza E11 (tipo 2).
EXCLUSIONES = {"DIABETES": re.compile(r"\bE1[02-4]\d?\b|(?<!NO )INSULINODEPENDIENTE", re.I)}
CODIGO_CIE10 = {"EPOC": "J44", "ASMA": "J45", "DIABETES": "E11"}

# --- Alias de columnas (se comparan normalizados: minúsculas, sin tildes ni espacios) ---
ALIAS_RIPS_AGREGADO = {
    "anio": ["ano", "anio", "año", "year"],
    "sexo": ["sexo_gen", "sexo", "genero"],
    "quinquenio": ["edad_quiquenio", "edad_quinquenio", "quinquenio", "grupo_edad"],
    "regimen": ["tipo_usuario_afiliacion", "regimen", "tipo_usuario"],
    "cod_localidad": ["prestador_localidad_codigo", "codigo_loc", "cod_localidad"],
    "localidad": ["prestador_localidad_nombre", "localidad", "nombre_localidad"],
    "tipo_atencion": ["tipo_atencion_nombre", "tipo_atencion"],
    "dx1": ["dxprincipal_agrupacion1_nombre", "grupo_cie10"],
    "dx2": ["dxprincipal_agrupacion2_nombre", "subgrupo_cie10", "diagnostico"],
    "cantidad": ["sum_atenciones", "atenciones", "numero_atenciones", "cantidad"],
}
ALIAS_INDIVIDUAL = {
    "fecha": ["fecha_atencion", "fecha", "fecha_consulta"],
    "anio": ["anio", "ano", "año"],
    "documento": ["numero_documento", "documento", "num_documento", "id_paciente"],
    "tipo_documento": ["tipo_documento", "tipo_doc"],
    "edad": ["edad", "edad_anios"],
    "sexo": ["sexo", "genero", "cod_sexo"],
    "estrato": ["estrato", "estrato_socioeconomico"],
    "dx": ["cod_dx", "codigo_diagnostico", "dx_principal", "cie10", "diagnostico"],
    "localidad": ["localidad", "localidad_residencia", "nombre_localidad"],
    "cod_localidad": ["cod_localidad", "codigo_localidad"],
    "ips": ["codigo_habilitacion", "ips_codigo", "cod_ips", "codigo_ips"],
    "tipo_atencion": ["tipo_atencion"],
    "regimen": ["regimen", "tipo_usuario"],
}
ALIAS_IPS = {
    "codigo": ["codigo_habilitacion", "cod_habilitacion", "codigo", "codigo_prestador", "cod_ips"],
    "nombre": ["nombre_prestador", "nombre_sede", "razon_social", "nombre", "nombre_ips"],
    "direccion": ["direccion", "direccion_sede"],
    "latitud": ["latitud", "lat", "y", "coord_y"],
    "longitud": ["longitud", "lon", "lng", "x", "coord_x"],
    "localidad": ["localidad", "nombre_localidad", "nomb_loc", "loc_nombre"],
    "cod_localidad": ["cod_localidad", "codigo_localidad", "cod_loc"],
}
ALIAS_ESTRATO = {
    "localidad": ["localidad", "nombre_localidad", "nomb_loc", "loc_nombre"],
    "cod_localidad": ["cod_localidad", "codigo_loc", "cod_loc", "codigo_localidad"],
    "estrato": ["estrato", "estrato_socioeconomico", "estrato_predominante"],
}

LOCALIDADES_BOGOTA = {
    "01": "USAQUEN", "02": "CHAPINERO", "03": "SANTA FE", "04": "SAN CRISTOBAL", "05": "USME",
    "06": "TUNJUELITO", "07": "BOSA", "08": "KENNEDY", "09": "FONTIBON", "10": "ENGATIVA",
    "11": "SUBA", "12": "BARRIOS UNIDOS", "13": "TEUSAQUILLO", "14": "LOS MARTIRES",
    "15": "ANTONIO NARINO", "16": "PUENTE ARANDA", "17": "LA CANDELARIA", "18": "RAFAEL URIBE URIBE",
    "19": "CIUDAD BOLIVAR", "20": "SUMAPAZ",
}


def quitar_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_col(c: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", quitar_tildes(str(c)).strip().lower().replace(" ", "_"))


def norm_texto(s) -> str:
    if s is None or (isinstance(s, float) and s != s):
        return ""
    return re.sub(r"\s+", " ", quitar_tildes(str(s)).upper()).strip()


def norm_localidad(nombre, codigo=None) -> str:
    """Nombre canónico de localidad a partir del nombre o del código (01..20)."""
    cod = re.sub(r"\D", "", str(codigo or ""))
    if cod:
        cod = cod.zfill(2)[-2:]
        if cod in LOCALIDADES_BOGOTA:
            return LOCALIDADES_BOGOTA[cod]
    n = norm_texto(nombre)
    n = re.sub(r"^\d+\s*[-.]?\s*", "", n)  # "02 - CHAPINERO" -> "CHAPINERO"
    return n


def codigo_localidad(nombre: str) -> str | None:
    for k, v in LOCALIDADES_BOGOTA.items():
        if v == nombre:
            return k
    return None


def mapear_columnas(columnas, alias: dict) -> dict:
    """Devuelve {campo_estandar: columna_original} para las columnas encontradas."""
    normal = {norm_col(c): c for c in columnas}
    out = {}
    for campo, opciones in alias.items():
        for o in opciones:
            if norm_col(o) in normal:
                out[campo] = normal[norm_col(o)]
                break
    return out


def clasificar_enfermedad(*textos) -> str | None:
    t = " ".join(norm_texto(x) for x in textos if x is not None)
    for nombre, patron in ENFERMEDAD_PATRONES.items():
        if patron.search(t):
            excl = EXCLUSIONES.get(nombre)
            if excl and excl.search(t) and not re.search(r"\bE11\d?\b|NO INSULINODEPENDIENTE", t):
                continue
            return nombre
    return None


def normalizar_sexo(s) -> str | None:
    t = norm_texto(s)
    if t in ("F", "FEMENINO", "MUJER", "MUJERES"):
        return "F"
    if t in ("M", "MASCULINO", "HOMBRE", "HOMBRES", "H"):
        return "M"
    if t in ("I", "INDETERMINADO", "NO DEFINIDO", "OTRO"):
        return "I"
    return None


def rango_quinquenio(texto) -> tuple[int, int] | None:
    """'25 a 29', 'De 25 a 29 años', '25-29' -> (25, 29). '80 y más' -> (80, 120)."""
    nums = [int(n) for n in re.findall(r"\d+", str(texto))]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return (nums[0], 120) if re.search(r"MAS|\+|MAYOR", norm_texto(texto)) else (nums[0], nums[0])
    return None


def punto_en_poligono(lat: float, lon: float, poligono: list[tuple[float, float]]) -> bool:
    """Algoritmo de ray casting; poligono = [(lat, lon), ...]."""
    if not poligono or lat is None or lon is None:
        return False
    dentro = False
    n = len(poligono)
    j = n - 1
    for i in range(n):
        yi, xi = poligono[i]
        yj, xj = poligono[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            dentro = not dentro
        j = i
    return dentro
