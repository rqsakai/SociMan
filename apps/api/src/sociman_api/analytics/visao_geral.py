"""Visão geral (spec 019, US1; FR-012 a FR-015): os 6 indicadores do período contra o anterior
de mesma duração, a série diária de views ganhas por conta, os 10 vídeos que mais ganharam views
no período, os insights e o ranking compacto da 016.

- `views`/`likes`: soma dos ganhos do período (`base.ganhos`); `engajamento`: (Δlikes +
  Δcomments + Δshares) ÷ Δviews; `seguidores`: por série, a última foto da conta antes do fim
  menos a última antes do início (sem foto antes, a primeira do período); `posts`: publicados no
  período; `mediana_post`: mediana da medida dos posts medidos.
- Variação = (valor − anterior) ÷ anterior; `null` ("sem base de comparação") sem anterior ou
  com anterior zero. Sem nenhum dado, o valor também é `null`.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, insights, schemas
from sociman_api.analytics.base import Ganho, PostAnalisado
from sociman_api.analytics.estatistica import mediana
from sociman_api.analytics.filtros import Filtro, Periodo
from sociman_api.metricas import consulta
from sociman_api.metricas.models import FotoConta, Serie
from sociman_api.metricas.schemas import VideosList
from sociman_api.perfis.models import Conta

PRINCIPAIS = 10
RANKING_LIMITE = 10


def seguidores(db: Session, filtro: Filtro, periodo: Periodo) -> tuple[int | None, int]:
    """(seguidores ganhos somados, séries com dado) no período."""
    stmt = select(Serie.id).outerjoin(Conta, Conta.id == Serie.conta_id)
    if filtro.conta_id is not None:
        stmt = stmt.where(Serie.conta_id == filtro.conta_id)
    elif filtro.perfil_id is not None:
        stmt = stmt.where(Conta.perfil_id == filtro.perfil_id)
    if filtro.rede is not None:
        stmt = stmt.where(Serie.rede == filtro.rede)
    fotos: dict[uuid.UUID, list[tuple[datetime, int]]] = {}
    for sid, quando, n in db.execute(
            select(FotoConta.serie_id, FotoConta.coletado_em, FotoConta.seguidores)
            .where(FotoConta.serie_id.in_(stmt), FotoConta.coletado_em < periodo.fim,
                   FotoConta.seguidores.is_not(None))
            .order_by(FotoConta.serie_id, FotoConta.coletado_em, FotoConta.id)):
        fotos.setdefault(sid, []).append((quando, int(n)))
    total, n = 0, 0
    for fs in fotos.values():
        inicio = base.views_antes(fs, periodo.ini)
        if inicio is None:
            no_periodo = [v for t, v in fs if t >= periodo.ini]
            if not no_periodo:
                continue
            inicio = no_periodo[0]
        total += fs[-1][1] - inicio
        n += 1
    return (total if n else None), n


def valores(posts: Sequence[PostAnalisado], ganhos: dict[uuid.UUID, Ganho],
             seg: tuple[int | None, int]) -> dict[str, tuple[float | None, int]]:
    """chave → (valor, n) de um período."""
    g = list(ganhos.values())
    views = sum(x.views for x in g)
    interacoes = sum(x.likes + x.comments + x.shares for x in g)
    medidos = [p.medida.valor for p in posts if p.medido]
    return {
        "views": (views if g else None, len(g)),
        "likes": (sum(x.likes for x in g) if g else None, len(g)),
        "engajamento": (interacoes / views if views else None, len(g)),
        "seguidores": seg,
        "posts": (len(posts), len(posts)),
        "mediana_post": (mediana(medidos), len(medidos)),  # type: ignore[arg-type]
    }


_valores = valores  # nome antigo (a aba Contas migra para `valores`)


def variacao(valor: float | None, anterior: float | None) -> float | None:
    if valor is None or not anterior:
        return None
    return (valor - anterior) / anterior


def indicadores(atual: dict[str, tuple[float | None, int]],
                anterior: dict[str, tuple[float | None, int]]) -> list[schemas.Indicador]:
    return [schemas.Indicador(chave=chave, valor=valor, anterior=anterior[chave][0],
                              variacao_pct=variacao(valor, anterior[chave][0]), n=n)
            for chave, (valor, n) in atual.items()]


def _ordem_conta(conta_id: uuid.UUID | None, rotulo: str) -> tuple:
    return (conta_id is None, str(conta_id) if conta_id else rotulo)


def serie_diaria(videos: Sequence[base.VideoEscopo],
                 por_dia: dict) -> list[schemas.DiaSerie]:
    """Views ganhas por dia e conta; toda conta do escopo aparece em todo dia (0 sem ganho),
    na ordem estável do `contaId` (anônimas no fim)."""
    conta_de = {v.video_id: (v.conta_id, v.rotulo_conta) for v in videos}
    contas = sorted(set(conta_de.values()), key=lambda c: _ordem_conta(*c))
    out = []
    for dia, ganhos in sorted(por_dia.items()):
        soma = dict.fromkeys(contas, 0)
        for vid, views in ganhos.items():
            soma[conta_de[vid]] += views
        out.append(schemas.DiaSerie(dia=dia, por_conta=[
            schemas.ViewsConta(conta_id=c, rotulo=r, views=soma[(c, r)]) for c, r in contas]))
    return out


def principais(db: Session, filtro: Filtro, ganhos: dict[uuid.UUID, Ganho],
               agora: datetime | None = None) -> list[schemas.PostResumo]:
    """Top 10 por views ganhas no período (desempate: o mais recente)."""
    com_ganho = {vid: g.views for vid, g in ganhos.items() if g.views > 0}
    posts = base.posts_por_id(db, filtro, list(com_ganho), agora)
    posts.sort(key=lambda p: (-com_ganho[p.video_id], -p.publicado_em.timestamp()))
    return [base.resumo(p, com_ganho[p.video_id]) for p in posts[:PRINCIPAIS]]


def ranking(db: Session, filtro: Filtro) -> VideosList:
    """A 1ª página do ranking da 016 (views totais), com o período e o escopo do filtro."""
    lista = consulta.ranking(db, perfil_id=filtro.perfil_id, conta_id=filtro.conta_id,
                             de=filtro.atual.de, ate=filtro.atual.ate, limite=RANKING_LIMITE)
    if filtro.rede is not None:
        itens = [v for v in lista.items if v.rede == filtro.rede]
        lista = VideosList(items=itens, next_cursor=lista.next_cursor if itens else None,
                           total=lista.total if itens else 0)
    return lista


def calcular(db: Session, filtro: Filtro, agora: datetime | None = None
             ) -> schemas.VisaoGeralOut:
    posts = base.posts(db, filtro, agora=agora)
    anteriores = base.posts(db, filtro, periodo=filtro.anterior, agora=agora)
    ganhos = base.ganhos(db, filtro)
    atual = valores(posts, ganhos, seguidores(db, filtro, filtro.atual))
    antes = valores(anteriores, base.ganhos(db, filtro, filtro.anterior),
                     seguidores(db, filtro, filtro.anterior))
    videos, por_dia = base.ganhos_por_dia(db, filtro)
    return schemas.VisaoGeralOut(
        contexto=base.contexto(filtro, posts), indicadores=indicadores(atual, antes),
        serie_diaria=serie_diaria(videos, por_dia),
        principais=principais(db, filtro, ganhos, agora),
        insights=insights.regras(posts, filtro.medida), ranking=ranking(db, filtro))
