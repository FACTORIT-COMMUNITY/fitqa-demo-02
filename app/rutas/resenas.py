"""Resenas: puntaje y comentario de una cancha.

Dos reglas sostienen que el promedio signifique algo: solo resena quien jugo ahi (tiene al
menos una reserva `completada` en esa cancha) y cada usuario deja una sola resena por
cancha. Editarla es libre; el promedio se recalcula solo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from .. import auth, db, serializadores as ser
from ..errores import Conflicto, NoEncontrado, SinPermiso
from ..esquemas import ResenaEditada, ResenaNueva
from ..validacion import validar_paginacion

router = APIRouter(tags=["resenas"])


def _buscar(resena_id: int) -> dict:
    fila = db.uno("SELECT * FROM resenas WHERE id = ?", (resena_id,))
    if fila is None:
        raise NoEncontrado("no existe esa resena")
    return fila


@router.get("/canchas/{cancha_id}/resenas")
def listar(
    cancha_id: int,
    puntaje_min: int | None = Query(default=None, ge=1, le=5),
    limite: int | None = Query(default=None),
    desde: int | None = Query(default=None),
):
    """Resenas de una cancha, de la mas nueva a la mas vieja."""
    if db.uno("SELECT id FROM canchas WHERE id = ?", (cancha_id,)) is None:
        raise NoEncontrado("no existe esa cancha")
    limite, desde = validar_paginacion(limite, desde)
    condiciones, parametros = ["cancha_id = ?"], [cancha_id]
    if puntaje_min is not None:
        condiciones.append("puntaje >= ?")
        parametros.append(puntaje_min)
    where = " WHERE " + " AND ".join(condiciones)
    total = db.escalar(f"SELECT COUNT(*) FROM resenas{where}", tuple(parametros))
    filas = db.consultar(
        f"SELECT * FROM resenas{where} ORDER BY id DESC LIMIT ? OFFSET ?",
        tuple(parametros) + (limite, desde),
    )
    promedio = db.escalar("SELECT AVG(puntaje) FROM resenas WHERE cancha_id = ?", (cancha_id,))
    salida = ser.pagina([ser.resena(f) for f in filas], total, limite, desde)
    salida["promedio"] = round(promedio, 2) if promedio is not None else None
    return salida


@router.post("/canchas/{cancha_id}/resenas", status_code=201)
def crear(cancha_id: int, cuerpo: ResenaNueva, usuario: dict = Depends(auth.actual)):
    """Deja una resena. Pide haber jugado ahi al menos una vez."""
    if db.uno("SELECT id FROM canchas WHERE id = ?", (cancha_id,)) is None:
        raise NoEncontrado("no existe esa cancha")
    jugo = db.uno(
        "SELECT 1 AS x FROM reservas WHERE cancha_id = ? AND usuario_id = ?"
        " AND estado = 'completada'",
        (cancha_id, usuario["id"]),
    )
    if jugo is None and not auth.es_admin(usuario):
        raise Conflicto("solo podes resenar una cancha en la que jugaste")
    ya = db.uno(
        "SELECT id FROM resenas WHERE cancha_id = ? AND usuario_id = ?",
        (cancha_id, usuario["id"]),
    )
    if ya:
        raise Conflicto("ya dejaste una resena en esta cancha")
    resena_id = db.ejecutar(
        "INSERT INTO resenas (cancha_id, usuario_id, puntaje, comentario, creada_en)"
        " VALUES (?,?,?,?,?)",
        (cancha_id, usuario["id"], cuerpo.puntaje, cuerpo.comentario, db.AHORA),
    )
    db.auditar(usuario["id"], "alta-resena", f"resena:{resena_id}")
    return ser.resena(_buscar(resena_id))


@router.get("/resenas/{resena_id}")
def detalle(resena_id: int):
    """Una resena."""
    return ser.resena(_buscar(resena_id))


@router.put("/resenas/{resena_id}")
def editar(resena_id: int, cuerpo: ResenaEditada, usuario: dict = Depends(auth.actual)):
    """Corrige la propia resena."""
    fila = _buscar(resena_id)
    if fila["usuario_id"] != usuario["id"] and not auth.es_admin(usuario):
        raise SinPermiso("esa resena no es tuya")
    db.ejecutar(
        "UPDATE resenas SET puntaje = ?, comentario = ? WHERE id = ?",
        (cuerpo.puntaje, cuerpo.comentario, resena_id),
    )
    db.auditar(usuario["id"], "edicion-resena", f"resena:{resena_id}")
    return ser.resena(_buscar(resena_id))


@router.delete("/resenas/{resena_id}", status_code=204)
def borrar(resena_id: int, usuario: dict = Depends(auth.actual)):
    """Borra la propia resena. El admin puede borrar cualquiera."""
    fila = _buscar(resena_id)
    if fila["usuario_id"] != usuario["id"] and not auth.es_admin(usuario):
        raise SinPermiso("esa resena no es tuya")
    db.ejecutar("DELETE FROM resenas WHERE id = ?", (resena_id,))
    db.auditar(usuario["id"], "baja-resena", f"resena:{resena_id}")
    return Response(status_code=204)
