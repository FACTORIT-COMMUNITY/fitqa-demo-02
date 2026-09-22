# Reserva de canchas

API y pantallas para reservar canchas de futbol 5 y 7 en varios predios. Maneja sedes,
canchas, horarios semanales, reservas con estado, equipos y resenas, con un panel de
gestion para quien administra un predio.

Python 3.13, FastAPI, SQLite de la biblioteca estandar y Jinja2 para las plantillas. Sin
build, sin ORM, sin servicios externos.

## Levantarlo

```bash
python -m venv .venv
.venv/Scripts/activate          # en Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 3211
```

`GET /health` responde `{"estado":"ok"}` cuando el proceso esta listo. Las pantallas quedan
en `http://localhost:3211/` y el contrato OpenAPI en `/docs` y `/openapi.json`. El archivo
`openapi.json` de la raiz es ese mismo contrato versionado; se regenera con
`python exportar_openapi.py`.

## Estado y datos

La base es SQLite **en memoria**: vive en el proceso y no deja archivo. El estado lo
comparten todas las peticiones.

`POST /admin/reset` devuelve la base a la semilla. No pide sesion: sin un reset accesible no
habria forma de aislar una prueba de la anterior. Reiniciar el proceso equivale a un reset.

La semilla es fija:

| Tabla | Filas |
|---|---|
| usuarios | 8 |
| sedes | 4 |
| canchas | 8 |
| horarios | 280 |
| reservas | 7 |
| equipos | 3 |
| resenas | 5 |

Las canchas tienen franjas de una hora, de 18:00 a 23:00, todos los dias de la semana.

### Cuentas de la semilla

| Email | Clave | Rol |
|---|---|---|
| `admin@canchas.test` | `admin123` | admin |
| `roberto@canchas.test` | `duenio123` | duenio (sedes 1 y 2) |
| `lucia@canchas.test` | `duenio123` | duenio (sedes 3 y 4) |
| `ana@canchas.test` | `jugador123` | jugador |
| `bruno@canchas.test` | `jugador123` | jugador |
| `carla@canchas.test` | `jugador123` | jugador |
| `diego@canchas.test` | `jugador123` | jugador |
| `elena@canchas.test` | `jugador123` | jugador, dada de baja |

## Autenticacion

`POST /auth/login` devuelve un token opaco que se manda en cada peticion:

```
Authorization: Bearer <token>
```

No es un JWT: el token vive en una tabla, asi que `POST /auth/logout` lo revoca de
inmediato. Cambiar la clave invalida todas las sesiones del usuario, incluida la que hizo
el cambio.

## Roles

| Rol | Puede |
|---|---|
| `jugador` | reservar para si mismo; ver y gestionar **solo sus propias reservas**; resenar canchas donde jugo; armar equipos |
| `duenio` | todo lo anterior, mas administrar **las sedes que tiene asignadas**: sus canchas, sus horarios, confirmar y cerrar sus reservas, y ver su panel |
| `admin` | todo, en todas las sedes |

Un duenio no manda en sedes ajenas. El registro publico (`POST /auth/registro`) siempre crea
un `jugador`; para crear un duenio o un admin hay que pasar por `POST /usuarios`, que pide
sesion de admin.

## Endpoints

### Sistema
| | |
|---|---|
| `GET /health` | listo para atender |
| `GET /version` | version y conteo de filas por tabla |
| `POST /admin/reset` | vuelve a la semilla |
| `GET /admin/auditoria` | registro de acciones (admin) |

### Autenticacion
| | |
|---|---|
| `POST /auth/registro` | alta publica, siempre rol jugador |
| `POST /auth/login` | devuelve token |
| `POST /auth/logout` | revoca el token |
| `GET /auth/yo` | usuario de la sesion |
| `PUT /auth/password` | cambia la clave propia |

### Usuarios (admin, salvo el propio)
`GET /usuarios` · `POST /usuarios` · `GET /usuarios/{id}` · `PUT /usuarios/{id}` ·
`DELETE /usuarios/{id}` · `PATCH /usuarios/{id}/rol` · `GET /usuarios/{id}/reservas`

### Sedes
`GET /sedes` · `POST /sedes` · `GET /sedes/{id}` · `PUT /sedes/{id}` · `DELETE /sedes/{id}` ·
`GET /sedes/{id}/canchas`

### Canchas
`GET /canchas` · `POST /canchas` · `GET /canchas/{id}` · `PUT /canchas/{id}` ·
`DELETE /canchas/{id}` · `PATCH /canchas/{id}/estado` · `GET /canchas/{id}/disponibilidad` ·
`GET /canchas/{id}/reservas`

### Horarios
`GET /canchas/{id}/horarios` · `POST /canchas/{id}/horarios` · `GET /horarios/{id}` ·
`PUT /horarios/{id}` · `DELETE /horarios/{id}`

### Reservas
`GET /reservas` · `POST /reservas` · `GET /reservas/agenda` · `GET /reservas/{id}` ·
`PUT /reservas/{id}` · `DELETE /reservas/{id}` · `POST /reservas/{id}/confirmar` ·
`POST /reservas/{id}/cancelar` · `POST /reservas/{id}/no-show` ·
`POST /reservas/{id}/completar` · `GET /reservas/{id}/historial`

### Equipos
`GET /equipos` · `POST /equipos` · `GET /equipos/{id}` · `PUT /equipos/{id}` ·
`DELETE /equipos/{id}` · `POST /equipos/{id}/miembros` ·
`DELETE /equipos/{id}/miembros/{usuario_id}`

### Resenas
`GET /canchas/{id}/resenas` · `POST /canchas/{id}/resenas` · `GET /resenas/{id}` ·
`PUT /resenas/{id}` · `DELETE /resenas/{id}`

### Panel (duenio o admin)
`GET /panel/resumen` · `GET /panel/ocupacion` · `GET /panel/cancelaciones` ·
`GET /panel/ranking-canchas`

### Pantallas
`/` · `/ui/login` · `/ui/canchas` · `/ui/reservas` · `/ui/agenda` · `/ui/panel`

## Reglas que la API cumple

### Estados de una reserva

```
pendiente ──┬─> confirmada ──┬─> completada
            │                ├─> no-show
            └─> cancelada <──┘
```

- Una reserva nace `pendiente`. La confirma quien administra la cancha.
- `cancelada`, `completada` y `no-show` **son terminales**: desde ahi no se sale.
- Completar o marcar no-show solo tiene sentido sobre una reserva `confirmada`.
- Cada cambio de estado queda registrado y se consulta en `GET /reservas/{id}/historial`.
- Mover una reserva de fecha u horario solo se puede mientras siga `pendiente`.

### Disponibilidad

- Una franja **ocupada por una reserva vigente** —`pendiente` o `confirmada`— no se puede
  volver a reservar: el intento devuelve 409.
- Una reserva `cancelada` o con `no-show` **libera** la franja.
- Una franja tomada por una reserva vigente figura `libre: false` en
  `GET /canchas/{id}/disponibilidad`.
- Solo se puede reservar una franja que exista en el horario de la cancha para ese dia de la
  semana. Cualquier otro rango devuelve 409.
- Los rangos son semiabiertos `[inicio, fin)`: 19:00-20:00 y 20:00-21:00 no se pisan.

### Estados de una cancha

- `habilitada`, `mantenimiento` o `baja`.
- Una cancha que **no esta habilitada no tiene disponibilidad** y no admite reservas nuevas.
- Borrar una cancha con reservas vigentes devuelve 409.

### Listados y paginacion

- Todos los listados devuelven `{datos, total, limite, desde}`.
- `total` es la cantidad de registros **que cumplen los filtros aplicados**, no la de la
  tabla entera.
- `desde=0` devuelve desde el primer registro, y la suma de todas las paginas da `total`.
- `limite` va de 1 a 100; el valor por defecto es 20. Fuera de rango: 400.
- `orden` solo acepta los campos documentados por recurso. Para canchas:
  `id`, `nombre`, `precio_hora`, `tipo`. `orden=precio_hora` ordena **por precio, de menor a
  mayor**. `direccion` es `asc` o `desc`.

### Unicidad

- `email` de usuario es unico, tanto en el alta como en la modificacion.
- `nombre` de sede y de equipo son unicos.
- `nombre` de cancha es unico dentro de su sede.
- Un usuario deja **una sola resena por cancha**, y solo si tiene al menos una reserva
  `completada` en esa cancha.

### Panel

- `ocupacion` mide las franjas **efectivamente tomadas** sobre las franjas configuradas para
  ese dia. Una reserva cancelada libera la franja y no cuenta.
- `cancelaciones` informa canceladas y no-shows sobre el total de reservas de la cancha.
- Un duenio ve unicamente las canchas de sus sedes.

### Errores

Todos tienen la misma forma:

```json
{"error": "texto legible"}
```

y los de validacion agregan detalles:

```json
{"error": "datos invalidos", "detalles": [{"campo": "puntaje", "problema": "..."}]}
```

| Codigo | Cuando |
|---|---|
| 400 | datos invalidos, parametro fuera de rango, enumerado desconocido |
| 401 | falta sesion o las credenciales no sirven |
| 403 | hay sesion pero el rol o la pertenencia no alcanzan |
| 404 | el recurso o la ruta no existen |
| 409 | choca con el estado actual: duplicado, transicion imposible, franja tomada |

## Notas de diseno

Tres decisiones que a primera vista parecen errores y no lo son.

**Los tres fallos de login dan la misma respuesta.** Email inexistente, clave equivocada y
cuenta dada de baja devuelven los tres `401` con el mensaje `email o clave incorrectos`.
Distinguirlos seria mas comodo para quien se equivoco y convertiria el login en un oraculo
de enumeracion: probando emails de a uno se averigua cuales estan registrados. La comodidad
no compensa.

**Borrar una reserva es idempotente.** `DELETE /reservas/{id}` devuelve `204` aunque esa
reserva no exista. El resultado que el llamador pide —que la reserva no este— ya se cumple,
y devolver 404 obliga a todo cliente a distinguir dos casos que terminan igual. Leerla con
`GET /reservas/{id}` si devuelve 404: ahi el recurso es la respuesta, y su ausencia importa.

**La baja de usuario no borra la fila.** `DELETE /usuarios/{id}` marca `activo = 0` y corta
las sesiones. Las reservas historicas siguen apuntando a ese usuario y borrarlo las dejaria
sin titular.
