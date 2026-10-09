"""Rotas de uma cena, das tomadas e do vínculo com o conteúdo (contracts/http-api.md da 010).
Dono e membro (`RequireUser`), menos as reversões (`RequireHumanOwner`). Sem DELETE.

O envio da tomada não é `UploadFile`: como o vídeo próprio da 014, o HD e o `Content-Length` são
conferidos antes e o multipart (`file`) é lido em streaming; o schema vai por `openapi_extra`.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from sociman_api.auth.deps import RequireHumanOwner, RequireUser
from sociman_api.cenas import schemas, tomadas, usos
from sociman_api.cenas import service as svc
from sociman_api.cenas.models import CenaStatus
from sociman_api.cortes import service as cortes_service
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis import base as perfil_base
from sociman_api.perfis.schemas import RevertIn, VersionsList

router = APIRouter(prefix="/api")

_ARQUIVO_BODY = {
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object",
            "required": ["file"],
            "properties": {
                "file": {"type": "string", "format": "binary",
                         "description": "MP4, MOV ou WebM, de 1 a 30 s, até 200 MB, qualquer "
                                        "proporção"},
            },
        }}},
    },
}


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- lista e criação da agência (spec 029) ----

@router.get("/cenas", operation_id="cenas_listar_agencia", response_model=schemas.CenasList,
            responses=_errors(400, 401, 403))
def listar_agencia(
    actor: RequireUser, db: DbSession,
    perfil_id: Annotated[str | None, Query(
        alias="perfilId", max_length=40,
        description="Perfil base: ausente = todas; `sem` = sem perfil base; ou um id")] = None,
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
    """As cenas da biblioteca da agência, de qualquer perfil base, com o nome dele."""
    return svc.listar(db, perfil_base.filtro_perfil(perfil_id), q=q, status=status or (),
                      avatar_id=avatar_id, cenario_id=cenario_id,
                      produto_imagem_id=produto_imagem_id, produto_id=produto_id,
                      tags=tag or (), arquivadas=arquivadas, cursor=cursor, limit=limit)


@router.post("/cenas", operation_id="cenas_criar_agencia", status_code=201,
             response_model=schemas.Cena, responses=_errors(400, 401, 403, 404, 409, 422))
def criar_agencia(body: schemas.CenaAgenciaIn, actor: RequireUser,
                  db: DbSession) -> schemas.Cena:
    """Cena nova com o perfil base opcional (`perfilId`; pode estar arquivado)."""
    cena = svc.criar(db, actor, body.perfil_id, body, exige_ativo=False)
    return svc.cena_out(db, cena, actor)


# ---- tomadas por id (antes de /cenas/{id}…) ----

@router.patch("/cenas/tomadas/{tomada_id}", operation_id="cenas_tomadas_update",
              response_model=schemas.Tomada, responses=_errors(400, 401, 403, 404, 409))
def tomada_update(tomada_id: UUID, body: schemas.NotaIn, actor: RequireUser,
                  db: DbSession) -> schemas.Tomada:
    t = tomadas.editar_nota(db, actor, tomada_id, body.version, body.nota)
    return tomadas.tomada_out(db, t, actor)


@router.post("/cenas/tomadas/{tomada_id}/arquivar", operation_id="cenas_tomadas_archive",
             response_model=schemas.Tomada, responses=_errors(400, 401, 403, 404, 409))
def tomada_archive(tomada_id: UUID, body: schemas.VersionIn, actor: RequireUser,
                   db: DbSession) -> schemas.Tomada:
    return tomadas.tomada_out(db, tomadas.arquivar(db, actor, tomada_id, body.version), actor)


@router.post("/cenas/tomadas/{tomada_id}/restaurar", operation_id="cenas_tomadas_restore",
             response_model=schemas.Tomada, responses=_errors(400, 401, 403, 404, 409))
def tomada_restore(tomada_id: UUID, body: schemas.VersionIn, actor: RequireUser,
                   db: DbSession) -> schemas.Tomada:
    return tomadas.tomada_out(db, tomadas.restaurar(db, actor, tomada_id, body.version), actor)


@router.get("/cenas/tomadas/{tomada_id}/versions", operation_id="cenas_tomadas_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def tomada_versions(tomada_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return tomadas.versoes(db, tomada_id)


@router.post("/cenas/tomadas/{tomada_id}/revert", operation_id="cenas_tomadas_revert",
             response_model=schemas.Tomada, responses=_errors(400, 401, 403, 404, 409))
def tomada_revert(tomada_id: UUID, body: RevertIn, actor: RequireHumanOwner,
                  db: DbSession) -> schemas.Tomada:
    t = tomadas.reverter(db, actor, tomada_id, body.version, body.to_version)
    return tomadas.tomada_out(db, t, actor)


# ---- cena ----

@router.get("/cenas/{cena_id}", operation_id="cenas_get", response_model=schemas.Cena,
            responses=_errors(401, 403, 404))
def get(cena_id: UUID, actor: RequireUser, db: DbSession) -> schemas.Cena:
    return svc.obter(db, cena_id, actor)


@router.patch("/cenas/{cena_id}", operation_id="cenas_update", response_model=schemas.Cena,
              responses=_errors(400, 401, 403, 404, 409, 422))
def update(cena_id: UUID, body: schemas.CenaPatch, actor: RequireUser,
           db: DbSession) -> schemas.Cena:
    return svc.cena_out(db, svc.editar(db, actor, cena_id, body), actor)


@router.post("/cenas/{cena_id}/duplicar", operation_id="cenas_duplicar", status_code=201,
             response_model=schemas.Cena, responses=_errors(401, 403, 404, 409))
def duplicar(cena_id: UUID, actor: RequireUser, db: DbSession) -> schemas.Cena:
    return svc.cena_out(db, svc.duplicar(db, actor, cena_id), actor)


@router.post("/cenas/{cena_id}/pronta", operation_id="cenas_pronta", response_model=schemas.Cena,
             responses=_errors(400, 401, 403, 404, 409, 422))
def pronta(cena_id: UUID, body: schemas.VersionIn, actor: RequireUser,
           db: DbSession) -> schemas.Cena:
    return svc.cena_out(db, svc.marcar_pronta(db, actor, cena_id, body.version), actor)


@router.post("/cenas/{cena_id}/rascunho", operation_id="cenas_rascunho",
             response_model=schemas.Cena, responses=_errors(400, 401, 403, 404, 409))
def rascunho(cena_id: UUID, body: schemas.VersionIn, actor: RequireUser,
             db: DbSession) -> schemas.Cena:
    return svc.cena_out(db, svc.voltar_rascunho(db, actor, cena_id, body.version), actor)


@router.post("/cenas/{cena_id}/remontar", operation_id="cenas_remontar",
             response_model=schemas.Cena, responses=_errors(400, 401, 403, 404, 409))
def remontar(cena_id: UUID, body: schemas.VersionIn, actor: RequireUser,
             db: DbSession) -> schemas.Cena:
    return svc.cena_out(db, svc.remontar(db, actor, cena_id, body.version), actor)


@router.post("/cenas/{cena_id}/arquivar", operation_id="cenas_archive",
             response_model=schemas.Cena, responses=_errors(400, 401, 403, 404, 409))
def archive(cena_id: UUID, body: schemas.VersionIn, actor: RequireUser,
            db: DbSession) -> schemas.Cena:
    return svc.cena_out(db, svc.arquivar(db, actor, cena_id, body.version), actor)


@router.post("/cenas/{cena_id}/restaurar", operation_id="cenas_restore",
             response_model=schemas.Cena, responses=_errors(400, 401, 403, 404, 409))
def restore(cena_id: UUID, body: schemas.VersionIn, actor: RequireUser,
            db: DbSession) -> schemas.Cena:
    return svc.cena_out(db, svc.restaurar(db, actor, cena_id, body.version), actor)


@router.get("/cenas/{cena_id}/versions", operation_id="cenas_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def versions(cena_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return svc.versoes(db, cena_id)


@router.post("/cenas/{cena_id}/revert", operation_id="cenas_revert",
             response_model=schemas.Cena, responses=_errors(400, 401, 403, 404, 409))
def revert(cena_id: UUID, body: RevertIn, actor: RequireHumanOwner,
           db: DbSession) -> schemas.Cena:
    cena = svc.reverter(db, actor, cena_id, body.version, body.to_version)
    return svc.cena_out(db, cena, actor)


# ---- tomadas da cena ----

@router.get("/cenas/{cena_id}/tomadas", operation_id="cenas_tomadas_list",
            response_model=schemas.TomadasList, responses=_errors(401, 403, 404))
def tomadas_list(cena_id: UUID, actor: RequireUser, db: DbSession,
                 arquivadas: Annotated[bool, Query()] = False) -> schemas.TomadasList:
    return tomadas.listar(db, cena_id, arquivadas, actor)


@router.post("/cenas/{cena_id}/tomadas", operation_id="cenas_tomadas_upload", status_code=201,
             response_model=schemas.Tomada, openapi_extra=_ARQUIVO_BODY,
             responses=_errors(400, 401, 403, 404, 409, 413, 503, 507))
async def tomadas_upload(cena_id: UUID, request: Request, actor: RequireUser,
                         db: DbSession) -> schemas.Tomada:
    await run_in_threadpool(tomadas.precheck, db, cena_id,
                            request.headers.get("content-length"))
    up = await tomadas.receive(request)
    try:
        t = await run_in_threadpool(tomadas.criar, db, actor, cena_id, up)
        return await run_in_threadpool(tomadas.tomada_out, db, t, actor)
    finally:
        cortes_service.cleanup_spool(up)


@router.post("/cenas/{cena_id}/tomadas/{tomada_id}/escolher",
             operation_id="cenas_tomadas_escolher", response_model=schemas.Cena,
             responses=_errors(400, 401, 403, 404, 409))
def tomadas_escolher(cena_id: UUID, tomada_id: UUID, body: schemas.VersionIn,
                     actor: RequireUser, db: DbSession) -> schemas.Cena:
    cena = tomadas.escolher(db, actor, cena_id, tomada_id, body.version)
    return svc.cena_out(db, cena, actor)


# ---- vínculo com o conteúdo ----

@router.get("/conteudos/{conteudo_id}/cenas", operation_id="conteudos_cenas_get",
            response_model=schemas.CenasResumoList, responses=_errors(401, 403, 404))
def conteudo_cenas(conteudo_id: UUID, actor: RequireUser,
                   db: DbSession) -> schemas.CenasResumoList:
    return usos.listar(db, conteudo_id)


@router.put("/conteudos/{conteudo_id}/cenas", operation_id="conteudos_cenas_put",
            response_model=schemas.UsosOut, responses=_errors(400, 401, 403, 404, 409, 422))
def conteudo_cenas_put(conteudo_id: UUID, body: schemas.UsosIn, actor: RequireUser,
                       db: DbSession) -> schemas.UsosOut:
    return usos.definir(db, actor, conteudo_id, body)
