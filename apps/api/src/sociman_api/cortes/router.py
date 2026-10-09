"""Rotas dos cortes (T026, contracts/http-api.md "Cortes"): dono e membro (`RequireUser`).
Não existe rota DELETE (FR-016, SC-005).

O envio não declara o corpo como `UploadFile`: o FastAPI leria o multipart inteiro antes da
rota. Aqui o HD e o `Content-Length` são conferidos primeiro, e o corpo é lido em streaming
(service.receive). O schema do multipart vai para o OpenAPI por `openapi_extra`.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from sociman_api.auth.deps import RequireUser
from sociman_api.cortes import service
from sociman_api.cortes.models import CorteOrigem, CorteStatus
from sociman_api.cortes.render import HOOK_MAX_CHARS
from sociman_api.cortes.schemas import (
    AplicarMarcaIn,
    Armazenamento,
    CorteOut,
    CortesList,
    HookIn,
)
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.schemas import VersionIn, VersionsList

router = APIRouter()

Db = DbSession

_UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object",
            "required": ["file", "hookText"],
            "properties": {
                "file": {"type": "string", "format": "binary",
                         "description": "MP4, MOV ou WebM, até 500 MB e 3 minutos"},
                "hookText": {"type": "string", "minLength": 1, "maxLength": HOOK_MAX_CHARS,
                             "description": "Texto do gancho (até 3 linhas no kit)"},
            },
        }}},
    },
}


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.post("/api/perfis/{perfil_id}/cortes", operation_id="cortes_upload",
             response_model=CorteOut, status_code=201, openapi_extra=_UPLOAD_BODY,
             responses=_errors(400, 401, 403, 404, 409, 413, 503, 507))
async def upload_corte(perfil_id: UUID, request: Request, actor: RequireUser,
                       db: Db) -> CorteOut:
    await run_in_threadpool(service.precheck, db, perfil_id,
                            request.headers.get("content-length"))
    up = await service.receive(request)
    try:
        corte = await run_in_threadpool(service.create_corte, db, actor, perfil_id, up)
        return CorteOut(corte=await run_in_threadpool(service.corte_out, db, corte))
    finally:
        service.cleanup_spool(up)


@router.get("/api/perfis/{perfil_id}/cortes", operation_id="cortes_list",
            response_model=CortesList, responses=_errors(401, 403, 404))
def list_cortes(
    perfil_id: UUID, actor: RequireUser, db: Db,
    status: Annotated[CorteStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[datetime | None, Query(description="Cursor: createdAt do último item")]
    = None,
    origem: Annotated[CorteOrigem | None, Query()] = None,
    envio_id: Annotated[UUID | None, Query(alias="envioId")] = None,
    archived: Annotated[bool, Query(description="true: só os arquivados")] = False,
) -> CortesList:
    return CortesList(items=service.list_cortes(db, perfil_id, status, limit, before, origem,
                                                envio_id, archived))


@router.get("/api/armazenamento", operation_id="armazenamento_get",
            response_model=Armazenamento, responses=_errors(401, 403))
def get_armazenamento(actor: RequireUser, db: Db) -> Armazenamento:
    return service.armazenamento(db)


@router.get("/api/cortes/{corte_id}", operation_id="cortes_get", response_model=CorteOut,
            responses=_errors(401, 403, 404))
def get_corte(corte_id: UUID, actor: RequireUser, db: Db) -> CorteOut:
    return CorteOut(corte=service.corte_out(db, service.get_corte_or_404(db, corte_id)))


@router.post("/api/cortes/{corte_id}/retry", operation_id="cortes_retry",
             response_model=CorteOut, responses=_errors(400, 401, 403, 404, 409))
def retry_corte(corte_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> CorteOut:
    return CorteOut(corte=service.corte_out(db, service.retry(db, actor, corte_id,
                                                              body.version)))


@router.get("/api/cortes/{corte_id}/versions", operation_id="cortes_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def corte_versions(corte_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return service.corte_versions(db, corte_id)


# ---- revisão dos clipes do OpenShorts (spec 006, T057) ----

@router.post("/api/cortes/aplicar-marca", operation_id="cortes_aplicar_marca",
             response_model=CortesList, responses=_errors(400, 401, 403, 404, 409, 503, 507))
def aplicar_marca(body: AplicarMarcaIn, actor: RequireUser, db: Db) -> CortesList:
    """`revisao` → `na_fila` com o kit atual (até 30, tudo ou nada)."""
    return CortesList(items=service.cortes_out(db, service.aplicar_marca(db, actor, body.items)))


@router.patch("/api/cortes/{corte_id}", operation_id="cortes_update_hook",
              response_model=CorteOut, responses=_errors(400, 401, 403, 404, 409, 503, 507))
def update_hook(corte_id: UUID, body: HookIn, actor: RequireUser, db: Db) -> CorteOut:
    """Edita o gancho de um clipe em `revisao`."""
    corte = service.editar_gancho(db, actor, corte_id, body.version, body.hook_text)
    return CorteOut(corte=service.corte_out(db, corte))


@router.post("/api/cortes/{corte_id}/archive", operation_id="cortes_archive",
             response_model=CorteOut, responses=_errors(400, 401, 403, 404, 409))
def archive_corte(corte_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> CorteOut:
    return CorteOut(corte=service.corte_out(db, service.arquivar(db, actor, corte_id,
                                                                 body.version)))


@router.post("/api/cortes/{corte_id}/restore", operation_id="cortes_restore",
             response_model=CorteOut, responses=_errors(400, 401, 403, 404, 409))
def restore_corte(corte_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> CorteOut:
    return CorteOut(corte=service.corte_out(db, service.restaurar(db, actor, corte_id,
                                                                  body.version)))
