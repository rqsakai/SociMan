"""Rotas da gestão do MCP (contracts/http-api.md da 009): clientes, interruptor e registro.

Todas **H** (`RequireHumanOwner`, inclusive as leituras: a tela é só do dono e um token MCP
nunca as alcança) e todas em `PROIBIDAS` no mapa. Criar e rotacionar devolvem o token uma vez,
com `Cache-Control: no-store`. Não existe DELETE: revogar é um POST final.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from sociman_api.auth.deps import RequireHumanOwner
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.mcp import schemas, service
from sociman_api.mcp.models import McpResultado, McpSituacao, McpVia
from sociman_api.perfis.schemas import VersionsList

router = APIRouter(prefix="/api/mcp")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _sem_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


# ---- clientes ----

@router.get("/clientes", operation_id="mcp_clientes_list", response_model=schemas.ClientesList,
            responses=_errors(401, 403))
def clientes_list(actor: RequireHumanOwner, db: DbSession,
                  situacao: Annotated[McpSituacao | None, Query()] = None
                  ) -> schemas.ClientesList:
    """Clientes MCP (inclusive revogados): ativos, suspensos, revogados, depois o nome."""
    return schemas.ClientesList(clientes=service.listar(db, situacao))


@router.post("/clientes", operation_id="mcp_clientes_create", status_code=201,
             response_model=schemas.ClienteComToken, responses=_errors(400, 401, 403, 409))
def clientes_create(body: schemas.CreateClienteIn, response: Response, actor: RequireHumanOwner,
                    db: DbSession) -> schemas.ClienteComToken:
    """Cria o cliente e devolve a credencial **uma única vez**."""
    cliente, token = service.criar(db, actor, body)
    _sem_cache(response)
    return schemas.ClienteComToken(cliente=service.cliente_out(db, cliente), token=token)


@router.get("/clientes/{cliente_id}", operation_id="mcp_clientes_get",
            response_model=schemas.ClienteOut, responses=_errors(401, 403, 404))
def clientes_get(cliente_id: UUID, actor: RequireHumanOwner, db: DbSession
                 ) -> schemas.ClienteOut:
    return schemas.ClienteOut(cliente=service.obter(db, cliente_id))


@router.patch("/clientes/{cliente_id}", operation_id="mcp_clientes_update",
              response_model=schemas.ClienteOut, responses=_errors(400, 401, 403, 404, 409))
def clientes_update(cliente_id: UUID, body: schemas.UpdateClienteIn, actor: RequireHumanOwner,
                    db: DbSession) -> schemas.ClienteOut:
    """Nome, descrição, escopo, limites e vencimento; valem na chamada seguinte."""
    cliente = service.editar(db, actor, cliente_id, body)
    return schemas.ClienteOut(cliente=service.cliente_out(db, cliente))


@router.post("/clientes/{cliente_id}/suspender", operation_id="mcp_clientes_suspender",
             response_model=schemas.ClienteOut, responses=_errors(400, 401, 403, 404, 409))
def clientes_suspender(cliente_id: UUID, body: schemas.VersionIn, actor: RequireHumanOwner,
                       db: DbSession) -> schemas.ClienteOut:
    cliente = service.suspender(db, actor, cliente_id, body.version)
    return schemas.ClienteOut(cliente=service.cliente_out(db, cliente))


@router.post("/clientes/{cliente_id}/reativar", operation_id="mcp_clientes_reativar",
             response_model=schemas.ClienteOut, responses=_errors(400, 401, 403, 404, 409))
def clientes_reativar(cliente_id: UUID, body: schemas.VersionIn, actor: RequireHumanOwner,
                      db: DbSession) -> schemas.ClienteOut:
    cliente = service.reativar(db, actor, cliente_id, body.version)
    return schemas.ClienteOut(cliente=service.cliente_out(db, cliente))


@router.post("/clientes/{cliente_id}/rotacionar", operation_id="mcp_clientes_rotacionar",
             response_model=schemas.ClienteComToken, responses=_errors(400, 401, 403, 404, 409))
def clientes_rotacionar(cliente_id: UUID, body: schemas.VersionIn, response: Response,
                        actor: RequireHumanOwner, db: DbSession) -> schemas.ClienteComToken:
    """Credencial nova (mostrada uma vez); a antiga deixa de valer na hora."""
    cliente, token = service.rotacionar(db, actor, cliente_id, body.version)
    _sem_cache(response)
    return schemas.ClienteComToken(cliente=service.cliente_out(db, cliente), token=token)


@router.post("/clientes/{cliente_id}/revogar", operation_id="mcp_clientes_revogar",
             response_model=schemas.ClienteOut, responses=_errors(400, 401, 403, 404, 409))
def clientes_revogar(cliente_id: UUID, body: schemas.VersionIn, actor: RequireHumanOwner,
                     db: DbSession) -> schemas.ClienteOut:
    """Final: o cliente fica na lista como revogado e nunca volta."""
    cliente = service.revogar(db, actor, cliente_id, body.version)
    return schemas.ClienteOut(cliente=service.cliente_out(db, cliente))


@router.get("/clientes/{cliente_id}/versions", operation_id="mcp_clientes_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def clientes_versions(cliente_id: UUID, actor: RequireHumanOwner, db: DbSession
                      ) -> VersionsList:
    return service.versoes_cliente(db, cliente_id)


# ---- interruptor ----

@router.get("/config", operation_id="mcp_config_get", response_model=schemas.McpConfig,
            responses=_errors(401, 403))
def config_get(actor: RequireHumanOwner, db: DbSession) -> schemas.McpConfig:
    """O botão da tela e o `MCP_HABILITADO` do servidor; os dois precisam estar ligados."""
    return service.config_out(service.config(db))


@router.put("/config", operation_id="mcp_config_update", response_model=schemas.McpConfig,
            responses=_errors(400, 401, 403, 409))
def config_update(body: schemas.McpConfigIn, actor: RequireHumanOwner, db: DbSession
                  ) -> schemas.McpConfig:
    return service.config_update(db, actor, body)


@router.get("/config/versions", operation_id="mcp_config_versions", response_model=VersionsList,
            responses=_errors(401, 403))
def config_versions(actor: RequireHumanOwner, db: DbSession) -> VersionsList:
    return service.config_versoes(db)


# ---- registro ----

@router.get("/chamadas", operation_id="mcp_chamadas_list", response_model=schemas.ChamadasPage,
            responses=_errors(400, 401, 403))
def chamadas_list(
    actor: RequireHumanOwner,
    db: DbSession,
    cliente_id: Annotated[UUID | None, Query(alias="clienteId")] = None,
    tool: Annotated[str | None, Query(max_length=128)] = None,
    resultado: Annotated[McpResultado | None, Query()] = None,
    via: Annotated[McpVia | None, Query()] = None,
    de: Annotated[datetime | None, Query()] = None,
    ate: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> schemas.ChamadasPage:
    """Registro de chamadas MCP (só inserção), da mais nova para a mais antiga."""
    return service.chamadas(db, cliente_id, tool, resultado, via, de, ate, cursor, limit)
