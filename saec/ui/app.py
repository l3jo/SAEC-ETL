"""Ventana principal, inicio de sesión y navegación."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..config import SETTINGS
from ..db import Database, probar_conexion
from ..models import Usuario
from . import tema
from .widgets import Tarea

MENU = [  # (clave, texto, solo_admin)
    ("diagnostico", "Diagnóstico", False),
    ("consultas", "Consultas", False),
    ("estadisticas", "Estadísticas", False),
    ("mapa", "Mapa de IPS", False),
    ("etl", "Proceso ETL", True),
    ("usuarios", "Usuarios", True),
    ("config", "Configuración", True),
]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SAEC — Análisis de Enfermedades Crónicas · Subred Norte")
        self.geometry("1280x800")
        self.minsize(1100, 700)
        tema.aplicar(self, SETTINGS.tema)
        self.usuario: Usuario | None = None
        self.vistas: dict[str, ttk.Frame] = {}
        self._contenedor = None
        self.protocol("WM_DELETE_WINDOW", self.salir)
        self.after(50, self.mostrar_login)

    # ---------------- login ----------------
    def mostrar_login(self):
        for w in self.winfo_children():
            w.destroy()
        from .vistas.login import LoginView
        LoginView(self, self.al_ingresar).pack(fill="both", expand=True)

    def al_ingresar(self, usuario: Usuario):
        self.usuario = usuario
        for w in self.winfo_children():
            w.destroy()
        self._construir_principal()
        self.mostrar("diagnostico")

    # ---------------- ventana principal ----------------
    def _construir_principal(self):
        lateral = tk.Frame(self, bg=tema.AZUL, width=210)
        lateral.pack(side="left", fill="y")
        lateral.pack_propagate(False)
        tk.Label(lateral, text="SAEC", bg=tema.AZUL, fg="white", font=tema.fuente(20, "bold")).pack(pady=(22, 0))
        tk.Label(lateral, text="Subred Integrada Norte", bg=tema.AZUL, fg="#AFC3D6", font=tema.fuente(9)).pack(pady=(0, 20))
        self.botones = {}
        for clave, texto, admin in MENU:
            if admin and not self.usuario.es_admin:
                continue
            b = tk.Label(lateral, text="   " + texto, anchor="w", bg=tema.AZUL, fg="white", font=tema.fuente(11),
                         pady=9, cursor="hand2")
            b.pack(fill="x", padx=8, pady=1)
            b.bind("<Button-1>", lambda e, c=clave: self.mostrar(c))
            self.botones[clave] = b
        pie = tk.Frame(lateral, bg=tema.AZUL)
        pie.pack(side="bottom", fill="x", padx=14, pady=14)
        tk.Label(pie, text=f"{self.usuario.nombre}\n{self.usuario.rol.title()}", bg=tema.AZUL, fg="#AFC3D6",
                 font=tema.fuente(9), justify="left").pack(anchor="w")
        salir = tk.Label(pie, text="Cerrar sesión", bg=tema.AZUL, fg="white", font=tema.fuente(9, "bold"), cursor="hand2")
        salir.pack(anchor="w", pady=(6, 0))
        salir.bind("<Button-1>", lambda e: self.cerrar_sesion())
        self._contenedor = ttk.Frame(self, padding=(16, 12))
        self._contenedor.pack(side="left", fill="both", expand=True)
        self.estado = tk.Label(self, text="", anchor="w", bg="#E5EAF0", fg=tema.GRIS, font=tema.fuente(8))
        self.estado.place(relx=0, rely=1, anchor="sw", relwidth=1, x=210)
        cfg = SETTINGS.db
        from .. import portable
        modo = " (portable, incluido en la carpeta)" if portable.es_portable() else ""
        self.set_estado(f"Conectado a PostgreSQL {cfg.host}:{cfg.port}/{cfg.dbname}{modo}")

    def set_estado(self, texto: str):
        if hasattr(self, "estado"):
            self.estado.config(text="  " + texto)

    def mostrar(self, clave: str):
        for c, b in self.botones.items():
            b.config(bg=tema.AZUL2 if c == clave else tema.AZUL, font=tema.fuente(11, "bold" if c == clave else "normal"))
        for v in self.vistas.values():
            v.pack_forget()
        if clave not in self.vistas:
            self.vistas[clave] = self._crear_vista(clave)
        v = self.vistas[clave]
        v.pack(fill="both", expand=True)
        if hasattr(v, "al_mostrar"):
            v.al_mostrar()

    def _crear_vista(self, clave: str):
        from .vistas import config, consultas, diagnostico, estadisticas, etl, mapa, usuarios
        clases = {"diagnostico": diagnostico.DiagnosticoView, "consultas": consultas.ConsultasView,
                  "estadisticas": estadisticas.EstadisticasView, "mapa": mapa.MapaView, "etl": etl.ETLView,
                  "usuarios": usuarios.UsuariosView, "config": config.ConfigView}
        return clases[clave](self._contenedor, self)

    def datos_actualizados(self):
        """Tras un ETL se recrean las vistas de análisis para que lean los datos nuevos."""
        for c in ("diagnostico", "consultas", "estadisticas", "mapa"):
            v = self.vistas.pop(c, None)
            if v is not None:
                v.destroy()

    def cerrar_sesion(self):
        self.usuario = None
        self.vistas.clear()
        self.mostrar_login()

    def salir(self):
        try:
            Database.get().engine.dispose()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
        from .. import portable
        portable.detener()  # en la versión portable se apaga el PostgreSQL incluido


def verificar_bd(widget, al_ok, al_error, al_progreso=None):
    """Arranca la base portable si corresponde y comprueba la conexión y el esquema (en segundo plano)."""
    def trabajo(t):
        from .. import portable
        try:
            info = portable.asegurar_servidor(lambda m: t.notificar(m))
        except Exception as exc:  # noqa: BLE001
            return ("sin_conexion", f"No se pudo iniciar PostgreSQL portable: {exc}")
        ok, msg = probar_conexion(SETTINGS.db)
        if info and ok:
            msg = info
        if not ok:
            return ("sin_conexion", msg)
        n = Database.get().escalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'atencion'")
        return ("ok", msg) if n else ("sin_esquema", msg)
    Tarea(widget, trabajo, al_ok, al_error, al_progreso).iniciar()
