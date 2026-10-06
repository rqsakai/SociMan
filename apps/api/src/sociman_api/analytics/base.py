"""Base de todas as abas (spec 019, data-model "PostAnalisado"): os posts publicados no período,
já medidos e caracterizados, e os ganhos de cada vídeo no período.

Reaproveita a 016 (nada recalculado por fora): `metricas.consulta.marcos` dá a medida do post
(1 h/24 h/7 d, com `estimado` e "ainda não" → aguardando), a última foto dá as views atuais e o
engajamento, e `metricas.anonimizar.caracteristicas` dá hora local, dia da semana, score, gancho,
modo e direito do canal (as séries anônimas usam as `features` congeladas). Hashtags: as do
destino ∪ as da legenda, normalizadas por `ia.guia.normalizar`.

Escopo: `contaId` → a série viva da conta; `perfilId` → as contas do perfil; sem os dois, todas
as séries (as anônimas entram, rotuladas "Conta anônima N"); `rede` filtra a série. Só leitura.

Spec 020: os totais diários da conta (`totais_diarios`) somam por dia e por série e trocam pelo
histórico importado do Studio os dias que a coleta não cobre inteiros (`metricas.studio.efetivo`,
só leitura). Sem Studio, a soma por dia dá os mesmos números do delta do período.
"""

import bisect
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, select, true
from sqlalchemy.orm import Session

from sociman_api import imaging
from sociman_api.analytics import estatistica, schemas
from sociman_api.analytics.filtros import Filtro, Periodo, fuso
from sociman_api.canais.models import CanalDireito, CanalFonte
from sociman_api.conteudos import consulta as conteudos_consulta
from sociman_api.conteudos.models import Conteudo
from sociman_api.cortes.models import Corte
from sociman_api.envios.models import Envio
from sociman_api.ia.guia import normalizar
from sociman_api.metricas import anonimizar, consulta
from sociman_api.metricas.models import FotoVideo, Serie, VideoRede
from sociman_api.metricas.studio import efetivo
from sociman_api.perfis.models import Conta, Platform
from sociman_api.postagem.models import Postagem

TITULO_MAX = 40
_HASHTAG = re.compile(r"#(\w+)", re.UNICODE)
PADRAO_CAMPOS = ("clip_min_s", "clip_max_s", "layout")


@dataclass(frozen=True)
class MedidaPost:
    valor: float | None
    estimado: bool
    aguardando: bool  # idade < marco: fora das comparações, no contador "aguardando"


@dataclass(frozen=True)
class CanalFonteRef:
    id: uuid.UUID
    titulo: str
    direito: CanalDireito


@dataclass(frozen=True)
class PostAnalisado:
    video_id: uuid.UUID
    serie_id: uuid.UUID  # interno: nunca vai para a resposta
    conta_id: uuid.UUID | None  # null se anônima
    perfil_id: uuid.UUID | None
    rotulo_conta: str  # "@handle" ou "Conta anônima N"
    rede: Platform
    anonima: bool
    publicado_em: datetime  # em APP_TZ
    hora_local: int  # 0–23
    dia_semana: int  # 0 = segunda
    duracao_s: int
    titulo_curto: str
    link: str | None
    thumb_url: str | None
    medida: MedidaPost
    views_atual: int | None
    engajamento: float | None
    hashtags: tuple[str, ...]
    vinculado: bool
    modo: str | None = None
    score: int | None = None
    gancho_caracteres: int | None = None
    canal_fonte: CanalFonteRef | None = None
    padrao: dict[str, Any] | None = None  # clip_min_s/clip_max_s/layout de `envios.config`
    conteudo_id: uuid.UUID | None = None
    destino_id: uuid.UUID | None = None

    @property
    def medido(self) -> bool:
        """Entra nas comparações: tem valor na medida (não está aguardando nem sem dado)."""
        return self.medida.valor is not None


@dataclass(frozen=True)
class Ganho:
    views: int
    likes: int
    comments: int
    shares: int


# ---- auxiliares puros ----

def titulo_curto(legenda: str | None, anonima: bool = False) -> str:
    """A legenda nos primeiros 40 caracteres com reticências (como o `truncar` da SPA)."""
    texto = " ".join((legenda or "").split())
    if not texto:
        return "Vídeo anônimo" if anonima else "Sem legenda"
    return texto if len(texto) <= TITULO_MAX else f"{texto[:TITULO_MAX].rstrip()}…"


def hashtags(do_destino: Iterable[str] | None, legenda: str | None) -> tuple[str, ...]:
    """As do destino ∪ as da legenda (`#(\\w+)`), normalizadas, sem `#` e sem repetir, na ordem
    em que aparecem."""
    vistas: dict[str, None] = {}
    brutas = [h.lstrip("#") for h in (do_destino or ())] + _HASHTAG.findall(legenda or "")
    for h in brutas:
        n = normalizar(h)
        if n:
            vistas.setdefault(n, None)
    return tuple(vistas)


def amostra(n: int, minimo: int) -> schemas.Amostra:
    a = estatistica.Amostra(n, minimo)
    return schemas.Amostra(n=a.n, minimo=a.minimo, suficiente=a.suficiente, faltam=a.faltam)


SEM_STUDIO = schemas.ContextoStudio(dias=0, series=0)


def contexto(filtro: Filtro, posts: Sequence[PostAnalisado],
             studio: schemas.ContextoStudio = SEM_STUDIO) -> schemas.Contexto:
    return schemas.Contexto(
        de=filtro.atual.de, ate=filtro.atual.ate, anterior_de=filtro.anterior.de,
        anterior_ate=filtro.anterior.ate, medida=filtro.medida, fuso=fuso(),
        posts_no_periodo=len(posts), aguardando=sum(p.medida.aguardando for p in posts),
        fora_do_sociman=sum(not p.vinculado and not p.anonima for p in posts),
        minimos=schemas.Minimos(grupo=estatistica.MIN_GRUPO,
                                correlacao=estatistica.MIN_CORRELACAO,
                                contas_radar=estatistica.MIN_CONTAS_RADAR),
        studio=studio)


# ---- escopo ----

def escopo(stmt: Select, filtro: Filtro) -> Select:
    """Junta `Serie` (e `Conta`, opcional) a um select que já tem `VideoRede` e aplica conta,
    perfil e rede."""
    stmt = (stmt.join(Serie, Serie.id == VideoRede.serie_id)
            .outerjoin(Conta, Conta.id == Serie.conta_id))
    if filtro.conta_id is not None:
        stmt = stmt.where(Serie.conta_id == filtro.conta_id)
    elif filtro.perfil_id is not None:
        stmt = stmt.where(Conta.perfil_id == filtro.perfil_id)
    if filtro.rede is not None:
        stmt = stmt.where(Serie.rede == filtro.rede)
    return stmt


# ---- posts do período ----

def _vinculos(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Any]:
    """Série, conta, destino, conteúdo, corte, envio e canal de cada vídeo (uma consulta)."""
    stmt = conteudos_consulta.join_corte(
        select(VideoRede.id, Serie.rotulo, Serie.rede, Conta.id.label("conta_id"),
               Conta.handle, Conta.perfil_id, Postagem.hashtags, Conteudo.id.label("conteudo_id"),
               conteudos_consulta.poster_key().label("poster_key"))
        .select_from(VideoRede)
        .join(Serie, Serie.id == VideoRede.serie_id)
        .outerjoin(Conta, Conta.id == Serie.conta_id)
        .outerjoin(Postagem, Postagem.id == VideoRede.destino_id)
        .outerjoin(Conteudo, Conteudo.id == Postagem.conteudo_id))
    stmt = (stmt.add_columns(Envio.config, CanalFonte.id.label("canal_id"),
                             CanalFonte.title.label("canal_titulo"),
                             CanalFonte.direito.label("canal_direito"))
            .outerjoin(Envio, Envio.id == Corte.envio_id)
            .outerjoin(CanalFonte, CanalFonte.id == Envio.canal_fonte_id)
            .where(VideoRede.id.in_(ids)))
    return {r.id: r for r in db.execute(stmt)}


def posts(db: Session, filtro: Filtro, *, periodo: Periodo | None = None,
          agora: datetime | None = None) -> list[PostAnalisado]:
    """Os vídeos do escopo publicados em `periodo` (padrão: o atual do filtro), na ordem de
    publicação, medidos pela medida do filtro."""
    periodo = periodo or filtro.atual
    stmt = escopo(select(VideoRede).select_from(VideoRede), filtro).where(
        VideoRede.publicado_em >= periodo.ini, VideoRede.publicado_em < periodo.fim
    ).order_by(VideoRede.publicado_em, VideoRede.id)
    return analisar(db, filtro, list(db.scalars(stmt)), agora)


def posts_por_id(db: Session, filtro: Filtro, ids: Sequence[uuid.UUID],
                 agora: datetime | None = None) -> list[PostAnalisado]:
    """Os vídeos dados (publicados em qualquer data), na ordem de publicação."""
    if not ids:
        return []
    videos = list(db.scalars(select(VideoRede).where(VideoRede.id.in_(list(ids)))
                             .order_by(VideoRede.publicado_em, VideoRede.id)))
    return analisar(db, filtro, videos, agora)


def analisar(db: Session, filtro: Filtro, videos: Sequence[VideoRede],
             agora: datetime | None = None) -> list[PostAnalisado]:
    """Mede e caracteriza os vídeos (na ordem recebida)."""
    if not videos:
        return []
    agora = agora or datetime.now(ZoneInfo("UTC"))
    ids = [v.id for v in videos]
    marcos = consulta.marcos(db, videos, agora)
    ultimas = consulta._ultimas(db, ids)
    vivos = [v for v in videos if v.anonimizado_em is None]
    carac = anonimizar.caracteristicas(db, vivos)
    linhas = _vinculos(db, ids)
    tz = ZoneInfo(fuso())
    out = []
    for v in videos:
        r = linhas[v.id]
        anonima = v.anonimizado_em is not None
        c = (v.features or {}) if anonima else carac.get(v.id, {})
        local = v.publicado_em.astimezone(tz)
        m = getattr(marcos[v.id], filtro.medida).views
        ultima = consulta._p(ultimas.get(v.id))
        vinculado = v.destino_id is not None
        canal = CanalFonteRef(r.canal_id, r.canal_titulo, r.canal_direito) \
            if vinculado and r.canal_id is not None else None
        padrao = {k: r.config.get(k) for k in PADRAO_CAMPOS} \
            if vinculado and r.config else None
        out.append(PostAnalisado(
            video_id=v.id, serie_id=v.serie_id,
            conta_id=None if anonima else r.conta_id,
            perfil_id=None if anonima else r.perfil_id,
            rotulo_conta=(r.rotulo or "Conta anônima") if anonima or r.handle is None
            else f"@{r.handle}",
            rede=r.rede, anonima=anonima, publicado_em=local,
            hora_local=c.get("hora_local", local.hour),
            dia_semana=c.get("dia_semana", local.weekday()),
            duracao_s=v.duracao_s, titulo_curto=titulo_curto(v.legenda or v.titulo, anonima),
            link=v.share_url,
            thumb_url=imaging.poster_url(r.poster_key) if vinculado and r.poster_key else None,
            medida=MedidaPost(m.valor, m.estimado, m.motivo == "ainda_nao"),
            views_atual=ultima.views if ultima is not None else None,
            engajamento=consulta.engajamento(ultima),
            hashtags=() if anonima else hashtags(r.hashtags if vinculado else None, v.legenda),
            vinculado=vinculado, modo=c.get("modo_envio"), score=c.get("score"),
            gancho_caracteres=c.get("gancho_caracteres"), canal_fonte=canal, padrao=padrao,
            conteudo_id=r.conteudo_id if vinculado else None, destino_id=v.destino_id))
    return out


# ---- ganhos no período ----

def _foto_antes(limite: datetime, nome: str):
    """A última foto do vídeo com `coletado_em < limite` (LATERAL … LIMIT 1)."""
    return (select(FotoVideo.views, FotoVideo.likes, FotoVideo.comments, FotoVideo.shares)
            .where(FotoVideo.video_id == VideoRede.id, FotoVideo.coletado_em < limite)
            .order_by(FotoVideo.coletado_em.desc(), FotoVideo.id.desc())
            .limit(1).lateral(nome))


def _delta(fim: int | None, ini: int | None) -> int:
    if fim is None:
        return 0
    return max(0, fim - (ini or 0))


def ganhos(db: Session, filtro: Filtro, periodo: Periodo | None = None
           ) -> dict[uuid.UUID, Ganho]:
    """Δviews/Δlikes/Δcomments/Δshares de cada vídeo do escopo (publicado em qualquer data) no
    período: a última foto antes do fim menos a última antes do início (0 sem foto antes; 0 se
    der negativo). Fotos exatamente em `ini` contam no período (intervalo `[ini, fim)`).
    Vídeos sem nenhuma foto até o fim ficam de fora."""
    periodo = periodo or filtro.atual
    fim = _foto_antes(periodo.fim, "foto_fim")
    ini = _foto_antes(periodo.ini, "foto_ini")
    stmt = escopo(
        select(VideoRede.id, fim.c.views, fim.c.likes, fim.c.comments, fim.c.shares,
               ini.c.views.label("views_ini"), ini.c.likes.label("likes_ini"),
               ini.c.comments.label("comments_ini"), ini.c.shares.label("shares_ini"))
        .select_from(VideoRede).join(fim, true()).outerjoin(ini, true()), filtro)
    return {r.id: Ganho(views=_delta(r.views, r.views_ini), likes=_delta(r.likes, r.likes_ini),
                        comments=_delta(r.comments, r.comments_ini),
                        shares=_delta(r.shares, r.shares_ini))
            for r in db.execute(stmt)}


# ---- fotos e ganhos por dia (série diária, calendário, audiência) ----

@dataclass(frozen=True)
class VideoEscopo:
    video_id: uuid.UUID
    conta_id: uuid.UUID | None  # null se anônima
    rotulo_conta: str
    publicado_em: datetime


def videos_escopo(db: Session, filtro: Filtro) -> list[VideoEscopo]:
    """Todos os vídeos do escopo (publicados em qualquer data), com a conta de cada um."""
    stmt = escopo(select(VideoRede.id, VideoRede.publicado_em, VideoRede.anonimizado_em,
                         Serie.rotulo, Conta.id.label("conta_id"), Conta.handle)
                  .select_from(VideoRede), filtro).order_by(VideoRede.publicado_em, VideoRede.id)
    out = []
    for r in db.execute(stmt):
        anonima = r.anonimizado_em is not None or r.handle is None
        out.append(VideoEscopo(r.id, None if anonima else r.conta_id,
                               (r.rotulo or "Conta anônima") if anonima else f"@{r.handle}",
                               r.publicado_em))
    return out


def fotos_views(db: Session, ids: Sequence[uuid.UUID], ate: datetime
                ) -> dict[uuid.UUID, list[tuple[datetime, int]]]:
    """(coletado_em, views) das fotos com views de cada vídeo, antes de `ate`, em ordem."""
    out: dict[uuid.UUID, list[tuple[datetime, int]]] = {}
    if not ids:
        return out
    rows = db.execute(select(FotoVideo.video_id, FotoVideo.coletado_em, FotoVideo.views)
                      .where(FotoVideo.video_id.in_(list(ids)), FotoVideo.coletado_em < ate,
                             FotoVideo.views.is_not(None))
                      .order_by(FotoVideo.video_id, FotoVideo.coletado_em, FotoVideo.id))
    for vid, quando, views in rows:
        out.setdefault(vid, []).append((quando, int(views)))
    return out


def views_antes(fotos: Sequence[tuple[datetime, int]], t: datetime) -> int | None:
    """As views da última foto com `coletado_em < t` (None sem foto antes)."""
    i = bisect.bisect_left(fotos, t, key=lambda f: f[0])
    return fotos[i - 1][1] if i else None


def dias(periodo: Periodo) -> list[date]:
    return [periodo.de + timedelta(days=k) for k in range(periodo.dias)]


# ---- totais diários da conta, com o Studio (spec 020) ----

@dataclass(frozen=True)
class SerieEscopo:
    serie_id: uuid.UUID
    conta_id: uuid.UUID | None  # null se anônima
    rotulo: str
    tem_videos: bool


@dataclass(frozen=True)
class TotalDia:
    """Os totais de um dia de uma série: os ganhos da coleta ou o dia do Studio (FR-013)."""

    views: int | None  # None: sem dado no dia
    likes: int | None
    comments: int | None
    shares: int | None
    seguidores_dif: int | None
    seguidores_fim: int | None  # total no fim do dia (base do crescimento)
    visitas_perfil: int | None  # só o Studio informa
    fonte: str  # coletado | studio (views, curtidas, comentários, compartilhamentos)
    fonte_seguidores: str  # coletado | studio
    comparacao: int | None  # as views da outra fonte, quando existem


def series_escopo(db: Session, filtro: Filtro) -> list[SerieEscopo]:
    """As séries do escopo (conta, perfil e rede), inclusive as sem vídeo."""
    tem = select(VideoRede.id).where(VideoRede.serie_id == Serie.id).exists()
    stmt = (select(Serie.id, Serie.rotulo, Serie.anonimizada_em, Conta.id.label("conta_id"),
                   Conta.handle, tem.label("tem_videos"))
            .select_from(Serie).outerjoin(Conta, Conta.id == Serie.conta_id))
    if filtro.conta_id is not None:
        stmt = stmt.where(Serie.conta_id == filtro.conta_id)
    elif filtro.perfil_id is not None:
        stmt = stmt.where(Conta.perfil_id == filtro.perfil_id)
    if filtro.rede is not None:
        stmt = stmt.where(Serie.rede == filtro.rede)
    out = []
    for r in db.execute(stmt.order_by(Serie.criada_em, Serie.id)):
        anonima = r.anonimizada_em is not None or r.handle is None
        out.append(SerieEscopo(r.id, None if anonima else r.conta_id,
                               (r.rotulo or "Conta anônima") if anonima else f"@{r.handle}",
                               bool(r.tem_videos)))
    return out


def _total(dia: date, api: efetivo.DiaApi, studio: dict[date, efetivo.DiaEfetivo],
           primeiro: date | None) -> TotalDia:
    e = studio.get(dia)
    vg = e.visao_geral if e is not None else None
    seg = e.seguidores if e is not None else None
    livre = not efetivo.coberto(dia, primeiro)
    api_views = api.views if api.tem_dado else None
    if livre and vg is not None:
        fonte, comparacao = efetivo.STUDIO, api_views
        views, likes, comments, shares = vg.views, vg.likes, vg.comments, vg.shares
    else:
        fonte, comparacao = efetivo.COLETADO, vg.views if vg is not None else None
        views = api_views
        likes, comments, shares = (api.likes, api.comments, api.shares) if api.tem_dado \
            else (None, None, None)
    if livre and seg is not None:
        fonte_seg = efetivo.STUDIO
        dif, fim = efetivo.ganho_seguidores(dia, studio), seg.seguidores
    else:
        fonte_seg, dif, fim = efetivo.COLETADO, api.seguidores_dif, api.seguidores_fim
    return TotalDia(views, likes, comments, shares, dif, fim,
                    vg.visitas_perfil if vg is not None else None, fonte, fonte_seg, comparacao)


def totais_diarios(db: Session, filtro: Filtro, periodo: Periodo | None = None,
                   series: Sequence[SerieEscopo] | None = None
                   ) -> dict[uuid.UUID, dict[date, TotalDia]]:
    """Por série do escopo e por dia do período: os ganhos da coleta (`efetivo.api_por_dia`) ou,
    nos dias que a coleta não cobre inteiros e que têm Studio ativo, o dia do Studio."""
    periodo = periodo or filtro.atual
    series = series_escopo(db, filtro) if series is None else series
    ids = [s.serie_id for s in series]
    api = efetivo.api_por_dia(db, ids, periodo.de, periodo.ate)
    # a véspera entra para o ganho de seguidores do 1º dia quando falta a diferença
    studio = efetivo.dias(db, ids, periodo.de - timedelta(days=1), periodo.ate)
    primeiros = efetivo.primeiro_dia_coberto(db, ids)
    return {sid: {dia: _total(dia, api[sid][dia], studio.get(sid, {}), primeiros[sid])
                  for dia in dias(periodo)} for sid in ids}


def uso_studio(db: Session, filtro: Filtro) -> schemas.ContextoStudio:
    """Dias distintos do período em que alguma série do escopo usou o Studio, e quantas séries."""
    ids = [s.serie_id for s in series_escopo(db, filtro)]
    studio = efetivo.dias(db, ids, filtro.atual.de, filtro.atual.ate)
    primeiros = efetivo.primeiro_dia_coberto(db, ids)
    usados: set[date] = set()
    series: set[uuid.UUID] = set()
    for sid, por_dia in studio.items():
        for dia in por_dia:
            if not efetivo.coberto(dia, primeiros[sid]):
                usados.add(dia)
                series.add(sid)
    return schemas.ContextoStudio(dias=len(usados), series=len(series))


def resumo(p: PostAnalisado, views_periodo: int = 0) -> schemas.PostResumo:
    return schemas.PostResumo(
        video_id=p.video_id, conta_id=p.conta_id, rotulo_conta=p.rotulo_conta,
        publicado_em=p.publicado_em, titulo_curto=p.titulo_curto, link=p.link,
        thumb_url=p.thumb_url,
        medida=schemas.Medida(valor=p.medida.valor, estimado=p.medida.estimado,
                              aguardando=p.medida.aguardando),
        views_atual=p.views_atual, views_periodo=views_periodo, engajamento=p.engajamento)
