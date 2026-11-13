"""Colores, fuentes y estilos ttk de la aplicación."""
import tkinter as tk
from tkinter import ttk

AZUL = "#1F3B57"
AZUL2 = "#2E5E8C"
FONDO = "#F3F6F9"
BLANCO = "#FFFFFF"
GRIS = "#6B7B8C"
BORDE = "#D5DCE3"
ROJO = "#C0392B"
NARANJA = "#E08A2E"
VERDE = "#4E9A4E"
TEAL = "#3E8E9C"
COLOR_ENF = {"EPOC": TEAL, "ASMA": NARANJA, "DIABETES": ROJO}
COLOR_NIVEL = {"ALTA": ROJO, "MEDIA": NARANJA, "BAJA": VERDE}


def fuente(tam: int = 10, peso: str = "normal") -> tuple:
    return ("Segoe UI", tam, peso) if tk.TkVersion and _es_windows() else ("DejaVu Sans", tam, peso)


def _es_windows() -> bool:
    import sys
    return sys.platform.startswith("win")


def aplicar(root: tk.Tk, tema: str = "clam") -> None:
    st = ttk.Style(root)
    try:
        st.theme_use(tema)
    except tk.TclError:
        st.theme_use("clam")
    root.configure(bg=FONDO)
    st.configure(".", font=fuente(10), background=FONDO)
    st.configure("TFrame", background=FONDO)
    st.configure("Card.TFrame", background=BLANCO, relief="solid", borderwidth=1)
    st.configure("TLabel", background=FONDO)
    st.configure("Card.TLabel", background=BLANCO)
    st.configure("Titulo.TLabel", font=fuente(16, "bold"), foreground=AZUL, background=FONDO)
    st.configure("Sub.TLabel", font=fuente(9), foreground=GRIS, background=FONDO)
    st.configure("H2.TLabel", font=fuente(11, "bold"), foreground=AZUL, background=BLANCO)
    st.configure("TCheckbutton", background=BLANCO)
    st.configure("Treeview", rowheight=24, font=fuente(9))
    st.configure("Treeview.Heading", font=fuente(9, "bold"), background="#DDE6EF")
    st.configure("Accent.TButton", background=AZUL2, foreground=BLANCO, font=fuente(10, "bold"))
    st.map("Accent.TButton", background=[("active", AZUL), ("disabled", "#9FB3C8")])
    st.configure("TProgressbar", troughcolor="#E5E8EB", background=VERDE, thickness=16)
    st.configure("TNotebook", background=FONDO)
    st.configure("TNotebook.Tab", padding=(12, 5), font=fuente(9, "bold"))
