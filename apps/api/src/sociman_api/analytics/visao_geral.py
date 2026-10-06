"""Visão geral (spec 019, US1; FR-012 a FR-015): os 6 indicadores do período contra o anterior
de mesma duração, a série diária de views ganhas por conta, os 10 vídeos que mais ganharam views
no período, os insights e o ranking compacto da 016.

- `views`/`likes`: soma dos ganhos do período; `engajamento`: (Δlikes + Δcomments + Δshares) ÷
  Δviews; `seguidores`: por série, a última foto da conta antes do fim menos a última antes do
  início (sem foto antes, a primeira do período); `posts`: publicados no período;
  `mediana_post`: mediana da medida dos posts medidos.
- Spec 020: views, curtidas, engajamento e seguidores somam os totais diários
  (`base.totais_diarios`), que usam o Studio nos dias que a coleta não cobre inteiros; sem Studio,
  é o mesmo número do delta do período. `diasStudio` conta esses dias.
- Variação = (valor − anterior) ÷ anterior; `null` ("sem base de comparação") sem anterior ou
  com anterior zero. Sem nenhum dado, o valor também é `null`.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy.orm import Session

from sociman_api.analytics import base, insights, schemas
from sociman_api.analytics.base import Ganho, PostAnalisado
from sociman_api.analytics.estatistica import mediana
from sociman_api.analytics.filtros import Filtro, Periodo
from sociman_api.metricas import consulta
from sociman_api.metricas.schemas import VideosList

PRINCIPAIS = 10
RANKING_LIMITE = 10


def valores(posts: Sequence[PostAnalisado], ganhos: dict[uuid.UUID, Ganho],
            totais: dict[uuid.UUID, dict[date, base.TotalDia]]
            ) -> dict[str, tuple[float | None, int, int]]:
    """chave → (valor, n, dias do Studio) de um período. Views, curtidas, engajamento e
    seguidores somam os totais diários (`base.totais_diarios`); `n` continua sendo o número de
    vídeos com dado (ou de séries, nos seguidores)."""
    dias = [t for por_dia in totais.values() for t in por_dia.values()]
    com = [t for t in dias if t.views is not None]
    views = sum(t.views for t in com)  # type: ignore[misc]
    likes = sum(t.likes or 0 for t in com)
    interacoes = sum((t.likes or 0) + (t.comments or 0) + (t.shares or 0) for t in com)
    studio = len({d for por_dia in totais.values() for d, t in por_dia.items()
                  if t.fonte == "studio"})
    seg_series = [[t.seguidores_dif for t in por_dia.values() if t.seguidores_dif is not None]
                  for por_dia in totais.values()]
    seg_series = [s for s in seg_series if s]
    seg_studio = len({d for por_dia in totais.values() for d, t in por_dia.items()
                      if t.fonte_seguidores == "studio" and t.seguidores_dif is not None})
    medidos = [p.medida.valor for p in posts if p.medido]
    n = len(ganhos)
    return {
        "views": (views if com else None, n, studio),
        "likes": (likes if com else None, n, studio),
        "engajamento": (interacoes / views if views else None, n, studio),
        "seguidores": (sum(map(sum, seg_series)) if seg_series else None, len(seg_series),
                       seg_studio),
        "posts": (len(posts), len(posts), 0),
        "mediana_post": (mediana(medidos), len(medidos), 0),  # type: ignore[arg-type]
    }


def variacao(valor: float | None, anterior: float | None) -> float | None:
    if valor is None or not anterior:
        return None
    return (valor - anterior) / anterior


def indicadores(atual: dict[str, tuple[float | None, int, int]],
                anterior: dict[str, tuple[float | None, int, int]]) -> list[schemas.Indicador]:
    return [schemas.Indicador(chave=chave, valor=valor, anterior=anterior[chave][0],
                              variacao_pct=variacao(valor, anterior[chave][0]), n=n,
                              dias_studio=dias_studio)
            for chave, (valor, n, dias_studio) in atual.items()]


def _ordem_conta(conta_id: uuid.UUID | None, rotulo: str) -> tuple:
    return (conta_id is None, str(conta_id) if conta_id else rotulo)


def serie_diaria(series: Sequence[base.SerieEscopo],
                 totais: dict[uuid.UUID, dict[date, base.TotalDia]],
                 periodo: Periodo) -> list[schemas.DiaSerie]:
    """Views ganhas por dia e conta; toda conta do escopo com vídeo (ou com dia do Studio no
    período) aparece em todo dia (0 sem ganho), na ordem estável do `contaId` (anônimas no fim).
    Cada dia diz a fonte (`studio` quando alguma série da conta usou o Studio) e traz as views
    da outra fonte em `comparacao` e as visitas ao perfil (spec 020)."""
    grupos: dict[tuple, list[uuid.UUID]] = {}
    for s in series:
        usa_studio = any(t.fonte == "studio" for t in totais[s.serie_id].values())
        if s.tem_videos or usa_studio:
            grupos.setdefault((s.conta_id, s.rotulo), []).append(s.serie_id)
    contas = sorted(grupos, key=lambda c: _ordem_conta(*c))
    out = []
    for dia in base.dias(periodo):
        por_conta = []
        for c, r in contas:
            ts = [totais[sid][dia] for sid in grupos[(c, r)]]
            comparacoes = [t.comparacao for t in ts if t.comparacao is not None]
            visitas = [t.visitas_perfil for t in ts if t.visitas_perfil is not None]
            por_conta.append(schemas.ViewsConta(
                conta_id=c, rotulo=r, views=sum(t.views or 0 for t in ts),
                fonte="studio" if any(t.fonte == "studio" for t in ts) else "coletado",
                comparacao=sum(comparacoes) if comparacoes else None,
                visitas_perfil=sum(visitas) if visitas else None))
        out.append(schemas.DiaSerie(dia=dia, por_conta=por_conta))
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
    series = base.series_escopo(db, filtro)
    totais = base.totais_diarios(db, filtro, series=series)
    atual = valores(posts, ganhos, totais)
    antes = valores(anteriores, base.ganhos(db, filtro, filtro.anterior),
                    base.totais_diarios(db, filtro, filtro.anterior, series))
    return schemas.VisaoGeralOut(
        contexto=base.contexto(filtro, posts), indicadores=indicadores(atual, antes),
        serie_diaria=serie_diaria(series, totais, filtro.atual),
        principais=principais(db, filtro, ganhos, agora),
        insights=insights.regras(posts, filtro.medida), ranking=ranking(db, filtro))
