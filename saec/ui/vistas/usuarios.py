"""Gestión de usuarios (rol administrador)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ...models import ROLES
from ...repositories import UsuarioRepository
from ...services.auth import AuthError, AuthService
from ..widgets import Tabla, Tarea


class UsuariosView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.auth = AuthService()
        self.repo = UsuarioRepository()
        self.id_sel: int | None = None
        ttk.Label(self, text="Usuarios", style="Titulo.TLabel").pack(anchor="w")
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill="both", expand=True, pady=8)
        self.tabla = Tabla(cuerpo, alto=18)
        self.tabla.pack(side="left", fill="both", expand=True)
        self.tabla.tv.bind("<<TreeviewSelect>>", self._seleccion)
        form = ttk.Frame(cuerpo, style="Card.TFrame", padding=14)
        form.pack(side="left", fill="y", padx=(8, 0))
        self.titulo = ttk.Label(form, text="Nuevo usuario", style="H2.TLabel")
        self.titulo.pack(anchor="w", pady=(0, 8))
        self.v = {k: tk.StringVar() for k in ("nombre", "correo", "clave")}
        self.v_rol = tk.StringVar(value="ANALISTA")
        self.v_activo = tk.BooleanVar(value=True)
        for etiqueta, k, show in (("Nombre", "nombre", ""), ("Correo", "correo", ""), ("Contraseña", "clave", "•")):
            ttk.Label(form, text=etiqueta, style="Card.TLabel").pack(anchor="w")
            e = ttk.Entry(form, textvariable=self.v[k], show=show, width=32)
            e.pack(fill="x", pady=(0, 8))
            if k == "correo":
                self.e_correo = e
        ttk.Label(form, text="Rol", style="Card.TLabel").pack(anchor="w")
        ttk.Combobox(form, textvariable=self.v_rol, values=list(ROLES), state="readonly").pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(form, text="Activo", variable=self.v_activo).pack(anchor="w")
        ttk.Label(form, text="Contraseña: mínimo 8 caracteres con letras y números.\n"
                             "Al editar, déjela vacía para no cambiarla.", style="Card.TLabel",
                  foreground="#6B7B8C", font=("DejaVu Sans", 8)).pack(anchor="w", pady=6)
        ttk.Button(form, text="Guardar", style="Accent.TButton", command=self.guardar).pack(fill="x", pady=(6, 4))
        ttk.Button(form, text="Nuevo", command=self.nuevo).pack(fill="x")

    def al_mostrar(self):
        self.cargar()

    def cargar(self):
        Tarea(self, lambda t: self.repo.listar(), lambda df: self.tabla.mostrar(
            df.rename(columns={"id_usuario": "ID", "nombre": "Nombre", "correo": "Correo", "rol": "Rol",
                               "activo": "Activo", "creado": "Creado"}), {"Correo": 220, "Nombre": 180, "ID": 50})).iniciar()

    def _seleccion(self, _e):
        sel = self.tabla.tv.selection()
        if not sel:
            return
        vals = self.tabla.tv.item(sel[0], "values")
        self.id_sel = int(vals[0])
        self.v["nombre"].set(vals[1]); self.v["correo"].set(vals[2]); self.v["clave"].set("")
        self.v_rol.set(vals[3]); self.v_activo.set(str(vals[4]) in ("Sí", "True", "1"))
        self.e_correo.config(state="disabled")
        self.titulo.config(text=f"Editar usuario #{self.id_sel}")

    def nuevo(self):
        self.id_sel = None
        for v in self.v.values():
            v.set("")
        self.v_rol.set("ANALISTA"); self.v_activo.set(True)
        self.e_correo.config(state="normal")
        self.titulo.config(text="Nuevo usuario")

    def guardar(self):
        try:
            if self.id_sel is None:
                self.auth.crear(self.v["nombre"].get(), self.v["correo"].get(), self.v["clave"].get(), self.v_rol.get())
            else:
                if self.id_sel == self.app.usuario.id_usuario and (not self.v_activo.get() or self.v_rol.get() != "ADMINISTRADOR"):
                    raise AuthError("No puede desactivarse ni quitarse el rol de administrador a sí mismo.")
                self.auth.actualizar(self.id_sel, self.v["nombre"].get(), self.v_rol.get(), self.v_activo.get(),
                                     self.v["clave"].get())
        except AuthError as exc:
            return messagebox.showwarning("Usuarios", str(exc), parent=self)
        self.app.set_estado("Usuario guardado")
        self.nuevo()
        self.cargar()
