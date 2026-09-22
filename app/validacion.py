"""Validaciones compartidas: fechas, horas, paginacion y orden.

Viven juntas porque son las reglas que todos los recursos repiten. Cada funcion levanta
`DatosInvalidos` con la lista de detalles ya armada, asi que los handlers no tienen que
construir respuestas de error a mano.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from .errores import DatosInvalidos
from .esquemas import LIMITE_DEFECTO, LIMITE_MAX, LIMITE_MIN

RX_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RX_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
RX_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def validar_fecha(valor: str, campo: str = "fecha") -> str:
    if not isinstance(valor, str) or not RX_FECHA.match(valor):
        raise DatosInvalidos(
            detalles=[{"campo": campo, "problema": "se espera el formato AAAA-MM-DD"}]
        )
    try:
        date.fromisoformat(valor)
    except ValueError:
        raise DatosInvalidos(
            detalles=[{"campo": campo, "problema": "no es una fecha del calendario"}]
        ) from None
    return valor


def validar_hora(valor: str, campo: str) -> str:
    if not isinstance(valor, str) or not RX_HORA.match(valor):
        raise DatosInvalidos(
            detalles=[{"campo": campo, "problema": "se espera el formato HH:MM en 24 horas"}]
        )
    return valor


def validar_rango(inicio: str, fin: str) -> tuple[str, str]:
    """El rango es semiabierto: `[inicio, fin)`. Una franja de 19:00 a 20:00 no choca con
    otra de 20:00 a 21:00."""
    validar_hora(inicio, "hora_inicio")
    validar_hora(fin, "hora_fin")
    if inicio >= fin:
        raise DatosInvalidos(
            detalles=[{"campo": "hora_fin", "problema": "tiene que ser posterior a hora_inicio"}]
        )
    return inicio, fin


def validar_email(valor: str) -> str:
    if not RX_EMAIL.match(valor or ""):
        raise DatosInvalidos(detalles=[{"campo": "email", "problema": "no parece un email"}])
    return valor.lower()


def validar_enumerado(valor: str, permitidos: tuple[str, ...], campo: str) -> str:
    if valor not in permitidos:
        raise DatosInvalidos(
            detalles=[{"campo": campo, "problema": f"tiene que ser uno de {list(permitidos)}"}]
        )
    return valor


def validar_paginacion(limite: int | None, desde: int | None) -> tuple[int, int]:
    limite = LIMITE_DEFECTO if limite is None else limite
    desde = 0 if desde is None else desde
    if limite < LIMITE_MIN or limite > LIMITE_MAX:
        raise DatosInvalidos(
            detalles=[
                {"campo": "limite", "problema": f"tiene que estar entre {LIMITE_MIN} y {LIMITE_MAX}"}
            ]
        )
    if desde < 0:
        raise DatosInvalidos(detalles=[{"campo": "desde", "problema": "no puede ser negativo"}])
    return limite, desde


def validar_orden(orden: str | None, permitidos: tuple[str, ...], defecto: str) -> str:
    if orden is None:
        return defecto
    if orden not in permitidos:
        raise DatosInvalidos(
            detalles=[{"campo": "orden", "problema": f"tiene que ser uno de {list(permitidos)}"}]
        )
    return orden


def validar_direccion(direccion: str | None) -> str:
    if direccion is None:
        return "asc"
    if direccion not in ("asc", "desc"):
        raise DatosInvalidos(
            detalles=[{"campo": "direccion", "problema": "tiene que ser asc o desc"}]
        )
    return direccion


def dia_de_semana(fecha: str) -> int:
    """0 = lunes ... 6 = domingo, igual que `horarios.dia_semana`."""
    return datetime.fromisoformat(fecha).weekday()
