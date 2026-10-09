"""Rotas das cenas de um perfil (contracts/http-api.md da 010): lista, criação e padrões. Dono e
membro (`RequireUser`), menos a reversão dos padrões (`RequireHumanOwner`). Sem DELETE.

Spec 029: a lista e a criação por perfil ficam `deprecated`, com o mesmo comportamento (o perfil
do caminho é o filtro e o perfil base); as novas são `GET/POST /api/cenas`. Os padrões continuam
do perfil."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query

from sociman_api.auth.deps import RequireHumanOwner, RequireUser
from sociman_api.cenas import padroes, schemas
from sociman_api.cenas import service as svc
from sociman_api.cenas.models import CenaStatus
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.schemas import RevertIn, VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404

router = APIRouter(prefix="/api/perfis")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/{perfil_id}/cenas", operation_id="cenas_list", response_model=schemas.CenasList,
            responses=_errors(400, 401, 403, 404), deprecated=True)
def list_(
    perfil_id: UUID, actor: RequireUser, db: DbSession,
    q: Annotated[str | None, Query(max_length=100,
                                   description="Nome, ação, fala ou produto (sem acento)")]
    = None,
    status: Annotated[list[CenaStatus] | None, Query(description="Status (OU)")] = None,
    avatar_id: Annotated[UUID | None, Query(alias="avatarId")] = None,
    cenario_id: Annotated[UUID | None, Query(alias="cenarioId")] = None,
    produto_imagem_id: Annotated[UUID | None, Query(alias="produtoImagemId")] = None,
    produto_id: Annotated[UUID | None, Query(alias="produtoId")] = None,
    tag: Annotated[list[str] | None, Query(description="Tags (E)")] = None,
    arquivadas: Annotated[Literal["false", "true", "all"], Query()] = "false",
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=svc.MAX_LIMIT)] = svc.DEFAULT_LIMIT,
) -> schemas.CenasList:
    """Use `GET /api/cenas?perfilId=` (spec 029)."""
    get_perfil_or_404(db, perfil_id)
    return svc.listar(db, perfil_id, q=q, status=status or (), avatar_id=avatar_id,
                      cenario_id=cenario_id, produto_imagem_id=produto_imagem_id,
                      produto_id=produto_id,
                      tags=tag or (), arquivadas=arquivadas, cursor=cursor, limit=limit)


@router.post("/{perfil_id}/cenas", operation_id="cenas_create", status_code=201,
             response_model=schemas.Cena, responses=_errors(400, 401, 403, 404, 409, 422),
             deprecated=True)
def create(perfil_id: UUID, body: schemas.CenaIn, actor: RequireUser,
           db: DbSession) -> schemas.Cena:
    """Use `POST /api/cenas` com `perfilId` (spec 029)."""
    return svc.cena_out(db, svc.criar(db, actor, perfil_id, body), actor)


@router.get("/{perfil_id}/cenas/padroes", operation_id="cenas_padroes_get",
            response_model=schemas.CenaPadroes, responses=_errors(401, 403, 404))
def padroes_get(perfil_id: UUID, actor: RequireUser, db: DbSession) -> schemas.CenaPadroes:
    return padroes.obter(db, perfil_id)


@router.put("/{perfil_id}/cenas/padroes", operation_id="cenas_padroes_put",
            response_model=schemas.CenaPadroes, responses=_errors(400, 401, 403, 404, 409))
def padroes_put(perfil_id: UUID, body: schemas.PadroesIn, actor: RequireUser,
                db: DbSession) -> schemas.CenaPadroes:
    return padroes.salvar(db, actor, perfil_id, body)


@router.get("/{perfil_id}/cenas/padroes/versions", operation_id="cenas_padroes_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def padroes_versions(perfil_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return padroes.versoes(db, perfil_id)


@router.post("/{perfil_id}/cenas/padroes/revert", operation_id="cenas_padroes_revert",
             response_model=schemas.CenaPadroes, responses=_errors(400, 401, 403, 404, 409))
def padroes_revert(perfil_id: UUID, body: RevertIn, actor: RequireHumanOwner,
                   db: DbSession) -> schemas.CenaPadroes:
    return padroes.reverter(db, actor, perfil_id, body.version, body.to_version)
