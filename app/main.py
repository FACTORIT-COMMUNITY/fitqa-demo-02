"""Armado de la aplicacion.

Aca se monta cada router y se normalizan los errores. FastAPI responde
`{"detail": ...}` por defecto y el sistema promete `{"error": ...}`; los manejadores de
abajo existen para que no convivan dos formatos de error en la misma API.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as ErrorHTTP

from . import db
from .errores import ErrorDominio
from .rutas import (
    autenticacion,
    canchas,
    equipos,
    horarios,
    panel,
    resenas,
    reservas,
    sedes,
    sistema,
    usuarios,
    vistas,
)

registro = logging.getLogger("canchas")

app = FastAPI(
    title="Reserva de canchas",
    version=sistema.VERSION,
    description=(
        "API de reserva de canchas de futbol 5 y 7. Autenticacion por token opaco en "
        "`Authorization: Bearer <token>`, tres roles (jugador, duenio, admin) y reservas "
        "con estado."
    ),
)

app.include_router(sistema.router)
app.include_router(autenticacion.router)
app.include_router(usuarios.router)
app.include_router(sedes.router)
app.include_router(canchas.router)
app.include_router(horarios.router)
app.include_router(reservas.router)
app.include_router(equipos.router)
app.include_router(resenas.router)
app.include_router(panel.router)
app.include_router(vistas.router)


@app.on_event("startup")
def preparar_base() -> None:
    """Crea y siembra la base antes de atender la primera peticion."""
    db.conexion()


@app.exception_handler(ErrorDominio)
def error_de_dominio(peticion: Request, exc: ErrorDominio) -> JSONResponse:
    return JSONResponse(status_code=exc.estado, content=exc.cuerpo())


@app.exception_handler(RequestValidationError)
def error_de_validacion(peticion: Request, exc: RequestValidationError) -> JSONResponse:
    """Traduce la validacion de Pydantic al formato de error del sistema."""
    detalles = []
    for e in exc.errors():
        campo = ".".join(str(p) for p in e.get("loc", []) if p not in ("body", "query"))
        detalles.append({"campo": campo or "cuerpo", "problema": e.get("msg", "invalido")})
    return JSONResponse(
        status_code=400, content={"error": "datos invalidos", "detalles": detalles}
    )


@app.exception_handler(ErrorHTTP)
def error_http(peticion: Request, exc: ErrorHTTP) -> JSONResponse:
    """Los 404 de ruta inexistente y los 405 de metodo equivocado pasan por aca."""
    mensaje = exc.detail if isinstance(exc.detail, str) else "error"
    if exc.status_code == 404:
        mensaje = "recurso inexistente"
    return JSONResponse(status_code=exc.status_code, content={"error": mensaje})


@app.exception_handler(Exception)
def error_no_previsto(peticion: Request, exc: Exception) -> JSONResponse:
    """Ultimo recorte: nada que se escape deberia llegar al cliente como traza."""
    registro.exception("error no previsto en %s %s", peticion.method, peticion.url.path)
    return JSONResponse(status_code=500, content={"error": "error interno"})
