"""Panel de gestion: los numeros que mira un duenio.

Todo lo de aca pide rol `duenio` o `admin`. Un duenio ve solo sus sedes; el admin, todo.
Los reportes no guardan nada: se calculan en el momento sobre las tablas.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import auth, db
from ..errores import NoEncontrado
from ..validacion import validar_fecha

router = APIRouter(prefix="/panel", tags=["panel"])


def _canchas_visibles(usuario: dict, sede_id: int | None) -> list[dict]:
    parametros: list = []
    where = ""
    if sede_id is not None:
        if db.uno("SELECT id FROM sedes WHERE id = ?", (sede_id,)) is None:
            raise NoEncontrado("no existe esa sede")
        where = " WHERE sede_id = ?"
        parametros.append(sede_id)
    canchas = db.consultar(f"SELECT * FROM canchas{where} ORDER BY id", tuple(parametros))
    if auth.es_admin(usuario):
        return canchas
    return [c for c in canchas if auth.administra_sede(usuario, c["sede_id"])]


@router.get("/resumen")
def resumen(sede_id: int | None = Query(default=None), usuario: dict = Depends(auth.actual)):
    """Conteos gruesos: canchas, reservas por estado y resenas."""
    auth.al_menos(usuario, "duenio")
    canchas = _canchas_visibles(usuario, sede_id)
    ids = [c["id"] for c in canchas]
    if not ids:
        return {"canchas": 0, "reservas": {}, "resenas": 0, "puntaje_promedio": None}
    marcas = ",".join("?" * len(ids))

    por_estado = db.consultar(
        f"SELECT estado, COUNT(*) AS n FROM reservas WHERE cancha_id IN ({marcas})"
        " GROUP BY estado",
        tuple(ids),
    )
    resenas = db.escalar(
        f"SELECT COUNT(*) FROM resenas WHERE cancha_id IN ({marcas})", tuple(ids)
    )
    promedio = db.escalar(
        f"SELECT AVG(puntaje) FROM resenas WHERE cancha_id IN ({marcas})", tuple(ids)
    )
    return {
        "canchas": len(ids),
        "habilitadas": sum(1 for c in canchas if c["estado"] == "habilitada"),
        "reservas": {f["estado"]: f["n"] for f in por_estado},
        "resenas": resenas,
        "puntaje_promedio": round(promedio, 2) if promedio is not None else None,
    }


@router.get("/ocupacion")
def ocupacion(
    fecha: str = Query(...),
    sede_id: int | None = Query(default=None),
    usuario: dict = Depends(auth.actual),
):
    """Porcentaje de franjas ocupadas por cancha para una fecha.

    El denominador son las franjas configuradas para ese dia de la semana; el numerador,
    las reservas que efectivamente ocupan la cancha.
    """
    auth.al_menos(usuario, "duenio")
    fecha = validar_fecha(fecha)
    from ..validacion import dia_de_semana

    dia = dia_de_semana(fecha)
    salida = []
    for cancha in _canchas_visibles(usuario, sede_id):
        franjas = db.escalar(
            "SELECT COUNT(*) FROM horarios WHERE cancha_id = ? AND dia_semana = ? AND activo = 1",
            (cancha["id"], dia),
        )
        reservadas = db.escalar(
            "SELECT COUNT(*) FROM reservas WHERE cancha_id = ? AND fecha = ?",
            (cancha["id"], fecha),
        )
        salida.append(
            {
                "cancha_id": cancha["id"],
                "cancha": cancha["nombre"],
                "franjas": franjas,
                "reservadas": reservadas,
                "ocupacion": round(reservadas / franjas * 100, 1) if franjas else 0.0,
            }
        )
    return {"fecha": fecha, "dia_semana": dia, "datos": salida}


@router.get("/cancelaciones")
def cancelaciones(
    sede_id: int | None = Query(default=None), usuario: dict = Depends(auth.actual)
):
    """Cancelaciones y no-shows por cancha, con su tasa sobre el total de reservas."""
    auth.al_menos(usuario, "duenio")
    salida = []
    for cancha in _canchas_visibles(usuario, sede_id):
        total = db.escalar(
            "SELECT COUNT(*) FROM reservas WHERE cancha_id = ?", (cancha["id"],)
        )
        canceladas = db.escalar(
            "SELECT COUNT(*) FROM reservas WHERE cancha_id = ? AND estado = 'cancelada'",
            (cancha["id"],),
        )
        no_show = db.escalar(
            "SELECT COUNT(*) FROM reservas WHERE cancha_id = ? AND estado = 'no-show'",
            (cancha["id"],),
        )
        salida.append(
            {
                "cancha_id": cancha["id"],
                "cancha": cancha["nombre"],
                "reservas": total,
                "canceladas": canceladas,
                "no_show": no_show,
                "tasa": round((canceladas + no_show) / total * 100, 1) if total else 0.0,
            }
        )
    return {"datos": salida}


@router.get("/ranking-canchas")
def ranking(
    sede_id: int | None = Query(default=None),
    limite: int = Query(default=10, ge=1, le=50),
    usuario: dict = Depends(auth.actual),
):
    """Canchas ordenadas por cantidad de reservas vigentes o jugadas."""
    auth.al_menos(usuario, "duenio")
    salida = []
    for cancha in _canchas_visibles(usuario, sede_id):
        usos = db.escalar(
            "SELECT COUNT(*) FROM reservas WHERE cancha_id = ?"
            " AND estado IN ('pendiente','confirmada','completada')",
            (cancha["id"],),
        )
        puntaje = db.escalar(
            "SELECT AVG(puntaje) FROM resenas WHERE cancha_id = ?", (cancha["id"],)
        )
        salida.append(
            {
                "cancha_id": cancha["id"],
                "cancha": cancha["nombre"],
                "reservas": usos,
                "puntaje_promedio": round(puntaje, 2) if puntaje is not None else None,
            }
        )
    salida.sort(key=lambda f: f["reservas"], reverse=True)
    return {"datos": salida[:limite]}
