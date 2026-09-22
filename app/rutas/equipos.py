"""Equipos: grupos de jugadores que reservan juntos.

El capitan es quien manda: edita el equipo y agrega o saca miembros. El admin puede todo.
Un equipo siempre tiene a su capitan como miembro; sacarlo rebota.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from .. import auth, db, serializadores as ser
from ..errores import Conflicto, NoEncontrado, SinPermiso
from ..esquemas import EquipoEditado, EquipoNuevo, MiembroNuevo
from ..validacion import validar_paginacion

router = APIRouter(prefix="/equipos", tags=["equipos"])


def _buscar(equipo_id: int) -> dict:
    fila = db.uno("SELECT * FROM equipos WHERE id = ?", (equipo_id,))
    if fila is None:
        raise NoEncontrado("no existe ese equipo")
    return fila


def _manda(usuario: dict, equipo: dict) -> bool:
    return auth.es_admin(usuario) or equipo["capitan_id"] == usuario["id"]


@router.get("")
def listar(
    busqueda: str | None = Query(default=None),
    capitan_id: int | None = Query(default=None),
    limite: int | None = Query(default=None),
    desde: int | None = Query(default=None),
):
    """Listado publico de equipos."""
    limite, desde = validar_paginacion(limite, desde)
    condiciones, parametros = [], []
    if busqueda:
        condiciones.append("nombre LIKE ?")
        parametros.append(f"%{busqueda}%")
    if capitan_id is not None:
        condiciones.append("capitan_id = ?")
        parametros.append(capitan_id)
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = db.escalar(f"SELECT COUNT(*) FROM equipos{where}", tuple(parametros))
    filas = db.consultar(
        f"SELECT * FROM equipos{where} ORDER BY id LIMIT ? OFFSET ?",
        tuple(parametros) + (limite, desde),
    )
    return ser.pagina([ser.equipo(f) for f in filas], total, limite, desde)


@router.post("", status_code=201)
def crear(cuerpo: EquipoNuevo, usuario: dict = Depends(auth.actual)):
    """Crea un equipo. Quien lo crea queda de capitan salvo que el admin diga otra cosa."""
    nombre = cuerpo.nombre.strip()
    if db.uno("SELECT id FROM equipos WHERE nombre = ?", (nombre,)):
        raise Conflicto("ya existe un equipo con ese nombre")
    capitan = usuario["id"]
    if cuerpo.capitan_id is not None and cuerpo.capitan_id != usuario["id"]:
        auth.exigir_rol(usuario, "admin")
        if db.uno("SELECT id FROM usuarios WHERE id = ?", (cuerpo.capitan_id,)) is None:
            raise NoEncontrado("no existe ese usuario")
        capitan = cuerpo.capitan_id
    equipo_id = db.ejecutar(
        "INSERT INTO equipos (nombre, capitan_id, creado_en) VALUES (?,?,?)",
        (nombre, capitan, db.AHORA),
    )
    db.ejecutar(
        "INSERT INTO equipo_miembros (equipo_id, usuario_id) VALUES (?,?)", (equipo_id, capitan)
    )
    db.auditar(usuario["id"], "alta-equipo", f"equipo:{equipo_id}")
    return ser.equipo(_buscar(equipo_id))


@router.get("/{equipo_id}")
def detalle(equipo_id: int):
    """Un equipo con sus miembros."""
    return ser.equipo(_buscar(equipo_id))


@router.put("/{equipo_id}")
def editar(equipo_id: int, cuerpo: EquipoEditado, usuario: dict = Depends(auth.actual)):
    """Renombra el equipo o le cambia el capitan. El capitan nuevo tiene que ser miembro."""
    equipo = _buscar(equipo_id)
    if not _manda(usuario, equipo):
        raise SinPermiso("solo el capitan puede editar el equipo")
    nombre = cuerpo.nombre.strip()
    choque = db.uno("SELECT id FROM equipos WHERE nombre = ? AND id <> ?", (nombre, equipo_id))
    if choque:
        raise Conflicto("ya existe un equipo con ese nombre")
    es_miembro = db.uno(
        "SELECT 1 AS x FROM equipo_miembros WHERE equipo_id = ? AND usuario_id = ?",
        (equipo_id, cuerpo.capitan_id),
    )
    if es_miembro is None:
        raise Conflicto("el capitan tiene que ser miembro del equipo")
    db.ejecutar(
        "UPDATE equipos SET nombre = ?, capitan_id = ? WHERE id = ?",
        (nombre, cuerpo.capitan_id, equipo_id),
    )
    db.auditar(usuario["id"], "edicion-equipo", f"equipo:{equipo_id}")
    return ser.equipo(_buscar(equipo_id))


@router.delete("/{equipo_id}", status_code=204)
def borrar(equipo_id: int, usuario: dict = Depends(auth.actual)):
    """Disuelve el equipo. Las reservas que lo mencionaban quedan sin equipo, no se borran."""
    equipo = _buscar(equipo_id)
    if not _manda(usuario, equipo):
        raise SinPermiso("solo el capitan puede disolver el equipo")
    db.ejecutar("UPDATE reservas SET equipo_id = NULL WHERE equipo_id = ?", (equipo_id,))
    db.ejecutar("DELETE FROM equipo_miembros WHERE equipo_id = ?", (equipo_id,))
    db.ejecutar("DELETE FROM equipos WHERE id = ?", (equipo_id,))
    db.auditar(usuario["id"], "baja-equipo", f"equipo:{equipo_id}")
    return Response(status_code=204)


@router.post("/{equipo_id}/miembros", status_code=201)
def agregar_miembro(
    equipo_id: int, cuerpo: MiembroNuevo, usuario: dict = Depends(auth.actual)
):
    """Suma un jugador al equipo."""
    equipo = _buscar(equipo_id)
    if not _manda(usuario, equipo):
        raise SinPermiso("solo el capitan puede sumar miembros")
    candidato = db.uno("SELECT * FROM usuarios WHERE id = ?", (cuerpo.usuario_id,))
    if candidato is None:
        raise NoEncontrado("no existe ese usuario")
    if not candidato["activo"]:
        raise Conflicto("no se puede sumar a un usuario dado de baja")
    ya = db.uno(
        "SELECT 1 AS x FROM equipo_miembros WHERE equipo_id = ? AND usuario_id = ?",
        (equipo_id, cuerpo.usuario_id),
    )
    if ya:
        raise Conflicto("ese jugador ya esta en el equipo")
    db.ejecutar(
        "INSERT INTO equipo_miembros (equipo_id, usuario_id) VALUES (?,?)",
        (equipo_id, cuerpo.usuario_id),
    )
    db.auditar(usuario["id"], "alta-miembro", f"equipo:{equipo_id}")
    return ser.equipo(_buscar(equipo_id))


@router.delete("/{equipo_id}/miembros/{usuario_id}", status_code=204)
def sacar_miembro(equipo_id: int, usuario_id: int, usuario: dict = Depends(auth.actual)):
    """Saca un jugador del equipo. Al capitan no se lo puede sacar."""
    equipo = _buscar(equipo_id)
    if not _manda(usuario, equipo):
        raise SinPermiso("solo el capitan puede sacar miembros")
    if equipo["capitan_id"] == usuario_id:
        raise Conflicto("el capitan no se puede sacar del equipo")
    borradas = db.ejecutar(
        "DELETE FROM equipo_miembros WHERE equipo_id = ? AND usuario_id = ?",
        (equipo_id, usuario_id),
    )
    if not borradas:
        raise NoEncontrado("ese jugador no esta en el equipo")
    db.auditar(usuario["id"], "baja-miembro", f"equipo:{equipo_id}")
    return Response(status_code=204)
