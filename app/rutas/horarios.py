"""Horarios: las franjas en las que una cancha se puede reservar.

Una franja es `(dia_semana, hora_inicio, hora_fin)` y se repite todas las semanas. La
disponibilidad de una fecha concreta sale de cruzar estas franjas con las reservas de ese
dia, y eso vive en `GET /canchas/{id}/disponibilidad`.

Las rutas cuelgan de dos prefijos a proposito: crear y listar necesitan la cancha en la
URL, y editar o borrar una franja ya creada no.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from .. import auth, db, serializadores as ser
from ..errores import Conflicto, NoEncontrado
from ..esquemas import HorarioEditado, HorarioNuevo
from ..validacion import validar_rango

router = APIRouter(tags=["horarios"])


def _se_pisan(a_ini: str, a_fin: str, b_ini: str, b_fin: str) -> bool:
    """Rango semiabierto `[inicio, fin)`: 19:00-20:00 y 20:00-21:00 no se pisan."""
    return a_ini < b_fin and a_fin > b_ini


@router.get("/canchas/{cancha_id}/horarios")
def listar(cancha_id: int, dia_semana: int | None = Query(default=None, ge=0, le=6)):
    """Franjas configuradas para la cancha."""
    if db.uno("SELECT id FROM canchas WHERE id = ?", (cancha_id,)) is None:
        raise NoEncontrado("no existe esa cancha")
    condiciones, parametros = ["cancha_id = ?"], [cancha_id]
    if dia_semana is not None:
        condiciones.append("dia_semana = ?")
        parametros.append(dia_semana)
    filas = db.consultar(
        f"SELECT * FROM horarios WHERE {' AND '.join(condiciones)}"
        " ORDER BY dia_semana, hora_inicio",
        tuple(parametros),
    )
    return {"datos": [ser.horario(f) for f in filas], "total": len(filas)}


@router.post("/canchas/{cancha_id}/horarios", status_code=201)
def crear(cancha_id: int, cuerpo: HorarioNuevo, usuario: dict = Depends(auth.actual)):
    """Agrega una franja. Rebota si se pisa con otra del mismo dia."""
    if db.uno("SELECT id FROM canchas WHERE id = ?", (cancha_id,)) is None:
        raise NoEncontrado("no existe esa cancha")
    auth.exigir_cancha(usuario, cancha_id)
    inicio, fin = validar_rango(cuerpo.hora_inicio, cuerpo.hora_fin)
    existentes = db.consultar(
        "SELECT hora_inicio, hora_fin FROM horarios WHERE cancha_id = ? AND dia_semana = ?",
        (cancha_id, cuerpo.dia_semana),
    )
    for h in existentes:
        if _se_pisan(inicio, fin, h["hora_inicio"], h["hora_fin"]):
            raise Conflicto(
                f"la franja se pisa con {h['hora_inicio']}-{h['hora_fin']} del mismo dia"
            )
    horario_id = db.ejecutar(
        "INSERT INTO horarios (cancha_id, dia_semana, hora_inicio, hora_fin, activo)"
        " VALUES (?,?,?,?,?)",
        (cancha_id, cuerpo.dia_semana, inicio, fin, 1 if cuerpo.activo else 0),
    )
    db.auditar(usuario["id"], "alta-horario", f"horario:{horario_id}")
    return ser.horario(db.uno("SELECT * FROM horarios WHERE id = ?", (horario_id,)))


@router.get("/horarios/{horario_id}")
def detalle(horario_id: int):
    """Una franja."""
    fila = db.uno("SELECT * FROM horarios WHERE id = ?", (horario_id,))
    if fila is None:
        raise NoEncontrado("no existe ese horario")
    return ser.horario(fila)


@router.put("/horarios/{horario_id}")
def editar(horario_id: int, cuerpo: HorarioEditado, usuario: dict = Depends(auth.actual)):
    """Mueve o desactiva una franja."""
    fila = db.uno("SELECT * FROM horarios WHERE id = ?", (horario_id,))
    if fila is None:
        raise NoEncontrado("no existe ese horario")
    auth.exigir_cancha(usuario, fila["cancha_id"])
    inicio, fin = validar_rango(cuerpo.hora_inicio, cuerpo.hora_fin)
    otras = db.consultar(
        "SELECT hora_inicio, hora_fin FROM horarios"
        " WHERE cancha_id = ? AND dia_semana = ? AND id <> ?",
        (fila["cancha_id"], cuerpo.dia_semana, horario_id),
    )
    for h in otras:
        if _se_pisan(inicio, fin, h["hora_inicio"], h["hora_fin"]):
            raise Conflicto(
                f"la franja se pisa con {h['hora_inicio']}-{h['hora_fin']} del mismo dia"
            )
    db.ejecutar(
        "UPDATE horarios SET dia_semana = ?, hora_inicio = ?, hora_fin = ?, activo = ?"
        " WHERE id = ?",
        (cuerpo.dia_semana, inicio, fin, 1 if cuerpo.activo else 0, horario_id),
    )
    db.auditar(usuario["id"], "edicion-horario", f"horario:{horario_id}")
    return ser.horario(db.uno("SELECT * FROM horarios WHERE id = ?", (horario_id,)))


@router.delete("/horarios/{horario_id}", status_code=204)
def borrar(horario_id: int, usuario: dict = Depends(auth.actual)):
    """Saca la franja. Las reservas ya hechas sobre ella no se tocan: son historia."""
    fila = db.uno("SELECT * FROM horarios WHERE id = ?", (horario_id,))
    if fila is None:
        raise NoEncontrado("no existe ese horario")
    auth.exigir_cancha(usuario, fila["cancha_id"])
    db.ejecutar("DELETE FROM horarios WHERE id = ?", (horario_id,))
    db.auditar(usuario["id"], "baja-horario", f"horario:{horario_id}")
    return Response(status_code=204)
