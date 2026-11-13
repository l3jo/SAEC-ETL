"""Generador de DATOS DE DEMOSTRACIÓN (sintéticos) para probar el software sin descargar los datasets.

Los archivos imitan los formatos reales:
  * rips_agregado_demo.csv        -> mismas 11 columnas del RIPS de Datos Abiertos Bogotá
  * atenciones_individuales_demo.csv -> plantilla de registros individuales (edad, sexo, estrato, CIE-10, IPS)
  * ips_demo.geojson              -> IPS ficticias con coordenadas
  * estrato_manzanas_demo.csv     -> estrato por manzana y localidad
Los valores son inventados: NO deben usarse para conclusiones reales.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .reglas import LOCALIDADES_BOGOTA

DX = {
    "EPOC": ("J44", "OTRAS ENFERMEDADES PULMONARES OBSTRUCTIVAS CRONICAS", "ENFERMEDADES DEL SISTEMA RESPIRATORIO"),
    "ASMA": ("J45", "ASMA", "ENFERMEDADES DEL SISTEMA RESPIRATORIO"),
    "DIABETES": ("E11", "DIABETES MELLITUS NO INSULINODEPENDIENTE", "ENFERMEDADES ENDOCRINAS, NUTRICIONALES Y METABOLICAS"),
}
OTROS_DX = [
    ("I10", "HIPERTENSION ESENCIAL (PRIMARIA)", "ENFERMEDADES DEL SISTEMA CIRCULATORIO"),
    ("J00", "RINOFARINGITIS AGUDA [RESFRIADO COMUN]", "ENFERMEDADES DEL SISTEMA RESPIRATORIO"),
    ("K29", "GASTRITIS Y DUODENITIS", "ENFERMEDADES DEL SISTEMA DIGESTIVO"),
    ("M54", "DORSALGIA", "ENFERMEDADES DEL SISTEMA OSTEOMUSCULAR"),
    ("E10", "DIABETES MELLITUS INSULINODEPENDIENTE", "ENFERMEDADES ENDOCRINAS, NUTRICIONALES Y METABOLICAS"),
]
IPS_DEMO = [  # nombres ficticios
    ("1100190001", "IPS DEMO CHAPINERO CENTRO", "CL 53 9 20", 4.6405, -74.0625),
    ("1100190002", "IPS DEMO LOURDES", "CL 63 10 15", 4.6485, -74.0600),
    ("1100190003", "IPS DEMO MARLY", "CL 50 11 30", 4.6370, -74.0640),
    ("1100190004", "IPS DEMO QUINTA CAMACHO", "CL 70 9 40", 4.6555, -74.0560),
    ("1100190005", "IPS DEMO EL CHICO", "CL 90 11 10", 4.6765, -74.0480),
    ("1100190006", "IPS DEMO ROSALES", "CL 72 5 50", 4.6560, -74.0500),
    ("1100190007", "IPS DEMO PARDO RUBIO", "CL 47 3 20", 4.6385, -74.0600),
    ("1100190008", "IPS DEMO LA CABRERA", "CL 85 8 30", 4.6705, -74.0490),
    ("1100190009", "IPS DEMO SAN LUIS", "CL 97 2 10", 4.6860, -74.0350),
    ("1100190010", "IPS DEMO SUBA (FUERA DEL ÁREA)", "CL 145 91 19", 4.7420, -74.0900),
]


def _probabilidades(edad, estrato, anio):
    """Pesos relativos por enfermedad (patrones plausibles pero sintéticos)."""
    t = anio - 2020
    pandemia = 0.75 if anio == 2020 else 1.0
    diab = 0.10 * math.exp((edad - 18) / 14) * (1.35 if estrato == 1 else 1.15 if estrato == 2 else 1.0) * (1.07 ** t)
    asma = 0.9 * (1.5 if edad < 30 else 1.1 if edad < 40 else 0.8) * (1.15 if estrato == 1 else 1.0) * (0.98 ** t)
    epoc = 0.004 * math.exp((edad - 18) / 8.5) * (1.4 if estrato == 1 else 1.2 if estrato == 2 else 1.0) * (1.04 ** t)
    return np.array([epoc, asma, diab]) * pandemia


def generar(destino: Path, semilla: int = 2026, pacientes: int = 9000) -> list[Path]:
    rng = np.random.default_rng(semilla)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    # ---------- IPS ----------
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
              "properties": {"codigo_habilitacion": c, "nombre_prestador": n, "direccion": d,
                             "nombre_localidad": "SUBA" if "SUBA" in n else "CHAPINERO"}}
             for c, n, d, lat, lon in IPS_DEMO]
    (destino / "ips_demo.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                                          ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- Estrato por manzana ----------
    dist = {"CHAPINERO": [0.08, 0.17, 0.20, 0.20, 0.10, 0.25], "USAQUEN": [0.03, 0.15, 0.27, 0.25, 0.12, 0.18],
            "SUBA": [0.02, 0.30, 0.38, 0.18, 0.08, 0.04], "ENGATIVA": [0.01, 0.30, 0.60, 0.07, 0.01, 0.01],
            "BARRIOS UNIDOS": [0.0, 0.05, 0.75, 0.18, 0.02, 0.0], "TEUSAQUILLO": [0.0, 0.02, 0.25, 0.65, 0.08, 0.0]}
    filas = []
    for loc, p in dist.items():
        cod = [k for k, v in LOCALIDADES_BOGOTA.items() if v == loc][0]
        for e in rng.choice(np.arange(1, 7), size=400, p=p):
            filas.append({"COD_LOC": cod, "LOCALIDAD": loc.title(), "ESTRATO": int(e)})
    pd.DataFrame(filas).to_csv(destino / "estrato_manzanas_demo.csv", index=False, sep=";")

    # ---------- Registros individuales ----------
    ips_area = [i[0] for i in IPS_DEMO[:-1]]
    pesos_ips = rng.dirichlet(np.ones(len(ips_area)) * 2)
    pac = pd.DataFrame({
        "tipo_documento": rng.choice(["CC", "CE", "PA"], pacientes, p=[0.93, 0.05, 0.02]),
        "numero_documento": rng.integers(10_000_000, 1_100_000_000, pacientes).astype(str),
        "edad0": rng.integers(18, 60, pacientes),
        "sexo": rng.choice(["F", "M"], pacientes, p=[0.56, 0.44]),
        "estrato": rng.choice([1, 2, 3, 4, 5], pacientes, p=[0.26, 0.37, 0.27, 0.07, 0.03]),
    })
    registros = []
    for anio in range(2020, 2027):
        meses = 10 if anio == 2026 else 12  # año en curso: datos hasta octubre
        n_aten = int(4200 * (0.78 if anio == 2020 else 1.0) * (1.03 ** (anio - 2020)) * meses / 12)
        quienes = rng.integers(0, pacientes, n_aten)
        for q in quienes:
            p = pac.iloc[q]
            edad = int(min(59, p.edad0 + (anio - 2020)))
            if rng.random() < 0.38:  # otra causa de consulta (se descarta en el ETL)
                dx = OTROS_DX[rng.integers(0, len(OTROS_DX))][0]
            else:
                w = _probabilidades(edad, p.estrato, anio)
                dx = DX[["EPOC", "ASMA", "DIABETES"][rng.choice(3, p=w / w.sum())]][0]
            f = date(anio, 1, 1) + timedelta(days=int(rng.integers(0, 30 * meses + (meses // 2))))
            fuera_area = rng.random() < 0.06
            registros.append({
                "fecha_atencion": f.isoformat(), "tipo_documento": p.tipo_documento,
                "numero_documento": p.numero_documento, "edad": edad, "sexo": p.sexo,
                "estrato": int(p.estrato), "cod_dx": dx,
                "localidad": "SUBA" if fuera_area else "CHAPINERO",
                "codigo_habilitacion": IPS_DEMO[-1][0] if fuera_area else rng.choice(ips_area, p=pesos_ips),
                "tipo_atencion": rng.choice(["CONSULTA", "URGENCIAS", "HOSPITALIZACION"], p=[0.82, 0.13, 0.05]),
                "regimen": rng.choice(["CONTRIBUTIVO", "SUBSIDIADO", "VINCULADO"], p=[0.45, 0.48, 0.07]),
            })
    ind = pd.DataFrame(registros).astype({"edad": object, "estrato": object})
    # suciedad controlada para ejercitar las validaciones
    n = len(ind)
    sucios = rng.choice(n, int(n * 0.03), replace=False)
    for k, i in enumerate(sucios):
        campo = ["edad", "sexo", "estrato", "fecha_atencion"][k % 4]
        ind.loc[i, campo] = {"edad": "", "sexo": "X", "estrato": "9", "fecha_atencion": "31/02/2023"}[campo]
    fuera_edad = rng.choice(n, int(n * 0.02), replace=False)
    ind.loc[fuera_edad, "edad"] = rng.integers(60, 80, len(fuera_edad))
    ind = pd.concat([ind, ind.sample(frac=0.005, random_state=1)])  # duplicados exactos
    ind.to_csv(destino / "atenciones_individuales_demo.csv", index=False)

    # ---------- RIPS agregado (formato Datos Abiertos) ----------
    quinq = [(a, a + 4) for a in range(15, 65, 5)]
    filas = []
    for anio in range(2020, 2026):
        for loc_cod, loc in [("02", "CHAPINERO"), ("01", "USAQUEN"), ("11", "SUBA")]:
            for sexo in ("FEMENINO", "MASCULINO"):
                for lo, hi in quinq:
                    edad = (lo + hi) / 2
                    for e3 in (1, 2, 3):
                        w = _probabilidades(edad, e3, anio)
                        for k, enf in enumerate(("EPOC", "ASMA", "DIABETES")):
                            base = 25 if loc == "CHAPINERO" else 60
                            val = int(rng.poisson(base * w[k] / 3 + 0.5))
                            if val:
                                c, nombre, grupo = DX[enf]
                                filas.append([anio, sexo, f"{lo} a {hi}", "CONTRIBUTIVO", loc_cod, loc,
                                              "CONSULTA", grupo, f"{c} {nombre}", "EPS DEMO", val])
                    c, nombre, grupo = OTROS_DX[int(rng.integers(0, len(OTROS_DX)))]
                    filas.append([anio, sexo, f"{lo} a {hi}", "SUBSIDIADO", loc_cod, loc, "CONSULTA", grupo,
                                  f"{c} {nombre}", "EPS DEMO", int(rng.integers(5, 300))])
    cols = ["ANO", "Sexo_Gen", "Edad_Quiquenio", "tipo_usuario_afiliacion", "prestador_localidad_codigo",
            "prestador_localidad_nombre", "tipo_atencion_nombre", "dxPrincipal_agrupacion1_nombre",
            "dxPrincipal_agrupacion2_nombre", "administradora_consolidada", "sum_atenciones"]
    pd.DataFrame(filas, columns=cols).to_csv(destino / "rips_agregado_demo.csv", index=False, sep=";")

    return [destino / "estrato_manzanas_demo.csv", destino / "ips_demo.geojson",
            destino / "atenciones_individuales_demo.csv", destino / "rips_agregado_demo.csv"]
