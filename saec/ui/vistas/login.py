"""Pantalla de inicio de sesión (verifica también la conexión con PostgreSQL)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ...config import SETTINGS, DBConfig, guardar_db
from ...db import Database, instalar_esquema
from ...services.auth import AuthService
from .. import tema
from ..app import verificar_bd
from ..widgets import Tarea


class LoginView(tk.Frame):
    def __init__(self, master, al_ingresar):
        super().__init__(master, bg=tema.AZUL)
        self.al_ingresar = al_ingresar
        caja = tk.Frame(self, bg=tema.BLANCO, padx=40, pady=30)
        caja.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(caja, text="SAEC", bg=tema.BLANCO, fg=tema.AZUL, font=tema.fuente(26, "bold")).pack()
        tk.Label(caja, text="Sistema de Análisis de Enfermedades Crónicas\nSubred Integrada de Servicios de Salud Norte",
                 bg=tema.BLANCO, fg=tema.GRIS, font=tema.fuente(10), justify="center").pack(pady=(0, 18))
        self.cuerpo = tk.Frame(caja, bg=tema.BLANCO)
        self.cuerpo.pack(fill="x")
        self.estado = tk.Label(caja, text="Verificando conexión con la base de datos…", bg=tema.BLANCO,
                               fg=tema.GRIS, font=tema.fuente(9), wraplength=340, justify="center")
        self.estado.pack(pady=(14, 0))
        verificar_bd(self, self._bd_ok, lambda e: self._sin_conexion(str(e)),
                     lambda m, p=None: self.estado.config(text=m, fg=tema.GRIS))

    def _limpiar(self):
        for w in self.cuerpo.winfo_children():
            w.destroy()

    def _bd_ok(self, resultado):
        estado, msg = resultado
        if estado == "sin_conexion":
            return self._sin_conexion(msg)
        if estado == "sin_esquema":
            return self._sin_esquema()
        self.estado.config(text=f"✔ {msg}")
        self._formulario()

    # ---------- formulario de ingreso ----------
    def _formulario(self):
        self._limpiar()
        self.v_correo = tk.StringVar(value="admin@saec.local")
        self.v_clave = tk.StringVar()
        for t, var, show in (("Correo", self.v_correo, ""), ("Contraseña", self.v_clave, "•")):
            tk.Label(self.cuerpo, text=t, bg=tema.BLANCO, anchor="w", font=tema.fuente(10)).pack(fill="x")
            e = ttk.Entry(self.cuerpo, textvariable=var, show=show, width=34, font=tema.fuente(11))
            e.pack(fill="x", pady=(0, 10), ipady=3)
            e.bind("<Return>", lambda ev: self._ingresar())
        self.boton = ttk.Button(self.cuerpo, text="Ingresar", style="Accent.TButton", command=self._ingresar)
        self.boton.pack(fill="x", ipady=4)
        self.after(100, lambda: self.cuerpo.winfo_children()[3].focus_set())

    def _ingresar(self):
        self.boton.config(state="disabled")
        correo, clave = self.v_correo.get(), self.v_clave.get()

        def fin(u):
            self.al_ingresar(u)

        def err(e):
            self.boton.config(state="normal")
            self.estado.config(text=str(e), fg=tema.ROJO)
        Tarea(self, lambda t: AuthService().login(correo, clave), fin, err).iniciar()

    # ---------- base sin instalar ----------
    def _sin_esquema(self):
        self._limpiar()
        self.estado.config(text="La base de datos existe pero no tiene las tablas de SAEC.", fg=tema.NARANJA)
        ttk.Button(self.cuerpo, text="Instalar base de datos", style="Accent.TButton",
                   command=self._instalar).pack(fill="x", ipady=4)

    def _instalar(self):
        self.estado.config(text="Instalando esquema…", fg=tema.GRIS)

        def trabajo(_t):
            instalar_esquema()
            return AuthService().asegurar_admin()

        def fin(creado):
            if creado:
                messagebox.showinfo("SAEC", "Base de datos instalada.\n\nUsuario inicial: admin@saec.local\n"
                                            "Contraseña: Admin2026\n\nCámbiela en la pantalla Usuarios.", parent=self)
            self.estado.config(text="✔ Base de datos lista", fg=tema.VERDE)
            self._formulario()
        Tarea(self, trabajo, fin).iniciar()

    # ---------- sin conexión ----------
    def _sin_conexion(self, msg: str):
        self._limpiar()
        self.estado.config(text=f"No fue posible conectar con PostgreSQL:\n{msg}", fg=tema.ROJO)
        cfg = SETTINGS.db
        self.vars = {}
        for etiqueta, clave, valor, show in (("Servidor", "host", cfg.host, ""), ("Puerto", "port", cfg.port, ""),
                                             ("Base de datos", "dbname", cfg.dbname, ""), ("Usuario", "user", cfg.user, ""),
                                             ("Contraseña", "password", cfg.password, "•")):
            fila = tk.Frame(self.cuerpo, bg=tema.BLANCO)
            fila.pack(fill="x", pady=2)
            tk.Label(fila, text=etiqueta, bg=tema.BLANCO, width=13, anchor="w").pack(side="left")
            v = tk.StringVar(value=str(valor))
            ttk.Entry(fila, textvariable=v, show=show, width=24).pack(side="left", fill="x", expand=True)
            self.vars[clave] = v
        ttk.Button(self.cuerpo, text="Probar y guardar conexión", style="Accent.TButton",
                   command=self._guardar_conexion).pack(fill="x", pady=(10, 0), ipady=3)

    def _guardar_conexion(self):
        try:
            nuevo = DBConfig(self.vars["host"].get(), int(self.vars["port"].get()), self.vars["dbname"].get(),
                             self.vars["user"].get(), self.vars["password"].get(), SETTINGS.db.admin_db)
        except ValueError:
            return messagebox.showwarning("SAEC", "El puerto debe ser numérico.", parent=self)
        guardar_db(nuevo)
        SETTINGS.db = nuevo
        Database.reiniciar(nuevo)
        self.estado.config(text="Probando conexión…", fg=tema.GRIS)

        def trabajo(_t):
            from ...db import crear_base_si_no_existe
            crear_base_si_no_existe(nuevo)
            Database.reiniciar(nuevo)
            return True
        Tarea(self, trabajo, lambda _: verificar_bd(self, self._bd_ok, lambda e: self._sin_conexion(str(e))),
              lambda e: self._sin_conexion(str(e).splitlines()[0])).iniciar()
