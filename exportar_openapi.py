"""Vuelca el contrato OpenAPI de la aplicacion a `openapi.json`.

FastAPI publica el contrato en `/openapi.json` cuando el proceso esta levantado, pero eso
no le sirve a quien necesita leerlo sin correr nada: generadores de cliente, revisiones de
contrato en el pipeline, herramientas de analisis. Por eso el archivo se versiona.

    python exportar_openapi.py

Correrlo despues de tocar rutas o esquemas. Si el archivo queda distinto de lo que este
script genera, el contrato versionado miente.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

DESTINO = Path(__file__).resolve().parent / "openapi.json"


def main() -> None:
    contrato = app.openapi()
    DESTINO.write_text(
        json.dumps(contrato, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    operaciones = sum(
        1
        for ruta in contrato["paths"].values()
        for metodo in ruta
        if metodo in ("get", "post", "put", "patch", "delete")
    )
    print(f"{DESTINO.name}: {len(contrato['paths'])} rutas, {operaciones} operaciones")


if __name__ == "__main__":
    main()
