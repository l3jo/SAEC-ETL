"""Componentes reutilizables de la interfaz."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import traceback
from tkinter import messagebox, ttk
from typing import Callable

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from ..models import ENFERMEDADES, Filtro
from . import tema


def resolver_fuente(f: Filtro) -> Filtro:
    """'Automática' = registros individuales si existen (traen estrato), si no RIPS agregado.
    Se llama dentro del hilo de trabajo porque consulta la base de datos."""
    if getattr(f, "_automatica", False):
        from ..repositories import AtencionRepository
        o = AtencionRepository().origenes()
        f.origen = "INDIVIDUAL" if "INDIVIDUAL" in o else ("AGREGADO" if "AGREGADO" in o else None)
    return f


class Tarea:
    """Ejecuta una función en un hilo y devuelve el resultado al hilo de Tkinter.

    Tkinter no es seguro para hilos: el trabajo pesado (consultas, ETL) se hace en un Thread y los
    mensajes vuelven por una Queue que se revisa con root.after().
    """

    def __init__(self, widget: tk.Misc, funcion: Callable, al_terminar: Callable | None = None,
                 al_error: Callable | None = None, al_progreso: Callable | None = None):
        self.widget, self.funcion = widget, funcion
        self.al_terminar, self.al_error, self.al_progreso = al_terminar, al_error, al_progreso
        self.cola: queue.Queue = queue.Queue()
        self.cancelar = threading.Event()

    def notificar(self, msg, pct=None):
        self.cola.put(("progreso", (msg, pct)))

    def iniciar(self) -> "Tarea":
        def trabajo():
            try:
                self.cola.put(("ok", self.funcion(self)))
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self.cola.put(("error", exc))
        threading.Thread(target=trabajo, daemon=True).start()
        self._revisar()
        return self

    def _revisar(self):
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "progreso":
                    if self.al_progreso:
                        self.al_progreso(*dato)
                elif tipo == "ok":
                    if self.al_terminar:
                        self.al_terminar(dato)
                    return
                else:
                    if self.al_error:
                        self.al_error(dato)
                    else:
                        messagebox.showerror("SAEC", str(dato), parent=self.widget)
                    return
        except queue.Empty:
            pass
        self.widget.after(100, self._revisar)


class Tarjeta(tk.Frame):
    """Indicador (KPI) con barra de color."""

    def __init__(self, master, titulo: str, color: str = tema.AZUL2):
        super().__init__(master, bg=tema.BLANCO, highlightbackground=tema.BORDE, highlightthickness=1)
        tk.Frame(self, bg=color, width=6).pack(side="left", fill="y")
        cuerpo = tk.Frame(self, bg=tema.BLANCO)
        cuerpo.pack(side="left", fill="both", expand=True, padx=12, pady=6)
        tk.Label(cuerpo, text=titulo, bg=tema.BLANCO, fg=tema.GRIS, font=tema.fuente(9)).pack(anchor="w")
        self.valor = tk.Label(cuerpo, text="—", bg=tema.BLANCO, fg=tema.AZUL, font=tema.fuente(18, "bold"))
        self.valor.pack(anchor="w")
        self.detalle = tk.Label(cuerpo, text="", bg=tema.BLANCO, fg=tema.GRIS, font=tema.fuente(8))
        self.detalle.pack(anchor="w")

    def set(self, valor: str, detalle: str = ""):
        self.valor.config(text=valor)
        self.detalle.config(text=detalle)


class BarraFiltros(ttk.Frame):
    """Filtros generales: enfermedad, año, estrato, edad y fuente de datos."""

    def __init__(self, master, al_aplicar: Callable[[Filtro], None], anios: list[int] | None = None,
                 mostrar_fuente: bool = True, texto_boton: str = "Aplicar filtros"):
        super().__init__(master, style="Card.TFrame", padding=8)
        self.al_aplicar = al_aplicar
        self.v_enf = tk.StringVar(value="Todas")
        self.v_anio = tk.StringVar(value="Todos")
        self.v_est = tk.StringVar(value="Todos")
        self.v_emin = tk.IntVar(value=18)
        self.v_emax = tk.IntVar(value=59)
        self.v_fuente = tk.StringVar(value="Automática")
        c = 0

        def etiqueta(t):
            nonlocal c
            ttk.Label(self, text=t, style="Card.TLabel").grid(row=0, column=c, padx=(8 if c else 2, 3)); c += 1

        etiqueta("Enfermedad")
        ttk.Combobox(self, textvariable=self.v_enf, values=["Todas", *ENFERMEDADES], width=9,
                     state="readonly").grid(row=0, column=c); c += 1
        etiqueta("Año")
        self.cb_anio = ttk.Combobox(self, textvariable=self.v_anio, width=7, state="readonly",
                                    values=["Todos", *[str(a) for a in (anios or range(2020, 2027))]])
        self.cb_anio.grid(row=0, column=c); c += 1
        etiqueta("Estrato")
        ttk.Combobox(self, textvariable=self.v_est, values=["Todos", "1", "2", "3"], width=6,
                     state="readonly").grid(row=0, column=c); c += 1
        etiqueta("Edad")
        ttk.Spinbox(self, from_=18, to=59, textvariable=self.v_emin, width=4).grid(row=0, column=c); c += 1
        ttk.Label(self, text="a", style="Card.TLabel").grid(row=0, column=c, padx=2); c += 1
        ttk.Spinbox(self, from_=18, to=59, textvariable=self.v_emax, width=4).grid(row=0, column=c); c += 1
        if mostrar_fuente:
            etiqueta("Fuente")
            ttk.Combobox(self, textvariable=self.v_fuente, width=12, state="readonly",
                         values=["Automática", "Individual", "RIPS agregado", "Todas"]).grid(row=0, column=c); c += 1
        self.boton = ttk.Button(self, text=texto_boton, style="Accent.TButton", command=self._aplicar)
        self.boton.grid(row=0, column=c, padx=(10, 2))
        self.columnconfigure(c + 1, weight=1)

    def filtro(self) -> Filtro:
        fuente = {"Individual": "INDIVIDUAL", "RIPS agregado": "AGREGADO"}.get(self.v_fuente.get())
        f = Filtro(enfermedad=None if self.v_enf.get() == "Todas" else self.v_enf.get(),
                   anio=None if self.v_anio.get() == "Todos" else int(self.v_anio.get()),
                   estrato=None if self.v_est.get() == "Todos" else int(self.v_est.get()),
                   edad_min=int(self.v_emin.get()), edad_max=int(self.v_emax.get()), origen=fuente)
        f._automatica = self.v_fuente.get() == "Automática"  # type: ignore[attr-defined]
        return f

    def _aplicar(self):
        try:
            f = self.filtro()
            f.validar()
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Filtros", str(exc), parent=self)
            return
        self.al_aplicar(f)


class Grafico(ttk.Frame):
    """Contenedor de una figura Matplotlib dentro de Tkinter."""

    def __init__(self, master, ancho=5.2, alto=3.3):
        super().__init__(master, style="Card.TFrame", padding=4)
        self.fig = Figure(figsize=(ancho, alto), dpi=100, layout="tight")  # se reajusta al cambiar de tamaño
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def dibujar(self, funcion: Callable[[Figure], Figure]):
        funcion(self.fig)
        self.canvas.draw_idle()


class Tabla(ttk.Frame):
    """Treeview con barra de desplazamiento que muestra un DataFrame."""

    def __init__(self, master, alto: int = 10):
        super().__init__(master, style="Card.TFrame", padding=4)
        self.tv = ttk.Treeview(self, show="headings", height=alto)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tv.yview)
        sbx = ttk.Scrollbar(self, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=sb.set, xscrollcommand=sbx.set)
        self.tv.grid(row=0, column=0, sticky="nsew"); sb.grid(row=0, column=1, sticky="ns")
        sbx.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)

    def mostrar(self, df: pd.DataFrame, anchos: dict | None = None):
        self.tv.delete(*self.tv.get_children())
        cols = list(df.columns)
        self.tv["columns"] = cols
        for c in cols:
            self.tv.heading(c, text=str(c))
            self.tv.column(c, width=(anchos or {}).get(c, max(80, min(260, len(str(c)) * 11))), anchor="center")
        crudas = [c for c in cols if str(c).lower() in SIN_FORMATO]
        for _, fila in df.iterrows():
            self.tv.insert("", "end", values=[v if c in crudas and not _nulo(v) else _fmt(v)
                                              for c, v in zip(cols, fila.values)])


SIN_FORMATO = {"id", "año", "anio", "inicio", "creado"}


def _nulo(v) -> bool:
    return v is None or v is pd.NA or (isinstance(v, float) and v != v)


def _fmt(v):
    import numpy as np
    if _nulo(v):
        return "—"
    if isinstance(v, (bool, np.bool_)):
        return "Sí" if v else "No"
    if isinstance(v, (int, np.integer)) or (isinstance(v, (float, np.floating)) and float(v).is_integer()):
        return f"{int(v):,}".replace(",", ".")
    if isinstance(v, (float, np.floating)):
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return v


class TextoDesplazable(ttk.Frame):
    def __init__(self, master, alto=12):
        super().__init__(master, style="Card.TFrame", padding=4)
        self.txt = tk.Text(self, height=alto, wrap="word", relief="flat", bg=tema.BLANCO, fg="#22313F",
                           font=tema.fuente(10), padx=10, pady=8, spacing1=2, spacing3=4)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.txt.tag_configure("h", font=tema.fuente(11, "bold"), foreground=tema.AZUL, spacing1=10)
        self.txt.tag_configure("adv", foreground="#8A5A00", background="#FEF5E7")
        self.txt.tag_configure("b", font=tema.fuente(10, "bold"))

    def limpiar(self):
        self.txt.configure(state="normal"); self.txt.delete("1.0", "end")

    def agregar(self, texto: str, tag: str | None = None):
        self.txt.insert("end", texto, tag)

    def bloquear(self):
        self.txt.configure(state="disabled")
