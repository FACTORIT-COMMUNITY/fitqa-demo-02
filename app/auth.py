"""Autenticacion por token opaco y control de acceso por rol.

No hay JWT ni firma: el token es un valor aleatorio que se guarda en la tabla `sesiones` y
se manda en `Authorization: Bearer <token>`. Cerrar sesion borra la fila, asi que la
revocacion es inmediata — que es justamente lo que un JWT no da gratis.

Los tres roles del sistema:

- `jugador` — reserva para si mismo, ve y edita lo propio.
- `duenio`  — administra las sedes que tiene asignadas y las canchas de esas sedes.
- `admin`   — todo.
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import Header

from . import db
from .errores import NoAutenticado, SinPermiso

JERARQUIA = {"jugador": 0, "duenio": 1, "admin": 2}


def emitir_token(usuario_id: int) -> str:
    token = secrets.token_hex(24)
    db.ejecutar(
        "INSERT INTO sesiones (token, usuario_id, creada_en) VALUES (?,?,?)",
        (token, usuario_id, db.AHORA),
    )
    return token


def revocar_token(token: str) -> bool:
    return db.ejecutar("DELETE FROM sesiones WHERE token = ?", (token,)) > 0


def revocar_sesiones_de(usuario_id: int) -> int:
    return db.ejecutar("DELETE FROM sesiones WHERE usuario_id = ?", (usuario_id,))


def _token_del_encabezado(authorization: str | None) -> str | None:
    if not authorization:
        return None
    partes = authorization.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    return partes[1].strip() or None


def usuario_de_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    return db.uno(
        "SELECT u.* FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id WHERE s.token = ?",
        (token,),
    )


def actual(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Dependencia: exige sesion valida y devuelve el usuario."""
    usuario = usuario_de_token(_token_del_encabezado(authorization))
    if usuario is None:
        raise NoAutenticado("hace falta iniciar sesion")
    if not usuario["activo"]:
        raise SinPermiso("la cuenta esta dada de baja")
    return usuario


def opcional(authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    """Dependencia: deja pasar sin sesion. La usan los listados publicos."""
    usuario = usuario_de_token(_token_del_encabezado(authorization))
    if usuario is not None and not usuario["activo"]:
        return None
    return usuario


def exigir_rol(usuario: dict, *roles: str) -> None:
    if usuario["rol"] not in roles:
        raise SinPermiso(f"esta operacion es para {' o '.join(roles)}")


def al_menos(usuario: dict, rol: str) -> None:
    if JERARQUIA.get(usuario["rol"], -1) < JERARQUIA[rol]:
        raise SinPermiso(f"esta operacion pide rol {rol} o superior")


def es_admin(usuario: dict) -> bool:
    return usuario["rol"] == "admin"


def administra_sede(usuario: dict, sede_id: int) -> bool:
    """Un duenio solo manda en las sedes que tiene asignadas; el admin, en todas."""
    if es_admin(usuario):
        return True
    if usuario["rol"] != "duenio":
        return False
    sede = db.uno("SELECT duenio_id FROM sedes WHERE id = ?", (sede_id,))
    return bool(sede and sede["duenio_id"] == usuario["id"])


def administra_cancha(usuario: dict, cancha_id: int) -> bool:
    cancha = db.uno("SELECT sede_id FROM canchas WHERE id = ?", (cancha_id,))
    return bool(cancha) and administra_sede(usuario, cancha["sede_id"])


def exigir_sede(usuario: dict, sede_id: int) -> None:
    if not administra_sede(usuario, sede_id):
        raise SinPermiso("esa sede no es tuya")


def exigir_cancha(usuario: dict, cancha_id: int) -> None:
    if not administra_cancha(usuario, cancha_id):
        raise SinPermiso("esa cancha no es tuya")
