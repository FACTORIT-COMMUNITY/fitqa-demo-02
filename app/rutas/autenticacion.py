"""Registro, inicio y cierre de sesion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response

from .. import auth, db, serializadores as ser
from ..errores import Conflicto, DatosInvalidos, NoAutenticado
from ..esquemas import CambioClave, Credenciales, Registro
from ..validacion import validar_email

router = APIRouter(prefix="/auth", tags=["autenticacion"])


@router.post("/registro", status_code=201)
def registrar(cuerpo: Registro):
    """Alta publica. Todo registro publico nace con rol `jugador`; para crear un duenio o
    un admin hay que pasar por `POST /usuarios`, que pide sesion de admin."""
    email = validar_email(cuerpo.email)
    if db.uno("SELECT id FROM usuarios WHERE email = ?", (email,)):
        raise Conflicto("ese email ya esta registrado")
    usuario_id = db.ejecutar(
        "INSERT INTO usuarios (nombre, email, clave_hash, rol, telefono, activo, creado_en)"
        " VALUES (?,?,?,?,?,?,?)",
        (cuerpo.nombre.strip(), email, db.hashear(cuerpo.clave), "jugador",
         cuerpo.telefono, 1, db.AHORA),
    )
    db.auditar(usuario_id, "registro", f"usuario:{usuario_id}")
    fila = db.uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    return ser.usuario(fila)


@router.post("/login")
def iniciar_sesion(cuerpo: Credenciales):
    """Devuelve un token opaco para mandar en `Authorization: Bearer <token>`.

    El email inexistente y la clave equivocada dan exactamente la misma respuesta. Es
    deliberado y esta explicado en las notas de diseno del README.
    """
    email = (cuerpo.email or "").strip().lower()
    usuario = db.uno("SELECT * FROM usuarios WHERE email = ?", (email,))
    if usuario is None or usuario["clave_hash"] != db.hashear(cuerpo.clave or ""):
        raise NoAutenticado("email o clave incorrectos")
    if not usuario["activo"]:
        raise NoAutenticado("email o clave incorrectos")
    token = auth.emitir_token(usuario["id"])
    db.auditar(usuario["id"], "login", f"usuario:{usuario['id']}")
    return {"token": token, "usuario": ser.usuario(usuario)}


@router.post("/logout", status_code=204)
def cerrar_sesion(authorization: str | None = Header(default=None)):
    """Borra la sesion. Es idempotente: cerrar una sesion ya cerrada tambien da 204."""
    token = (authorization or "").split(None, 1)
    if len(token) == 2 and token[0].lower() == "bearer":
        auth.revocar_token(token[1].strip())
    return Response(status_code=204)


@router.get("/yo")
def quien_soy(usuario: dict = Depends(auth.actual)):
    """El usuario de la sesion actual."""
    return ser.usuario(usuario)


@router.put("/password", status_code=204)
def cambiar_clave(cuerpo: CambioClave, usuario: dict = Depends(auth.actual)):
    """Cambia la clave propia e invalida todas las sesiones, incluida la que hizo el cambio."""
    if usuario["clave_hash"] != db.hashear(cuerpo.clave_actual or ""):
        raise NoAutenticado("la clave actual no coincide")
    if cuerpo.clave_nueva == cuerpo.clave_actual:
        raise DatosInvalidos(
            detalles=[{"campo": "clave_nueva", "problema": "tiene que ser distinta de la actual"}]
        )
    db.ejecutar(
        "UPDATE usuarios SET clave_hash = ? WHERE id = ?",
        (db.hashear(cuerpo.clave_nueva), usuario["id"]),
    )
    auth.revocar_sesiones_de(usuario["id"])
    db.auditar(usuario["id"], "cambio-clave", f"usuario:{usuario['id']}")
    return Response(status_code=204)
