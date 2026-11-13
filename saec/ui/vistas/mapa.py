"""Mapa de IPS del área de estudio (tkintermapview / OpenStreetMap).

Si tkintermapview no está instalado o no hay Internet para las teselas, se muestra un mapa
esquemático con Matplotlib (coordenadas y polígono del área de estudio).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ...config import SETTINGS
from ...models import Filtro
from ...services.consultas import IPSService
from .. import tema
from ..widgets import BarraFiltros, Grafico, Tabla, Tarea, resolver_fuente

try:
    import tkintermapview  # type: ignore
except ImportError:  # pragma: no cover
    tkintermapview = None


class MapaView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.svc = IPSService()
        self.f = Filtro()
        ttk.Label(self, text="Mapa de instituciones (IPS) del área de estudio", style="Titulo.TLabel").pack(anchor="w")
        self.filtros = BarraFiltros(self, self.aplicar)
        self.filtros.pack(fill="x", pady=8)
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill="both", expand=True)
        cuerpo.columnconfigure(0, weight=3); cuerpo.columnconfigure(1, weight=2); cuerpo.rowconfigure(0, weight=1)
        marco = ttk.Frame(cuerpo, style="Card.TFrame", padding=4)
        marco.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.modo = tk.StringVar(value="osm" if tkintermapview else "esquema")
        barra = ttk.Frame(marco, style="Card.TFrame")
        barra.pack(fill="x")
        for v, t in (("osm", "Mapa OpenStreetMap"), ("esquema", "Esquemático (sin Internet)")):
            ttk.Radiobutton(barra, text=t, value=v, variable=self.modo, command=self._cambiar_modo).pack(side="left", padx=4)
        self.contenedor = ttk.Frame(marco, style="Card.TFrame")
        self.contenedor.pack(fill="both", expand=True)
        self.mapa = None
        self.esquema = None
        der = ttk.Frame(cuerpo)
        der.grid(row=0, column=1, sticky="nsew")
        self.tabla = Tabla(der, alto=12)
        self.tabla.pack(fill="both", expand=True)
        self.tabla.tv.bind("<<TreeviewSelect>>", self._seleccion)
        self.detalle = ttk.Label(der, text="Seleccione una IPS para ver el detalle.", style="Sub.TLabel", justify="left")
        self.detalle.pack(fill="x", pady=6)
        self.df = pd.DataFrame()
        self._cambiar_modo()
        self._cargado = False

    def al_mostrar(self):
        if not self._cargado:
            self._cargado = True
            self.aplicar(self.filtros.filtro())

    def _cambiar_modo(self):
        for w in self.contenedor.winfo_children():
            w.pack_forget()
        if self.modo.get() == "osm" and tkintermapview:
            if self.mapa is None:
                self.mapa = tkintermapview.TkinterMapView(self.contenedor, corner_radius=0)
                self.mapa.set_position(4.660, -74.052)
                self.mapa.set_zoom(14)
            self.mapa.pack(fill="both", expand=True)
        else:
            if self.esquema is None:
                self.esquema = Grafico(self.contenedor, 6, 5)
            self.esquema.pack(fill="both", expand=True)
        self._pintar()

    def aplicar(self, f: Filtro):
        self.f = f
        Tarea(self, lambda t: self.svc.listar_ips(resolver_fuente(f)), self._recibir).iniciar()

    def _recibir(self, df: pd.DataFrame):
        self.df = df
        self.tabla.mostrar(df.rename(columns={"id": "ID", "nombre": "IPS", "direccion": "Dirección",
                                             "total_casos": "Atenciones"})[["ID", "IPS", "Dirección", "Atenciones"]],
                           {"IPS": 220, "ID": 50, "Dirección": 120, "Atenciones": 80})
        self._pintar()

    def _pintar(self):
        df = self.df
        if self.modo.get() == "osm" and self.mapa is not None:
            self.mapa.delete_all_marker()
            self.mapa.delete_all_polygon()
            if SETTINGS.poligono:
                self.mapa.set_polygon(SETTINGS.poligono, outline_color=tema.AZUL2, fill_color=None, border_width=2,
                                      name="Área de estudio")
            for _, r in df.iterrows():
                self.mapa.set_marker(r["latitud"], r["longitud"], text=f"{r['nombre'].title()} ({r['total_casos']:,})".replace(",", "."))
        elif self.esquema is not None:
            def fig_esquema(fig):
                fig.clear()
                ax = fig.add_subplot(111)
                if SETTINGS.poligono:
                    pts = SETTINGS.poligono + [SETTINGS.poligono[0]]
                    ax.plot([p[1] for p in pts], [p[0] for p in pts], color=tema.AZUL2, lw=1.5, label="Área de estudio")
                    ax.fill([p[1] for p in pts], [p[0] for p in pts], color=tema.AZUL2, alpha=0.06)
                if not df.empty:
                    tam = 40 + 400 * df["total_casos"] / max(df["total_casos"].max(), 1)
                    ax.scatter(df["longitud"], df["latitud"], s=tam, color=tema.ROJO, alpha=0.6, edgecolor="white")
                    for _, r in df.iterrows():
                        ax.annotate(r["nombre"].replace("IPS DEMO ", "").title(), (r["longitud"], r["latitud"]),
                                    fontsize=7, xytext=(5, 4), textcoords="offset points")
                ax.set_aspect("equal")
                ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
                ax.set_title("IPS dentro del área de estudio (tamaño = atenciones)", fontsize=10, loc="left")
                ax.grid(color="#E6EBF0")
                fig.tight_layout()
                return fig
            self.esquema.dibujar(fig_esquema)

    def _seleccion(self, _e):
        sel = self.tabla.tv.selection()
        if not sel:
            return
        id_ips = int(self.tabla.tv.item(sel[0], "values")[0])
        fila = self.df[self.df["id"] == id_ips].iloc[0]
        if self.mapa is not None and self.modo.get() == "osm":
            self.mapa.set_position(fila["latitud"], fila["longitud"])

        def mostrar(det):
            txt = f"{fila['nombre'].title()} — {fila['direccion'] or ''}\n" + "\n".join(
                f"  {r.enfermedad}: {r.casos:,}".replace(",", ".") for r in det.itertuples())
            self.detalle.config(text=txt)
        Tarea(self, lambda t: self.svc.detalle_ips(id_ips, self.f), mostrar).iniciar()
