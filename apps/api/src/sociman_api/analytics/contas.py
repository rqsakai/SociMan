"""Contas, perfis e redes (spec 019, US5; FR-025 a FR-027).

- **Tabelas:** os 6 indicadores da visão geral (mesmo cálculo, `visao_geral`) por conta e por
  perfil, só das contas com dado no período (post publicado ou views ganhas). Contas anônimas
  ficam de fora (não têm `contaId`); no perfil entram as contas dele que aparecem na tabela.
- **Radar:** 6 eixos por conta com post no período contra a média simples dessas contas
  (índice = valor ÷ média × 100, cortado em 200 com `acima`). Com menos de `MIN_CONTAS_RADAR`
  contas, `radar = null` e o motivo. O radar ignora o filtro de conta (a média precisa das
  outras contas do perfil, ou de todas): com `contaId`, devolve só o radar daquela conta.

Eixos: `views_por_post` (mediana da medida), `engajamento` (Δinterações ÷ Δviews no período),
`frequencia` (posts por dia), `crescimento` (seguidores ganhos ÷ seguidores no início, fração),
`velocidade_1h` (mediana do marco de 1 h) e `acima_mediana` (fração dos posts medidos da conta
acima da mediana de todos os posts medidos das contas do radar). Só leitura.
"""

import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, estatistica, schemas, visao_geral
from sociman_api.analytics.base import Ganho, PostAnalisado
from sociman_api.analytics.filtros import Filtro, Periodo
from sociman_api.canais.schemas import PerfilRef
from sociman_api.metricas.models import FotoConta, Serie
from sociman_api.perfis.models import Conta, Perfil

ACIMA_DE = 200.0
EIXOS = ("views_por_post", "engajamento", "frequencia", "crescimento", "velocidade_1h",
         "acima_mediana")


def _so(posts: Sequence[PostAnalisado], contas: set[uuid.UUID]) -> list[PostAnalisado]:
    return [p for p in posts if p.conta_id in contas]


def _ganhos_de(ganhos: dict[uuid.UUID, Ganho], conta_de: dict[uuid.UUID, uuid.UUID | None],
               contas: set[uuid.UUID]) -> dict[uuid.UUID, Ganho]:
    return {vid: g for vid, g in ganhos.items() if conta_de.get(vid) in contas}


def _seguidores(partes: Sequence[tuple[int | None, int]]) -> tuple[int | None, int]:
    com = [v for v, _ in partes if v is not None]
    return (sum(com) if com else None), sum(n for _, n in partes)


def crescimento(db: Session, conta_id: uuid.UUID, periodo: Periodo) -> float | None:
    """Seguidores ganhos ÷ seguidores no início (a última foto antes do início; sem ela, a
    primeira do período), na série viva da conta. None sem foto ou com base zero."""
    fotos = [(t, int(n)) for t, n in db.execute(
        select(FotoConta.coletado_em, FotoConta.seguidores)
        .join(Serie, Serie.id == FotoConta.serie_id)
        .where(Serie.conta_id == conta_id, Serie.anonimizada_em.is_(None),
               FotoConta.coletado_em < periodo.fim, FotoConta.seguidores.is_not(None))
        .order_by(FotoConta.coletado_em, FotoConta.id))]
    inicio = base.views_antes(fotos, periodo.ini)
    if inicio is None:
        no_periodo = [n for t, n in fotos if t >= periodo.ini]
        inicio = no_periodo[0] if no_periodo else None
    if not inicio:
        return None
    return (fotos[-1][1] - inicio) / inicio


# ---- radar ----

def _media(valores: Sequence[float | None]) -> float | None:
    com = [v for v in valores if v is not None]
    return sum(com) / len(com) if com else None


def eixo(chave: str, valor: float | None, media: float | None) -> schemas.EixoRadar:
    if valor is None or not media:
        return schemas.EixoRadar(chave=chave, valor=valor, media=media, indice=None, acima=False)
    indice = valor / media * 100
    return schemas.EixoRadar(chave=chave, valor=valor, media=media,
                             indice=min(indice, ACIMA_DE), acima=indice > ACIMA_DE)


def radar(db: Session, filtro: Filtro, posts: Sequence[PostAnalisado],
          posts_h1: Sequence[PostAnalisado], ganhos: dict[uuid.UUID, Ganho],
          conta_de: dict[uuid.UUID, uuid.UUID | None], rotulos: dict[uuid.UUID, str]
          ) -> tuple[list[schemas.RadarConta] | None, str | None]:
    contas = sorted({p.conta_id for p in posts if p.conta_id is not None},
                    key=lambda c: rotulos[c])
    if len(contas) < estatistica.MIN_CONTAS_RADAR:
        return None, (f"O radar precisa de pelo menos {estatistica.MIN_CONTAS_RADAR} contas "
                      f"com posts no período (há {len(contas)}).")
    geral = estatistica.mediana([p.medida.valor for p in posts  # type: ignore[misc]
                                 if p.medido and p.conta_id in contas])
    valores: dict[uuid.UUID, dict[str, float | None]] = {}
    for c in contas:
        dela = [p for p in posts if p.conta_id == c]
        medidos = [p.medida.valor for p in dela if p.medido]
        g = _ganhos_de(ganhos, conta_de, {c}).values()
        views = sum(x.views for x in g)
        h1 = [p.medida.valor for p in posts_h1 if p.conta_id == c and p.medido]
        valores[c] = {
            "views_por_post": estatistica.mediana(medidos),  # type: ignore[arg-type]
            "engajamento": sum(x.likes + x.comments + x.shares for x in g) / views
            if views else None,
            "frequencia": len(dela) / filtro.atual.dias,
            "crescimento": crescimento(db, c, filtro.atual),
            "velocidade_1h": estatistica.mediana(h1),  # type: ignore[arg-type]
            "acima_mediana": sum(v > geral for v in medidos) / len(medidos)  # type: ignore
            if medidos and geral is not None else None,
        }
    medias = {e: _media([valores[c][e] for c in contas]) for e in EIXOS}
    escolhidas = [c for c in contas if filtro.conta_id in (None, c)]
    if not escolhidas:
        return None, "A conta não tem posts no período."
    return [schemas.RadarConta(conta_id=c, rotulo=rotulos[c],
                               eixos=[eixo(e, valores[c][e], medias[e]) for e in EIXOS])
            for c in escolhidas], None


# ---- tabelas ----

def calcular(db: Session, filtro: Filtro, agora: datetime | None = None) -> schemas.ContasOut:
    largo = replace(filtro, conta_id=None)  # perfil e rede continuam valendo
    posts = base.posts(db, largo, agora=agora)
    anteriores = base.posts(db, largo, periodo=largo.anterior, agora=agora)
    ganhos = base.ganhos(db, largo)
    ganhos_ant = base.ganhos(db, largo, largo.anterior)
    conta_de = {v.video_id: v.conta_id for v in base.videos_escopo(db, largo)}
    com_dado = {p.conta_id for p in posts if p.conta_id is not None} | {
        conta_de[vid] for vid, g in ganhos.items()
        if g.views > 0 and conta_de.get(vid) is not None}
    rows = db.execute(select(Conta, Perfil).join(Perfil, Perfil.id == Conta.perfil_id)
                      .where(Conta.id.in_(com_dado))).all() if com_dado else []
    info = {c.id: (c, p) for c, p in rows}
    rotulos = {cid: f"@{c.handle}" for cid, (c, _) in info.items()}

    def indicadores(contas: set[uuid.UUID],
                    seg: dict[uuid.UUID, tuple[tuple[int | None, int], ...]]
                    ) -> list[schemas.Indicador]:
        atual = visao_geral.valores(_so(posts, contas), _ganhos_de(ganhos, conta_de, contas),
                                     _seguidores([seg[c][0] for c in contas]))
        antes = visao_geral.valores(_so(anteriores, contas),
                                     _ganhos_de(ganhos_ant, conta_de, contas),
                                     _seguidores([seg[c][1] for c in contas]))
        return visao_geral.indicadores(atual, antes)

    na_tabela = sorted((c for c in info if filtro.conta_id in (None, c)),
                       key=lambda c: rotulos[c])
    seg = {c: (visao_geral.seguidores(db, replace(largo, conta_id=c), largo.atual),
               visao_geral.seguidores(db, replace(largo, conta_id=c), largo.anterior))
           for c in na_tabela}
    contas_out = []
    perfis: dict[uuid.UUID, tuple[Perfil, set[uuid.UUID]]] = {}
    for c in na_tabela:
        conta, perfil = info[c]
        ref = PerfilRef(id=perfil.id, name=perfil.name, slug=perfil.slug)
        contas_out.append(schemas.ContaLinha(conta_id=c, rotulo=rotulos[c], perfil=ref,
                                             rede=conta.platform,
                                             indicadores=indicadores({c}, seg)))
        perfis.setdefault(perfil.id, (perfil, set()))[1].add(c)
    perfis_out = [schemas.PerfilLinha(perfil=PerfilRef(id=p.id, name=p.name, slug=p.slug),
                                      indicadores=indicadores(cs, seg))
                  for p, cs in sorted(perfis.values(), key=lambda x: x[0].name)]

    h1 = posts if filtro.medida == "h1" else base.posts(db, replace(largo, medida="h1"),
                                                         agora=agora)
    radar_out, motivo = radar(db, filtro, posts, h1, ganhos, conta_de, rotulos)
    contexto = base.contexto(filtro, base.posts(db, filtro, agora=agora)
                             if filtro.conta_id is not None else posts)
    return schemas.ContasOut(contexto=contexto, contas=contas_out, perfis=perfis_out,
                             radar=radar_out, radar_motivo=motivo)
