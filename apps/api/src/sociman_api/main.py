"""App FastAPI. Tudo sob /api (o edge nginx roteia /api/* para cá)."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sociman_api.db import get_engine

app = FastAPI(title="SociMan API", version="0.1.0", openapi_url="/api/openapi.json", docs_url="/api/docs")


@app.get("/api/health")
def health() -> JSONResponse:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
        db = "ok"
    except Exception:  # noqa: BLE001 — health reporta, não propaga
        db = "unavailable"
    status = 200 if db == "ok" else 503
    return JSONResponse({"status": "ok" if db == "ok" else "degraded", "db": db}, status_code=status)
