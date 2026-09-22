"""Sedes: los predios que agrupan canchas."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from .. import auth, db, serializadores as ser
from ..errores import Conflicto, NoEncontrado
from ..esquemas import SedeEditada, SedeNueva
from ..validacion import validar_direccion, validar_orden, validar_paginacion

router = APIRouter(prefix="/sedes", tags=["sedes"])

ORDEN_SEDES = ("id", "nombre", "ciudad")


@router.get("")
def listar(
    ciudad: str | None = Query(default=None),
    activa: bool | None = Query(default=None),
    orden: str | None = Query(default=None),
    direccion: str | None = Query(default=None),
    limite: int | None = Query(default=None),
    desde: int | None = Query(default=None),
):
    """Listado publico de sedes. No pide sesion: es la vitrina del sistema."""
    limite, desde = validar_paginacion(limite, desde)
    orden = validar_orden(orden, ORDEN_SEDES, "id")
    direccion = validar_direccion(direccion)

    condiciones, parametros = [], []
    if ciudad is not None:
        condiciones.append("ciudad = ?")
        parametros.append(ciudad)
    if activa is not None:
        condiciones.append("activa = ?")
        parametros.append(1 if activa else 0)
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

    total = db.escalar(f"SELECT COUNT(*) FROM sedes{where}", tuple(parametros))
    filas = db.consultar(
        f"SELECT * FROM sedes{where} ORDER BY {orden} {direccion.upper()} LIMIT ? OFFSET ?",
        tuple(parametros) + (limite, desde),
    )
    return ser.pagina([ser.sede(f) for f in filas], total, limite, desde)


@router.post("", status_code=201)
def crear(cuerpo: SedeNueva, usuario: dict = Depends(auth.actual)):
    """Alta de sede. Solo el admin crea sedes; el duenio administra las que le asignaron."""
    auth.exigir_rol(usuario, "admin")
    if db.uno("SELECT id FROM sedes WHERE nombre = ?", (cuerpo.nombre.strip(),)):
        raise Conflicto("ya existe una sede con ese nombre")
    if cuerpo.duenio_id is not None:
        duenio = db.uno("SELECT rol FROM usuarios WHERE id = ?", (cuerpo.duenio_id,))
        if duenio is None:
            raise NoEncontrado("no existe ese usuario para asignar como duenio")
        if duenio["rol"] == "jugador":
            raise Conflicto("el usuario asignado tiene que ser duenio o admin")
    sede_id = db.ejecutar(
        "INSERT INTO sedes (nombre, direccion, ciudad, telefono, duenio_id, activa)"
        " VALUES (?,?,?,?,?,1)",
        (cuerpo.nombre.strip(), cuerpo.direccion, cuerpo.ciudad, cuerpo.telefono,
         cuerpo.duenio_id),
    )
    db.auditar(usuario["id"], "alta-sede", f"sede:{sede_id}")
    return ser.sede(db.uno("SELECT * FROM sedes WHERE id = ?", (sede_id,)))


@router.get("/{sede_id}")
def detalle(sede_id: int):
    """Una sede."""
    fila = db.uno("SELECT * FROM sedes WHERE id = ?", (sede_id,))
    if fila is None:
        raise NoEncontrado("no existe esa sede")
    return ser.sede(fila)


@router.put("/{sede_id}")
def editar(sede_id: int, cuerpo: SedeEditada, usuario: dict = Depends(auth.actual)):
    """Actualiza los datos de la sede. El duenio puede editar la suya."""
    fila = db.uno("SELECT * FROM sedes WHERE id = ?", (sede_id,))
    if fila is None:
        raise NoEncontrado("no existe esa sede")
    auth.exigir_sede(usuario, sede_id)
    choque = db.uno(
        "SELECT id FROM sedes WHERE nombre = ? AND id <> ?", (cuerpo.nombre.strip(), sede_id)
    )
    if choque:
        raise Conflicto("ya existe una sede con ese nombre")
    # Reasignar el duenio es privilegio del admin: si el duenio pudiera, se autoasignaria
    # sedes ajenas.
    duenio_id = cuerpo.duenio_id if auth.es_admin(usuario) else fila["duenio_id"]
    db.ejecutar(
        "UPDATE sedes SET nombre = ?, direccion = ?, ciudad = ?, telefono = ?, duenio_id = ?,"
        " activa = ? WHERE id = ?",
        (cuerpo.nombre.strip(), cuerpo.direccion, cuerpo.ciudad, cuerpo.telefono, duenio_id,
         1 if cuerpo.activa else 0, sede_id),
    )
    db.auditar(usuario["id"], "edicion-sede", f"sede:{sede_id}")
    return ser.sede(db.uno("SELECT * FROM sedes WHERE id = ?", (sede_id,)))


@router.delete("/{sede_id}", status_code=204)
def borrar(sede_id: int, usuario: dict = Depends(auth.actual)):
    """Baja de sede. Rebota si todavia tiene canchas: primero se dan de baja las canchas."""
    auth.exigir_rol(usuario, "admin")
    fila = db.uno("SELECT * FROM sedes WHERE id = ?", (sede_id,))
    if fila is None:
        raise NoEncontrado("no existe esa sede")
    canchas = db.escalar("SELECT COUNT(*) FROM canchas WHERE sede_id = ?", (sede_id,))
    if canchas:
        raise Conflicto(f"la sede todavia tiene {canchas} canchas")
    db.ejecutar("DELETE FROM sedes WHERE id = ?", (sede_id,))
    db.auditar(usuario["id"], "baja-sede", f"sede:{sede_id}")
    return Response(status_code=204)


@router.get("/{sede_id}/canchas")
def canchas_de_la_sede(sede_id: int, estado: str | None = Query(default=None)):
    """Canchas que pertenecen a la sede."""
    if db.uno("SELECT id FROM sedes WHERE id = ?", (sede_id,)) is None:
        raise NoEncontrado("no existe esa sede")
    condiciones, parametros = ["sede_id = ?"], [sede_id]
    if estado is not None:
        from ..esquemas import ESTADOS_CANCHA
        from ..validacion import validar_enumerado

        condiciones.append("estado = ?")
        parametros.append(validar_enumerado(estado, ESTADOS_CANCHA, "estado"))
    filas = db.consultar(
        f"SELECT * FROM canchas WHERE {' AND '.join(condiciones)} ORDER BY id",
        tuple(parametros),
    )
    return {"datos": [ser.cancha(f) for f in filas], "total": len(filas)}
