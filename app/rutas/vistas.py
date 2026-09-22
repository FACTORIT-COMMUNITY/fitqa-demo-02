"""Pantallas HTML.

El front es deliberadamente pobre: plantillas Jinja servidas desde el mismo proceso que
consumen la propia API con `fetch`. No hay bundler, ni framework, ni build. Lo que importa
es que exista una superficie de navegador para probar, no que sea linda.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .sistema import VERSION

PLANTILLAS = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "plantillas"))

router = APIRouter(tags=["vistas"], include_in_schema=False)


def _render(peticion: Request, plantilla: str, titulo: str, **extra) -> HTMLResponse:
    contexto = {"request": peticion, "titulo": titulo, "version": VERSION}
    contexto.update(extra)
    return PLANTILLAS.TemplateResponse(plantilla, contexto)


@router.get("/", response_class=HTMLResponse)
def portada(peticion: Request):
    """Vitrina: sedes y canchas disponibles."""
    return _render(peticion, "portada.html", "Canchas del barrio")


@router.get("/ui/login", response_class=HTMLResponse)
def login(peticion: Request):
    """Formulario de inicio de sesion. Guarda el token en `sessionStorage`."""
    return _render(peticion, "login.html", "Iniciar sesion")


@router.get("/ui/canchas", response_class=HTMLResponse)
def canchas(peticion: Request):
    """Listado de canchas con filtros y orden."""
    return _render(peticion, "canchas.html", "Canchas")


@router.get("/ui/reservas", response_class=HTMLResponse)
def reservas(peticion: Request):
    """Mis reservas y el formulario para pedir una nueva."""
    return _render(peticion, "reservas.html", "Reservas")


@router.get("/ui/agenda", response_class=HTMLResponse)
def agenda(peticion: Request):
    """Grilla horaria del dia, para duenio y admin."""
    return _render(peticion, "agenda.html", "Agenda")


@router.get("/ui/panel", response_class=HTMLResponse)
def panel(peticion: Request):
    """Numeros de gestion, para duenio y admin."""
    return _render(peticion, "panel.html", "Panel")
