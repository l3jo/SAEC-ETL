"""Gráficos estadísticos interactivos (Matplotlib embebido)."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

import pandas as pd

from ...models import ENFERMEDADES, Filtro
from ...services import graficos
from ...services.consultas import EstadisticasService
from .. import tema
from ..widgets import BarraFiltros, Grafico, Tabla, Tarea, resolver_fuente

OPCIONES = [("frecuencia", "Frecuencia por enfermedad"), ("edad", "Casos por grupo de edad"),
            ("estrato", "Casos por estrato"), ("tendencia", "Tendencia anual"), ("sexo", "Distribución por sexo")]


class EstadisticasView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.svc = EstadisticasService()
        self.datos: dict = {}
        ttk.Label(self, text="Estadísticas", style="Titulo.TLabel").pack(anchor="w")
        self.filtros = BarraFiltros(self, self.aplicar)
        self.filtros.pack(fill="x", pady=8)
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill="both", expand=True)
        menu = ttk.Frame(cuerpo, style="Card.TFrame", padding=10)
        menu.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(menu, text="Gráfico", style="H2.TLabel").pack(anchor="w", pady=(0, 6))
        self.v_op = tk.StringVar(value="frecuencia")
        for clave, texto in OPCIONES:
            tk.Radiobutton(menu, text=texto, value=clave, variable=self.v_op, command=self.dibujar, bg=tema.BLANCO,
                           anchor="w", font=tema.fuente(10), activebackground=tema.BLANCO).pack(fill="x", pady=2)
        der = ttk.Frame(cuerpo)
        der.pack(side="left", fill="both", expand=True)
        self.grafico = Grafico(der, 8, 4.2)
        self.grafico.pack(fill="both", expand=True)
        self.tabla = Tabla(der, alto=6)
        self.tabla.pack(fill="x", pady=(8, 0))
        self._cargado = False

    def al_mostrar(self):
        if not self._cargado:
            self._cargado = True
            self.aplicar(self.filtros.filtro())

    def aplicar(self, f: Filtro):
        def trabajo(_t):
            return self.svc.atenciones.resumen(resolver_fuente(f))
        Tarea(self, trabajo, self._recibir).iniciar()

    def _recibir(self, df: pd.DataFrame):
        self.df = df
        self.dibujar()

    def dibujar(self):
        df = getattr(self, "df", pd.DataFrame())
        op = self.v_op.get()
        if df.empty:
            self.grafico.dibujar(graficos._vacio)
            self.tabla.mostrar(pd.DataFrame({"Mensaje": ["Sin datos"]}))
            return
        if op == "frecuencia":
            s = df.groupby("enfermedad")["casos"].sum().reindex(ENFERMEDADES, fill_value=0)
            self.grafico.dibujar(lambda fig: graficos.frecuencia(s, fig))
            tabla = s.reset_index().rename(columns={"enfermedad": "Enfermedad", "casos": "Atenciones"})
        elif op == "edad":
            ct = df.pivot_table(index="enfermedad", columns="grupo_edad", values="casos", aggfunc="sum",
                                fill_value=0).reindex(index=ENFERMEDADES, fill_value=0)
            self.grafico.dibujar(lambda fig: graficos.por_edad(ct, fig))
            tabla = ct.reset_index().rename(columns={"enfermedad": "Enfermedad"})
        elif op == "estrato":
            d = df[df["estrato"].notna()]
            ct = None if d.empty else d.assign(estrato=d["estrato"].astype(int)).pivot_table(
                index="enfermedad", columns="estrato", values="casos", aggfunc="sum", fill_value=0).reindex(index=ENFERMEDADES, fill_value=0)
            self.grafico.dibujar(lambda fig: graficos.por_estrato(ct, fig))
            tabla = pd.DataFrame({"Mensaje": ["Los datos no tienen estrato"]}) if ct is None else \
                ct.rename(columns=lambda c: f"Estrato {c}").reset_index().rename(columns={"enfermedad": "Enfermedad"})
        elif op == "tendencia":
            an = df.pivot_table(index="anio", columns="enfermedad", values="casos", aggfunc="sum",
                                fill_value=0).reindex(columns=ENFERMEDADES, fill_value=0).sort_index()
            self.grafico.dibujar(lambda fig: graficos.tendencia(an, fig, date.today().year))
            tabla = an.reset_index().rename(columns={"anio": "Año"})
        else:
            ct = df[df["sexo"].isin(["F", "M"])].pivot_table(index="enfermedad", columns="sexo", values="casos",
                                                            aggfunc="sum", fill_value=0).reindex(index=ENFERMEDADES, fill_value=0)
            for c in ("F", "M"):
                if c not in ct:
                    ct[c] = 0
            self.grafico.dibujar(lambda fig: graficos.por_sexo(ct, fig))
            tabla = ct[["F", "M"]].rename(columns={"F": "Mujeres", "M": "Hombres"}).reset_index().rename(columns={"enfermedad": "Enfermedad"})
        self.tabla.mostrar(tabla)
