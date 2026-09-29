"""Trilha `sync` do agendador (research R2): sincronização dos canais e renovação de métricas.

Uma volta (a cada `AGENDADOR_SYNC_S`):
1. canais ativos com `next_sync_at <= agora`:
   - 1ª sync (`full_synced_at` nulo): pagina a playlist de uploads (1 unidade por página de
     50, mais 1 do `videos.list`), com commit e `sync_progress {lidos, total}` a cada página.
     No máximo `PAGINAS_POR_VOLTA` por volta: um canal grande continua na volta seguinte, do
     `pageToken` salvo (reiniciar o agendador também retoma dali);
   - incremental (a cada `SYNC_NOVOS_H`): lê a playlist até o primeiro vídeo já conhecido;
     uma vez por dia também relê nome, @, avatar e contagens do canal;
2. vídeos com `next_metrics_at <= agora`, em lotes de 50: grava `video_metricas`,
   `vph_recente` e a pontuação (R3). A frequência vem da idade: +1 h até 7 dias, +24 h até 60
   dias, +7 d depois. Um id que o YouTube não devolve mais fica `disponivel = false`.

Cota (R2): em 95% a sync pausa (`CotaPausada`) e os canais devidos ficam `pausado_cota` até a
meia-noite do Pacífico. Erro de chave ou do YouTube deixa o canal em `erro` (mensagem sem a
chave), com notificação `canal_erro` (uma por canal e dia) e nova tentativa em 1 h.

Tudo aqui é estado de job: nenhuma versão no histórico.
"""

import logging
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from sociman_api.canais import score, youtube
from sociman_api.canais.models import CanalFonte, CanalSync, VideoFonte, VideoMetrica
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo

log = logging.getLogger("sociman.agendador.sync")

CANAIS_POR_VOLTA = 10
PAGINAS_POR_VOLTA = 20  # 1ª sync: até 1.000 vídeos por volta
PAGINAS_INCREMENTAL = 5
LOTES_METRICAS_POR_VOLTA = 10  # até 500 vídeos por volta
RETRY_ERRO = timedelta(hours=1)
INFO_CANAL = timedelta(hours=24)
VPH_JANELA = timedelta(hours=6)


def rodar(db: Session, client: youtube.YoutubeClient | None = None,
          agora: datetime | None = None) -> int:
    """Uma volta da trilha; devolve quantos canais e vídeos tratou (0 = nada a fazer)."""
    proprio = client is None
    client = client or youtube.novo_cliente()
    try:
        if not client.configurado:  # o agendador já deixa a trilha ociosa, com o motivo
            return 0
        return _volta(db, client, agora or datetime.now(UTC))
    finally:
        if proprio:
            client.close()


def _volta(db: Session, client: youtube.YoutubeClient, agora: datetime) -> int:
    tratados = 0
    try:
        for canal_id in _canais_devidos(db, agora):
            canal = db.get(CanalFonte, canal_id)
            if canal is None or canal.archived:
                continue
            tratados += _sincronizar_canal(db, client, canal, agora)
            db.commit()
        tratados += _renovar_metricas(db, client, agora)
        db.commit()
    except youtube.CotaPausada as exc:
        db.rollback()
        _pausar(db, exc.renova_em, agora)
    except ApiError as exc:
        if exc.code != "youtube_quota":
            raise
        db.rollback()
        _pausar(db, youtube.renova_em(agora), agora)
    return tratados


def _canais_devidos(db: Session, agora: datetime) -> list[uuid.UUID]:
    return list(db.scalars(
        select(CanalFonte.id)
        .where(CanalFonte.archived_at.is_(None), CanalFonte.next_sync_at <= agora)
        .order_by(CanalFonte.next_sync_at, CanalFonte.id)
        .limit(CANAIS_POR_VOLTA)
    ))


def _pausar(db: Session, renova: datetime, agora: datetime) -> None:
    """Canais devidos ficam "Pausado até a cota renovar"; as métricas esperam a renovação."""
    n = db.execute(
        update(CanalFonte)
        .where(CanalFonte.archived_at.is_(None), CanalFonte.next_sync_at <= agora)
        .values(sync_status=CanalSync.pausado_cota, next_sync_at=renova)
    ).rowcount
    db.commit()
    log.warning("cota do YouTube em 95%%: sync pausada até %s (%d canais)", renova.isoformat(), n)


# ---- canal ----

def _sincronizar_canal(db: Session, client: youtube.YoutubeClient, canal: CanalFonte,
                       agora: datetime) -> int:
    try:
        if canal.full_synced_at is None:
            return _sync_completa(db, client, canal, agora)
        return _sync_incremental(db, client, canal, agora)
    except youtube.YoutubeErro as exc:
        if exc.code == "youtube_unconfigured":
            raise
        db.rollback()  # as páginas já gravadas ficam; a atual não
        _marcar_erro(db, canal, exc.message, agora)
        return 1


def _sync_completa(db: Session, client: youtube.YoutubeClient, canal: CanalFonte,
                   agora: datetime) -> int:
    progresso = dict(canal.sync_progress or {})
    pagina = progresso.get("pagina")
    lidos = int(progresso.get("lidos") or 0)
    total = progresso.get("total")
    canal.sync_status = CanalSync.sincronizando
    for _ in range(PAGINAS_POR_VOLTA):
        resultado = client.playlist(canal.uploads_playlist_id, pagina)
        _gravar_videos(db, client, canal, resultado.video_ids, agora)
        lidos += len(resultado.video_ids)
        total = resultado.total if resultado.total is not None else total
        pagina = resultado.proxima
        canal.sync_progress = {"lidos": lidos, "total": total, "pagina": pagina}
        db.commit()  # a lista aparece aos poucos (edge case)
        if not pagina:
            break
    if pagina:  # canal grande: continua na próxima volta
        canal.next_sync_at = agora
        return 1
    canal.full_synced_at = agora
    _concluir(canal, agora, {"infoEm": agora.isoformat()})
    return 1


def _sync_incremental(db: Session, client: youtube.YoutubeClient, canal: CanalFonte,
                      agora: datetime) -> int:
    progresso = dict(canal.sync_progress or {})
    info_em = progresso.get("infoEm")
    if info_em is None or datetime.fromisoformat(info_em) <= agora - INFO_CANAL:
        _atualizar_info(client, canal)
        info_em = agora.isoformat()
    canal.sync_status = CanalSync.sincronizando
    pagina: str | None = None
    for _ in range(PAGINAS_INCREMENTAL):
        resultado = client.playlist(canal.uploads_playlist_id, pagina)
        conhecidos = set(db.scalars(select(VideoFonte.youtube_video_id).where(
            VideoFonte.youtube_video_id.in_(resultado.video_ids))))
        novos: list[str] = []
        achou_conhecido = False
        for vid in resultado.video_ids:
            if vid in conhecidos:
                achou_conhecido = True
                break
            novos.append(vid)
        _gravar_videos(db, client, canal, novos, agora)
        db.commit()
        if achou_conhecido or not resultado.proxima:
            break
        pagina = resultado.proxima
    _concluir(canal, agora, {"infoEm": info_em})
    return 1


def _atualizar_info(client: youtube.YoutubeClient, canal: CanalFonte) -> None:
    infos = client.canais([canal.youtube_channel_id], sync=True)
    if not infos:
        raise youtube.YoutubeErro(404, "canal_not_found",
                                  "O canal não foi encontrado no YouTube (removido?)")
    info = infos[0]
    canal.title = info.title
    canal.handle = info.handle
    canal.avatar_url = info.avatar_url
    canal.subscribers = info.subscribers
    canal.video_count = info.video_count
    canal.uploads_playlist_id = info.uploads_playlist_id


def _concluir(canal: CanalFonte, agora: datetime, progresso: dict) -> None:
    canal.sync_status = CanalSync.ok
    canal.sync_error = None
    canal.sync_progress = progresso
    canal.last_synced_at = agora
    canal.next_sync_at = agora + timedelta(hours=get_settings().sync_novos_h)


def _marcar_erro(db: Session, canal: CanalFonte, mensagem: str, agora: datetime) -> None:
    canal.sync_status = CanalSync.erro
    canal.sync_error = youtube.redact(mensagem)[:500]
    canal.next_sync_at = agora + RETRY_ERRO
    notificacoes.criar(
        db, NotificacaoTipo.canal_erro, f"Erro ao sincronizar {canal.title}"[:200],
        canal.sync_error, f"/app/fontes/{canal.id}", ("canal", canal.id),
        f"canal_erro:{canal.id}:{youtube.dia_cota(agora).isoformat()}",
        notificacoes.destinatarios_padrao(db, canal.created_by),
    )
    db.commit()
    log.warning("canal %s em erro: %s", canal.id, canal.sync_error)


# ---- vídeos e métricas ----

def proxima_metrica(published_at: datetime, agora: datetime) -> datetime:
    idade = agora - published_at
    if idade <= timedelta(days=7):
        return agora + timedelta(hours=1)
    if idade <= timedelta(days=60):
        return agora + timedelta(hours=24)
    return agora + timedelta(days=7)


def _aplicar_leitura(db: Session, video: VideoFonte, info: youtube.VideoInfo,
                     agora: datetime) -> None:
    video.title = info.title
    video.description = info.description
    video.thumbnail_url = info.thumbnail_url
    video.published_at = info.published_at
    video.duration_s = info.duration_s
    video.live = info.live
    video.disponivel = True
    video.views = info.views
    video.likes = info.likes
    video.comments = info.comments
    video.metrics_at = agora
    video.next_metrics_at = proxima_metrica(info.published_at, agora)
    db.add(VideoMetrica(video_id=video.id, observed_at=agora, views=info.views,
                        likes=info.likes, comments=info.comments))


def _gravar_videos(db: Session, client: youtube.YoutubeClient, canal: CanalFonte,
                   ids: Sequence[str], agora: datetime) -> int:
    """Insere ou atualiza os vídeos dos ids (um `videos.list`); devolve quantos são novos."""
    if not ids:
        return 0
    infos = client.videos(list(ids))
    existentes = {v.youtube_video_id: v for v in db.scalars(
        select(VideoFonte).where(VideoFonte.youtube_video_id.in_(ids)))}
    tocados: list[VideoFonte] = []
    novos = 0
    for info in infos:
        video = existentes.get(info.youtube_video_id)
        if video is None:
            video = VideoFonte(id=uuid.uuid4(), canal_id=canal.id,
                               youtube_video_id=info.youtube_video_id, first_seen_at=agora,
                               title=info.title, published_at=info.published_at,
                               next_metrics_at=agora)
            db.add(video)
            novos += 1
        _aplicar_leitura(db, video, info, agora)
        tocados.append(video)
    devolvidos = {i.youtube_video_id for i in infos}
    for vid, video in existentes.items():
        if vid not in devolvidos:
            _indisponivel(video, agora)
            tocados.append(video)
    db.flush()
    _recalcular(db, canal.id, tocados, agora)
    return novos


def _indisponivel(video: VideoFonte, agora: datetime) -> None:
    video.disponivel = False
    video.next_metrics_at = agora + timedelta(days=7)  # confere se voltou


def _renovar_metricas(db: Session, client: youtube.YoutubeClient, agora: datetime) -> int:
    tratados = 0
    for _ in range(LOTES_METRICAS_POR_VOLTA):
        lote = list(db.scalars(
            select(VideoFonte)
            .join(CanalFonte, CanalFonte.id == VideoFonte.canal_id)
            .where(CanalFonte.archived_at.is_(None), VideoFonte.next_metrics_at <= agora)
            .order_by(VideoFonte.next_metrics_at, VideoFonte.id)
            .limit(50)
        ))
        if not lote:
            break
        infos = {i.youtube_video_id: i for i in client.videos(
            [v.youtube_video_id for v in lote])}
        por_canal: dict[uuid.UUID, list[VideoFonte]] = {}
        for video in lote:
            info = infos.get(video.youtube_video_id)
            if info is None:
                _indisponivel(video, agora)
            else:
                _aplicar_leitura(db, video, info, agora)
            por_canal.setdefault(video.canal_id, []).append(video)
        db.flush()
        for canal_id, videos in por_canal.items():
            _recalcular(db, canal_id, videos, agora)
        db.commit()
        tratados += len(lote)
    return tratados


def _vph_recentes(db: Session, videos: Iterable[VideoFonte],
                  agora: datetime) -> dict[uuid.UUID, Decimal | None]:
    """Views/h entre a leitura atual e a mais recente com pelo menos 6 h de distância."""
    videos = list(videos)
    ids = [v.id for v in videos]
    if not ids:
        return {}
    limite = agora - VPH_JANELA
    anteriores = {
        row.video_id: row for row in db.execute(
            select(VideoMetrica.video_id, VideoMetrica.observed_at, VideoMetrica.views)
            .where(VideoMetrica.video_id.in_(ids), VideoMetrica.observed_at <= limite)
            .order_by(VideoMetrica.video_id, VideoMetrica.observed_at.desc())
            .ext(distinct_on(VideoMetrica.video_id))
        )
    }
    out: dict[uuid.UUID, Decimal | None] = {}
    for video in videos:
        prev = anteriores.get(video.id)
        if prev is None or prev.views is None or video.views is None or video.metrics_at is None:
            out[video.id] = None
            continue
        horas = (video.metrics_at - prev.observed_at).total_seconds() / 3600
        vph = max(video.views - prev.views, 0) / horas if horas > 0 else 0
        out[video.id] = Decimal(str(round(vph, 2)))
    return out


def _entrada(video: VideoFonte) -> score.Entrada:
    return score.Entrada(
        views=video.views, likes=video.likes, comments=video.comments,
        published_at=video.published_at, duration_s=video.duration_s, live=video.live,
        disponivel=video.disponivel,
        vph_recente=float(video.vph_recente) if video.vph_recente is not None else None,
    )


def _recalcular(db: Session, canal_id: uuid.UUID, videos: Sequence[VideoFonte],
                agora: datetime) -> None:
    """`vph_recente` e pontuação dos vídeos tocados, contra as medianas do canal (R3)."""
    if not videos:
        return
    vphs = _vph_recentes(db, videos, agora)
    for video in videos:
        video.vph_recente = vphs.get(video.id)
    amostra = list(db.scalars(
        select(VideoFonte)
        .where(VideoFonte.canal_id == canal_id, VideoFonte.disponivel.is_(True))
        .order_by(VideoFonte.published_at.desc(), VideoFonte.id)
        .limit(score.AMOSTRA_CANAL)
    ))
    entradas = [_entrada(v) for v in amostra]
    mediana_vph = score.mediana([score.vph(e, agora) for e in entradas])
    mediana_eng = score.mediana([score.engajamento(e) for e in entradas])
    for video in videos:
        r = score.calcular(_entrada(video), mediana_vph, mediana_eng, agora)
        video.score = r.score
        video.score_reason = r.reason
        video.score_detail = r.detail
        video.recomendavel = r.recomendavel
