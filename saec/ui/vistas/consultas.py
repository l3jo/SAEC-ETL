"""Consulta de atenciones con filtros y paginación."""
from __future__ import annotations

from tkinter import filedialog, messagebox, ttk

from ...config import SETTINGS, base_dir
from ...models import Filtro
from ...services.consultas import ConsultaService
from ..widgets import BarraFiltros, Tabla, Tarea, resolver_fuente


class ConsultasView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.svc = ConsultaService()
        self.f = Filtro()
        self.pagina, self.total = 1, 0
        self.limite = SETTINGS.registros_por_pagina
        ttk.Label(self, text="Consulta de atenciones", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self, text="Registros cargados por el ETL. Con RIPS agregado cada fila representa varias atenciones "
                             "(columna 'cantidad') y la edad se muestra como grupo.", style="Sub.TLabel").pack(anchor="w")
        self.filtros = BarraFiltros(self, self.aplicar)
        self.filtros.pack(fill="x", pady=8)
        self.tabla = Tabla(self, alto=20)
        self.tabla.pack(fill="both", expand=True)
        pie = ttk.Frame(self)
        pie.pack(fill="x", pady=(6, 0))
        self.b_ant = ttk.Button(pie, text="◀ Anterior", command=lambda: self.ir(self.pagina - 1))
        self.b_ant.pack(side="left")
        self.lbl = ttk.Label(pie, text="")
        self.lbl.pack(side="left", padx=10)
        self.b_sig = ttk.Button(pie, text="Siguiente ▶", command=lambda: self.ir(self.pagina + 1))
        self.b_sig.pack(side="left")
        ttk.Button(pie, text="Exportar a Excel", command=self.exportar).pack(side="right")
        self._cargado = False

    def al_mostrar(self):
        if not self._cargado:
            self._cargado = True
            self.aplicar(self.filtros.filtro())

    def aplicar(self, f: Filtro):
        self.f = f
        self.ir(1)

    def ir(self, pagina: int):
        paginas = max(1, -(-self.total // self.limite))
        if self.total and not 1 <= pagina <= paginas:
            return
        self.lbl.config(text="Consultando…")
        Tarea(self, lambda t: self.svc.consultar_atenciones(resolver_fuente(self.f), pagina, self.limite),
              lambda r: self._mostrar(pagina, *r)).iniciar()

    def _mostrar(self, pagina, df, total):
        self.pagina, self.total = pagina, total
        paginas = max(1, -(-total // self.limite))
        df = df.rename(columns={"id_atencion": "ID", "anio": "Año", "enfermedad": "Enfermedad", "codigo_cie10": "CIE-10",
                                "sexo": "Sexo", "edad": "Edad", "estrato": "Estrato", "localidad": "Localidad",
                                "institucion": "IPS", "cantidad": "Cantidad", "origen": "Fuente"})
        self.tabla.mostrar(df, {"IPS": 230, "ID": 70, "Año": 60, "Sexo": 50, "Cantidad": 70})
        self.lbl.config(text=f"Página {pagina} de {paginas} · {total:,} registros".replace(",", "."))
        self.b_ant.state(["!disabled"] if pagina > 1 else ["disabled"])
        self.b_sig.state(["!disabled"] if pagina < paginas else ["disabled"])

    def exportar(self):
        if not self.total:
            return messagebox.showinfo("SAEC", "No hay registros para exportar.", parent=self)
        ruta = filedialog.asksaveasfilename(parent=self, initialdir=base_dir() / "reportes", defaultextension=".xlsx",
                                            initialfile="consulta_atenciones.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not ruta:
            return
        f = self.f

        def trabajo(_t):
            df, _ = self.svc.consultar_atenciones(f, 1, 1_000_000)
            df.to_excel(ruta, index=False)
            return ruta
        Tarea(self, trabajo, lambda r: self.app.set_estado(f"Exportado: {r}")).iniciar()
