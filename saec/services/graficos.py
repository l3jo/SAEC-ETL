"""Gráficos Matplotlib reutilizados por la interfaz (FigureCanvasTkAgg) y por los reportes PDF."""
from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from ..models import ENFERMEDADES, GRUPOS_EDAD

COLORES = {"EPOC": "#3E8E9C", "ASMA": "#E08A2E", "DIABETES": "#C0392B"}
GRIS = "#5B6B7A"


def _compacto(ax) -> bool:
    return ax.figure.get_figwidth() < 5


def _estilo(ax, titulo: str):
    c = _compacto(ax)
    ax.set_title(titulo, fontsize=9.5 if c else 11, fontweight="bold", color="#1F3B57", loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#B8C4D0"); ax.spines["bottom"].set_color("#B8C4D0")
    ax.tick_params(colors=GRIS, labelsize=7.5 if c else 9)
    ax.grid(axis="y", color="#E6EBF0", linewidth=0.8)
    ax.set_axisbelow(True)


def _miles(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def _vacio(fig: Figure, texto: str = "Sin datos para los filtros seleccionados") -> Figure:
    import textwrap
    fig.clear()
    ax = fig.add_subplot(111)
    ax.axis("off")
    ancho = 26 if fig.get_figwidth() < 5 else 50
    ax.text(0.5, 0.5, "\n".join(textwrap.wrap(texto, ancho)), ha="center", va="center", color=GRIS, fontsize=10)
    return fig


def frecuencia(por_enf: pd.Series, fig: Figure | None = None) -> Figure:  # noqa: D401
    fig = fig or Figure(figsize=(5.2, 3.4), dpi=100)
    fig.clear()
    if por_enf is None or por_enf.sum() == 0:
        return _vacio(fig)
    ax = fig.add_subplot(111)
    s = por_enf.reindex(ENFERMEDADES, fill_value=0).sort_values(ascending=False)
    barras = ax.bar(s.index, s.values, color=[COLORES[e] for e in s.index], width=0.6)
    tot = s.sum()
    for b, v in zip(barras, s.values):
        p_txt = f"{v / tot * 100:.1f}".replace(".", ",")
        ax.text(b.get_x() + b.get_width() / 2, v, f"{_miles(v)}\n({p_txt} %)",
                ha="center", va="bottom", fontsize=7.5 if _compacto(ax) else 9, color="#1F3B57")
    ax.set_ylim(0, s.max() * 1.25)
    ax.yaxis.set_major_formatter(lambda v, _: _miles(v))
    _estilo(ax, "Por enfermedad" if _compacto(ax) else "Atenciones por enfermedad")
    fig.tight_layout()
    return fig


def por_edad(ct: pd.DataFrame, fig: Figure | None = None) -> Figure:
    fig = fig or Figure(figsize=(5.2, 3.4), dpi=100)
    fig.clear()
    if ct is None or ct.to_numpy().sum() == 0:
        return _vacio(fig)
    ax = fig.add_subplot(111)
    x = np.arange(len(GRUPOS_EDAD))
    w = 0.26
    for k, enf in enumerate(ENFERMEDADES):
        ax.bar(x + (k - 1) * w, ct.loc[enf].reindex(GRUPOS_EDAD, fill_value=0).values, w, label=enf, color=COLORES[enf])
    ax.set_xticks(x, list(GRUPOS_EDAD) if _compacto(ax) else [f"{g} años" for g in GRUPOS_EDAD])
    ax.yaxis.set_major_formatter(lambda v, _: _miles(v))
    ax.legend(frameon=False, fontsize=7 if _compacto(ax) else 8)
    _estilo(ax, "Por grupo de edad" if _compacto(ax) else "Atenciones por grupo de edad")
    fig.tight_layout()
    return fig


def por_estrato(ct: pd.DataFrame | None, fig: Figure | None = None, porcentaje: bool = True) -> Figure:
    fig = fig or Figure(figsize=(5.2, 3.4), dpi=100)
    fig.clear()
    if ct is None or ct.to_numpy().sum() == 0:
        return _vacio(fig, "Los datos cargados no tienen estrato")
    ax = fig.add_subplot(111)
    est = list(ct.columns)
    comp = ct.div(ct.sum(axis=0), axis=1) * 100 if porcentaje else ct
    abajo = np.zeros(len(est))
    for enf in ENFERMEDADES:
        vals = comp.loc[enf].values
        ax.bar([(f"E{e}" if _compacto(ax) else f"Estrato {e}") for e in est], vals, bottom=abajo, color=COLORES[enf],
               label=enf, width=0.55)
        for i, v in enumerate(vals):
            if v >= 6:
                ax.text(i, abajo[i] + v / 2, f"{v:.0f}%", ha="center", va="center", color="white",
                        fontsize=6.5 if _compacto(ax) else 8, fontweight="bold")
        abajo += vals
    ax.set_ylim(0, 100 if porcentaje else abajo.max() * 1.1)
    if _compacto(ax):
        ax.legend(frameon=False, fontsize=6.5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12),
                  handlelength=1.0, columnspacing=0.8)
    else:
        ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1, 1))
    _estilo(ax, ("Composición por estrato (%)" if _compacto(ax) else "Composición de atenciones por estrato (%)")
            if porcentaje else "Atenciones por estrato")
    fig.tight_layout()
    return fig


def tendencia(anual: pd.DataFrame, fig: Figure | None = None, anio_en_curso: int | None = None) -> Figure:
    fig = fig or Figure(figsize=(5.2, 3.4), dpi=100)
    fig.clear()
    if anual is None or anual.to_numpy().sum() == 0:
        return _vacio(fig)
    ax = fig.add_subplot(111)
    for enf in ENFERMEDADES:
        s = anual[enf]
        ax.plot(s.index, s.values, marker="o", color=COLORES[enf], label=enf, linewidth=2, markersize=4)
        if anio_en_curso in s.index:
            ax.plot([anio_en_curso], [s[anio_en_curso]], marker="o", markersize=7, markerfacecolor="white",
                    markeredgecolor=COLORES[enf])
    c = _compacto(ax)
    ax.set_xticks(list(anual.index), [f"'{str(a)[2:]}" if c else str(a) for a in anual.index])
    ax.yaxis.set_major_formatter(lambda v, _: _miles(v))
    ax.legend(frameon=False, fontsize=6.5 if c else 8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12),
              handlelength=1.2, columnspacing=0.8)
    titulo = "Tendencia anual" if c else "Tendencia anual de atenciones"
    if anio_en_curso in anual.index and not c:
        titulo += f" (○ {anio_en_curso}: año en curso)"
    _estilo(ax, titulo)
    fig.tight_layout()
    return fig


def por_sexo(ct: pd.DataFrame, fig: Figure | None = None) -> Figure:
    fig = fig or Figure(figsize=(5.2, 3.0), dpi=100)
    fig.clear()
    if ct is None or ct.to_numpy().sum() == 0:
        return _vacio(fig)
    ax = fig.add_subplot(111)
    comp = ct[["F", "M"]].div(ct[["F", "M"]].sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * 100
    ax.barh(comp.index, comp["F"], color="#8E5A9B", label="Mujeres")
    ax.barh(comp.index, comp["M"], left=comp["F"], color="#5DA5DA", label="Hombres")
    for i, (f_, m_) in enumerate(zip(comp["F"], comp["M"])):
        ax.text(f_ / 2, i, f"{f_:.0f}%", ha="center", va="center", color="white", fontsize=8)
        ax.text(f_ + m_ / 2, i, f"{m_:.0f}%", ha="center", va="center", color="white", fontsize=8)
    ax.set_xlim(0, 100)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="lower center", bbox_to_anchor=(0.5, -0.32))
    _estilo(ax, "Distribución por sexo (%)")
    fig.tight_layout()
    return fig


def figura(clave: str, dx, fig: Figure | None = None) -> Figure:
    """Gráfico de una sección del diagnóstico."""
    from datetime import date
    s = dx.series
    if clave == "frecuencia":
        return frecuencia(s.get("por_enf"), fig)
    if clave == "edad":
        return por_edad(s.get("edad"), fig)
    if clave == "estrato":
        return por_estrato(s.get("estrato"), fig)
    if clave == "tendencia":
        return tendencia(s.get("anual"), fig, anio_en_curso=date.today().year)
    if clave == "sexo":
        return por_sexo(s.get("sexo"), fig)
    raise KeyError(clave)
