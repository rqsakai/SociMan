"""App FastAPI. Tudo sob /api (o edge nginx roteia /api/* para cá)."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sociman_api.auth.router_auth import router as auth_router
from sociman_api.auth.router_events import router as events_router
from sociman_api.auth.router_users import router as users_router
from sociman_api.db import get_engine
from sociman_api.errors import install_openapi_error_contract, register_error_handlers
from sociman_api.redis import get_redis

app = FastAPI(title="SociMan API", version="0.1.0", openapi_url="/api/openapi.json", docs_url="/api/docs")
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(events_router)
install_openapi_error_contract(app)


@app.get("/api/health")
def health() -> JSONResponse:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
        db = "ok"
    except Exception:  # noqa: BLE001 — health reporta, não propaga
        db = "unavailable"
    try:
        get_redis().ping()
        cache = "ok"
    except Exception:  # noqa: BLE001
        cache = "unavailable"
    healthy = db == "ok" and cache == "ok"
    return JSONResponse({"status": "ok" if healthy else "degraded", "db": db, "redis": cache},
                        status_code=200 if healthy else 503)
