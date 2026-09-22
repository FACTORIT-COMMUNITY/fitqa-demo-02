"""Reservas: el flujo con estado del sistema.

Una reserva nace `pendiente` y desde ahi solo puede moverse por las transiciones de
`TRANSICIONES`. Cada cambio deja una fila en `reserva_eventos`, que es lo que devuelve
`GET /reservas/{id}/historial`.

    pendiente ──┬─> confirmada ──┬─> completada
                │                ├─> no-show
                └─> cancelada <──┘

`cancelada`, `completada` y `no-show` son terminales.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from .. import auth, db, serializadores as ser
from ..errores import Conflicto, DatosInvalidos, NoEncontrado, SinPermiso
from ..esquemas import (
    ESTADOS_RESERVA,
    ORDEN_RESERVAS,
    MotivoCancelacion,
    ReservaEditada,
    ReservaNueva,
)
from ..validacion import (
    dia_de_semana,
    validar_direccion,
    validar_enumerado,
    validar_fecha,
    validar_orden,
    validar_paginacion,
    validar_rango,
)

router = APIRouter(prefix="/reservas", tags=["reservas"])

TRANSICIONES: dict[str, tuple[str, ...]] = {
    "pendiente": ("confirmada", "cancelada"),
    "confirmada": ("cancelada", "completada", "no-show"),
    "cancelada": (),
    "completada": (),
    "no-show": (),
}

SELECT_RESERVA = (
    "SELECT r.*, c.nombre AS cancha_nombre, u.nombre AS usuario_nombre FROM reservas r"
    " JOIN canchas c ON c.id = r.cancha_id"
    " JOIN usuarios u ON u.id = r.usuario_id"
)


def _buscar(reserva_id: int) -> dict:
    fila = db.uno(SELECT_RESERVA + " WHERE r.id = ?", (reserva_id,))
    if fila is None:
        raise NoEncontrado("no existe esa reserva")
    return fila


def _transicionar(reserva: dict, nuevo: str, usuario: dict) -> dict:
    """Aplica un cambio de estado validandolo contra la tabla de transiciones."""
    actual = reserva["estado"]
    if nuevo not in TRANSICIONES[actual]:
        raise Conflicto(f"una reserva {actual} no puede pasar a {nuevo}")
    db.ejecutar("UPDATE reservas SET estado = ? WHERE id = ?", (nuevo, reserva["id"]))
    db.ejecutar(
        "INSERT INTO reserva_eventos"
        " (reserva_id, estado_anterior, estado_nuevo, usuario_id, creado_en) VALUES (?,?,?,?,?)",
        (reserva["id"], actual, nuevo, usuario["id"], db.AHORA),
    )
    db.auditar(usuario["id"], f"reserva-{nuevo}", f"reserva:{reserva['id']}")
    return _buscar(reserva["id"])


def _puede_gestionar(usuario: dict, reserva: dict) -> bool:
    """Gestiona la reserva quien la hizo, quien administra la cancha, o el admin."""
    if auth.es_admin(usuario) or reserva["usuario_id"] == usuario["id"]:
        return True
    return auth.administra_cancha(usuario, reserva["cancha_id"])


@router.get("")
def listar(
    cancha_id: int | None = Query(default=None),
    usuario_id: int | None = Query(default=None),
    estado: str | None = Query(default=None),
    fecha: str | None = Query(default=None),
    orden: str | None = Query(default=None),
    direccion: str | None = Query(default=None),
    limite: int | None = Query(default=None),
    desde: int | None = Query(default=None),
    usuario: dict = Depends(auth.actual),
):
    """Listado paginado. Un jugador solo ve las suyas; duenio y admin ven todas."""
    limite, desde = validar_paginacion(limite, desde)
    orden = validar_orden(orden, ORDEN_RESERVAS, "fecha")
    direccion = validar_direccion(direccion)

    condiciones, parametros = [], []
    if usuario["rol"] == "jugador":
        condiciones.append("r.usuario_id = ?")
        parametros.append(usuario["id"])
    elif usuario_id is not None:
        condiciones.append("r.usuario_id = ?")
        parametros.append(usuario_id)
    if cancha_id is not None:
        condiciones.append("r.cancha_id = ?")
        parametros.append(cancha_id)
    if fecha is not None:
        condiciones.append("r.fecha = ?")
        parametros.append(validar_fecha(fecha))

    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = db.escalar(f"SELECT COUNT(*) FROM reservas r{where}", tuple(parametros))

    if estado is not None:
        condiciones.append("r.estado = ?")
        parametros.append(validar_enumerado(estado, ESTADOS_RESERVA, "estado"))
        where = " WHERE " + " AND ".join(condiciones)

    filas = db.consultar(
        f"{SELECT_RESERVA}{where} ORDER BY r.{orden} {direccion.upper()}, r.hora_inicio"
        " LIMIT ? OFFSET ?",
        tuple(parametros) + (limite, desde),
    )
    return ser.pagina([ser.reserva(f) for f in filas], total, limite, desde)


@router.post("", status_code=201)
def crear(cuerpo: ReservaNueva, usuario: dict = Depends(auth.actual)):
    """Crea una reserva en estado `pendiente`.

    Rebota si la cancha no esta habilitada, si la franja no existe en el horario de ese dia
    o si choca con otra reserva de la misma cancha, fecha y rango.
    """
    cancha = db.uno("SELECT * FROM canchas WHERE id = ?", (cuerpo.cancha_id,))
    if cancha is None:
        raise NoEncontrado("no existe esa cancha")
    if cancha["estado"] != "habilitada":
        raise Conflicto(f"la cancha esta {cancha['estado']}")

    fecha = validar_fecha(cuerpo.fecha)
    inicio, fin = validar_rango(cuerpo.hora_inicio, cuerpo.hora_fin)

    # Reservar por otro es privilegio de quien administra la cancha.
    titular = usuario["id"]
    if cuerpo.usuario_id is not None and cuerpo.usuario_id != usuario["id"]:
        if not auth.administra_cancha(usuario, cuerpo.cancha_id):
            raise SinPermiso("no podes reservar a nombre de otro usuario")
        if db.uno("SELECT id FROM usuarios WHERE id = ?", (cuerpo.usuario_id,)) is None:
            raise NoEncontrado("no existe ese usuario")
        titular = cuerpo.usuario_id

    if cuerpo.equipo_id is not None:
        if db.uno("SELECT id FROM equipos WHERE id = ?", (cuerpo.equipo_id,)) is None:
            raise NoEncontrado("no existe ese equipo")

    dia = dia_de_semana(fecha)
    franja = db.uno(
        "SELECT id FROM horarios WHERE cancha_id = ? AND dia_semana = ?"
        " AND hora_inicio = ? AND hora_fin = ? AND activo = 1",
        (cuerpo.cancha_id, dia, inicio, fin),
    )
    if franja is None:
        raise Conflicto("esa franja no esta en el horario de la cancha para ese dia")

    # Choque con otra reserva de la misma cancha y fecha.
    ocupadas = db.consultar(
        "SELECT id, hora_inicio, hora_fin FROM reservas"
        " WHERE cancha_id = ? AND fecha = ? AND estado = 'confirmada'",
        (cuerpo.cancha_id, fecha),
    )
    for r in ocupadas:
        if inicio < r["hora_fin"] and fin > r["hora_inicio"]:
            raise Conflicto(f"la franja choca con la reserva {r['id']}")

    reserva_id = db.ejecutar(
        "INSERT INTO reservas"
        " (cancha_id, usuario_id, equipo_id, fecha, hora_inicio, hora_fin, estado, nota,"
        "  creada_en) VALUES (?,?,?,?,?,?,'pendiente',?,?)",
        (cuerpo.cancha_id, titular, cuerpo.equipo_id, fecha, inicio, fin, cuerpo.nota,
         db.AHORA),
    )
    db.ejecutar(
        "INSERT INTO reserva_eventos"
        " (reserva_id, estado_anterior, estado_nuevo, usuario_id, creado_en) VALUES (?,?,?,?,?)",
        (reserva_id, None, "pendiente", usuario["id"], db.AHORA),
    )
    db.auditar(usuario["id"], "alta-reserva", f"reserva:{reserva_id}")
    return ser.reserva(_buscar(reserva_id))


@router.get("/agenda")
def agenda(
    fecha: str = Query(...),
    sede_id: int | None = Query(default=None),
    usuario: dict = Depends(auth.actual),
):
    """Grilla del dia: por cada cancha, sus franjas con quien las ocupa.

    Se declara antes que `/{reserva_id}` a proposito: si estuviera despues, `agenda` se
    leeria como un id y la ruta nunca se alcanzaria.
    """
    auth.al_menos(usuario, "duenio")
    fecha = validar_fecha(fecha)
    dia = dia_de_semana(fecha)

    parametros: list = []
    where = ""
    if sede_id is not None:
        if db.uno("SELECT id FROM sedes WHERE id = ?", (sede_id,)) is None:
            raise NoEncontrado("no existe esa sede")
        where = " WHERE sede_id = ?"
        parametros.append(sede_id)
    canchas = db.consultar(f"SELECT * FROM canchas{where} ORDER BY id", tuple(parametros))
    if not auth.es_admin(usuario):
        canchas = [c for c in canchas if auth.administra_sede(usuario, c["sede_id"])]

    grilla = []
    for cancha in canchas:
        franjas = db.consultar(
            "SELECT hora_inicio, hora_fin FROM horarios"
            " WHERE cancha_id = ? AND dia_semana = ? AND activo = 1 ORDER BY hora_inicio",
            (cancha["id"], dia),
        )
        reservas = db.consultar(
            SELECT_RESERVA + " WHERE r.cancha_id = ? AND r.fecha = ?", (cancha["id"], fecha)
        )
        celdas = []
        for f in franjas:
            ocupa = next(
                (
                    r
                    for r in reservas
                    if r["hora_inicio"] == f["hora_inicio"]
                    and r["estado"] in ("pendiente", "confirmada")
                ),
                None,
            )
            celdas.append(
                {
                    "hora_inicio": f["hora_inicio"],
                    "hora_fin": f["hora_fin"],
                    "reserva": ser.reserva(ocupa) if ocupa else None,
                }
            )
        grilla.append(
            {"cancha_id": cancha["id"], "cancha": cancha["nombre"], "franjas": celdas}
        )
    return {"fecha": fecha, "dia_semana": dia, "canchas": grilla}


@router.get("/{reserva_id}")
def detalle(reserva_id: int, usuario: dict = Depends(auth.actual)):
    """Una reserva."""
    fila = _buscar(reserva_id)
    return ser.reserva(fila)


@router.put("/{reserva_id}")
def editar(reserva_id: int, cuerpo: ReservaEditada, usuario: dict = Depends(auth.actual)):
    """Mueve una reserva de fecha u horario. Solo mientras siga `pendiente`."""
    fila = _buscar(reserva_id)
    if not _puede_gestionar(usuario, fila):
        raise SinPermiso("esa reserva no es tuya")
    if fila["estado"] != "pendiente":
        raise Conflicto(f"una reserva {fila['estado']} ya no se puede mover")

    fecha = validar_fecha(cuerpo.fecha)
    inicio, fin = validar_rango(cuerpo.hora_inicio, cuerpo.hora_fin)
    dia = dia_de_semana(fecha)
    franja = db.uno(
        "SELECT id FROM horarios WHERE cancha_id = ? AND dia_semana = ?"
        " AND hora_inicio = ? AND hora_fin = ? AND activo = 1",
        (fila["cancha_id"], dia, inicio, fin),
    )
    if franja is None:
        raise Conflicto("esa franja no esta en el horario de la cancha para ese dia")
    ocupadas = db.consultar(
        "SELECT id, hora_inicio, hora_fin FROM reservas"
        " WHERE cancha_id = ? AND fecha = ? AND id <> ?"
        " AND estado IN ('pendiente','confirmada')",
        (fila["cancha_id"], fecha, reserva_id),
    )
    for r in ocupadas:
        if inicio < r["hora_fin"] and fin > r["hora_inicio"]:
            raise Conflicto(f"la franja choca con la reserva {r['id']}")
    if cuerpo.equipo_id is not None:
        if db.uno("SELECT id FROM equipos WHERE id = ?", (cuerpo.equipo_id,)) is None:
            raise NoEncontrado("no existe ese equipo")

    db.ejecutar(
        "UPDATE reservas SET fecha = ?, hora_inicio = ?, hora_fin = ?, equipo_id = ?,"
        " nota = ? WHERE id = ?",
        (fecha, inicio, fin, cuerpo.equipo_id, cuerpo.nota, reserva_id),
    )
    db.auditar(usuario["id"], "edicion-reserva", f"reserva:{reserva_id}")
    return ser.reserva(_buscar(reserva_id))


@router.delete("/{reserva_id}", status_code=204)
def borrar(reserva_id: int, usuario: dict = Depends(auth.actual)):
    """Saca la reserva del sistema.

    Es idempotente a proposito: borrar una reserva que ya no esta tambien devuelve 204. Ver
    las notas de diseno del README.
    """
    fila = db.uno("SELECT * FROM reservas WHERE id = ?", (reserva_id,))
    if fila is None:
        return Response(status_code=204)
    if not _puede_gestionar(usuario, fila):
        raise SinPermiso("esa reserva no es tuya")
    if fila["estado"] == "confirmada":
        raise Conflicto("una reserva confirmada se cancela, no se borra")
    db.ejecutar("DELETE FROM reserva_eventos WHERE reserva_id = ?", (reserva_id,))
    db.ejecutar("DELETE FROM reservas WHERE id = ?", (reserva_id,))
    db.auditar(usuario["id"], "baja-reserva", f"reserva:{reserva_id}")
    return Response(status_code=204)


@router.post("/{reserva_id}/confirmar")
def confirmar(reserva_id: int, usuario: dict = Depends(auth.actual)):
    """Confirma la reserva. La confirma quien administra la cancha, o el admin."""
    fila = _buscar(reserva_id)
    if not auth.es_admin(usuario) and not auth.administra_cancha(usuario, fila["cancha_id"]):
        raise SinPermiso("confirmar es potestad de quien administra la cancha")
    if fila["estado"] in ("completada", "no-show"):
        raise Conflicto(f"una reserva {fila['estado']} no se puede confirmar")
    db.ejecutar("UPDATE reservas SET estado = 'confirmada' WHERE id = ?", (reserva_id,))
    db.ejecutar(
        "INSERT INTO reserva_eventos"
        " (reserva_id, estado_anterior, estado_nuevo, usuario_id, creado_en) VALUES (?,?,?,?,?)",
        (reserva_id, fila["estado"], "confirmada", usuario["id"], db.AHORA),
    )
    db.auditar(usuario["id"], "reserva-confirmada", f"reserva:{reserva_id}")
    return ser.reserva(_buscar(reserva_id))


@router.post("/{reserva_id}/cancelar")
def cancelar(
    reserva_id: int,
    cuerpo: MotivoCancelacion | None = None,
    usuario: dict = Depends(auth.actual),
):
    """Cancela la reserva y libera la franja."""
    fila = _buscar(reserva_id)
    if not _puede_gestionar(usuario, fila):
        raise SinPermiso("esa reserva no es tuya")
    salida = _transicionar(fila, "cancelada", usuario)
    if cuerpo is not None and cuerpo.motivo:
        db.ejecutar("UPDATE reservas SET nota = ? WHERE id = ?", (cuerpo.motivo, reserva_id))
        salida = _buscar(reserva_id)
    return ser.reserva(salida)


@router.post("/{reserva_id}/no-show")
def marcar_no_show(reserva_id: int, usuario: dict = Depends(auth.actual)):
    """Marca que el titular no se presento. Solo sobre una reserva confirmada."""
    fila = _buscar(reserva_id)
    if not auth.es_admin(usuario) and not auth.administra_cancha(usuario, fila["cancha_id"]):
        raise SinPermiso("marcar no-show es potestad de quien administra la cancha")
    return ser.reserva(_transicionar(fila, "no-show", usuario))


@router.post("/{reserva_id}/completar")
def completar(reserva_id: int, usuario: dict = Depends(auth.actual)):
    """Cierra la reserva como jugada. Solo sobre una reserva confirmada."""
    fila = _buscar(reserva_id)
    if not auth.es_admin(usuario) and not auth.administra_cancha(usuario, fila["cancha_id"]):
        raise SinPermiso("completar es potestad de quien administra la cancha")
    return ser.reserva(_transicionar(fila, "completada", usuario))


@router.get("/{reserva_id}/historial")
def historial(reserva_id: int, usuario: dict = Depends(auth.actual)):
    """Los cambios de estado de la reserva, del mas viejo al mas nuevo."""
    fila = _buscar(reserva_id)
    if not _puede_gestionar(usuario, fila):
        raise SinPermiso("esa reserva no es tuya")
    eventos = db.consultar(
        "SELECT * FROM reserva_eventos WHERE reserva_id = ? ORDER BY id", (reserva_id,)
    )
    return {"reserva_id": reserva_id, "datos": [ser.evento(e) for e in eventos],
            "total": len(eventos)}
