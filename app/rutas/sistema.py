"""Salud del proceso, version y utilidades de administracion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import auth, db, serializadores as ser
from ..validacion import validar_paginacion

router = APIRouter(tags=["sistema"])

VERSION = "1.4.0"


@router.get("/health")
def salud():
    """Responde apenas el proceso esta listo para atender."""
    return {"estado": "ok"}


@router.get("/version")
def version():
    """Version del servicio y conteo de filas por tabla, util para saber si hubo reset."""
    return {
        "version": VERSION,
        "filas": {
            "usuarios": db.escalar("SELECT COUNT(*) FROM usuarios"),
            "sedes": db.escalar("SELECT COUNT(*) FROM sedes"),
            "canchas": db.escalar("SELECT COUNT(*) FROM canchas"),
            "horarios": db.escalar("SELECT COUNT(*) FROM horarios"),
            "reservas": db.escalar("SELECT COUNT(*) FROM reservas"),
            "equipos": db.escalar("SELECT COUNT(*) FROM equipos"),
            "resenas": db.escalar("SELECT COUNT(*) FROM resenas"),
        },
    }


@router.post("/admin/reset")
def reiniciar():
    """Devuelve la base a la semilla documentada en el README.

    No pide sesion a proposito: la base es en memoria y sin este endpoint abierto no habria
    forma de aislar una prueba de la anterior. En un sistema de verdad esto no existiria.
    """
    db.reiniciar()
    return {"estado": "reiniciado", "usuarios": db.escalar("SELECT COUNT(*) FROM usuarios")}


@router.get("/admin/auditoria")
def auditoria(
    accion: str | None = Query(default=None),
    usuario_id: int | None = Query(default=None),
    limite: int | None = Query(default=None),
    desde: int | None = Query(default=None),
    usuario: dict = Depends(auth.actual),
):
    """Registro de acciones, de la mas nueva a la mas vieja."""
    auth.exigir_rol(usuario, "admin")
    limite, desde = validar_paginacion(limite, desde)
    condiciones, parametros = [], []
    if accion is not None:
        condiciones.append("accion = ?")
        parametros.append(accion)
    if usuario_id is not None:
        condiciones.append("usuario_id = ?")
        parametros.append(usuario_id)
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = db.escalar(f"SELECT COUNT(*) FROM auditoria{where}", tuple(parametros))
    filas = db.consultar(
        f"SELECT * FROM auditoria{where} ORDER BY id DESC LIMIT ? OFFSET ?",
        tuple(parametros) + (limite, desde),
    )
    return ser.pagina([ser.auditoria(f) for f in filas], total, limite, desde)
