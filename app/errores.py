"""Errores de dominio y su traduccion a HTTP.

Todas las respuestas de error del sistema tienen la misma forma:

    {"error": "texto legible"}

y las de validacion agregan una lista de detalles:

    {"error": "datos invalidos", "detalles": [{"campo": "puntaje", "problema": "..."}]}

FastAPI trae su propio `{"detail": ...}`; `main.py` registra manejadores que lo reescriben
a esta forma para que no convivan dos contratos de error en la misma API.
"""

from __future__ import annotations


class ErrorDominio(Exception):
    """Base de los errores que el sistema sabe explicar."""

    estado = 400
    mensaje = "error"

    def __init__(self, mensaje: str | None = None, detalles: list[dict] | None = None):
        super().__init__(mensaje or self.mensaje)
        self.mensaje = mensaje or self.mensaje
        self.detalles = detalles or []

    def cuerpo(self) -> dict:
        cuerpo: dict = {"error": self.mensaje}
        if self.detalles:
            cuerpo["detalles"] = self.detalles
        return cuerpo


class DatosInvalidos(ErrorDominio):
    estado = 400
    mensaje = "datos invalidos"


class NoAutenticado(ErrorDominio):
    estado = 401
    mensaje = "credenciales invalidas"


class SinPermiso(ErrorDominio):
    estado = 403
    mensaje = "no tenes permiso para esta operacion"


class NoEncontrado(ErrorDominio):
    estado = 404
    mensaje = "recurso inexistente"


class Conflicto(ErrorDominio):
    estado = 409
    mensaje = "la operacion choca con el estado actual"
