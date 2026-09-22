"""Base de datos del sistema de reservas.

SQLite en memoria: vive en el proceso y no deja archivo. Todo el estado es compartido por
todas las peticiones, asi que cualquier prueba que escriba tiene que llamar antes a
`POST /admin/reset`.

La conexion es una sola y global. `check_same_thread=False` hace falta porque uvicorn
atiende los handlers sincronicos en un pool de hilos, y `_CANDADO` serializa los accesos
para que dos peticiones simultaneas no se pisen a mitad de una transaccion.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from typing import Any

_CONEXION: sqlite3.Connection | None = None
_CANDADO = threading.RLock()


ESQUEMA = """
CREATE TABLE usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT    NOT NULL,
    email       TEXT    NOT NULL UNIQUE,
    clave_hash  TEXT    NOT NULL,
    rol         TEXT    NOT NULL DEFAULT 'jugador',
    telefono    TEXT,
    activo      INTEGER NOT NULL DEFAULT 1,
    creado_en   TEXT    NOT NULL
);

CREATE TABLE sesiones (
    token       TEXT    PRIMARY KEY,
    usuario_id  INTEGER NOT NULL,
    creada_en   TEXT    NOT NULL
);

CREATE TABLE sedes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT    NOT NULL,
    direccion   TEXT    NOT NULL,
    ciudad      TEXT    NOT NULL,
    telefono    TEXT,
    duenio_id   INTEGER,
    activa      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE canchas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sede_id      INTEGER NOT NULL,
    nombre       TEXT    NOT NULL,
    tipo         TEXT    NOT NULL DEFAULT 'futbol5',
    superficie   TEXT    NOT NULL DEFAULT 'sintetico',
    techada      INTEGER NOT NULL DEFAULT 0,
    precio_hora  INTEGER NOT NULL DEFAULT 0,
    estado       TEXT    NOT NULL DEFAULT 'habilitada'
);

CREATE TABLE horarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cancha_id    INTEGER NOT NULL,
    dia_semana   INTEGER NOT NULL,
    hora_inicio  TEXT    NOT NULL,
    hora_fin     TEXT    NOT NULL,
    activo       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE reservas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cancha_id    INTEGER NOT NULL,
    usuario_id   INTEGER NOT NULL,
    equipo_id    INTEGER,
    fecha        TEXT    NOT NULL,
    hora_inicio  TEXT    NOT NULL,
    hora_fin     TEXT    NOT NULL,
    estado       TEXT    NOT NULL DEFAULT 'pendiente',
    nota         TEXT,
    creada_en    TEXT    NOT NULL
);

CREATE TABLE reserva_eventos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reserva_id      INTEGER NOT NULL,
    estado_anterior TEXT,
    estado_nuevo    TEXT    NOT NULL,
    usuario_id      INTEGER,
    creado_en       TEXT    NOT NULL
);

CREATE TABLE equipos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT    NOT NULL UNIQUE,
    capitan_id INTEGER NOT NULL,
    creado_en  TEXT    NOT NULL
);

CREATE TABLE equipo_miembros (
    equipo_id  INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    PRIMARY KEY (equipo_id, usuario_id)
);

CREATE TABLE resenas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cancha_id  INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    puntaje    INTEGER NOT NULL,
    comentario TEXT,
    creada_en  TEXT    NOT NULL
);

CREATE TABLE auditoria (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    accion     TEXT    NOT NULL,
    recurso    TEXT    NOT NULL,
    creado_en  TEXT    NOT NULL
);
"""


def hashear(clave: str) -> str:
    """Hash de contrasena. SHA-256 con sal fija: suficiente para un sistema de demostracion
    y a proposito reproducible, para que la semilla siempre genere los mismos valores."""
    return hashlib.sha256(("canchas:" + clave).encode("utf-8")).hexdigest()


# La semilla es fija y sin fechas relativas: si dependiera de `date.today()`, la misma
# prueba daria distinto segun el dia en que se corra.
USUARIOS_SEMILLA = [
    # nombre, email, clave, rol, telefono, activo
    ("Administrador", "admin@canchas.test", "admin123", "admin", "11-5550-0001", 1),
    ("Roberto Sede", "roberto@canchas.test", "duenio123", "duenio", "11-5550-0002", 1),
    ("Lucia Predio", "lucia@canchas.test", "duenio123", "duenio", "11-5550-0003", 1),
    ("Ana Torres", "ana@canchas.test", "jugador123", "jugador", "11-5550-0010", 1),
    ("Bruno Diaz", "bruno@canchas.test", "jugador123", "jugador", "11-5550-0011", 1),
    ("Carla Gomez", "carla@canchas.test", "jugador123", "jugador", "11-5550-0012", 1),
    ("Diego Ruiz", "diego@canchas.test", "jugador123", "jugador", "11-5550-0013", 1),
    ("Elena Paz", "elena@canchas.test", "jugador123", "jugador", "11-5550-0014", 0),
]

SEDES_SEMILLA = [
    # nombre, direccion, ciudad, telefono, duenio_id, activa
    ("Predio Norte", "Av. Libertador 4500", "Buenos Aires", "11-4444-1000", 2, 1),
    ("Complejo Sur", "Calle Mitre 120", "Avellaneda", "11-4444-2000", 2, 1),
    ("Club Oeste", "Ruta 8 km 32", "San Miguel", "11-4444-3000", 3, 1),
    ("Deportivo Este", "Av. Costanera 900", "Quilmes", "11-4444-4000", 3, 0),
]

CANCHAS_SEMILLA = [
    # sede_id, nombre, tipo, superficie, techada, precio_hora, estado
    (1, "Norte 1", "futbol5", "sintetico", 1, 20000, "habilitada"),
    (1, "Norte 2", "futbol5", "sintetico", 0, 18000, "habilitada"),
    (1, "Norte 3", "futbol7", "sintetico", 0, 100000, "habilitada"),
    (2, "Sur A", "futbol5", "cemento", 0, 9000, "habilitada"),
    (2, "Sur B", "futbol5", "sintetico", 1, 21000, "mantenimiento"),
    (3, "Oeste Central", "futbol7", "natural", 0, 30000, "habilitada"),
    (3, "Oeste Chica", "futbol5", "sintetico", 1, 19500, "habilitada"),
    (4, "Este Unica", "futbol5", "sintetico", 0, 15000, "habilitada"),
]

# Franjas de una hora. dia_semana: 0 = lunes ... 6 = domingo.
HORARIOS_SEMILLA: list[tuple[int, int, str, str, int]] = []
for _cancha in range(1, 9):
    for _dia in range(0, 7):
        for _h in (18, 19, 20, 21, 22):
            HORARIOS_SEMILLA.append((_cancha, _dia, f"{_h:02d}:00", f"{_h + 1:02d}:00", 1))

RESERVAS_SEMILLA = [
    # cancha_id, usuario_id, equipo_id, fecha, hora_inicio, hora_fin, estado, nota
    (1, 4, 1, "2026-10-05", "19:00", "20:00", "confirmada", "Partido semanal"),
    (1, 5, None, "2026-10-05", "21:00", "22:00", "pendiente", None),
    (2, 6, 2, "2026-10-06", "20:00", "21:00", "confirmada", None),
    (3, 4, 1, "2026-10-07", "18:00", "19:00", "cancelada", "Se suspendio por lluvia"),
    (4, 7, None, "2026-10-07", "22:00", "23:00", "confirmada", "Ultima franja"),
    (6, 5, 2, "2026-10-08", "19:00", "20:00", "completada", None),
    (7, 6, None, "2026-10-09", "20:00", "21:00", "no-show", None),
]

EQUIPOS_SEMILLA = [
    ("Los Pibes", 4),
    ("Fulbito FC", 6),
    ("Domingueros", 7),
]

MIEMBROS_SEMILLA = [
    (1, 4),
    (1, 5),
    (1, 7),
    (2, 6),
    (2, 4),
    (3, 7),
]

RESENAS_SEMILLA = [
    (1, 4, 5, "Impecable el cesped y las luces."),
    (1, 5, 4, "Muy buena, pero los vestuarios son chicos."),
    (2, 6, 3, "Zafable. El piso esta gastado."),
    (4, 7, 2, "Cemento y sin techo, se moja todo."),
    (6, 5, 5, "La mejor de la zona."),
]

AHORA = "2026-09-01T10:00:00"


def conexion() -> sqlite3.Connection:
    """Devuelve la conexion global, creandola y sembrandola la primera vez."""
    global _CONEXION
    with _CANDADO:
        if _CONEXION is None:
            _CONEXION = sqlite3.connect(":memory:", check_same_thread=False)
            _CONEXION.row_factory = sqlite3.Row
            reiniciar()
        return _CONEXION


def reiniciar() -> None:
    """Tira todo y vuelve a sembrar. Es lo que hace `POST /admin/reset`."""
    global _CONEXION
    with _CANDADO:
        if _CONEXION is None:
            _CONEXION = sqlite3.connect(":memory:", check_same_thread=False)
            _CONEXION.row_factory = sqlite3.Row
        cx = _CONEXION
        for tabla in (
            "auditoria", "resenas", "equipo_miembros", "equipos", "reserva_eventos",
            "reservas", "horarios", "canchas", "sedes", "sesiones", "usuarios",
        ):
            cx.execute(f"DROP TABLE IF EXISTS {tabla}")
        cx.executescript(ESQUEMA)
        _sembrar(cx)
        cx.commit()


def _sembrar(cx: sqlite3.Connection) -> None:
    for nombre, email, clave, rol, telefono, activo in USUARIOS_SEMILLA:
        cx.execute(
            "INSERT INTO usuarios (nombre, email, clave_hash, rol, telefono, activo, creado_en)"
            " VALUES (?,?,?,?,?,?,?)",
            (nombre, email, hashear(clave), rol, telefono, activo, AHORA),
        )
    cx.executemany(
        "INSERT INTO sedes (nombre, direccion, ciudad, telefono, duenio_id, activa)"
        " VALUES (?,?,?,?,?,?)",
        SEDES_SEMILLA,
    )
    cx.executemany(
        "INSERT INTO canchas (sede_id, nombre, tipo, superficie, techada, precio_hora, estado)"
        " VALUES (?,?,?,?,?,?,?)",
        CANCHAS_SEMILLA,
    )
    cx.executemany(
        "INSERT INTO horarios (cancha_id, dia_semana, hora_inicio, hora_fin, activo)"
        " VALUES (?,?,?,?,?)",
        HORARIOS_SEMILLA,
    )
    cx.executemany(
        "INSERT INTO equipos (nombre, capitan_id, creado_en) VALUES (?,?,?)",
        [(n, c, AHORA) for n, c in EQUIPOS_SEMILLA],
    )
    cx.executemany(
        "INSERT INTO equipo_miembros (equipo_id, usuario_id) VALUES (?,?)", MIEMBROS_SEMILLA
    )
    for cancha, usuario, equipo, fecha, ini, fin, estado, nota in RESERVAS_SEMILLA:
        cur = cx.execute(
            "INSERT INTO reservas"
            " (cancha_id, usuario_id, equipo_id, fecha, hora_inicio, hora_fin, estado, nota,"
            "  creada_en) VALUES (?,?,?,?,?,?,?,?,?)",
            (cancha, usuario, equipo, fecha, ini, fin, estado, nota, AHORA),
        )
        cx.execute(
            "INSERT INTO reserva_eventos"
            " (reserva_id, estado_anterior, estado_nuevo, usuario_id, creado_en)"
            " VALUES (?,?,?,?,?)",
            (cur.lastrowid, None, estado, usuario, AHORA),
        )
    cx.executemany(
        "INSERT INTO resenas (cancha_id, usuario_id, puntaje, comentario, creada_en)"
        " VALUES (?,?,?,?,?)",
        [(c, u, p, t, AHORA) for c, u, p, t in RESENAS_SEMILLA],
    )


# --- Helpers de acceso ----------------------------------------------------------------


def consultar(sql: str, parametros: tuple = ()) -> list[dict[str, Any]]:
    with _CANDADO:
        return [dict(f) for f in conexion().execute(sql, parametros).fetchall()]


def uno(sql: str, parametros: tuple = ()) -> dict[str, Any] | None:
    filas = consultar(sql, parametros)
    return filas[0] if filas else None


def escalar(sql: str, parametros: tuple = ()) -> Any:
    fila = uno(sql, parametros)
    return next(iter(fila.values())) if fila else None


def ejecutar(sql: str, parametros: tuple = ()) -> int:
    """Corre una sentencia de escritura y devuelve el id insertado (o el rowcount)."""
    with _CANDADO:
        cx = conexion()
        cur = cx.execute(sql, parametros)
        cx.commit()
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def auditar(usuario_id: int | None, accion: str, recurso: str) -> None:
    ejecutar(
        "INSERT INTO auditoria (usuario_id, accion, recurso, creado_en) VALUES (?,?,?,?)",
        (usuario_id, accion, recurso, AHORA),
    )
