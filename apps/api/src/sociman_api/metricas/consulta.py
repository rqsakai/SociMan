"""Leituras das métricas (spec 016): o estado da coleta de uma conta (US1) e, na US4, curvas,
marcos, ranking e a resolução da conta (research R15). Tudo derivado na leitura, sem cache.

Marcos (R15): interpolação linear em `idade_s` entre a foto logo antes e a logo depois do marco
`T` (buscadas por `LATERAL … LIMIT 1` sobre `ix_metricas_video_fotos_idade`), com a âncora
`(0, 0)`; `estimado` quando as duas fotos distam mais de 25% de `T`; "ainda não" com o vídeo mais
novo que `T`; "sem dado" sem foto depois de `T` e a última a mais de 10% de `T`. As contagens
entram como vieram (sem forçar monotonia).
"""

import base64
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, Text, case, cast, func, literal, select, text
from sqlalchemy.orm import Session

from sociman_api import imaging
from sociman_api.canais.schemas import PerfilRef
from sociman_api.config import Settings, get_settings
from sociman_api.conteudos import consulta as conteudos_consulta
from sociman_api.conteudos.models import Conteudo
from sociman_api.conteudos.service import conta_ref
from sociman_api.errors import ApiError
from sociman_api.metricas import schemas
from sociman_api.metricas.estado import ErroColeta, EstadoColeta
from sociman_api.metricas.models import FotoConta, FotoVideo, Serie, VideoRede
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.postagem.models import Postagem
from sociman_api.publicacao import conexoes
from sociman_api.publicacao.models import Conexao, ConexaoEstado

# ---- estado da coleta (US1, T024) ----


def serie_viva(db: Session, conta_id) -> Serie | None:
    return db.scalar(select(Serie).where(Serie.conta_id == conta_id,
                                         Serie.anonimizada_em.is_(None)))


def serie_ativa(serie: Serie | None, conexao: Conexao | None, settings: Settings) -> bool:
    """As 5 condições do data-model: série viva, conexão `conectada`, escopos, sem
    `sem_permissao_desde` e `METRICAS_COLETA_HABILITADA`."""
    return (serie is not None and serie.anonimizada_em is None
            and conexao is not None and conexao.estado == ConexaoEstado.conectada
            and conexoes.metricas_liberadas(conexao)
            and serie.sem_permissao_desde is None
            and settings.metricas_coleta_habilitada)


def _proxima(db: Session, serie: Serie) -> datetime | None:
    fila = db.scalar(select(func.min(VideoRede.proxima_coleta_em))
                     .where(VideoRede.serie_id == serie.id))
    candidatas = [t for t in (serie.lista_proxima_em, serie.conta_proxima_em, fila) if t]
    proxima = min(candidatas) if candidatas else None
    if serie.adiar_ate is not None and (proxima is None or serie.adiar_ate > proxima):
        proxima = serie.adiar_ate
    return proxima


def estado_coleta(db: Session, conta: Conta, conexao: Conexao | None,
                  settings: Settings | None = None) -> EstadoColeta:
    settings = settings or get_settings()
    serie = serie_viva(db, conta.id)
    videos = fotos = 0
    proxima = None
    if serie is not None:
        videos = db.scalar(select(func.count()).select_from(VideoRede)
                           .where(VideoRede.serie_id == serie.id)) or 0
        fotos = db.scalar(select(func.count()).select_from(FotoVideo)
                          .join(VideoRede, VideoRede.id == FotoVideo.video_id)
                          .where(VideoRede.serie_id == serie.id)) or 0
        fotos += db.scalar(select(func.count()).select_from(FotoConta)
                           .where(FotoConta.serie_id == serie.id)) or 0
        proxima = _proxima(db, serie)
    return montar_estado(conexao, serie, settings, videos, fotos, proxima)


def montar_estado(conexao: Conexao | None, serie: Serie | None, settings: Settings,
                  videos: int = 0, fotos: int = 0,
                  proxima: datetime | None = None) -> EstadoColeta:
    """A parte sem banco do `EstadoColeta` (testável sozinha)."""
    conectada = conexao is not None and conexao.estado == ConexaoEstado.conectada
    faltando = sorted(conexoes.ESCOPOS_METRICAS - set(conexao.escopos or ())) \
        if conectada else []
    permissao = "sem_conexao" if not conectada else ("faltando" if faltando else "ok")
    ativa = serie_ativa(serie, conexao, settings)
    erro = None
    if serie is not None and serie.ultimo_erro_codigo and serie.ultimo_erro_em:
        erro = ErroColeta(codigo=serie.ultimo_erro_codigo,
                          motivo=serie.ultimo_erro_motivo or "", em=serie.ultimo_erro_em)
    return EstadoColeta(
        permissao=permissao, escopos_faltando=faltando, coletando=ativa,
        habilitada=settings.metricas_coleta_habilitada,
        ultima_coleta_em=serie.ultima_coleta_em if serie else None,
        proxima_coleta_em=proxima if ativa else None,
        erro=erro,
        varredura_concluida=bool(serie and serie.varredura_concluida_em),
        videos=videos, fotos=fotos)


# ---- marcos (R15, T063) ----

H1, H24, D7, D30 = 3600, 24 * 3600, 7 * 24 * 3600, 30 * 24 * 3600
MARCOS = {"h1": H1, "h24": H24, "d7": D7, "d30": D30}
METRICAS = ("views", "likes", "comments", "shares")
ESTIMADO_ACIMA = 0.25  # intervalo entre as fotos > 25% de T
ULTIMA_ATE = 0.10  # sem foto depois de T: a última vale se estiver a até 10% de T
SEM_LIMITE = 2**31 - 1  # alvo "depois de tudo" (a última foto)


@dataclass(frozen=True)
class Ponto:
    """Uma foto reduzida ao que os marcos usam."""

    idade_s: int
    views: int | None
    likes: int | None
    comments: int | None
    shares: int | None


def _valor(valor: float | None) -> schemas.MarcoValor:
    if valor is None:
        return schemas.MarcoValor(valor=None, estimado=False, motivo="sem_dado")
    return schemas.MarcoValor(valor=float(valor), estimado=False, motivo=None)


def marco(antes: Ponto | None, depois: Ponto | None, t: int, idade_atual_s: float,
          metrica: str) -> schemas.MarcoValor:
    """O marco `t` (s) de uma métrica, a partir da foto logo antes (`idade_s ≤ t`) e da logo
    depois (`idade_s ≥ t`)."""
    if idade_atual_s < t:
        return schemas.MarcoValor(valor=None, estimado=False, motivo="ainda_nao")
    if antes is not None and antes.idade_s == t:
        return _valor(getattr(antes, metrica))
    if depois is not None and depois.idade_s == t:
        return _valor(getattr(depois, metrica))
    if depois is None:
        if antes is not None and t - antes.idade_s <= ULTIMA_ATE * t:
            return _valor(getattr(antes, metrica))
        return _valor(None)
    a_idade, a_valor = (antes.idade_s, getattr(antes, metrica)) if antes is not None else (0, 0)
    d_valor = getattr(depois, metrica)
    if a_valor is None or d_valor is None:
        return _valor(None)
    valor = a_valor + (d_valor - a_valor) * (t - a_idade) / (depois.idade_s - a_idade)
    return schemas.MarcoValor(valor=float(valor),
                              estimado=depois.idade_s - a_idade > ESTIMADO_ACIMA * t,
                              motivo=None)


def interpolar(antes: Ponto | None, depois: Ponto | None, t: int, metrica: str
               ) -> float | None:
    """Valor cru em `t` (sem motivo), para a velocidade."""
    return marco(antes, depois, t, t, metrica).valor


def vizinhas(pontos: Sequence[Ponto], t: int) -> tuple[Ponto | None, Ponto | None]:
    """(logo antes, logo depois) de `t` numa lista ordenada por idade (a versão em memória do
    `LATERAL`)."""
    antes = next((p for p in reversed(pontos) if p.idade_s <= t), None)
    depois = next((p for p in pontos if p.idade_s >= t), None)
    return antes, depois


def engajamento(ultima: Ponto | None) -> float | None:
    """`(likes + comments + shares) ÷ views` da última foto; 0 com views = 0."""
    if ultima is None or ultima.views is None:
        return None
    if ultima.views == 0:
        return 0.0
    soma = sum(getattr(ultima, m) or 0 for m in ("likes", "comments", "shares"))
    return soma / ultima.views


def velocidade(ultima: Ponto | None, antes: Ponto | None, depois: Ponto | None
               ) -> float | None:
    """Views por hora nas últimas 24 h de idade (`última − interpolado(idade − 24 h)` ÷ 24);
    com menos de 24 h, `views ÷ idade_h`. `antes`/`depois` são as vizinhas de `idade − 24 h`."""
    if ultima is None or ultima.views is None or ultima.idade_s <= 0:
        return None
    if ultima.idade_s < H24:
        return ultima.views / (ultima.idade_s / 3600)
    base = interpolar(antes, depois, ultima.idade_s - H24, "views")
    return None if base is None else (ultima.views - base) / 24


def _marcos(pontos_por_t: dict[int, tuple[Ponto | None, Ponto | None]],
            idade_atual_s: float) -> schemas.Marcos:
    def um(t: int) -> schemas.MarcoMetricas:
        antes, depois = pontos_por_t[t]
        return schemas.MarcoMetricas(**{m: marco(antes, depois, t, idade_atual_s, m)
                                        for m in METRICAS})

    return schemas.Marcos(**{nome: um(t) for nome, t in MARCOS.items()})


# ---- buscas por índice (LATERAL) ----

_SQL_VIZINHAS = text("""
SELECT p.vid, p.alvo,
       a.idade_s, a.views, a.likes, a.comments, a.shares,
       d.idade_s, d.views, d.likes, d.comments, d.shares
FROM unnest(CAST(:vids AS uuid[]), CAST(:alvos AS int[])) AS p(vid, alvo)
LEFT JOIN LATERAL (
    SELECT f.idade_s, f.views, f.likes, f.comments, f.shares FROM metricas_video_fotos f
    WHERE f.video_id = p.vid AND f.idade_s <= p.alvo ORDER BY f.idade_s DESC LIMIT 1) a ON true
LEFT JOIN LATERAL (
    SELECT f.idade_s, f.views, f.likes, f.comments, f.shares FROM metricas_video_fotos f
    WHERE f.video_id = p.vid AND f.idade_s >= p.alvo ORDER BY f.idade_s ASC LIMIT 1) d ON true
""")


def _ponto(linha: Sequence[Any]) -> Ponto | None:
    return None if linha[0] is None else Ponto(*linha)


def _vizinhas_sql(db: Session, pares: Sequence[tuple[uuid.UUID, int]]
                  ) -> dict[tuple[uuid.UUID, int], tuple[Ponto | None, Ponto | None]]:
    """(antes, depois) de cada `(vídeo, alvo_s)`, numa consulta só."""
    if not pares:
        return {}
    rows = db.execute(_SQL_VIZINHAS, {"vids": [str(v) for v, _ in pares],
                                      "alvos": [int(a) for _, a in pares]})
    return {(r[0], r[1]): (_ponto(r[2:7]), _ponto(r[7:12])) for r in rows}


def _ultimas(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, FotoVideo]:
    if not ids:
        return {}
    fotos = db.scalars(text(
        "SELECT u.id FROM unnest(CAST(:vids AS uuid[])) AS p(vid) "
        "JOIN LATERAL (SELECT f.id FROM metricas_video_fotos f WHERE f.video_id = p.vid "
        "ORDER BY f.idade_s DESC LIMIT 1) u ON true"), {"vids": [str(i) for i in ids]}).all()
    if not fotos:
        return {}
    return {f.video_id: f for f in db.scalars(select(FotoVideo).where(FotoVideo.id.in_(fotos)))}


def _p(f: FotoVideo | None) -> Ponto | None:
    return None if f is None else Ponto(f.idade_s, f.views, f.likes, f.comments, f.shares)


@dataclass
class _Numeros:
    marcos: dict[str, tuple[Ponto | None, Ponto | None]]
    ultima: FotoVideo | None
    velocidade: float | None
    engajamento: float | None


def _numeros(db: Session, videos: Sequence[VideoRede], marcos: Sequence[str],
             com_ultima: bool = True) -> dict[uuid.UUID, _Numeros]:
    """Marcos pedidos e, com `com_ultima`, última foto, velocidade e engajamento de cada vídeo
    (buscas por índice; sem a última, só as vizinhas dos marcos)."""
    ultimas = _ultimas(db, [v.id for v in videos]) if com_ultima else {}
    pares = [(v.id, MARCOS[m]) for v in videos for m in marcos]
    pares += [(i, f.idade_s - H24) for i, f in ultimas.items() if f.idade_s >= H24]
    viz = _vizinhas_sql(db, pares)
    out: dict[uuid.UUID, _Numeros] = {}
    for v in videos:
        ultima = ultimas.get(v.id)
        u = _p(ultima)
        vel = None
        if u is not None:
            antes, depois = viz.get((v.id, u.idade_s - H24), (None, None))
            vel = velocidade(u, antes, depois)
        out[v.id] = _Numeros({m: viz.get((v.id, MARCOS[m]), (None, None)) for m in marcos},
                             ultima, vel, engajamento(u))
    return out


def marcos(db: Session, videos: Sequence[VideoRede], agora: datetime | None = None
           ) -> dict[uuid.UUID, schemas.Marcos]:
    """Os 4 marcos de cada vídeo (exportação, R16)."""
    agora = agora or datetime.now(ZoneInfo("UTC"))
    pares = [(v.id, t) for v in videos for t in MARCOS.values()]
    viz = _vizinhas_sql(db, pares)
    return {v.id: _marcos({t: viz.get((v.id, t), (None, None)) for t in MARCOS.values()},
                          _idade(v, agora))
            for v in videos}


# ---- vídeo: resumo e detalhe ----

def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


def _local(dt: datetime | None) -> datetime | None:
    return dt.astimezone(_tz()) if dt is not None else None


def _idade(v: VideoRede, agora: datetime) -> float:
    return (agora - v.publicado_em).total_seconds()


def origem_sql() -> Any:
    """`anonima`, `fora` (sem vínculo) ou a origem do conteúdo ligado (`corte`/`video_proprio`)."""
    return case((VideoRede.anonimizado_em.is_not(None), literal("anonima")),
                (VideoRede.destino_id.is_(None), literal("fora")),
                else_=cast(Conteudo.origem, Text))


def _com_vinculo(stmt: Select) -> Select:
    return (stmt.join(Serie, Serie.id == VideoRede.serie_id)
            .outerjoin(Conta, Conta.id == Serie.conta_id)
            .outerjoin(Postagem, Postagem.id == VideoRede.destino_id)
            .outerjoin(Conteudo, Conteudo.id == Postagem.conteudo_id))


def _foto_out(f: FotoVideo) -> schemas.FotoVideo:
    return schemas.FotoVideo(coletado_em=_local(f.coletado_em), idade_s=f.idade_s,
                             alvo_idade_min=f.alvo_idade_min, views=f.views, likes=f.likes,
                             comments=f.comments, shares=f.shares)


def _resumos(db: Session, videos: Sequence[VideoRede], agora: datetime,
             numeros: dict[uuid.UUID, _Numeros]) -> list[schemas.VideoResumo]:
    if not videos:
        return []
    ids = [v.id for v in videos]
    rows = db.execute(conteudos_consulta.join_corte(_com_vinculo(
        select(VideoRede.id, Serie, Conta, Perfil, Postagem.conteudo_id,
               origem_sql().label("origem"),
               conteudos_consulta.poster_key().label("poster_key"))
        .select_from(VideoRede))
        .outerjoin(Perfil, Perfil.id == Conta.perfil_id))
        .where(VideoRede.id.in_(ids))).all()
    por_id = {r.id: r for r in rows}
    estados = conexoes.conta_refs(db, {r.Conta.id for r in rows if r.Conta is not None})
    out = []
    for v in videos:
        r = por_id[v.id]
        n = numeros[v.id]
        anonimo = v.anonimizado_em is not None
        conta = None if anonimo or r.Conta is None else r.Conta
        idade = _idade(v, agora)
        m24, m7 = n.marcos["h24"], n.marcos["d7"]
        out.append(schemas.VideoResumo(
            id=v.id, rede=r.Serie.rede, conta_id=conta.id if conta else None,
            conta=conta_ref(conta, estados.get(conta.id, "nao_conectada")) if conta else None,
            serie_rotulo=r.Serie.rotulo,
            perfil=PerfilRef(id=r.Perfil.id, name=r.Perfil.name, slug=r.Perfil.slug)
            if conta is not None and r.Perfil is not None else None,
            origem=r.origem, publicado_em=_local(v.publicado_em), duracao_s=v.duracao_s,
            legenda=v.legenda, url=v.share_url, disponivel=v.disponivel,
            indisponivel_desde=_local(v.indisponivel_desde),
            conteudo_id=r.conteudo_id if v.destino_id else None, destino_id=v.destino_id,
            vinculo_metodo=v.vinculo_metodo.value if v.vinculo_metodo else None,
            miniatura_url=imaging.poster_url(r.poster_key)
            if v.destino_id and r.poster_key else None,
            ultima=_foto_out(n.ultima) if n.ultima is not None else None,
            views24h=marco(*m24, H24, idade, "views"), views7d=marco(*m7, D7, idade, "views"),
            engajamento=n.engajamento, velocidade=n.velocidade))
    return out


def resumos(db: Session, videos: Sequence[VideoRede], agora: datetime | None = None
            ) -> list[schemas.VideoResumo]:
    agora = agora or datetime.now(ZoneInfo("UTC"))
    return _resumos(db, videos, agora, _numeros(db, videos, ("h24", "d7")))


def detalhe(db: Session, video: VideoRede, agora: datetime | None = None
            ) -> schemas.VideoDetalhe:
    """Resumo + todas as fotos (curva) + os 4 marcos + quando a coleta parou."""
    agora = agora or datetime.now(ZoneInfo("UTC"))
    fotos = list(db.scalars(select(FotoVideo).where(FotoVideo.video_id == video.id)
                            .order_by(FotoVideo.idade_s, FotoVideo.id)))
    pontos = [_p(f) for f in fotos]
    ultima = fotos[-1] if fotos else None
    u = _p(ultima)
    vel = velocidade(u, *vizinhas(pontos, u.idade_s - H24)) if u is not None else None
    numeros = {video.id: _Numeros({m: vizinhas(pontos, t) for m, t in MARCOS.items()},
                                  ultima, vel, engajamento(u))}
    [resumo] = _resumos(db, [video], agora, numeros)
    parada = None
    if video.anonimizado_em is not None:
        parada = video.anonimizado_em
    elif video.proxima_coleta_em is None and _idade(video, agora) >= 365 * 24 * 3600:
        parada = max(video.publicado_em + timedelta(days=365), video.descoberto_em)
    idade = _idade(video, agora)
    return schemas.VideoDetalhe(
        **resumo.model_dump(), fotos=[_foto_out(f) for f in fotos],
        marcos=_marcos({t: vizinhas(pontos, t) for t in MARCOS.values()}, idade),
        coleta_parada_em=_local(parada))


# ---- ranking (R15) ----

ORDEM_MARCO = {"views24h": "h24", "views7d": "d7"}


def _periodo(de: date | None, ate: date | None) -> tuple[datetime | None, datetime | None]:
    """Datas de `APP_TZ` → instantes: `de` 00:00 inclusive, `ate` até o fim do dia."""
    tz = _tz()
    ini = datetime.combine(de, time.min, tz) if de else None
    fim = datetime.combine(ate + timedelta(days=1), time.min, tz) if ate else None
    return ini, fim


def _cursor_ler(cursor: str | None) -> list[Any] | None:
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "validation_error", "Cursor inválido") from None


def _cursor_escrever(chave: tuple) -> str:
    return base64.urlsafe_b64encode(json.dumps(list(chave)).encode()).decode()


def ranking(db: Session, *, perfil_id: uuid.UUID | None = None,
            conta_id: uuid.UUID | None = None, origens: Sequence[str] | None = None,
            de: date | None = None, ate: date | None = None, ordem: str = "views",
            direcao: str = "desc", cursor: str | None = None, limite: int = 50,
            agora: datetime | None = None) -> schemas.VideosList:
    """Filtros em SQL; a métrica da ordem calculada para todos os filtrados (2 buscas por
    índice por vídeo) e a página montada só para os `limite` da vez. `views` (padrão) é o total
    atual: as views da última foto. Ordem estável: (métrica,
    `publicado_em`, `id`), com os sem valor no fim nas duas direções. Sem `origem`, as séries
    anônimas ficam de fora (elas entram com `origem=anonima`)."""
    agora = agora or datetime.now(ZoneInfo("UTC"))
    stmt = _com_vinculo(select(VideoRede).select_from(VideoRede))
    origem = origem_sql()
    stmt = stmt.where(origem.in_(list(origens)) if origens else origem != "anonima")
    if conta_id is not None:
        stmt = stmt.where(Serie.conta_id == conta_id)
    if perfil_id is not None:
        stmt = stmt.where(Conta.perfil_id == perfil_id)
    ini, fim = _periodo(de, ate)
    if ini is not None:
        stmt = stmt.where(VideoRede.publicado_em >= ini)
    if fim is not None:
        stmt = stmt.where(VideoRede.publicado_em < fim)
    videos = list(db.scalars(stmt))
    sinal = -1 if direcao == "desc" else 1

    if ordem == "publicadoEm":
        valores = {v.id: v.publicado_em.timestamp() for v in videos}
    elif ordem == "views":
        # total atual: basta a última foto (1 busca por índice por vídeo)
        ultimas = _ultimas(db, [v.id for v in videos])
        valores = {v.id: ultimas[v.id].views if v.id in ultimas else None for v in videos}
    else:
        marco_nome = ORDEM_MARCO.get(ordem)
        # ordem por marco: bastam as vizinhas dele (a última só para engajamento/velocidade)
        numeros = _numeros(db, videos, (marco_nome,) if marco_nome else (),
                           com_ultima=marco_nome is None)
        if marco_nome:
            t = MARCOS[marco_nome]
            valores = {v.id: marco(*numeros[v.id].marcos[marco_nome], t, _idade(v, agora),
                                   "views").valor for v in videos}
        else:
            valores = {v.id: getattr(numeros[v.id], ordem) for v in videos}

    def chave(v: VideoRede) -> tuple:
        valor = valores[v.id]
        return (valor is None, sinal * (valor or 0), sinal * v.publicado_em.timestamp(),
                sinal * v.id.int)

    ordenados = sorted(videos, key=chave)
    depois = _cursor_ler(cursor)
    if depois is not None:
        ordenados = [v for v in ordenados if list(chave(v)) > depois]
    pagina = ordenados[:limite]
    proximo = _cursor_escrever(chave(pagina[-1])) if len(ordenados) > limite else None
    return schemas.VideosList(items=_resumos(db, pagina, agora,
                                             _numeros(db, pagina, ("h24", "d7"))),
                              next_cursor=proximo, total=len(videos))


# ---- conta (US4) ----

AUTO_HORA_ATE = timedelta(days=14)
PERIODO_PADRAO = timedelta(days=30)

# A rede não dá as views totais da conta: elas são derivadas das fotos dos vídeos. Em cada corte
# `t`, soma-se, por vídeo da série, as views da última foto com `coletado_em ≤ t` (vídeo sem foto
# até `t` não entra). Uma volta da coleta grava a foto da conta e as dos vídeos com o mesmo
# `agora`, então o corte no `coletado_em` da foto da conta já pega os vídeos da mesma volta.
_SQL_VIEWS_CONTA = text("""
SELECT c.t, sum(u.views), count(u.views)
FROM unnest(CAST(:cortes AS timestamptz[])) AS c(t)
CROSS JOIN metricas_videos v
JOIN LATERAL (
    SELECT f.views FROM metricas_video_fotos f
    WHERE f.video_id = v.id AND f.coletado_em <= c.t AND f.views IS NOT NULL
    ORDER BY f.idade_s DESC, f.id DESC LIMIT 1) u ON true
WHERE v.serie_id = :serie
GROUP BY c.t
""")


def views_conta(db: Session, serie_id: uuid.UUID, cortes: Sequence[datetime]
                ) -> dict[datetime, int | None]:
    """Views totais da série em cada corte (None quando nenhum vídeo tinha foto até ali)."""
    if not cortes:
        return {}
    rows = db.execute(_SQL_VIEWS_CONTA, {"cortes": list(cortes), "serie": serie_id})
    somas = {r[0]: int(r[1]) for r in rows if r[2]}
    return {t: somas.get(t) for t in cortes}


def conta_metricas(db: Session, conta: Conta, de: date | None = None, ate: date | None = None,
                   resolucao: str = "auto") -> schemas.ContaMetricasOut:
    """Fotos da conta no período (hora até 14 dias em `auto`, senão a última de cada dia de
    `APP_TZ`), com as views derivadas dos vídeos em cada foto, o total atual de views e as
    publicações marcadas."""
    tz = _tz()
    hoje = datetime.now(tz).date()
    ate = ate or hoje
    de = de or (ate - PERIODO_PADRAO)
    if de > ate:
        raise ApiError(400, "validation_error", "O início do período é depois do fim")
    ini, fim = _periodo(de, ate)
    coleta = estado_coleta(db, conta, conexoes.conexao_viva(db, conta.id))
    serie = serie_viva(db, conta.id)
    if serie is None:
        return schemas.ContaMetricasOut(coleta=coleta, fotos=[], publicacoes=[],
                                        views_total=None)
    fotos = list(db.scalars(select(FotoConta).where(
        FotoConta.serie_id == serie.id, FotoConta.janela_em >= ini, FotoConta.janela_em < fim)
        .order_by(FotoConta.janela_em)))
    por_hora = resolucao == "hora" or (resolucao == "auto" and fim - ini <= AUTO_HORA_ATE)
    if not por_hora:
        por_dia: dict[date, FotoConta] = {}
        for f in fotos:
            por_dia[f.janela_em.astimezone(tz).date()] = f  # a última de cada dia
        fotos = list(por_dia.values())
    agora = datetime.now(ZoneInfo("UTC"))
    views = views_conta(db, serie.id, [f.coletado_em for f in fotos] + [agora])
    pubs = db.execute(select(VideoRede.id, VideoRede.publicado_em, Postagem.conteudo_id)
                      .outerjoin(Postagem, Postagem.id == VideoRede.destino_id)
                      .where(VideoRede.serie_id == serie.id, VideoRede.publicado_em >= ini,
                             VideoRede.publicado_em < fim)
                      .order_by(VideoRede.publicado_em, VideoRede.id)).all()
    return schemas.ContaMetricasOut(
        coleta=coleta,
        fotos=[schemas.FotoConta(coletado_em=_local(f.coletado_em), janela_em=_local(f.janela_em),
                                 seguidores=f.seguidores, seguindo=f.seguindo,
                                 curtidas=f.curtidas, videos=f.videos,
                                 views=views[f.coletado_em]) for f in fotos],
        views_total=views[agora],
        publicacoes=[schemas.Publicacao(video_id=p.id, publicado_em=_local(p.publicado_em),
                                        conteudo_id=p.conteudo_id) for p in pubs])
