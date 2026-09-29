"""Rotas de canais-fonte e da descoberta (contracts/http-api.md da 006, "Canais" e
"Descoberta").

Os caminhos evitam os termos do guarda do princípio I (`/api/canais`, `/api/videos-fonte`;
`operationId` `canais_*` e `videos_fonte_*`). O direito e a reversão são só do dono
(`RequireOwner`, princípios II e VII). O cliente do YouTube chega por dependência
(`get_youtube_client`), trocada nos testes.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.canais import service_canais, service_videos
from sociman_api.canais.schemas import (
    CanaisList,
    CanalOut,
    CreateCanalIn,
    DireitoIn,
    Ordem,
    ResolverIn,
    ResolverOut,
    UpdateCanalIn,
    VideoDetalheOut,
    VideosList,
)
from sociman_api.canais.youtube import YoutubeClient, get_youtube_client
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList

router = APIRouter(prefix="/api")

Youtube = Annotated[YoutubeClient, Depends(get_youtube_client)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _out(db: DbSession, canal) -> CanalOut:
    return CanalOut(canal=service_canais.canal_out(db, canal))


# ---- canais ----

@router.post("/canais/resolver", operation_id="canais_resolver", response_model=ResolverOut,
             responses=_errors(400, 401, 403, 404, 429, 502, 503))
def resolver(body: ResolverIn, actor: RequireUser, db: DbSession, yt: Youtube) -> ResolverOut:
    return service_canais.resolver(db, yt, body.entrada)


@router.post("/canais", operation_id="canais_create", status_code=201, response_model=CanalOut,
             responses=_errors(400, 401, 403, 404, 409, 429, 502, 503))
def create_canal(body: CreateCanalIn, actor: RequireUser, db: DbSession,
                 yt: Youtube) -> CanalOut:
    return _out(db, service_canais.create_canal(db, actor, yt, body))


@router.get("/canais", operation_id="canais_list", response_model=CanaisList,
            responses=_errors(401, 403))
def list_canais(actor: RequireUser, db: DbSession, archived: bool = False,
                perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
                q: Annotated[str | None, Query(max_length=200)] = None) -> CanaisList:
    return CanaisList(items=service_canais.list_canais(db, archived, perfil_id, q))


@router.get("/canais/{canal_id}", operation_id="canais_get", response_model=CanalOut,
            responses=_errors(401, 403, 404))
def get_canal(canal_id: UUID, actor: RequireUser, db: DbSession) -> CanalOut:
    return _out(db, service_canais.get_canal(db, canal_id))


@router.patch("/canais/{canal_id}", operation_id="canais_update", response_model=CanalOut,
              responses=_errors(400, 401, 403, 404, 409))
def update_canal(canal_id: UUID, body: UpdateCanalIn, actor: RequireUser,
                 db: DbSession) -> CanalOut:
    return _out(db, service_canais.update_canal(db, actor, canal_id, body))


@router.put("/canais/{canal_id}/direito", operation_id="canais_direito", response_model=CanalOut,
            responses=_errors(400, 401, 403, 404, 409))
def mudar_direito(canal_id: UUID, body: DireitoIn, actor: RequireOwner,
                  db: DbSession) -> CanalOut:
    return _out(db, service_canais.mudar_direito(db, actor, canal_id, body))


@router.post("/canais/{canal_id}/sincronizar", operation_id="canais_sincronizar",
             response_model=CanalOut, responses=_errors(401, 403, 404, 409, 429, 503))
def sincronizar(canal_id: UUID, actor: RequireUser, db: DbSession, yt: Youtube) -> CanalOut:
    return _out(db, service_canais.sincronizar(db, yt, canal_id))


@router.post("/canais/{canal_id}/archive", operation_id="canais_archive",
             response_model=CanalOut, responses=_errors(400, 401, 403, 404, 409))
def archive_canal(canal_id: UUID, body: VersionIn, actor: RequireUser,
                  db: DbSession) -> CanalOut:
    return _out(db, service_canais.archive_canal(db, actor, canal_id, body.version))


@router.post("/canais/{canal_id}/restore", operation_id="canais_restore",
             response_model=CanalOut, responses=_errors(400, 401, 403, 404, 409))
def restore_canal(canal_id: UUID, body: VersionIn, actor: RequireUser,
                  db: DbSession) -> CanalOut:
    return _out(db, service_canais.restore_canal(db, actor, canal_id, body.version))


@router.get("/canais/{canal_id}/versions", operation_id="canais_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def list_versions(canal_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service_canais.list_versions(db, canal_id)


@router.post("/canais/{canal_id}/revert", operation_id="canais_revert", response_model=CanalOut,
             responses=_errors(400, 401, 403, 404, 409))
def revert_canal(canal_id: UUID, body: RevertIn, actor: RequireOwner,
                 db: DbSession) -> CanalOut:
    return _out(db, service_canais.revert_canal(db, actor, canal_id, body.version,
                                                body.to_version))


# ---- descoberta ----

@router.get("/videos-fonte", operation_id="videos_fonte_list", response_model=VideosList,
            responses=_errors(400, 401, 403, 404))
def list_videos(
    actor: RequireUser, db: DbSession,
    perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
    canal_id: Annotated[list[UUID] | None, Query(alias="canalId")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    publicado_desde: Annotated[datetime | None, Query(alias="publicadoDesde")] = None,
    publicado_ate: Annotated[datetime | None, Query(alias="publicadoAte")] = None,
    duracao_min: Annotated[int | None, Query(alias="duracaoMin", ge=0)] = None,
    duracao_max: Annotated[int | None, Query(alias="duracaoMax", ge=0)] = None,
    nao_cortados: Annotated[bool, Query(alias="naoCortados")] = False,
    recomendaveis: bool = True,
    ordem: Ordem = "score",
    limit: Annotated[int, Query(ge=1, le=service_videos.LIMIT_MAX)] = service_videos.LIMIT_PADRAO,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> VideosList:
    return service_videos.list_videos(
        db, perfil_id=perfil_id, canal_ids=canal_id or [], q=q, publicado_desde=publicado_desde,
        publicado_ate=publicado_ate, duracao_min=duracao_min, duracao_max=duracao_max,
        nao_cortados=nao_cortados, recomendaveis=recomendaveis, ordem=ordem, limit=limit,
        cursor=cursor,
    )


@router.get("/videos-fonte/{video_id}", operation_id="videos_fonte_get",
            response_model=VideoDetalheOut, responses=_errors(401, 403, 404))
def get_video(video_id: UUID, actor: RequireUser, db: DbSession) -> VideoDetalheOut:
    return service_videos.get_video(db, video_id)
