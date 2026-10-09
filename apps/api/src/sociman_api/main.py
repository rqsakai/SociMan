"""App FastAPI. Tudo sob /api (o edge nginx roteia /api/* para cá)."""

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sociman_api import datadir
from sociman_api.agencia.router import router as agencia_router  # spec 013
from sociman_api.analytics.router import router as analytics_router  # spec 019
from sociman_api.anotacoes.router import router as anotacoes_router  # spec 009
from sociman_api.aprendizado.router import router as aprendizado_router  # spec 023
from sociman_api.assets.router import router as assets_router
from sociman_api.assets.router_perfil import router as assets_perfil_router
from sociman_api.auth.router_auth import router as auth_router
from sociman_api.auth.router_events import router as events_router
from sociman_api.auth.router_users import router as users_router
from sociman_api.canais.router import router as canais_router
from sociman_api.cenas import usos_assets as _cenas_usos  # noqa: F401 — spec 010: "onde é usado"
from sociman_api.cenas.router import router as cenas_router  # spec 010
from sociman_api.cenas.router_perfil import router as cenas_perfil_router  # spec 010
from sociman_api.conteudos.router import router as conteudos_router
from sociman_api.conteudos.router_video import router as conteudos_video_router
from sociman_api.cortes.router import router as cortes_router
from sociman_api.db import get_engine
from sociman_api.envios.router import router as envios_router
from sociman_api.errors import install_openapi_error_contract, register_error_handlers
from sociman_api.geracao.router import router as geracao_router  # spec 021
from sociman_api.geracao.router_audios import router as audios_router  # spec 021
from sociman_api.ia.router import router as ia_router
from sociman_api.ia.router_guia import router as guia_router  # spec 017
from sociman_api.integracoes import router as integracoes_router
from sociman_api.marca.router import router as kit_router
from sociman_api.marca.router_fontes import router as fontes_router
from sociman_api.marca.router_fundos import router as fundos_router
from sociman_api.marca.router_marca_dagua import router as marca_dagua_router
from sociman_api.mcp import portao as mcp_portao  # spec 009
from sociman_api.mcp import servidor as mcp_servidor  # spec 009
from sociman_api.mcp.registro import RegistroMiddleware as RegistroMcpMiddleware  # spec 009
from sociman_api.mcp.router import router as mcp_router  # spec 009
from sociman_api.metricas.router import router as metricas_router  # spec 016
from sociman_api.metricas.studio.router import router as studio_router  # spec 020
from sociman_api.notificacoes.router import router as notificacoes_router
from sociman_api.perfis.router_contas import router as contas_router
from sociman_api.perfis.router_imagens import router as imagens_router
from sociman_api.perfis.router_perfis import router as perfis_router
from sociman_api.postagem.router import router as postagem_router
from sociman_api.produtos.router import router as produtos_router  # spec 012
from sociman_api.produtos.router_perfil import router as produtos_perfil_router  # spec 012
from sociman_api.publicacao.router import router as publicacao_router
from sociman_api.redis import get_redis
from sociman_api.router_midia import router as midia_router

datadir.pin_tempdir()  # spool de upload no HD, nunca no /tmp do container

# Spec 009 (R5): todo token MCP passa pelo portão, em qualquer rota e antes da validação.
app = FastAPI(title="SociMan API", version="0.1.0", openapi_url="/api/openapi.json", docs_url="/api/docs",
              dependencies=[Depends(mcp_portao.dependencia)])
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
app.include_router(assets_perfil_router)
app.include_router(assets_router)
app.include_router(canais_router)
app.include_router(envios_router)
app.include_router(postagem_router)
app.include_router(notificacoes_router)
app.include_router(integracoes_router)
app.include_router(ia_router)
app.include_router(conteudos_router)  # spec 014
app.include_router(conteudos_video_router)  # spec 014: vídeo próprio
app.include_router(publicacao_router)  # spec 015: conexões, interruptor e execução
app.include_router(metricas_router)  # spec 016: métricas, vínculo e exportação
app.include_router(guia_router)  # spec 017: guia de comunicação do perfil e da conta
app.include_router(analytics_router)  # spec 019: analytics de decisão (só leitura)
app.include_router(mcp_router)  # spec 009: clientes MCP, interruptor e registro (só dono humano)
app.include_router(anotacoes_router)  # spec 009: anotações e propostas dos agentes
mcp_servidor.montar(app)  # spec 009: endpoint MCP `/mcp` (fora do OpenAPI)
app.add_middleware(RegistroMcpMiddleware)  # spec 009: registro das chamadas com token MCP
app.include_router(studio_router)  # spec 020: histórico do TikTok Studio
app.include_router(cenas_perfil_router)  # spec 010: cenas do perfil e padrões
app.include_router(cenas_router)  # spec 010: cena, tomadas e vínculo com o conteúdo
app.include_router(agencia_router)  # spec 013: importação da agência (só dono humano grava)
app.include_router(aprendizado_router)  # spec 023: aprender com o desempenho
app.include_router(geracao_router)  # spec 021: geração local com candidatos
app.include_router(audios_router)  # spec 021: áudios do perfil
app.include_router(produtos_perfil_router)  # spec 012: produtos do perfil
app.include_router(produtos_router)  # spec 012: produto, ficha, variantes e aprovação
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
