"""Modelos de entrada y salida.

Los de entrada son Pydantic, asi que FastAPI valida tipos y los publica en el contrato
OpenAPI. Los de salida se arman a mano en `serializadores.py`: las filas salen de SQLite
como diccionarios y convertirlas dos veces no agrega nada.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- Vocabulario del dominio ----------------------------------------------------------

ROLES = ("admin", "duenio", "jugador")
ESTADOS_RESERVA = ("pendiente", "confirmada", "cancelada", "completada", "no-show")
ESTADOS_CANCHA = ("habilitada", "mantenimiento", "baja")
TIPOS_CANCHA = ("futbol5", "futbol7", "futbol11")
SUPERFICIES = ("sintetico", "cemento", "natural")

ORDEN_CANCHAS = ("id", "nombre", "precio_hora", "tipo")
ORDEN_RESERVAS = ("id", "fecha", "estado")
ORDEN_USUARIOS = ("id", "nombre", "email")

LIMITE_MIN = 1
LIMITE_MAX = 100
LIMITE_DEFECTO = 20


# --- Autenticacion --------------------------------------------------------------------


class Registro(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    clave: str = Field(min_length=8, max_length=72)
    telefono: str | None = Field(default=None, max_length=30)


class Credenciales(BaseModel):
    email: str
    clave: str


class CambioClave(BaseModel):
    clave_actual: str
    clave_nueva: str = Field(min_length=8, max_length=72)


# --- Usuarios -------------------------------------------------------------------------


class UsuarioNuevo(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    clave: str = Field(min_length=8, max_length=72)
    rol: str = "jugador"
    telefono: str | None = Field(default=None, max_length=30)


class UsuarioEditado(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    telefono: str | None = Field(default=None, max_length=30)
    activo: bool = True


class CambioRol(BaseModel):
    rol: str


# --- Sedes ----------------------------------------------------------------------------


class SedeNueva(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    direccion: str = Field(min_length=3, max_length=160)
    ciudad: str = Field(min_length=2, max_length=80)
    telefono: str | None = Field(default=None, max_length=30)
    duenio_id: int | None = None


class SedeEditada(SedeNueva):
    activa: bool = True


# --- Canchas --------------------------------------------------------------------------


class CanchaNueva(BaseModel):
    sede_id: int
    nombre: str = Field(min_length=1, max_length=80)
    tipo: str = "futbol5"
    superficie: str = "sintetico"
    techada: bool = False
    precio_hora: int = Field(default=0, ge=0, le=10_000_000)


class CanchaEditada(CanchaNueva):
    pass


class CambioEstadoCancha(BaseModel):
    estado: str


# --- Horarios -------------------------------------------------------------------------


class HorarioNuevo(BaseModel):
    dia_semana: int = Field(ge=0, le=6)
    hora_inicio: str
    hora_fin: str
    activo: bool = True


class HorarioEditado(BaseModel):
    dia_semana: int = Field(ge=0, le=6)
    hora_inicio: str
    hora_fin: str
    activo: bool = True


# --- Reservas -------------------------------------------------------------------------


class ReservaNueva(BaseModel):
    cancha_id: int
    fecha: str
    hora_inicio: str
    hora_fin: str
    equipo_id: int | None = None
    nota: str | None = Field(default=None, max_length=280)
    usuario_id: int | None = None  # solo admin/duenio pueden reservar por otro


class ReservaEditada(BaseModel):
    fecha: str
    hora_inicio: str
    hora_fin: str
    equipo_id: int | None = None
    nota: str | None = Field(default=None, max_length=280)


class MotivoCancelacion(BaseModel):
    motivo: str | None = Field(default=None, max_length=280)


# --- Equipos --------------------------------------------------------------------------


class EquipoNuevo(BaseModel):
    nombre: str = Field(min_length=2, max_length=60)
    capitan_id: int | None = None


class EquipoEditado(BaseModel):
    nombre: str = Field(min_length=2, max_length=60)
    capitan_id: int


class MiembroNuevo(BaseModel):
    usuario_id: int


# --- Resenas --------------------------------------------------------------------------


class ResenaNueva(BaseModel):
    puntaje: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=500)


class ResenaEditada(BaseModel):
    puntaje: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=500)
