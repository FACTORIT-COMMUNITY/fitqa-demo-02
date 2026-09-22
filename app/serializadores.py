"""Como se ve cada recurso en la respuesta.

Una funcion por recurso, todas con la misma forma: reciben la fila cruda de SQLite y
devuelven el diccionario publico. Aca es donde se decide que NO sale — el `clave_hash` de
un usuario, por ejemplo, nunca cruza el borde.
"""

from __future__ import annotations

from typing import Any

from . import db


def usuario(fila: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "nombre": fila["nombre"],
        "email": fila["email"],
        "rol": fila["rol"],
        "telefono": fila["telefono"],
        "activo": bool(fila["activo"]),
        "creado_en": fila["creado_en"],
    }


def sede(fila: dict[str, Any]) -> dict[str, Any]:
    canchas = db.escalar("SELECT COUNT(*) FROM canchas WHERE sede_id = ?", (fila["id"],))
    return {
        "id": fila["id"],
        "nombre": fila["nombre"],
        "direccion": fila["direccion"],
        "ciudad": fila["ciudad"],
        "telefono": fila["telefono"],
        "duenio_id": fila["duenio_id"],
        "activa": bool(fila["activa"]),
        "canchas": canchas,
    }


def cancha(fila: dict[str, Any]) -> dict[str, Any]:
    puntaje = db.escalar("SELECT AVG(puntaje) FROM resenas WHERE cancha_id = ?", (fila["id"],))
    return {
        "id": fila["id"],
        "sede_id": fila["sede_id"],
        "nombre": fila["nombre"],
        "tipo": fila["tipo"],
        "superficie": fila["superficie"],
        "techada": bool(fila["techada"]),
        "precio_hora": fila["precio_hora"],
        "estado": fila["estado"],
        "puntaje_promedio": round(puntaje, 2) if puntaje is not None else None,
    }


def horario(fila: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "cancha_id": fila["cancha_id"],
        "dia_semana": fila["dia_semana"],
        "hora_inicio": fila["hora_inicio"],
        "hora_fin": fila["hora_fin"],
        "activo": bool(fila["activo"]),
    }


def reserva(fila: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "cancha_id": fila["cancha_id"],
        "cancha": fila.get("cancha_nombre"),
        "usuario_id": fila["usuario_id"],
        "usuario": fila.get("usuario_nombre"),
        "equipo_id": fila["equipo_id"],
        "fecha": fila["fecha"],
        "hora_inicio": fila["hora_inicio"],
        "hora_fin": fila["hora_fin"],
        "estado": fila["estado"],
        "nota": fila["nota"],
        "creada_en": fila["creada_en"],
    }


def evento(fila: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "reserva_id": fila["reserva_id"],
        "estado_anterior": fila["estado_anterior"],
        "estado_nuevo": fila["estado_nuevo"],
        "usuario_id": fila["usuario_id"],
        "creado_en": fila["creado_en"],
    }


def equipo(fila: dict[str, Any]) -> dict[str, Any]:
    miembros = db.consultar(
        "SELECT u.id, u.nombre, u.email FROM equipo_miembros m"
        " JOIN usuarios u ON u.id = m.usuario_id WHERE m.equipo_id = ? ORDER BY u.id",
        (fila["id"],),
    )
    return {
        "id": fila["id"],
        "nombre": fila["nombre"],
        "capitan_id": fila["capitan_id"],
        "creado_en": fila["creado_en"],
        "miembros": miembros,
    }


def resena(fila: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "cancha_id": fila["cancha_id"],
        "usuario_id": fila["usuario_id"],
        "puntaje": fila["puntaje"],
        "comentario": fila["comentario"],
        "creada_en": fila["creada_en"],
    }


def auditoria(fila: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "usuario_id": fila["usuario_id"],
        "accion": fila["accion"],
        "recurso": fila["recurso"],
        "creado_en": fila["creado_en"],
    }


def pagina(datos: list, total: int, limite: int, desde: int) -> dict[str, Any]:
    """Sobre de paginacion, igual para todos los listados."""
    return {"datos": datos, "total": total, "limite": limite, "desde": desde}
