"""Mercado: o YouTube de origem (spec 019, US7; FR-030/FR-031; research R8).

Base: `videos_fonte` dos canais-fonte não arquivados do escopo (com perfil ou conta no filtro,
os canais ligados ao perfil), sem lives (`live = nenhum`). A série `video_metricas` é rasa demais
e não entra.

- **Publicação:** 7 × 24 células (dia da semana × hora em `APP_TZ`) com quantos vídeos foram
  publicados no período.
- **Velocidade por horário:** mediana de `views ÷ idade_h` por horário de publicação, para os
  vídeos com idade entre 24 h e 7 d (idade na última leitura de métricas, `metrics_at`, ou
  agora); `amostraPequena` com 0 < n < `MIN_GRUPO`. Independe do período (é sempre a janela
  recente).
- **Oportunidades:** top 25 por velocidade dos vídeos disponíveis e sem envio (nenhum envio não
  arquivado e não descartado; com perfil, do perfil), velocidade = `vph_recente` ou, sem ele,
  `views ÷ idade_h` (mínimo 1 h) para os publicados nas últimas 72 h. O atalho leva à seleção
  existente ("Descobrir"); o aviso de direito continua lá (princípio II).
- **Canais:** por canal, os vídeos publicados no período e a mediana da velocidade da janela.

Só leitura.
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, case, exists, func, literal, select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, estatistica, schemas
from sociman_api.analytics.filtros import Filtro, fuso
from sociman_api.canais.models import CanalFonte, CanalPerfil, VideoFonte, VideoLive
from sociman_api.envios.models import Envio, EnvioStatus
from sociman_api.perfis.models import Conta

OPORTUNIDADES = 25
JANELA_MIN = timedelta(hours=24)
JANELA_MAX = timedelta(days=7)
RECENTE = timedelta(hours=72)
IDADE_MIN_H = 1.0


def _perfil(db: Session, filtro: Filtro) -> uuid.UUID | None:
    if filtro.conta_id is not None:
        return db.scalar(select(Conta.perfil_id).where(Conta.id == filtro.conta_id))
    return filtro.perfil_id


def _escopo(stmt: Select, perfil_id: uuid.UUID | None) -> Select:
    stmt = (stmt.join(CanalFonte, CanalFonte.id == VideoFonte.canal_id)
            .where(CanalFonte.archived_at.is_(None), VideoFonte.live == VideoLive.nenhum))
    if perfil_id is not None:
        stmt = stmt.where(exists().where(CanalPerfil.canal_id == CanalFonte.id,
                                         CanalPerfil.perfil_id == perfil_id))
    return stmt


def _celula(dt: datetime, tz: ZoneInfo) -> tuple[int, int]:
    local = dt.astimezone(tz)
    return local.weekday(), local.hour


def _mapa(valores: dict[tuple[int, int], list[float]], contagem: bool) -> schemas.Mapa:
    celulas = []
    for dia in range(7):
        for hora in range(24):
            vs = valores.get((dia, hora), [])
            valor = (len(vs) or None) if contagem else estatistica.mediana(vs)
            celulas.append(schemas.CelulaMapa(
                dia=dia, hora=hora, valor=valor, n=len(vs),
                amostra_pequena=not contagem and 0 < len(vs) < estatistica.MIN_GRUPO))
    return schemas.Mapa(celulas=celulas)


def velocidade(views: int | None, publicado: datetime, lido_em: datetime) -> float | None:
    idade_h = (lido_em - publicado).total_seconds() / 3600
    if views is None or idade_h <= 0:
        return None
    return views / idade_h


def calcular(db: Session, filtro: Filtro, agora: datetime | None = None) -> schemas.MercadoOut:
    agora = agora or datetime.now(ZoneInfo("UTC"))
    tz = ZoneInfo(fuso())
    perfil_id = _perfil(db, filtro)

    # publicação no período
    publicados: dict[tuple[int, int], list[float]] = {}
    por_canal: dict[uuid.UUID, int] = {}
    for canal_id, quando in db.execute(_escopo(
            select(VideoFonte.canal_id, VideoFonte.published_at).select_from(VideoFonte),
            perfil_id).where(VideoFonte.published_at >= filtro.atual.ini,
                             VideoFonte.published_at < filtro.atual.fim)):
        publicados.setdefault(_celula(quando, tz), []).append(1)
        por_canal[canal_id] = por_canal.get(canal_id, 0) + 1

    # velocidade na janela de 24 h a 7 d
    rapidez: dict[tuple[int, int], list[float]] = {}
    vel_canal: dict[uuid.UUID, list[float]] = {}
    for canal_id, quando, views, lido in db.execute(_escopo(
            select(VideoFonte.canal_id, VideoFonte.published_at, VideoFonte.views,
                   VideoFonte.metrics_at).select_from(VideoFonte), perfil_id)
            .where(VideoFonte.published_at >= agora - JANELA_MAX - timedelta(days=1),
                   VideoFonte.views.is_not(None))):
        lido = lido or agora
        if not JANELA_MIN <= lido - quando <= JANELA_MAX:
            continue
        v = velocidade(views, quando, lido)
        if v is not None:
            rapidez.setdefault(_celula(quando, tz), []).append(v)
            vel_canal.setdefault(canal_id, []).append(v)

    # oportunidades
    idade_h = func.greatest(func.extract("epoch", literal(agora) - VideoFonte.published_at)
                            / 3600, IDADE_MIN_H)
    vel = func.coalesce(VideoFonte.vph_recente, case(
        (VideoFonte.published_at >= agora - RECENTE, VideoFonte.views / idade_h)))
    envio = exists().where(Envio.video_fonte_id == VideoFonte.id, Envio.archived_at.is_(None),
                           Envio.status != EnvioStatus.descartado)
    if perfil_id is not None:
        envio = envio.where(Envio.perfil_id == perfil_id)
    rows = db.execute(_escopo(
        select(VideoFonte, CanalFonte.title, CanalFonte.direito, vel.label("vel"))
        .select_from(VideoFonte), perfil_id)
        .where(VideoFonte.disponivel, ~envio, vel.is_not(None),
               VideoFonte.published_at <= agora)
        .order_by(vel.desc(), VideoFonte.published_at.desc(), VideoFonte.id)
        .limit(OPORTUNIDADES)).all()
    oportunidades = [schemas.Oportunidade(
        video_fonte_id=v.id, titulo_curto=base.titulo_curto(v.title),
        canal=schemas.CanalOportunidade(id=v.canal_id, titulo=titulo, direito=direito),
        idade_h=round((agora - v.published_at).total_seconds() / 3600, 2), views=v.views,
        velocidade=round(float(vel_v), 2),
        link_gerar_cortes=f"/app/descobrir?canal={v.canal_id}&video={v.id}")
        for v, titulo, direito, vel_v in rows]

    ids = set(por_canal) | set(vel_canal)
    canais = db.execute(select(CanalFonte.id, CanalFonte.title, CanalFonte.direito)
                        .where(CanalFonte.id.in_(ids))).all() if ids else []
    lista = [schemas.CanalMercado(canal_id=cid, titulo=titulo, direito=direito,
                                  videos=por_canal.get(cid, 0),
                                  mediana_velocidade=estatistica.mediana(vel_canal.get(cid, [])))
             for cid, titulo, direito in canais]
    lista.sort(key=lambda c: (c.mediana_velocidade is None, -(c.mediana_velocidade or 0),
                              c.titulo))
    return schemas.MercadoOut(
        contexto=base.contexto(filtro, base.posts(db, filtro, agora=agora)),
        publicacao=_mapa(publicados, contagem=True),
        velocidade_por_horario=_mapa(rapidez, contagem=False),
        oportunidades=oportunidades, canais=lista)
