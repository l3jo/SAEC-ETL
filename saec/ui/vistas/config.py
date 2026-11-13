"""Configuración de la conexión a PostgreSQL y mantenimiento del esquema."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ...config import CONFIG_PATH, SETTINGS, DBConfig, guardar_db
from ...db import Database, instalar_esquema, probar_conexion, refrescar_vistas
from ..widgets import Tarea


class ConfigView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        ttk.Label(self, text="Configuración", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self, text=f"Archivo: {CONFIG_PATH}", style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
        from ... import portable
        if portable.es_portable():
            ttk.Label(self, text=f"Versión portable: PostgreSQL incluido en {portable.PG_DATA}. "
                                 "SAEC lo inicia y lo detiene solo; no cambie estos datos.",
                      style="Sub.TLabel").pack(anchor="w", pady=(0, 6))
        caja = ttk.Frame(self, style="Card.TFrame", padding=16)
        caja.pack(anchor="w")
        ttk.Label(caja, text="Conexión a PostgreSQL", style="H2.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        cfg = SETTINGS.db
        self.v = {}
        for i, (et, k, val, show) in enumerate((("Servidor", "host", cfg.host, ""), ("Puerto", "port", cfg.port, ""),
                                                ("Base de datos", "dbname", cfg.dbname, ""), ("Usuario", "user", cfg.user, ""),
                                                ("Contraseña", "password", cfg.password, "•")), start=1):
            ttk.Label(caja, text=et, style="Card.TLabel").grid(row=i, column=0, sticky="w", padx=(0, 10), pady=3)
            self.v[k] = tk.StringVar(value=str(val))
            ttk.Entry(caja, textvariable=self.v[k], show=show, width=30).grid(row=i, column=1, pady=3)
        b = ttk.Frame(caja, style="Card.TFrame")
        b.grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(b, text="Probar conexión", command=self.probar).pack(side="left")
        ttk.Button(b, text="Guardar", style="Accent.TButton", command=self.guardar).pack(side="left", padx=6)
        self.lbl = ttk.Label(caja, text="", style="Card.TLabel", wraplength=420)
        self.lbl.grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))

        mant = ttk.Frame(self, style="Card.TFrame", padding=16)
        mant.pack(anchor="w", pady=10, fill="x")
        ttk.Label(mant, text="Mantenimiento", style="H2.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Button(mant, text="Instalar / actualizar esquema y vistas", command=self.instalar).pack(anchor="w")
        ttk.Button(mant, text="Refrescar vista materializada", command=self.refrescar).pack(anchor="w", pady=6)
        p = SETTINGS.poblacion
        ttk.Label(mant, style="Card.TLabel", justify="left", text=(
            "Parámetros de población (editar en settings.ini y reiniciar):\n"
            f"  Edad {p.edad_min}-{p.edad_max} · Años {p.anio_min}-{p.anio_max} · Estratos {p.estratos} · "
            f"Localidades {', '.join(p.localidades)}")).pack(anchor="w", pady=(6, 0))

    def _cfg(self) -> DBConfig:
        return DBConfig(self.v["host"].get(), int(self.v["port"].get()), self.v["dbname"].get(), self.v["user"].get(),
                        self.v["password"].get(), SETTINGS.db.admin_db)

    def probar(self):
        try:
            cfg = self._cfg()
        except ValueError:
            return self.lbl.config(text="El puerto debe ser numérico.")
        Tarea(self, lambda t: probar_conexion(cfg),
              lambda r: self.lbl.config(text=("✔ " if r[0] else "✖ ") + r[1])).iniciar()

    def guardar(self):
        try:
            cfg = self._cfg()
        except ValueError:
            return self.lbl.config(text="El puerto debe ser numérico.")
        guardar_db(cfg)
        SETTINGS.db = cfg
        Database.reiniciar(cfg)
        self.app.datos_actualizados()
        self.lbl.config(text="Configuración guardada.")

    def instalar(self):
        if messagebox.askyesno("SAEC", "Se crearán las tablas y vistas que falten (los datos existentes se conservan). "
                                       "¿Continuar?", parent=self):
            Tarea(self, lambda t: instalar_esquema(), lambda _: self.app.set_estado("Esquema actualizado")).iniciar()

    def refrescar(self):
        Tarea(self, lambda t: refrescar_vistas(), lambda _: self.app.set_estado("Vista materializada actualizada")).iniciar()
