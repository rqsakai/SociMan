"""Rotas das anotações e propostas (contracts/http-api.md da 009, `operationId` `anotacoes_*`).

Acesso: **U** (`RequireUser`: humano ou cliente MCP, conforme o mapa) para ler, criar, editar e
arquivar; **Hu** (`RequireHuman`) para descartar; **H** (`RequireHumanOwner`) para reverter.
Aplicar uma proposta é o save do destino com `propostaId` (`PATCH /api/destinos/{id}`).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from sociman_api.anotacoes import schemas, service
from sociman_api.anotacoes.models import AnotacaoAlvo, AnotacaoSituacao, AnotacaoTipo
from sociman_api.auth.deps import RequireHuman, RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis import base as perfil_base
from sociman_api.perfis.schemas import RevertIn, VersionsList

router = APIRouter(prefix="/api/anotacoes")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _out(db, anotacao) -> schemas.AnotacaoOut:
    return schemas.AnotacaoOut(anotacao=service.anotacao_out(db, anotacao))


@router.get("", operation_id="anotacoes_list", response_model=schemas.AnotacoesPage,
            responses=_errors(400, 401, 403))
def anotacoes_list(
    actor: RequireUser,
    db: DbSession,
    alvo_tipo: Annotated[AnotacaoAlvo | None, Query(alias="alvoTipo")] = None,
    alvo_id: Annotated[UUID | None, Query(alias="alvoId")] = None,
    perfil_id: Annotated[str | None, Query(
        alias="perfilId", max_length=40,
        description="Um id de perfil ou `sem` (sem perfil); cena e produto pelo perfil base "
                    "atual")] = None,
    situacao: Annotated[AnotacaoSituacao | None, Query()] = None,
    tipo: Annotated[AnotacaoTipo | None, Query()] = None,
    autor_cliente_id: Annotated[UUID | None, Query(alias="autorClienteId")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> schemas.AnotacoesPage:
    """Anotações e propostas, das mais novas para as mais antigas, com filtros. `q` busca um
    trecho do texto, sem acento e sem caixa (spec 024)."""
    return service.listar(db, alvo_tipo, alvo_id, perfil_base.filtro_perfil(perfil_id),
                          situacao, tipo, autor_cliente_id, cursor, limit, q)


@router.get("/resumo", operation_id="anotacoes_resumo", response_model=schemas.AnotacoesResumo,
            responses=_errors(401, 403))
def anotacoes_resumo(actor: RequireUser, db: DbSession,
                     perfil_id: Annotated[str | None, Query(alias="perfilId", max_length=40)]
                     = None) -> schemas.AnotacoesResumo:
    """Quantas propostas estão abertas (contador do menu)."""
    return service.resumo(db, perfil_base.filtro_perfil(perfil_id))


@router.post("", operation_id="anotacoes_create", status_code=201,
             response_model=schemas.AnotacaoOut, responses=_errors(400, 401, 403, 404, 409))
def anotacoes_create(body: schemas.CreateAnotacaoIn, actor: RequireUser, db: DbSession
                     ) -> schemas.AnotacaoOut:
    """Grava uma observação ou uma proposta de texto (só em destino) presa a um item."""
    return _out(db, service.criar(db, actor, body))


@router.get("/{anotacao_id}", operation_id="anotacoes_get", response_model=schemas.AnotacaoOut,
            responses=_errors(401, 403, 404))
def anotacoes_get(anotacao_id: UUID, actor: RequireUser, db: DbSession) -> schemas.AnotacaoOut:
    return _out(db, service.get_or_404(db, anotacao_id))


@router.patch("/{anotacao_id}", operation_id="anotacoes_update",
              response_model=schemas.AnotacaoOut, responses=_errors(400, 401, 403, 404, 409))
def anotacoes_update(anotacao_id: UUID, body: schemas.UpdateAnotacaoIn, actor: RequireUser,
                     db: DbSession) -> schemas.AnotacaoOut:
    """Só o autor, só com a anotação aberta."""
    return _out(db, service.editar(db, actor, anotacao_id, body))


@router.post("/{anotacao_id}/archive", operation_id="anotacoes_archive",
             response_model=schemas.AnotacaoOut, responses=_errors(400, 401, 403, 404, 409))
def anotacoes_archive(anotacao_id: UUID, body: schemas.AnotacaoVersionIn, actor: RequireUser,
                      db: DbSession) -> schemas.AnotacaoOut:
    """O autor ou um dono, só com a anotação aberta."""
    return _out(db, service.arquivar(db, actor, anotacao_id, body.version))


@router.post("/{anotacao_id}/descartar", operation_id="anotacoes_descartar",
             response_model=schemas.AnotacaoOut, responses=_errors(400, 401, 403, 404, 409))
def anotacoes_descartar(anotacao_id: UUID, body: schemas.DescartarIn, actor: RequireHuman,
                        db: DbSession) -> schemas.AnotacaoOut:
    """Ato humano: descarta a proposta, com motivo opcional."""
    return _out(db, service.descartar(db, actor, anotacao_id, body.version, body.motivo))


@router.post("/{anotacao_id}/revert", operation_id="anotacoes_revert",
             response_model=schemas.AnotacaoOut, responses=_errors(400, 401, 403, 404, 409))
def anotacoes_revert(anotacao_id: UUID, body: RevertIn, actor: RequireHumanOwner,
                     db: DbSession) -> schemas.AnotacaoOut:
    """Só o dono humano."""
    return _out(db, service.reverter(db, actor, anotacao_id, body.version, body.to_version))


@router.get("/{anotacao_id}/versions", operation_id="anotacoes_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def anotacoes_versions(anotacao_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service.versoes(db, anotacao_id)
