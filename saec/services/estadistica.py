"""Funciones estadísticas sin dependencias externas (no requiere SciPy)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _gammq(a: float, x: float) -> float:
    """Función gamma incompleta regularizada superior Q(a, x) (Numerical Recipes)."""
    if x < 0 or a <= 0:
        raise ValueError("argumentos no válidos")
    if x == 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:  # serie
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(1000):
            ap += 1
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-14:
                break
        return 1.0 - s * math.exp(-x + a * math.log(x) - gln)
    # fracción continua (Lentz)
    b = x + 1 - a
    c = 1 / 1e-300
    d = 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def chi2_sf(x: float, gl: int) -> float:
    """P(Chi2 >= x) con gl grados de libertad."""
    return _gammq(gl / 2.0, x / 2.0)


def chi_cuadrado(tabla: pd.DataFrame) -> dict | None:
    """Prueba de independencia chi-cuadrado y V de Cramér para una tabla de contingencia."""
    t = tabla.loc[tabla.sum(axis=1) > 0, tabla.sum(axis=0) > 0].to_numpy(dtype=float)
    if t.shape[0] < 2 or t.shape[1] < 2:
        return None
    n = t.sum()
    esperado = np.outer(t.sum(axis=1), t.sum(axis=0)) / n
    chi2 = float(((t - esperado) ** 2 / esperado).sum())
    gl = (t.shape[0] - 1) * (t.shape[1] - 1)
    v = math.sqrt(chi2 / (n * (min(t.shape) - 1)))
    return {"chi2": chi2, "gl": gl, "p": chi2_sf(chi2, gl), "v_cramer": v, "n": int(n),
            "esperado_min": float(esperado.min())}


def fuerza_asociacion(v: float) -> str:
    if v < 0.05:
        return "despreciable"
    if v < 0.10:
        return "débil"
    if v < 0.20:
        return "moderada"
    return "fuerte"


def tendencia(serie: pd.Series) -> dict | None:
    """Cambio porcentual anual promedio con ajuste log-lineal (serie indexada por año)."""
    s = serie[serie > 0].sort_index()
    if len(s) < 3:
        return None
    x = s.index.to_numpy(dtype=float)
    y = np.log(s.to_numpy(dtype=float))
    pendiente, intercepto = np.polyfit(x, y, 1)
    pred = pendiente * x + intercepto
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1e-12
    cambio = (math.exp(pendiente) - 1) * 100
    return {"cambio_anual_pct": cambio, "r2": 1 - ss_res / ss_tot, "desde": int(x[0]), "hasta": int(x[-1]),
            "valor_inicial": int(s.iloc[0]), "valor_final": int(s.iloc[-1]),
            "variacion_total_pct": (s.iloc[-1] / s.iloc[0] - 1) * 100}


def clasificar_tendencia(cambio: float) -> str:
    if cambio >= 3:
        return "en aumento"
    if cambio <= -3:
        return "en descenso"
    return "estable"
