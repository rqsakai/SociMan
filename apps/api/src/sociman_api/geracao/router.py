"""Rotas das gerações (contracts/http-api.md da spec 021, research R16).

Ler (lista, detalhe, versões) é `RequireUser`; pedir, escolher, cancelar, tentar de novo e gerar
outras são **`RequireHuman`** (dono ou membro humano; outro ator → 403 `somente_humano` + o
evento `publicacao_recusada`, FR-008). Nada é `RequireHumanOwner`: nada publica. Sem DELETE e
sem revert (a geração não tem "reverter", exceção do princípio VII). No `mcp/mapa.py`, as
escritas ficam em `PROIBIDAS` e as leituras em `FORA`.

Spec 029 (R5): `POST /api/geracoes` (o alvo dá o item; `perfilBaseId` opcional) e
`GET /api/geracoes?alvoTipo&alvoId` (as gerações do item, de qualquer perfil base). As rotas por
perfil ficam `deprecated`, com o mesmo comportamento (o perfil do caminho é o padrão do
`perfilBaseId`; a lista filtra pelo perfil base usado).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from sociman_api.auth.deps import RequireHuman, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.geracao import schemas, service
from sociman_api.geracao.models import GeracaoAlvo, GeracaoStatus
from sociman_api.perfis.schemas import VersionsList

router = APIRouter(prefix="/api")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.post("/geracoes", operation_id="geracoes_pedir_agencia", status_code=201,
             response_model=schemas.GeracaoDetalhe, responses=_errors(400, 401, 403, 404, 409, 503))
def pedir_agencia(body: schemas.GeracaoIn, actor: RequireHuman,
                  db: DbSession) -> schemas.GeracaoDetalhe:
    return service.geracao_out(db, service.pedir(db, actor, body))


@router.get("/geracoes", operation_id="geracoes_listar_agencia",
            response_model=schemas.GeracoesPagina, responses=_errors(400, 401, 403))
def listar_agencia(
    actor: RequireUser, db: DbSession,
    alvo_tipo: Annotated[GeracaoAlvo, Query(alias="alvoTipo")],
    alvo_id: Annotated[UUID, Query(alias="alvoId")],
    status: Annotated[list[GeracaoStatus] | None, Query()] = None,
    passo: Annotated[str | None, Query(max_length=40)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limite: Annotated[int, Query(ge=1, le=service.LIMITE_MAX)] = service.LIMITE_PADRAO,
) -> schemas.GeracoesPagina:
    return service.listar(db, None, alvo_tipo=alvo_tipo, alvo_id=alvo_id, status=status,
                          passo=passo, cursor=cursor, limite=limite)


@router.post("/perfis/{perfil_id}/geracoes", operation_id="geracoes_criar", status_code=201,
             response_model=schemas.GeracaoDetalhe, deprecated=True,
             responses=_errors(400, 401, 403, 404, 409, 503))
def criar(perfil_id: UUID, body: schemas.GeracaoIn, actor: RequireHuman,
          db: DbSession) -> schemas.GeracaoDetalhe:
    g = service.pedir(db, actor, body, perfil_caminho=perfil_id)
    return service.geracao_out(db, g)


@router.get("/perfis/{perfil_id}/geracoes", operation_id="geracoes_listar", deprecated=True,
            response_model=schemas.GeracoesPagina, responses=_errors(400, 401, 403, 404))
def listar(
    perfil_id: UUID, actor: RequireUser, db: DbSession,
    alvo_tipo: Annotated[GeracaoAlvo | None, Query(alias="alvoTipo")] = None,
    alvo_id: Annotated[UUID | None, Query(alias="alvoId")] = None,
    status: Annotated[list[GeracaoStatus] | None, Query()] = None,
    passo: Annotated[str | None, Query(max_length=40)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limite: Annotated[int, Query(ge=1, le=service.LIMITE_MAX)] = service.LIMITE_PADRAO,
) -> schemas.GeracoesPagina:
    return service.listar(db, perfil_id, alvo_tipo=alvo_tipo, alvo_id=alvo_id, status=status,
                          passo=passo, cursor=cursor, limite=limite)


@router.get("/geracoes/{geracao_id}", operation_id="geracoes_detalhe",
            response_model=schemas.GeracaoDetalhe, responses=_errors(401, 403, 404))
def detalhe(geracao_id: UUID, actor: RequireUser, db: DbSession) -> schemas.GeracaoDetalhe:
    return service.detalhe(db, geracao_id)


@router.get("/geracoes/{geracao_id}/versoes", operation_id="geracoes_versoes",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def versoes(geracao_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service.versoes(db, geracao_id)


@router.post("/geracoes/{geracao_id}/escolher", operation_id="geracoes_escolher",
             response_model=schemas.GeracaoEscolhida,
             responses=_errors(400, 401, 403, 404, 409))
def escolher(geracao_id: UUID, body: schemas.EscolherIn, actor: RequireHuman,
             db: DbSession) -> schemas.GeracaoEscolhida:
    g, alvo = service.escolher(db, actor, geracao_id, body)
    out = service.geracao_out(db, g)
    return schemas.GeracaoEscolhida(**out.model_dump(), alvo=schemas.AlvoGeracao(
        tipo=g.alvo_tipo, id=g.alvo_id, version=alvo.version))


@router.post("/geracoes/{geracao_id}/cancelar", operation_id="geracoes_cancelar",
             response_model=schemas.GeracaoDetalhe, responses=_errors(400, 401, 403, 404, 409))
def cancelar(geracao_id: UUID, body: schemas.VersaoIn, actor: RequireHuman,
             db: DbSession) -> schemas.GeracaoDetalhe:
    return service.geracao_out(db, service.cancelar(db, actor, geracao_id, body.version))


@router.post("/geracoes/{geracao_id}/tentar-de-novo", operation_id="geracoes_tentar_de_novo",
             response_model=schemas.GeracaoDetalhe, responses=_errors(400, 401, 403, 404, 409))
def tentar_de_novo(geracao_id: UUID, body: schemas.VersaoIn, actor: RequireHuman,
                   db: DbSession) -> schemas.GeracaoDetalhe:
    return service.geracao_out(db, service.tentar_de_novo(db, actor, geracao_id, body.version))


@router.post("/geracoes/{geracao_id}/gerar-outras", operation_id="geracoes_gerar_outras",
             status_code=201, response_model=schemas.GeracaoDetalhe,
             responses=_errors(400, 401, 403, 404, 409))
def gerar_outras(geracao_id: UUID, body: schemas.VersaoIn, actor: RequireHuman,
                 db: DbSession) -> schemas.GeracaoDetalhe:
    return service.geracao_out(db, service.gerar_outras(db, actor, geracao_id, body.version))
