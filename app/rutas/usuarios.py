"""Administracion de usuarios. Todo lo de aca pide rol admin, salvo el detalle propio."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from .. import auth, db, serializadores as ser
from ..errores import Conflicto, DatosInvalidos, NoEncontrado, SinPermiso
from ..esquemas import (
    ORDEN_USUARIOS,
    ROLES,
    CambioRol,
    UsuarioEditado,
    UsuarioNuevo,
)
from ..validacion import (
    validar_direccion,
    validar_email,
    validar_enumerado,
    validar_orden,
    validar_paginacion,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("")
def listar(
    rol: str | None = Query(default=None),
    activo: bool | None = Query(default=None),
    busqueda: str | None = Query(default=None),
    orden: str | None = Query(default=None),
    direccion: str | None = Query(default=None),
    limite: int | None = Query(default=None),
    desde: int | None = Query(default=None),
    usuario: dict = Depends(auth.actual),
):
    """Listado paginado de usuarios."""
    auth.exigir_rol(usuario, "admin")
    limite, desde = validar_paginacion(limite, desde)
    orden = validar_orden(orden, ORDEN_USUARIOS, "id")
    direccion = validar_direccion(direccion)

    condiciones, parametros = [], []
    if rol is not None:
        condiciones.append("rol = ?")
        parametros.append(validar_enumerado(rol, ROLES, "rol"))
    if activo is not None:
        condiciones.append("activo = ?")
        parametros.append(1 if activo else 0)
    if busqueda:
        condiciones.append("(nombre LIKE ? OR email LIKE ?)")
        parametros += [f"%{busqueda}%", f"%{busqueda}%"]
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

    total = db.escalar(f"SELECT COUNT(*) FROM usuarios{where}", tuple(parametros))
    filas = db.consultar(
        f"SELECT * FROM usuarios{where} ORDER BY {orden} {direccion.upper()} LIMIT ? OFFSET ?",
        tuple(parametros) + (limite, desde),
    )
    return ser.pagina([ser.usuario(f) for f in filas], total, limite, desde)


@router.post("", status_code=201)
def crear(cuerpo: UsuarioNuevo, usuario: dict = Depends(auth.actual)):
    """Alta con rol elegido. Es la unica forma de crear un duenio o un admin."""
    auth.exigir_rol(usuario, "admin")
    email = validar_email(cuerpo.email)
    rol = validar_enumerado(cuerpo.rol, ROLES, "rol")
    if db.uno("SELECT id FROM usuarios WHERE email = ?", (email,)):
        raise Conflicto("ese email ya esta registrado")
    nuevo_id = db.ejecutar(
        "INSERT INTO usuarios (nombre, email, clave_hash, rol, telefono, activo, creado_en)"
        " VALUES (?,?,?,?,?,?,?)",
        (cuerpo.nombre.strip(), email, db.hashear(cuerpo.clave), rol, cuerpo.telefono, 1,
         db.AHORA),
    )
    db.auditar(usuario["id"], "alta-usuario", f"usuario:{nuevo_id}")
    return ser.usuario(db.uno("SELECT * FROM usuarios WHERE id = ?", (nuevo_id,)))


@router.get("/{usuario_id}")
def detalle(usuario_id: int, usuario: dict = Depends(auth.actual)):
    """Un usuario. Cada cual puede ver el propio; el resto, solo el admin."""
    if usuario["id"] != usuario_id:
        auth.exigir_rol(usuario, "admin")
    fila = db.uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    if fila is None:
        raise NoEncontrado("no existe ese usuario")
    return ser.usuario(fila)


@router.put("/{usuario_id}")
def editar(usuario_id: int, cuerpo: UsuarioEditado, usuario: dict = Depends(auth.actual)):
    """Actualiza nombre, email, telefono y estado de alta."""
    if usuario["id"] != usuario_id:
        auth.exigir_rol(usuario, "admin")
    fila = db.uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    if fila is None:
        raise NoEncontrado("no existe ese usuario")
    email = validar_email(cuerpo.email)
    choque = db.uno("SELECT id FROM usuarios WHERE email = ? AND id <> ?", (email, usuario_id))
    if choque:
        raise Conflicto("ese email ya esta registrado")
    activo = cuerpo.activo if auth.es_admin(usuario) else bool(fila["activo"])
    db.ejecutar(
        "UPDATE usuarios SET nombre = ?, email = ?, telefono = ?, activo = ? WHERE id = ?",
        (cuerpo.nombre.strip(), email, cuerpo.telefono, 1 if activo else 0, usuario_id),
    )
    if not activo:
        auth.revocar_sesiones_de(usuario_id)
    db.auditar(usuario["id"], "edicion-usuario", f"usuario:{usuario_id}")
    return ser.usuario(db.uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)))


@router.delete("/{usuario_id}", status_code=204)
def dar_de_baja(usuario_id: int, usuario: dict = Depends(auth.actual)):
    """Baja logica: el usuario queda inactivo y sus sesiones se cortan. No se borra la fila
    porque las reservas historicas siguen apuntando a ella."""
    auth.exigir_rol(usuario, "admin")
    fila = db.uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    if fila is None:
        raise NoEncontrado("no existe ese usuario")
    if usuario["id"] == usuario_id:
        raise Conflicto("un admin no puede darse de baja a si mismo")
    db.ejecutar("UPDATE usuarios SET activo = 0 WHERE id = ?", (usuario_id,))
    auth.revocar_sesiones_de(usuario_id)
    db.auditar(usuario["id"], "baja-usuario", f"usuario:{usuario_id}")
    return Response(status_code=204)


@router.patch("/{usuario_id}/rol")
def cambiar_rol(usuario_id: int, cuerpo: CambioRol, usuario: dict = Depends(auth.actual)):
    """Promueve o degrada. El admin no puede degradarse a si mismo: si lo hiciera y fuera el
    unico, el sistema quedaria sin nadie que pueda administrarlo."""
    auth.exigir_rol(usuario, "admin")
    rol = validar_enumerado(cuerpo.rol, ROLES, "rol")
    fila = db.uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    if fila is None:
        raise NoEncontrado("no existe ese usuario")
    if usuario["id"] == usuario_id and rol != "admin":
        raise Conflicto("un admin no puede quitarse el rol a si mismo")
    db.ejecutar("UPDATE usuarios SET rol = ? WHERE id = ?", (rol, usuario_id))
    db.auditar(usuario["id"], "cambio-rol", f"usuario:{usuario_id}")
    return ser.usuario(db.uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)))


@router.get("/{usuario_id}/reservas")
def reservas_del_usuario(
    usuario_id: int,
    estado: str | None = Query(default=None),
    limite: int | None = Query(default=None),
    desde: int | None = Query(default=None),
    usuario: dict = Depends(auth.actual),
):
    """Reservas de un usuario. Cada cual ve las propias; el admin, las de cualquiera."""
    if usuario["id"] != usuario_id and not auth.es_admin(usuario):
        raise SinPermiso("solo podes ver tus propias reservas")
    if db.uno("SELECT id FROM usuarios WHERE id = ?", (usuario_id,)) is None:
        raise NoEncontrado("no existe ese usuario")
    limite, desde = validar_paginacion(limite, desde)
    condiciones, parametros = ["r.usuario_id = ?"], [usuario_id]
    if estado is not None:
        from ..esquemas import ESTADOS_RESERVA

        condiciones.append("r.estado = ?")
        parametros.append(validar_enumerado(estado, ESTADOS_RESERVA, "estado"))
    where = " WHERE " + " AND ".join(condiciones)
    total = db.escalar(f"SELECT COUNT(*) FROM reservas r{where}", tuple(parametros))
    filas = db.consultar(
        "SELECT r.*, c.nombre AS cancha_nombre, u.nombre AS usuario_nombre FROM reservas r"
        " JOIN canchas c ON c.id = r.cancha_id"
        " JOIN usuarios u ON u.id = r.usuario_id"
        f"{where} ORDER BY r.fecha, r.hora_inicio LIMIT ? OFFSET ?",
        tuple(parametros) + (limite, desde),
    )
    return ser.pagina([ser.reserva(f) for f in filas], total, limite, desde)
