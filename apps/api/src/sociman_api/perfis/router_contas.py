"""Rotas de contas (T015, contracts/http-api.md "Contas"). Dono e membro (R10).

A reversão é só do dono (`RequireOwner`, FR-013).
"""

from uuid import UUID

from fastapi import APIRouter

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis import service_contas
from sociman_api.perfis.schemas import (
    ContaOut,
    CreateContaIn,
    RevertIn,
    UpdateContaIn,
    VersionIn,
    VersionsList,
)
from sociman_api.perfis.service_perfis import conta_out

router = APIRouter(prefix="/api")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.post("/perfis/{perfil_id}/contas", operation_id="contas_create", status_code=201,
             response_model=ContaOut, responses=_errors(400, 401, 403, 404, 409))
def create_conta(perfil_id: UUID, body: CreateContaIn, actor: RequireUser,
                 db: DbSession) -> ContaOut:
    conta = service_contas.create_conta(db, actor, perfil_id, body)
    return ContaOut(conta=conta_out(db, conta))


@router.patch("/contas/{conta_id}", operation_id="contas_update", response_model=ContaOut,
              responses=_errors(400, 401, 403, 404, 409))
def update_conta(conta_id: UUID, body: UpdateContaIn, actor: RequireUser,
                 db: DbSession) -> ContaOut:
    conta = service_contas.update_conta(db, actor, conta_id, body)
    return ContaOut(conta=conta_out(db, conta))


@router.post("/contas/{conta_id}/archive", operation_id="contas_archive", response_model=ContaOut,
             responses=_errors(400, 401, 403, 404, 409))
def archive_conta(conta_id: UUID, body: VersionIn, actor: RequireUser,
                  db: DbSession) -> ContaOut:
    conta = service_contas.archive_conta(db, actor, conta_id, body.version)
    return ContaOut(conta=conta_out(db, conta))


@router.post("/contas/{conta_id}/restore", operation_id="contas_restore", response_model=ContaOut,
             responses=_errors(400, 401, 403, 404, 409))
def restore_conta(conta_id: UUID, body: VersionIn, actor: RequireUser,
                  db: DbSession) -> ContaOut:
    conta = service_contas.restore_conta(db, actor, conta_id, body.version)
    return ContaOut(conta=conta_out(db, conta))


@router.get("/contas/{conta_id}/versions", operation_id="contas_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def list_versions(conta_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service_contas.list_versions(db, conta_id)


@router.post("/contas/{conta_id}/revert", operation_id="contas_revert", response_model=ContaOut,
             responses=_errors(400, 401, 403, 404, 409))
def revert_conta(conta_id: UUID, body: RevertIn, actor: RequireOwner,
                 db: DbSession) -> ContaOut:
    conta = service_contas.revert_conta(db, actor, conta_id, body.version, body.to_version)
    return ContaOut(conta=conta_out(db, conta))
