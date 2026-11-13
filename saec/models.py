"""Entidades del dominio y objetos de valor."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

ENFERMEDADES = ("EPOC", "ASMA", "DIABETES")
GRUPOS_EDAD = ("18-29", "30-39", "40-49", "50-59")
ESTRATOS = (1, 2, 3)
ROLES = ("ANALISTA", "ADMINISTRADOR")


def grupo_edad(edad: int | float | None) -> str | None:
    """Grupo de edad del proyecto para una edad exacta."""
    if edad is None:
        return None
    e = int(edad)
    if 18 <= e <= 29:
        return "18-29"
    if 30 <= e <= 39:
        return "30-39"
    if 40 <= e <= 49:
        return "40-49"
    if 50 <= e <= 59:
        return "50-59"
    return None


def grupo_de_quinquenio(desde: int, hasta: int) -> str | None:
    """Ubica un quinquenio (p. ej. 25-29) en el grupo de edad del proyecto."""
    medio = (desde + hasta) / 2
    if hasta < 18 or desde > 59:
        return None
    return grupo_edad(max(18, min(59, medio)))


@dataclass
class Filtro:
    enfermedad: Optional[str] = None
    edad_min: int = 18
    edad_max: int = 59
    estrato: Optional[int] = None
    anio: Optional[int] = None
    id_ips: Optional[int] = None
    localidad: Optional[str] = None
    origen: Optional[str] = None  # INDIVIDUAL | AGREGADO | None (todas)

    def validar(self) -> None:
        if not (18 <= self.edad_min <= self.edad_max <= 59):
            raise ValueError("La edad debe estar entre 18 y 59 años y la mínima no puede superar la máxima.")
        if self.estrato is not None and self.estrato not in ESTRATOS:
            raise ValueError("El estrato debe ser 1, 2 o 3.")
        if self.anio is not None and not 2020 <= self.anio <= 2026:
            raise ValueError("El año debe estar entre 2020 y 2026.")
        if self.enfermedad is not None and self.enfermedad not in ENFERMEDADES:
            raise ValueError("Enfermedad no válida.")

    def grupos_incluidos(self) -> list[str]:
        """Grupos de edad que se cruzan con el rango [edad_min, edad_max]."""
        out = []
        for g in GRUPOS_EDAD:
            a, b = (int(x) for x in g.split("-"))
            if b >= self.edad_min and a <= self.edad_max:
                out.append(g)
        return out

    def como_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def descripcion(self) -> str:
        partes = [f"Edad {self.edad_min}-{self.edad_max}"]
        partes.append(f"Enfermedad: {self.enfermedad or 'todas'}")
        partes.append(f"Estrato: {self.estrato or '1-3'}")
        partes.append(f"Año: {self.anio or '2020-2026'}")
        if self.localidad:
            partes.append(f"Localidad: {self.localidad}")
        if self.id_ips:
            partes.append(f"IPS: {self.id_ips}")
        if self.origen:
            partes.append("Fuente: " + ("registros individuales" if self.origen == "INDIVIDUAL" else "RIPS agregado"))
        return " · ".join(partes)


@dataclass
class Usuario:
    id_usuario: int
    nombre: str
    correo: str
    rol: str
    activo: bool = True

    @property
    def es_admin(self) -> bool:
        return self.rol == "ADMINISTRADOR"


@dataclass
class ResultadoETL:
    id_ejecucion: int = 0
    leidos: int = 0
    cargados: int = 0
    rechazados: int = 0
    fuera_poblacion: int = 0
    atenciones: int = 0
    estado: str = "EN_PROCESO"
    mensajes: list = field(default_factory=list)
