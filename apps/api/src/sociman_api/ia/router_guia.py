"""Rotas do guia de comunicação (contracts/http-api.md da spec 017): `/api/perfis/{id}/guia` e
`/api/contas/{id}/guia`.

GET e `versions`: dono e membro (`RequireUser`). PUT e `revert`: só o dono (`RequireOwner`).
Não existe rota DELETE (limpar o guia = salvar vazio). O montar e o testar ficam em
`ia/router.py` (`/api/ia/guia/*`).
"""

from uuid import UUID

from fastapi import APIRouter

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.ia import schemas_guia as schemas
from sociman_api.ia import service_guia as service
from sociman_api.perfis.schemas import RevertIn, VersionsList

router = APIRouter(prefix="/api")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- guia do perfil ----

@router.get("/perfis/{perfil_id}/guia", operation_id="guias_perfil_get",
            response_model=schemas.GuiaOut, responses=_errors(401, 403, 404))
def perfil_get(perfil_id: UUID, actor: RequireUser, db: DbSession) -> schemas.GuiaOut:
    return service.obter_perfil(db, perfil_id)


@router.put("/perfis/{perfil_id}/guia", operation_id="guias_perfil_update",
            response_model=schemas.GuiaOut, responses=_errors(400, 401, 403, 404, 409))
def perfil_update(perfil_id: UUID, body: schemas.GuiaIn, actor: RequireOwner,
                  db: DbSession) -> schemas.GuiaOut:
    return service.put_perfil(db, actor, perfil_id, body)


@router.get("/perfis/{perfil_id}/guia/versions", operation_id="guias_perfil_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def perfil_versions(perfil_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service.versions_perfil(db, perfil_id)


@router.post("/perfis/{perfil_id}/guia/revert", operation_id="guias_perfil_revert",
             response_model=schemas.GuiaOut, responses=_errors(400, 401, 403, 404, 409))
def perfil_revert(perfil_id: UUID, body: RevertIn, actor: RequireOwner,
                  db: DbSession) -> schemas.GuiaOut:
    return service.revert_perfil(db, actor, perfil_id, body)


# ---- guia da conta ----

@router.get("/contas/{conta_id}/guia", operation_id="guias_conta_get",
            response_model=schemas.GuiaContaOut, responses=_errors(401, 403, 404))
def conta_get(conta_id: UUID, actor: RequireUser, db: DbSession) -> schemas.GuiaContaOut:
    return service.obter_conta(db, conta_id)


@router.put("/contas/{conta_id}/guia", operation_id="guias_conta_update",
            response_model=schemas.GuiaContaOut, responses=_errors(400, 401, 403, 404, 409))
def conta_update(conta_id: UUID, body: schemas.GuiaIn, actor: RequireOwner,
                 db: DbSession) -> schemas.GuiaContaOut:
    return service.put_conta(db, actor, conta_id, body)


@router.get("/contas/{conta_id}/guia/versions", operation_id="guias_conta_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def conta_versions(conta_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service.versions_conta(db, conta_id)


@router.post("/contas/{conta_id}/guia/revert", operation_id="guias_conta_revert",
             response_model=schemas.GuiaContaOut, responses=_errors(400, 401, 403, 404, 409))
def conta_revert(conta_id: UUID, body: RevertIn, actor: RequireOwner,
                 db: DbSession) -> schemas.GuiaContaOut:
    return service.revert_conta(db, actor, conta_id, body)
