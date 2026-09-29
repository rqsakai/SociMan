"""App FastAPI. Tudo sob /api (o edge nginx roteia /api/* para cá)."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sociman_api import datadir
from sociman_api.auth.router_auth import router as auth_router
from sociman_api.auth.router_events import router as events_router
from sociman_api.auth.router_users import router as users_router
from sociman_api.cortes.router import router as cortes_router
from sociman_api.db import get_engine
from sociman_api.errors import install_openapi_error_contract, register_error_handlers
from sociman_api.marca.router import router as kit_router
from sociman_api.marca.router_fontes import router as fontes_router
from sociman_api.marca.router_fundos import router as fundos_router
from sociman_api.marca.router_marca_dagua import router as marca_dagua_router
from sociman_api.perfis.router_contas import router as contas_router
from sociman_api.perfis.router_imagens import router as imagens_router
from sociman_api.perfis.router_perfis import router as perfis_router
from sociman_api.redis import get_redis
from sociman_api.router_midia import router as midia_router

datadir.pin_tempdir()  # spool de upload no HD, nunca no /tmp do container

app = FastAPI(title="SociMan API", version="0.1.0", openapi_url="/api/openapi.json", docs_url="/api/docs")
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(events_router)
app.include_router(perfis_router)
app.include_router(contas_router)
app.include_router(imagens_router)
app.include_router(kit_router)
app.include_router(cortes_router)
app.include_router(fontes_router)
app.include_router(marca_dagua_router)
app.include_router(fundos_router)
app.include_router(midia_router)
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
    # HD de dados fora ou cheio degrada, mas a API segue no ar (R5): 200.
    storage = {"ok": "ok", "sem_sentinela": "unavailable",
               "pouco_espaco": "low_space"}[datadir.status().reason]
    healthy = db == "ok" and cache == "ok"
    return JSONResponse({"status": "ok" if healthy and storage == "ok" else "degraded", "db": db,
                         "redis": cache, "storage": storage},
                        status_code=200 if healthy else 503)
