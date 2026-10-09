"""Rotas de padrões de corte e envios ao OpenShorts (contracts/http-api.md da 006).

Dono e membro (`RequireUser`); só a reversão dos padrões é do dono (princípio VII). Não existe
rota DELETE, e nenhum caminho nem `operationId` fala em publicar (princípio I).

O envio por arquivo não declara o corpo como `UploadFile` (o FastAPI leria o multipart inteiro
antes da rota): o HD e o `Content-Length` são conferidos primeiro, e o corpo é lido em streaming
(envios/upload.py). O schema do multipart vai para o OpenAPI por `openapi_extra`.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.cortes import service as cortes_service
from sociman_api.db import DbSession
from sociman_api.envios import schemas, service_envios, service_padroes, upload
from sociman_api.envios.models import EnvioStatus
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList

router = APIRouter(prefix="/api")

Db = DbSession

_ARQUIVO_BODY = {
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object",
            "required": ["file"],
            "properties": {
                "file": {"type": "string", "format": "binary",
                         "description": "MP4, MOV ou WebM, de 45 s a 3 h, até 2 GB"},
                "titulo": {"type": "string", "maxLength": 200,
                           "description": "Título do vídeo (padrão: o nome do arquivo)"},
            },
        }}},
    },
}


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- padrões de corte ----

@router.get("/perfis/{perfil_id}/padroes-corte", operation_id="envios_padroes_get",
            response_model=schemas.PadroesCorteOut, responses=_errors(401, 403, 404))
def get_padroes(perfil_id: UUID, actor: RequireUser, db: Db) -> schemas.PadroesCorteOut:
    return schemas.PadroesCorteOut(padroes=service_padroes.get_padroes(db, perfil_id))


@router.put("/perfis/{perfil_id}/padroes-corte", operation_id="envios_padroes_put",
            response_model=schemas.PadroesCorteOut, responses=_errors(400, 401, 403, 404, 409))
def put_padroes(perfil_id: UUID, body: schemas.PadroesCorteIn, actor: RequireUser,
                db: Db) -> schemas.PadroesCorteOut:
    return schemas.PadroesCorteOut(padroes=service_padroes.put_padroes(db, actor, perfil_id,
                                                                       body))


@router.get("/perfis/{perfil_id}/padroes-corte/versions",
            operation_id="envios_padroes_versions", response_model=VersionsList,
            responses=_errors(401, 403, 404))
def padroes_versions(perfil_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return service_padroes.padroes_versions(db, perfil_id)


@router.post("/perfis/{perfil_id}/padroes-corte/revert", operation_id="envios_padroes_revert",
             response_model=schemas.PadroesCorteOut,
             responses=_errors(400, 401, 403, 404, 409))
def revert_padroes(perfil_id: UUID, body: RevertIn, actor: RequireOwner,
                   db: Db) -> schemas.PadroesCorteOut:
    return schemas.PadroesCorteOut(padroes=service_padroes.revert_padroes(
        db, actor, perfil_id, body.version, body.to_version))


# ---- seleção (US2) ----

@router.post("/perfis/{perfil_id}/envios", operation_id="envios_selecionar",
             response_model=schemas.EnvioOut, status_code=201,
             responses=_errors(400, 401, 403, 404, 409))
def selecionar(perfil_id: UUID, body: schemas.SelecionarIn, actor: RequireUser,
               db: Db) -> schemas.EnvioOut:
    """Vídeo de canal (`videoFonteId`) ou avulso por link (`url`, `titulo?`) → `selecionado`."""
    envio = service_envios.selecionar(db, actor, perfil_id, body)
    return schemas.EnvioOut(envio=service_envios.envio_out(db, envio))


@router.post("/perfis/{perfil_id}/envios/arquivo", operation_id="envios_arquivo",
             response_model=schemas.EnvioOut, status_code=201, openapi_extra=_ARQUIVO_BODY,
             responses=_errors(400, 401, 403, 404, 409, 413, 503, 507))
async def enviar_arquivo(perfil_id: UUID, request: Request, actor: RequireUser,
                         db: Db) -> schemas.EnvioOut:
    """Avulso por arquivo (até 2 GB, de 45 s a 3 h) → `selecionado`."""
    await run_in_threadpool(upload.precheck, db, perfil_id,
                            request.headers.get("content-length"))
    up = await upload.receive(request)
    try:
        envio = await run_in_threadpool(upload.create, db, actor, perfil_id, up)
        return schemas.EnvioOut(envio=await run_in_threadpool(service_envios.envio_out, db,
                                                              envio))
    finally:
        cortes_service.cleanup_spool(up)


# ---- envios ----

@router.get("/envios", operation_id="envios_list", response_model=schemas.EnviosList,
            responses=_errors(401, 403))
def list_envios(
    actor: RequireUser, db: Db,
    perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
    status: Annotated[list[EnvioStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[datetime | None, Query(description="Cursor: createdAt do último item")]
    = None,
) -> schemas.EnviosList:
    return schemas.EnviosList(items=service_envios.listar(db, perfil_id, status, limit, before))


@router.post("/envios/enviar", operation_id="envios_enviar", response_model=schemas.EnviosList,
             responses=_errors(400, 401, 403, 404, 409))
def enviar(body: schemas.EnviarIn, actor: RequireUser, db: Db) -> schemas.EnviosList:
    """Envia ao OpenShorts (até 20, tudo ou nada). Canal `sem_acordo` ou avulso exige
    `confirmarAviso` (409 `aviso_direito`, princípio II)."""
    envios = service_envios.enviar(db, actor, body)
    return schemas.EnviosList(items=service_envios.envios_out(db, envios))


@router.get("/envios/{envio_id}", operation_id="envios_get",
            response_model=schemas.EnvioDetalhe, responses=_errors(401, 403, 404))
def get_envio(envio_id: UUID, actor: RequireUser, db: Db) -> schemas.EnvioDetalhe:
    return service_envios.detalhe(db, envio_id)


@router.post("/envios/{envio_id}/confirmar-qualidade", operation_id="envios_confirmar_qualidade",
             response_model=schemas.EnvioOut, responses=_errors(400, 401, 403, 404, 409))
def confirmar_qualidade(envio_id: UUID, body: schemas.ConfirmarQualidadeIn, actor: RequireUser,
                        db: Db) -> schemas.EnvioOut:
    envio = service_envios.confirmar_qualidade(db, actor, envio_id, body.version, body.enviar)
    return schemas.EnvioOut(envio=service_envios.envio_out(db, envio))


@router.post("/envios/{envio_id}/retry", operation_id="envios_retry",
             response_model=schemas.EnvioOut, responses=_errors(400, 401, 403, 404, 409))
def retry(envio_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> schemas.EnvioOut:
    envio = service_envios.retry(db, actor, envio_id, body.version)
    return schemas.EnvioOut(envio=service_envios.envio_out(db, envio))


@router.post("/envios/{envio_id}/archive", operation_id="envios_archive",
             response_model=schemas.EnvioOut, responses=_errors(400, 401, 403, 404, 409))
def archive(envio_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> schemas.EnvioOut:
    """Descarta (`descartado`, sem apagar): só em `selecionado`, `falhou`, `sem_clipes` e
    `pronto`."""
    envio = service_envios.descartar(db, actor, envio_id, body.version)
    return schemas.EnvioOut(envio=service_envios.envio_out(db, envio))


@router.get("/envios/{envio_id}/versions", operation_id="envios_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def envio_versions(envio_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return service_envios.envio_versions(db, envio_id)
