# Reserva de canchas — contexto para agentes

API de reserva de canchas. Python + FastAPI + `sqlite3` de la biblioteca estandar. El
README tiene la spec completa: endpoints, roles, las reglas que la API promete cumplir y las
notas de diseno. Leelo antes de tocar nada.

## Levantar el sistema

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 3211
```

Queda escuchando hasta que lo maten. `GET /health` responde `{"estado":"ok"}` cuando esta
listo. Si el arranque falla con `EADDRINUSE` o `error while attempting to bind`, el puerto
esta tomado: usa otro `--port`.

## Estado y aislamiento entre pruebas

La base es SQLite **en memoria**: vive en el proceso, no hay archivo. Todo el estado es
compartido por todas las peticiones, asi que:

- **Llama `POST /admin/reset` antes de cada caso que escriba.** Devuelve la base a la
  semilla documentada en el README. No pide sesion.
- Un caso que no resetea ve lo que dejo el anterior. No es un defecto del sistema, es como
  funciona una base en memoria.
- Reiniciar el proceso equivale a un reset.
- **Un reset invalida todos los tokens.** Despues de resetear hay que volver a hacer login.

## Autenticacion desde una prueba

Casi todo pide sesion. El ciclo minimo:

```bash
TOKEN=$(curl -s -X POST localhost:3211/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@canchas.test","clave":"admin123"}' | jq -r .token)

curl -s localhost:3211/reservas -H "Authorization: Bearer $TOKEN"
```

Las cuentas de la semilla, con sus roles, estan en el README. Hay dos duenios con sedes
distintas a proposito: sirven para probar que uno no manda en las sedes del otro.

## El contrato

`openapi.json` en la raiz es el contrato versionado, el mismo que el proceso publica en
`/openapi.json`. Se regenera con `python exportar_openapi.py` y hay que actualizarlo cuando
se toca una ruta o un esquema: si queda distinto de lo que el script genera, el contrato
versionado miente.

## Convenciones del codigo

- Un modulo por recurso en `app/rutas/`, cada uno con su `APIRouter` llamado `router`.
- Las rutas se declaran una por una con `@router.<verbo>(...)`, sin registro dinamico: el
  archivo de cada recurso es el indice de su superficie HTTP y se lee de arriba abajo.
- `app/db.py` tiene el esquema, la semilla y los helpers de acceso (`consultar`, `uno`,
  `escalar`, `ejecutar`). No hay ORM.
- `app/esquemas.py` tiene los modelos Pydantic de entrada y el vocabulario del dominio
  (estados, roles, campos ordenables). `app/serializadores.py` decide que sale en cada
  respuesta.
- `app/validacion.py` concentra las validaciones compartidas: fechas, horas, rangos,
  paginacion y orden. Levantan `DatosInvalidos` con los detalles ya armados.
- `app/errores.py` define los errores de dominio; `app/main.py` los traduce a HTTP y
  reescribe el `{"detail": ...}` de FastAPI al `{"error": ...}` del sistema.
- Espanol sin tildes en identificadores y comentarios del codigo; con tildes en el texto que
  ve el usuario y en la documentacion.

## El front

`app/plantillas/` son plantillas Jinja servidas por `app/rutas/vistas.py`. Consumen la
propia API con `fetch` y guardan el token en `sessionStorage`. No hay bundler ni framework:
lo que se ve en el navegador es lo que dice el HTML.

Las pantallas no cubren toda la API — son `/`, `/ui/login`, `/ui/canchas`, `/ui/reservas`,
`/ui/agenda` y `/ui/panel`. Todo lo demas se ejercita por HTTP.

## Que hace falta para probar

El proceso levantado y un cliente HTTP. No hay servicios externos, ni colas, ni base que
provisionar. Las fechas de la semilla son de octubre de 2026 y estan fijas a proposito: nada
depende de `date.today()`, asi que la misma prueba da lo mismo cualquier dia.
