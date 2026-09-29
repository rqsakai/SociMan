"""Descoberta de vídeos dos canais-fonte (US2, contracts/http-api.md "Descoberta").

Os filtros e a ordem ficam no SQL; a paginação é por cursor opaco (keyset estável por
`(ordem, id)`, ambos decrescentes). Com `perfilId`, o score exibido já tem o fator "já
cortado" (× 0,3) e a ordem `score` usa esse valor. Canal arquivado sai da descoberta.
"""

import base64
import binascii
import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import ColumnElement, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from sociman_api import imaging
from sociman_api.canais import schemas
from sociman_api.canais.models import CanalFonte, CanalPerfil, VideoFonte, VideoMetrica
from sociman_api.canais.score import FATOR_JA_CORTADO, score_exibido
from sociman_api.envios.models import Envio, EnvioStatus
from sociman_api.errors import ApiError
from sociman_api.perfis.service_perfis import get_perfil_or_404

LIMIT_PADRAO = 50
LIMIT_MAX = 100
METRICAS = 50
THUMB_W, THUMB_H = 320, 180
# "Já cortado": envio do vídeo para o perfil que passou da seleção e não foi descartado.
_NAO_CORTADO = (EnvioStatus.selecionado, EnvioStatus.descartado)


def video_url(youtube_video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={youtube_video_id}"


def _invalido(message: str) -> ApiError:
    return ApiError(400, "validation_error", message)


def _ja_cortado_expr(perfil_id: uuid.UUID) -> ColumnElement[bool]:
    return exists().where(
        Envio.video_fonte_id == VideoFonte.id,
        Envio.perfil_id == perfil_id,
        Envio.archived_at.is_(None),
        Envio.status.not_in(_NAO_CORTADO),
    )


def _chave(ordem: str, perfil_id: uuid.UUID | None) -> ColumnElement[Any]:
    if ordem == "views":
        return func.coalesce(VideoFonte.views, -1)
    if ordem == "vph":
        return func.coalesce(VideoFonte.vph_recente, -1)
    if ordem == "data":
        return VideoFonte.published_at
    if perfil_id is None:
        return VideoFonte.score
    return case((_ja_cortado_expr(perfil_id),
                 func.round(VideoFonte.score * FATOR_JA_CORTADO, 1)),
                else_=VideoFonte.score)


# ---- cursor ----

def _codificar(ordem: str, valor: Any, video_id: uuid.UUID) -> str:
    raw = json.dumps({"o": ordem, "v": str(valor), "id": str(video_id)})
    return base64.urlsafe_b64encode(raw.encode()).rstrip(b"=").decode()


def _decodificar(cursor: str, ordem: str) -> tuple[Any, uuid.UUID]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if data["o"] != ordem:
            raise ValueError("cursor de outra ordem")
        video_id = uuid.UUID(data["id"])
        raw = data["v"]
        if ordem == "data":
            valor: Any = datetime.fromisoformat(raw)
        elif ordem == "views":
            valor = int(raw)
        else:
            valor = Decimal(raw)
        return valor, video_id
    except (binascii.Error, ValueError, KeyError, TypeError, InvalidOperation,
            json.JSONDecodeError) as exc:
        raise _invalido("Cursor inválido; recarregue a lista") from exc


# ---- saída ----

def videos_out(db: Session, videos: Sequence[VideoFonte],
               perfil_id: uuid.UUID | None = None) -> list[schemas.VideoFonte]:
    if not videos:
        return []
    canais = {c.id: c for c in db.scalars(
        select(CanalFonte).where(CanalFonte.id.in_({v.canal_id for v in videos})))}
    envios = db.execute(
        select(Envio.video_fonte_id, Envio.perfil_id, Envio.id, Envio.status)
        .where(Envio.video_fonte_id.in_([v.id for v in videos]), Envio.archived_at.is_(None),
               Envio.status != EnvioStatus.descartado)
        .order_by(Envio.created_at, Envio.id)
    ).all()
    cortados: dict[uuid.UUID, list[schemas.JaCortado]] = {}
    selecionados: dict[uuid.UUID, list[schemas.Selecionado]] = {}
    for vid, pid, eid, status in envios:
        if status == EnvioStatus.selecionado:
            selecionados.setdefault(vid, []).append(
                schemas.Selecionado(perfil_id=pid, envio_id=eid))
        else:
            cortados.setdefault(vid, []).append(
                schemas.JaCortado(perfil_id=pid, envio_id=eid, status=status.value))
    out = []
    for v in videos:
        canal = canais[v.canal_id]
        ja = cortados.get(v.id, [])
        cortado_no_perfil = perfil_id is not None and any(j.perfil_id == perfil_id for j in ja)
        out.append(schemas.VideoFonte(
            id=v.id,
            canal=schemas.CanalRef(id=canal.id, title=canal.title, direito=canal.direito),
            youtube_video_id=v.youtube_video_id, url=video_url(v.youtube_video_id),
            title=v.title, thumbnail_url=imaging.remote_url(v.thumbnail_url, THUMB_W, THUMB_H),
            published_at=v.published_at, duration_s=v.duration_s, live=v.live,
            disponivel=v.disponivel, views=v.views, likes=v.likes, comments=v.comments,
            vph_recente=float(v.vph_recente) if v.vph_recente is not None else None,
            score=float(score_exibido(v.score, cortado_no_perfil)),
            score_reason=v.score_reason,
            score_detail=schemas.ScoreDetail.model_validate(v.score_detail or {}),
            recomendavel=v.recomendavel, ja_cortado=ja, selecionado=selecionados.get(v.id, []),
        ))
    return out


# ---- consultas ----

def list_videos(
    db: Session, *, perfil_id: uuid.UUID | None = None,
    canal_ids: Sequence[uuid.UUID] = (), q: str | None = None,
    publicado_desde: datetime | None = None, publicado_ate: datetime | None = None,
    duracao_min: int | None = None, duracao_max: int | None = None,
    nao_cortados: bool = False, recomendaveis: bool = True, ordem: str = "score",
    limit: int = LIMIT_PADRAO, cursor: str | None = None,
) -> schemas.VideosList:
    if nao_cortados and perfil_id is None:
        raise _invalido("O filtro \"não cortados\" precisa de um perfil")
    if duracao_min is not None and duracao_max is not None and duracao_min > duracao_max:
        raise _invalido("A duração mínima é maior que a máxima")
    if publicado_desde and publicado_ate and publicado_desde > publicado_ate:
        raise _invalido("O período começa depois de terminar")
    if perfil_id is not None:
        get_perfil_or_404(db, perfil_id)

    filtros: list[ColumnElement[bool]] = [CanalFonte.archived_at.is_(None)]
    if perfil_id is not None:
        filtros.append(VideoFonte.canal_id.in_(
            select(CanalPerfil.canal_id).where(CanalPerfil.perfil_id == perfil_id)))
    if canal_ids:
        filtros.append(VideoFonte.canal_id.in_(list(canal_ids)))
    if q and q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filtros.append(VideoFonte.title.ilike(f"%{term}%", escape="\\"))
    if publicado_desde is not None:
        filtros.append(VideoFonte.published_at >= publicado_desde)
    if publicado_ate is not None:
        filtros.append(VideoFonte.published_at <= publicado_ate)
    if duracao_min is not None:
        filtros.append(VideoFonte.duration_s >= duracao_min)
    if duracao_max is not None:
        filtros.append(VideoFonte.duration_s <= duracao_max)
    if nao_cortados and perfil_id is not None:
        filtros.append(~_ja_cortado_expr(perfil_id))
    if recomendaveis:
        filtros.append(VideoFonte.recomendavel.is_(True))

    base = select(VideoFonte).join(CanalFonte, CanalFonte.id == VideoFonte.canal_id).where(
        *filtros)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    chave = _chave(ordem, perfil_id).label("k")
    stmt = base.add_columns(chave)
    if cursor:
        valor, ultimo_id = _decodificar(cursor, ordem)
        key = _chave(ordem, perfil_id)
        stmt = stmt.where(or_(key < valor, and_(key == valor, VideoFonte.id < ultimo_id)))
    limit = min(max(limit, 1), LIMIT_MAX)
    rows = db.execute(stmt.order_by(chave.desc(), VideoFonte.id.desc()).limit(limit + 1)).all()
    pagina = rows[:limit]
    proximo = None
    if len(rows) > limit:
        ultimo, k = pagina[-1]
        proximo = _codificar(ordem, k.isoformat() if isinstance(k, datetime) else k, ultimo.id)
    return schemas.VideosList(items=videos_out(db, [r[0] for r in pagina], perfil_id),
                              next_cursor=proximo, total=total)


def get_video(db: Session, video_id: uuid.UUID) -> schemas.VideoDetalheOut:
    video = db.get(VideoFonte, video_id)
    if video is None:
        raise ApiError(404, "not_found", "Vídeo não encontrado")
    metricas = db.scalars(
        select(VideoMetrica).where(VideoMetrica.video_id == video_id)
        .order_by(VideoMetrica.observed_at.desc(), VideoMetrica.id.desc()).limit(METRICAS))
    return schemas.VideoDetalheOut(
        video=videos_out(db, [video])[0],
        metricas=[schemas.Metrica(observed_at=m.observed_at, views=m.views, likes=m.likes,
                                  comments=m.comments) for m in metricas],
    )
