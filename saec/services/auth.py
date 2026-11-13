"""Autenticación y gestión de usuarios (contraseñas con bcrypt)."""
from __future__ import annotations

import re

import bcrypt

from ..models import ROLES, Usuario
from ..repositories import UsuarioRepository


class AuthError(Exception):
    pass


def hash_contrasena(clave: str) -> str:
    return bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verificar(clave: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(clave.encode("utf-8"), h.encode())
    except ValueError:
        return False


def validar_clave(clave: str) -> None:
    if len(clave) < 8 or not re.search(r"\d", clave) or not re.search(r"[A-Za-z]", clave):
        raise AuthError("La contraseña debe tener al menos 8 caracteres, con letras y números.")


class AuthService:
    def __init__(self, repo: UsuarioRepository | None = None):
        self.repo = repo or UsuarioRepository()

    def login(self, correo: str, clave: str) -> Usuario:
        u = self.repo.por_correo(correo.strip())
        if not u or not verificar(clave, u["contrasena_hash"]):
            raise AuthError("Correo o contraseña incorrectos.")
        if not u["activo"]:
            raise AuthError("El usuario está desactivado. Contacte al administrador.")
        return Usuario(int(u["id_usuario"]), u["nombre"], u["correo"], u["rol"], bool(u["activo"]))

    def crear(self, nombre: str, correo: str, clave: str, rol: str) -> int:
        if rol not in ROLES:
            raise AuthError("Rol no válido.")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo):
            raise AuthError("Correo no válido.")
        if not nombre.strip():
            raise AuthError("El nombre es obligatorio.")
        validar_clave(clave)
        if self.repo.por_correo(correo):
            raise AuthError("Ya existe un usuario con ese correo.")
        return self.repo.crear(nombre.strip(), correo.strip().lower(), hash_contrasena(clave), rol)

    def actualizar(self, id_usuario: int, nombre: str, rol: str, activo: bool, nueva_clave: str = "") -> None:
        if rol not in ROLES:
            raise AuthError("Rol no válido.")
        h = None
        if nueva_clave:
            validar_clave(nueva_clave)
            h = hash_contrasena(nueva_clave)
        self.repo.actualizar(id_usuario, nombre.strip(), rol, activo, h)

    def asegurar_admin(self, correo: str = "admin@saec.local", clave: str = "Admin2026") -> bool:
        """Crea el administrador inicial si la tabla de usuarios está vacía."""
        if self.repo.contar() == 0:
            self.repo.crear("Administrador SAEC", correo, hash_contrasena(clave), "ADMINISTRADOR")
            return True
        return False
