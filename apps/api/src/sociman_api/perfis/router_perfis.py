"""Rotas de perfis (T011, contracts/http-api.md "Perfis"): dono e membro (`RequireUser`).

A reversão é só do dono (`RequireOwner`, FR-013). Imagens ficam em outro router. Não existe
rota DELETE (FR-014).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis import service_perfis as service
from sociman_api.perfis.models import PerfilStatus
from sociman_api.perfis.schemas import (
    CreatePerfilIn,
    PerfilDetail,
    PerfilOut,
    PerfisList,
    RevertIn,
    SlugSuggestion,
    UpdatePerfilIn,
    VersionIn,
    VersionsList,
)

router = APIRouter(prefix="/api/perfis")

Db = DbSession


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("", operation_id="perfis_list", response_model=PerfisList,
            responses=_errors(401, 403))
def list_perfis(
    actor: RequireUser, db: Db,
    q: Annotated[str | None, Query(max_length=80)] = None,
    status: PerfilStatus | None = None,
    archived: bool = False,
) -> PerfisList:
    return PerfisList(items=service.list_perfis(db, q, status, archived))


@router.get("/slug-suggestion", operation_id="perfis_slug_suggestion",
            response_model=SlugSuggestion, responses=_errors(401, 403))
def slug_suggestion(actor: RequireUser, db: Db,
                    name: Annotated[str, Query(max_length=80)]) -> SlugSuggestion:
    return SlugSuggestion(slug=service.slug_suggestion(db, name))


@router.post("", operation_id="perfis_create", response_model=PerfilOut, status_code=201,
             responses=_errors(400, 401, 403, 409))
def create_perfil(body: CreatePerfilIn, actor: RequireUser, db: Db) -> PerfilOut:
    perfil = service.create_perfil(db, actor, body)
    return PerfilOut(perfil=service.perfil_out(db, perfil))


@router.get("/{perfil_id}", operation_id="perfis_get", response_model=PerfilDetail,
            responses=_errors(401, 403, 404))
def get_perfil(perfil_id: UUID, actor: RequireUser, db: Db) -> PerfilDetail:
    return service.get_perfil(db, perfil_id)


@router.patch("/{perfil_id}", operation_id="perfis_update", response_model=PerfilOut,
              responses=_errors(400, 401, 403, 404, 409))
def update_perfil(perfil_id: UUID, body: UpdatePerfilIn, actor: RequireUser,
                  db: Db) -> PerfilOut:
    perfil = service.update_perfil(db, actor, perfil_id, body)
    return PerfilOut(perfil=service.perfil_out(db, perfil))


@router.post("/{perfil_id}/archive", operation_id="perfis_archive", response_model=PerfilOut,
             responses=_errors(400, 401, 403, 404, 409))
def archive_perfil(perfil_id: UUID, body: VersionIn, actor: RequireUser,
                   db: Db) -> PerfilOut:
    perfil = service.archive_perfil(db, actor, perfil_id, body.version)
    return PerfilOut(perfil=service.perfil_out(db, perfil))


@router.post("/{perfil_id}/restore", operation_id="perfis_restore", response_model=PerfilOut,
             responses=_errors(400, 401, 403, 404, 409))
def restore_perfil(perfil_id: UUID, body: VersionIn, actor: RequireUser,
                   db: Db) -> PerfilOut:
    perfil = service.restore_perfil(db, actor, perfil_id, body.version)
    return PerfilOut(perfil=service.perfil_out(db, perfil))


@router.get("/{perfil_id}/versions", operation_id="perfis_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def perfil_versions(perfil_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return service.perfil_versions(db, perfil_id)


@router.post("/{perfil_id}/revert", operation_id="perfis_revert", response_model=PerfilOut,
             responses=_errors(400, 401, 403, 404, 409))
def revert_perfil(perfil_id: UUID, body: RevertIn, actor: RequireOwner,
                  db: Db) -> PerfilOut:
    perfil = service.revert_perfil(db, actor, perfil_id, body.version, body.to_version)
    return PerfilOut(perfil=service.perfil_out(db, perfil))
