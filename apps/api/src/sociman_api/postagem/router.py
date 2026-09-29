"""Rotas de textos, postagens e calendário (contracts/http-api.md da 006, "Postagens", US5).

Dono e membro (`RequireUser`), menos a reversão (`RequireOwner`, princípio VII). `postado` só
muda por esta rota humana (princípio I); nada aqui publica. Não existe rota DELETE.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.ia.cliente import IaClient, get_ia_client
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList
from sociman_api.postagem import schemas, service

router = APIRouter(prefix="/api")

Textos = Annotated[IaClient | None, Depends(get_ia_client)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _out(db: DbSession, postagem) -> schemas.PostagemOut:
    return schemas.PostagemOut(postagem=service.postagem_out(db, postagem))


# ---- sugestões ----

# Deprecated desde a spec 008: o painel usa `POST /api/ia/gerar` (`postagem.textos`).
@router.post("/cortes/{corte_id}/sugestoes", operation_id="postagens_sugerir",
             response_model=schemas.SugestaoOut, deprecated=True,
             responses=_errors(400, 401, 403, 404, 502, 503, 504))
def sugerir(corte_id: UUID, body: schemas.SugestaoIn, actor: RequireUser, db: DbSession,
            client: Textos) -> schemas.SugestaoOut:
    row = service.sugerir(db, actor, corte_id, body, client)
    return schemas.SugestaoOut(sugestao=service.sugestao_out(row))


@router.get("/cortes/{corte_id}/sugestoes", operation_id="postagens_sugestoes",
            response_model=schemas.SugestoesList, responses=_errors(401, 403, 404),
            deprecated=True)
def list_sugestoes(corte_id: UUID, actor: RequireUser, db: DbSession) -> schemas.SugestoesList:
    return schemas.SugestoesList(items=service.list_sugestoes(db, corte_id))


# ---- postagens ----

@router.get("/cortes/{corte_id}/postagens", operation_id="postagens_list",
            response_model=schemas.PostagensList, responses=_errors(401, 403, 404))
def list_postagens(
    corte_id: UUID, actor: RequireUser, db: DbSession,
    archived: Annotated[bool | None, Query(description="Sem o filtro, todas")] = None,
) -> schemas.PostagensList:
    return schemas.PostagensList(items=service.list_postagens(db, corte_id, archived))


@router.post("/cortes/{corte_id}/postagens", operation_id="postagens_create", status_code=201,
             response_model=schemas.PostagemOut, responses=_errors(400, 401, 403, 404, 409))
def create_postagem(corte_id: UUID, body: schemas.CreatePostagemIn, actor: RequireUser,
                    db: DbSession) -> schemas.PostagemOut:
    return _out(db, service.create_postagem(db, actor, corte_id, body))


@router.get("/postagens/{postagem_id}", operation_id="postagens_get",
            response_model=schemas.PostagemOut, responses=_errors(401, 403, 404))
def get_postagem(postagem_id: UUID, actor: RequireUser, db: DbSession) -> schemas.PostagemOut:
    return _out(db, service.get_postagem_or_404(db, postagem_id))


@router.patch("/postagens/{postagem_id}", operation_id="postagens_update",
              response_model=schemas.PostagemOut, responses=_errors(400, 401, 403, 404, 409))
def update_postagem(postagem_id: UUID, body: schemas.UpdatePostagemIn, actor: RequireUser,
                    db: DbSession) -> schemas.PostagemOut:
    return _out(db, service.update_postagem(db, actor, postagem_id, body))


@router.post("/postagens/{postagem_id}/postado", operation_id="postagens_marcar_postado",
             response_model=schemas.PostagemOut, responses=_errors(400, 401, 403, 404, 409))
def marcar_postado(postagem_id: UUID, body: schemas.PostadoIn, actor: RequireUser,
                   db: DbSession) -> schemas.PostagemOut:
    return _out(db, service.marcar_postado(db, actor, postagem_id, body.version,
                                           body.posted_url))


@router.post("/postagens/{postagem_id}/archive", operation_id="postagens_archive",
             response_model=schemas.PostagemOut, responses=_errors(400, 401, 403, 404, 409))
def archive_postagem(postagem_id: UUID, body: VersionIn, actor: RequireUser,
                     db: DbSession) -> schemas.PostagemOut:
    return _out(db, service.archive_postagem(db, actor, postagem_id, body.version))


@router.post("/postagens/{postagem_id}/restore", operation_id="postagens_restore",
             response_model=schemas.PostagemOut, responses=_errors(400, 401, 403, 404, 409))
def restore_postagem(postagem_id: UUID, body: VersionIn, actor: RequireUser,
                     db: DbSession) -> schemas.PostagemOut:
    return _out(db, service.restore_postagem(db, actor, postagem_id, body.version))


@router.get("/postagens/{postagem_id}/versions", operation_id="postagens_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def postagem_versions(postagem_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service.list_versions(db, postagem_id)


@router.post("/postagens/{postagem_id}/revert", operation_id="postagens_revert",
             response_model=schemas.PostagemOut, responses=_errors(400, 401, 403, 404, 409))
def revert_postagem(postagem_id: UUID, body: RevertIn, actor: RequireOwner,
                    db: DbSession) -> schemas.PostagemOut:
    return _out(db, service.revert_postagem(db, actor, postagem_id, body.version,
                                            body.to_version))


# ---- calendário ----

@router.get("/calendario", operation_id="postagens_calendario",
            response_model=schemas.CalendarioOut, responses=_errors(400, 401, 403))
def calendario(
    actor: RequireUser, db: DbSession,
    de: Annotated[date, Query(description="Primeiro dia (local, APP_TZ)")],
    ate: Annotated[date, Query(description="Último dia, inclusive (até 62 dias)")],
    perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
    plataforma: Annotated[Platform | None, Query()] = None,
) -> schemas.CalendarioOut:
    return service.calendario(db, de, ate, perfil_id, plataforma)
