"""Pantalla principal: DIAGNÓSTICO SITUACIONAL AUTOMÁTICO.

Se genera "de una vez" al ingresar al sistema con la población objetivo del proyecto
(18-59 años, EPOC/asma/diabetes, estratos 1-3, 2020-2026, área de estudio de la Subred Norte).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...config import base_dir
from ...models import Filtro
from ...services import graficos, reportes
from ...services.diagnostico import Diagnostico, DiagnosticoService, fmt
from .. import tema
from ..widgets import BarraFiltros, Grafico, Tarea, Tarjeta, TextoDesplazable, resolver_fuente


def abrir_archivo(ruta) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(ruta)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta)])
    except Exception:  # noqa: BLE001
        pass


class DiagnosticoView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.dx: Diagnostico | None = None
        self.svc = DiagnosticoService()
        cab = ttk.Frame(self)
        cab.pack(fill="x")
        ttk.Label(cab, text="Diagnóstico situacional", style="Titulo.TLabel").pack(side="left")
        self.lbl_sub = ttk.Label(cab, text="", style="Sub.TLabel")
        self.lbl_sub.pack(side="left", padx=12, pady=(6, 0))
        self.filtros = BarraFiltros(self, self.generar, texto_boton="Generar diagnóstico")
        self.filtros.pack(fill="x", pady=(8, 8))

        kp = ttk.Frame(self)
        kp.pack(fill="x")
        self.t_total = Tarjeta(kp, "Atenciones analizadas", tema.AZUL2)
        self.t_enf = {e: Tarjeta(kp, e.title() if e != "EPOC" else "EPOC", tema.COLOR_ENF[e]) for e in ("EPOC", "ASMA", "DIABETES")}
        self.t_pers = Tarjeta(kp, "Personas atendidas", tema.GRIS)
        for i, t in enumerate([self.t_total, *self.t_enf.values(), self.t_pers]):
            t.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            kp.columnconfigure(i, weight=1)

        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill="both", expand=True, pady=(10, 0))
        cuerpo.columnconfigure(0, weight=3); cuerpo.columnconfigure(1, weight=2); cuerpo.rowconfigure(0, weight=1)

        self.nb = ttk.Notebook(cuerpo)
        self.nb.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        hoja = ttk.Frame(self.nb, padding=4)
        self.nb.add(hoja, text="Gráficos")
        self.graficos = {}
        for i, clave in enumerate(("frecuencia", "tendencia", "edad", "estrato")):
            g = Grafico(hoja, 4.6, 2.75)
            g.grid(row=i // 2, column=i % 2, sticky="nsew", padx=2, pady=2)
            self.graficos[clave] = g
        for i in range(2):
            hoja.columnconfigure(i, weight=1); hoja.rowconfigure(i, weight=1)
        self.hallazgos = TextoDesplazable(self.nb)
        self.nb.add(self.hallazgos, text="Hallazgos detallados")

        der = ttk.Frame(cuerpo, style="Card.TFrame", padding=10)
        der.grid(row=0, column=1, sticky="nsew")
        ttk.Label(der, text="Priorización y acciones", style="H2.TLabel").pack(anchor="w")
        self.prio = tk.Frame(der, bg=tema.BLANCO)
        self.prio.pack(fill="x", pady=(6, 6))
        self._ajustables: list[tk.Label] = []
        self.prio.bind("<Configure>", self._ajustar_texto)
        ttk.Label(der, text="Conclusión", style="H2.TLabel").pack(anchor="w", pady=(4, 0))
        self.conclusion = tk.Text(der, height=9, wrap="word", relief="flat", bg="#F7F9FB", font=tema.fuente(9),
                                  padx=8, pady=6)
        self.conclusion.pack(fill="both", expand=True, pady=(4, 6))
        bot = tk.Frame(der, bg=tema.BLANCO)
        bot.pack(fill="x")
        self.b_pdf = ttk.Button(bot, text="Exportar PDF", style="Accent.TButton", command=lambda: self.exportar("pdf"))
        self.b_pdf.pack(side="left")
        ttk.Button(bot, text="Exportar Excel", command=lambda: self.exportar("xlsx")).pack(side="left", padx=6)
        ttk.Button(bot, text="Copiar texto", command=self.copiar).pack(side="left")
        self._generado = False

    def al_mostrar(self):
        if not self._generado:  # el diagnóstico se genera automáticamente la primera vez
            self._generado = True
            self.generar(self.filtros.filtro())

    def generar(self, f: Filtro):
        self._solicitud = getattr(self, "_solicitud", 0) + 1
        mi_solicitud = self._solicitud
        self.filtros.boton.config(state="disabled")
        self.lbl_sub.config(text="Generando diagnóstico…")
        self.app.set_estado("Generando diagnóstico…")
        uid = self.app.usuario.id_usuario if self.app.usuario else None

        def trabajo(_t):
            return self.svc.generar(resolver_fuente(f), id_usuario=uid)
        def mostrar(dx):
            if mi_solicitud == self._solicitud:  # descarta resultados de solicitudes anteriores
                self._mostrar(dx)
        Tarea(self, trabajo, mostrar, self._error).iniciar()

    def _error(self, exc):
        self.filtros.boton.config(state="normal")
        self.lbl_sub.config(text="")
        messagebox.showerror("Diagnóstico", str(exc), parent=self)

    def _mostrar(self, dx: Diagnostico):
        self.dx = dx
        self.filtros.boton.config(state="normal")
        self.lbl_sub.config(text=f"{dx.fuente} · {dx.generado:%Y-%m-%d %H:%M}")
        self.app.set_estado(f"Diagnóstico generado: {dx.filtro}")
        k = dx.kpis
        if not k:
            for t in [self.t_total, *self.t_enf.values(), self.t_pers]:
                t.set("—")
        else:
            self.t_total.set(fmt(k["total"]), k["periodo"])
            for e, t in self.t_enf.items():
                t.set(fmt(k["por_enfermedad"][e]), f"{fmt(k['participacion'][e], 1)} % del total")
            if k.get("personas"):
                self.t_pers.set(fmt(k["personas"]), f"{fmt(k['concentracion'], 1)} atenciones por persona")
            else:
                self.t_pers.set("n/d", "datos agregados")
        for clave, g in self.graficos.items():
            g.dibujar(lambda fig, c=clave: graficos.figura(c, dx, fig) if dx.total else graficos._vacio(fig))
        # hallazgos
        h = self.hallazgos
        h.limpiar()
        for a in dx.advertencias:
            h.agregar(f"⚠ {a}\n", "adv")
        for s in dx.secciones:
            h.agregar(s.titulo + "\n", "h")
            for x in s.hallazgos:
                h.agregar(f"• {x}\n")
        h.bloquear()
        # prioridades
        for w in self.prio.winfo_children():
            w.destroy()
        self._ajustables = []
        for p in dx.prioridades:
            fila = tk.Frame(self.prio, bg="#F7F9FB", highlightbackground=tema.BORDE, highlightthickness=1)
            fila.pack(fill="x", pady=3)
            tk.Label(fila, text=f" {p['nivel']} ", bg=tema.COLOR_NIVEL[p["nivel"]], fg="white",
                     font=tema.fuente(8, "bold")).pack(side="left", fill="y")
            info = tk.Frame(fila, bg="#F7F9FB")
            info.pack(side="left", fill="x", expand=True, padx=8, pady=4)
            tk.Label(info, text=f"{p['orden']}. {p['enfermedad']}  ·  puntaje {fmt(p['puntaje'], 2)}", bg="#F7F9FB",
                     fg=tema.AZUL, font=tema.fuente(10, "bold"), anchor="w").pack(fill="x")
            for texto, color in ((" · ".join(p["razones"]), tema.GRIS), ("→ " + p["acciones"][0], "#22313F")):
                lbl = tk.Label(info, text=texto, bg="#F7F9FB", fg=color, font=tema.fuente(8), anchor="w",
                               justify="left", wraplength=max(200, self.prio.winfo_width() - 90))
                lbl.pack(fill="x")
                self._ajustables.append(lbl)
        self.conclusion.configure(state="normal")
        self.conclusion.delete("1.0", "end")
        self.conclusion.insert("1.0", dx.conclusion)
        self.conclusion.configure(state="disabled")

    def _ajustar_texto(self, evento):
        for lbl in self._ajustables:
            lbl.configure(wraplength=max(200, evento.width - 90))

    def exportar(self, ext: str):
        if not self.dx or not self.dx.total:
            return messagebox.showinfo("SAEC", "Primero genere un diagnóstico con datos.", parent=self)
        sugerido = reportes.nombre_archivo("diagnostico", ext, base_dir() / "reportes")
        ruta = filedialog.asksaveasfilename(parent=self, initialdir=sugerido.parent, initialfile=sugerido.name,
                                            defaultextension="." + ext,
                                            filetypes=[("PDF", "*.pdf")] if ext == "pdf" else [("Excel", "*.xlsx")])
        if not ruta:
            return
        dx, uid = self.dx, self.app.usuario.id_usuario

        def trabajo(_t):
            r = reportes.diagnostico_pdf(dx, ruta) if ext == "pdf" else reportes.diagnostico_excel(dx, ruta)
            from ...repositories import SalidaRepository
            SalidaRepository().registrar_reporte(uid, "DIAGNOSTICO", ext.upper(), {"filtro": dx.filtro}, str(r))
            return r
        Tarea(self, trabajo, lambda r: (self.app.set_estado(f"Archivo generado: {r}"), abrir_archivo(r))).iniciar()

    def copiar(self):
        if self.dx:
            self.clipboard_clear()
            self.clipboard_append(self.dx.texto())
            self.app.set_estado("Diagnóstico copiado al portapapeles")
