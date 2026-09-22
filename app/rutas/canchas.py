"""Canchas: el recurso que se reserva."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from .. import auth, db, serializadores as ser
from ..errores import Conflicto, DatosInvalidos, NoEncontrado
from ..esquemas import (
    ESTADOS_CANCHA,
    ORDEN_CANCHAS,
    SUPERFICIES,
    TIPOS_CANCHA,
    CambioEstadoCancha,
    CanchaEditada,
    CanchaNueva,
)
from ..validacion import (
    dia_de_semana,
    validar_direccion,
    validar_enumerado,
    validar_fecha,
    validar_orden,
    validar_paginacion,
)

router = APIRouter(prefix="/canchas", tags=["canchas"])


@router.get("")
def listar(
    sede_id: int | None = Query(default=None),
    tipo: str | None = Query(default=None),
    techada: bool | None = Query(default=None),
    estado: str | None = Query(default=None),
    precio_max: int | None = Query(default=None),
    orden: str | None = Query(default=None),
    direccion: str | None = Query(default=None),
    limite: int | None = Query(default=None),
    desde: int | None = Query(default=None),
):
    """Listado publico de canchas, con filtros y orden."""
    limite, desde = validar_paginacion(limite, desde)
    orden = validar_orden(orden, ORDEN_CANCHAS, "id")
    direccion = validar_direccion(direccion)

    condiciones, parametros = [], []
    if sede_id is not None:
        condiciones.append("sede_id = ?")
        parametros.append(sede_id)
    if tipo is not None:
        condiciones.append("tipo = ?")
        parametros.append(validar_enumerado(tipo, TIPOS_CANCHA, "tipo"))
    if techada is not None:
        condiciones.append("techada = ?")
        parametros.append(1 if techada else 0)
    if estado is not None:
        condiciones.append("estado = ?")
        parametros.append(validar_enumerado(estado, ESTADOS_CANCHA, "estado"))
    if precio_max is not None:
        if precio_max < 0:
            raise DatosInvalidos(
                detalles=[{"campo": "precio_max", "problema": "no puede ser negativo"}]
            )
        condiciones.append("precio_hora <= ?")
        parametros.append(precio_max)
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

    filas = db.consultar(f"SELECT * FROM canchas{where}", tuple(parametros))
    total = len(filas)
    # El orden se resuelve en Python y no en SQL porque `orden` puede apuntar a una columna
    # calculada. La clave se pasa por `str` para que una columna con nulos no rompa la
    # comparacion.
    filas.sort(key=lambda f: str(f[orden] or ""), reverse=(direccion == "desc"))
    pagina = filas[desde : desde + limite]
    return ser.pagina([ser.cancha(f) for f in pagina], total, limite, desde)


@router.post("", status_code=201)
def crear(cuerpo: CanchaNueva, usuario: dict = Depends(auth.actual)):
    """Alta de cancha dentro de una sede."""
    sede = db.uno("SELECT * FROM sedes WHERE id = ?", (cuerpo.sede_id,))
    if sede is None:
        raise NoEncontrado("no existe esa sede")
    auth.exigir_sede(usuario, cuerpo.sede_id)
    tipo = validar_enumerado(cuerpo.tipo, TIPOS_CANCHA, "tipo")
    superficie = validar_enumerado(cuerpo.superficie, SUPERFICIES, "superficie")
    choque = db.uno(
        "SELECT id FROM canchas WHERE sede_id = ? AND nombre = ?",
        (cuerpo.sede_id, cuerpo.nombre.strip()),
    )
    if choque:
        raise Conflicto("ya hay una cancha con ese nombre en la sede")
    cancha_id = db.ejecutar(
        "INSERT INTO canchas (sede_id, nombre, tipo, superficie, techada, precio_hora, estado)"
        " VALUES (?,?,?,?,?,?,'habilitada')",
        (cuerpo.sede_id, cuerpo.nombre.strip(), tipo, superficie, 1 if cuerpo.techada else 0,
         cuerpo.precio_hora),
    )
    db.auditar(usuario["id"], "alta-cancha", f"cancha:{cancha_id}")
    return ser.cancha(db.uno("SELECT * FROM canchas WHERE id = ?", (cancha_id,)))


@router.get("/{cancha_id}")
def detalle(cancha_id: int):
    """Una cancha."""
    fila = db.uno("SELECT * FROM canchas WHERE id = ?", (cancha_id,))
    if fila is None:
        raise NoEncontrado("no existe esa cancha")
    return ser.cancha(fila)


@router.put("/{cancha_id}")
def editar(cancha_id: int, cuerpo: CanchaEditada, usuario: dict = Depends(auth.actual)):
    """Actualiza los datos de la cancha. No cambia el estado: para eso esta el PATCH."""
    fila = db.uno("SELECT * FROM canchas WHERE id = ?", (cancha_id,))
    if fila is None:
        raise NoEncontrado("no existe esa cancha")
    auth.exigir_cancha(usuario, cancha_id)
    if cuerpo.sede_id != fila["sede_id"]:
        if db.uno("SELECT id FROM sedes WHERE id = ?", (cuerpo.sede_id,)) is None:
            raise NoEncontrado("no existe esa sede")
        auth.exigir_sede(usuario, cuerpo.sede_id)
    tipo = validar_enumerado(cuerpo.tipo, TIPOS_CANCHA, "tipo")
    superficie = validar_enumerado(cuerpo.superficie, SUPERFICIES, "superficie")
    choque = db.uno(
        "SELECT id FROM canchas WHERE sede_id = ? AND nombre = ? AND id <> ?",
        (cuerpo.sede_id, cuerpo.nombre.strip(), cancha_id),
    )
    if choque:
        raise Conflicto("ya hay una cancha con ese nombre en la sede")
    db.ejecutar(
        "UPDATE canchas SET sede_id = ?, nombre = ?, tipo = ?, superficie = ?, techada = ?,"
        " precio_hora = ? WHERE id = ?",
        (cuerpo.sede_id, cuerpo.nombre.strip(), tipo, superficie, 1 if cuerpo.techada else 0,
         cuerpo.precio_hora, cancha_id),
    )
    db.auditar(usuario["id"], "edicion-cancha", f"cancha:{cancha_id}")
    return ser.cancha(db.uno("SELECT * FROM canchas WHERE id = ?", (cancha_id,)))


@router.delete("/{cancha_id}", status_code=204)
def borrar(cancha_id: int, usuario: dict = Depends(auth.actual)):
    """Borra la cancha. Rebota si tiene reservas vigentes (pendientes o confirmadas):
    borrarla las dejaria huerfanas."""
    fila = db.uno("SELECT * FROM canchas WHERE id = ?", (cancha_id,))
    if fila is None:
        raise NoEncontrado("no existe esa cancha")
    auth.exigir_cancha(usuario, cancha_id)
    vigentes = db.escalar(
        "SELECT COUNT(*) FROM reservas WHERE cancha_id = ?"
        " AND estado IN ('pendiente','confirmada')",
        (cancha_id,),
    )
    if vigentes:
        raise Conflicto(f"la cancha tiene {vigentes} reservas vigentes")
    db.ejecutar("DELETE FROM horarios WHERE cancha_id = ?", (cancha_id,))
    db.ejecutar("DELETE FROM canchas WHERE id = ?", (cancha_id,))
    db.auditar(usuario["id"], "baja-cancha", f"cancha:{cancha_id}")
    return Response(status_code=204)


@router.patch("/{cancha_id}/estado")
def cambiar_estado(
    cancha_id: int, cuerpo: CambioEstadoCancha, usuario: dict = Depends(auth.actual)
):
    """Habilita, pone en mantenimiento o da de baja la cancha."""
    fila = db.uno("SELECT * FROM canchas WHERE id = ?", (cancha_id,))
    if fila is None:
        raise NoEncontrado("no existe esa cancha")
    auth.exigir_cancha(usuario, cancha_id)
    estado = validar_enumerado(cuerpo.estado, ESTADOS_CANCHA, "estado")
    db.ejecutar("UPDATE canchas SET estado = ? WHERE id = ?", (estado, cancha_id))
    db.auditar(usuario["id"], f"estado-{estado}", f"cancha:{cancha_id}")
    return ser.cancha(db.uno("SELECT * FROM canchas WHERE id = ?", (cancha_id,)))


@router.get("/{cancha_id}/disponibilidad")
def disponibilidad(cancha_id: int, fecha: str = Query(...)):
    """Franjas libres y ocupadas de una cancha para una fecha.

    Se arma cruzando los horarios del dia de la semana con las reservas vigentes de esa
    fecha. Una reserva cancelada o con no-show libera la franja.
    """
    if db.uno("SELECT id FROM canchas WHERE id = ?", (cancha_id,)) is None:
        raise NoEncontrado("no existe esa cancha")
    fecha = validar_fecha(fecha)
    dia = dia_de_semana(fecha)

    franjas = db.consultar(
        "SELECT hora_inicio, hora_fin FROM horarios"
        " WHERE cancha_id = ? AND dia_semana = ? AND activo = 1"
        " ORDER BY hora_inicio",
        (cancha_id, dia),
    )
    ocupadas = db.consultar(
        "SELECT hora_inicio, hora_fin FROM reservas"
        " WHERE cancha_id = ? AND fecha = ? AND estado IN ('pendiente','confirmada')",
        (cancha_id, fecha),
    )

    salida = [dict(f, libre=True) for f in franjas]
    # Se recorren las franjas marcando las que chocan con alguna reserva. El rango es
    # semiabierto, asi que dos franjas contiguas no se pisan entre si.
    for i in range(len(salida) - 1):
        franja = salida[i]
        for r in ocupadas:
            if r["hora_inicio"] < franja["hora_fin"] and r["hora_fin"] > franja["hora_inicio"]:
                franja["libre"] = False
                break

    return {
        "cancha_id": cancha_id,
        "fecha": fecha,
        "dia_semana": dia,
        "franjas": salida,
        "libres": sum(1 for f in salida if f["libre"]),
    }


@router.get("/{cancha_id}/reservas")
def reservas_de_la_cancha(
    cancha_id: int,
    fecha: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    usuario: dict = Depends(auth.actual),
):
    """Reservas de una cancha. Es informacion de gestion: la ve quien administra la sede."""
    if db.uno("SELECT id FROM canchas WHERE id = ?", (cancha_id,)) is None:
        raise NoEncontrado("no existe esa cancha")
    auth.exigir_cancha(usuario, cancha_id)
    condiciones, parametros = ["r.cancha_id = ?"], [cancha_id]
    if fecha is not None:
        condiciones.append("r.fecha = ?")
        parametros.append(validar_fecha(fecha))
    if estado is not None:
        from ..esquemas import ESTADOS_RESERVA

        condiciones.append("r.estado = ?")
        parametros.append(validar_enumerado(estado, ESTADOS_RESERVA, "estado"))
    filas = db.consultar(
        "SELECT r.*, c.nombre AS cancha_nombre, u.nombre AS usuario_nombre FROM reservas r"
        " JOIN canchas c ON c.id = r.cancha_id"
        " JOIN usuarios u ON u.id = r.usuario_id"
        f" WHERE {' AND '.join(condiciones)} ORDER BY r.fecha, r.hora_inicio",
        tuple(parametros),
    )
    return {"datos": [ser.reserva(f) for f in filas], "total": len(filas)}
