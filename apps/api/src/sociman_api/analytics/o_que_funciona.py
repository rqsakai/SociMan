"""O que funciona (spec 019, US3; FR-019 a FR-022).

As análises de corte (dispersões, canais-fonte, modos e padrões) usam só os posts **vinculados**
a um destino do SociMan e já medidos; os sem vínculo (inclusive anônimos) ficam fora e são
contados em `excluidosSemVinculo`. As hashtags (do destino ∪ da legenda) existem também fora do
SociMan, então o lift usa todos os posts medidos.

- Dispersões: medida × duração (s), × gancho (caracteres) e × score; ρ de Spearman e leitura só
  com `MIN_CORRELACAO` pontos (abaixo, só os pontos e a amostra).
- Canais, modos e padrões: n, mediana da medida (modos e padrões também a do engajamento) e lift
  sobre a mediana geral dos vinculados, só com `MIN_GRUPO` posts no grupo; ordem por mediana.
- Hashtags: só as usadas em `MIN_GRUPO` posts; lift = mediana com a hashtag ÷ mediana geral;
  ordem por lift (do maior para o menor).
"""

from collections.abc import Callable, Hashable, Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from sociman_api.analytics import base, schemas
from sociman_api.analytics.base import PostAnalisado
from sociman_api.analytics.estatistica import (
    MIN_CORRELACAO,
    MIN_GRUPO,
    leitura_correlacao,
    lift,
    mediana,
    spearman,
)
from sociman_api.analytics.filtros import Filtro

MODOS = {"lembrete": "Lembrete", "criar_rascunho": "Rascunho", "publicar": "Publicar direto"}


def dispersao(posts: Sequence[PostAnalisado],
              x: Callable[[PostAnalisado], float | None]) -> schemas.Dispersao:
    pontos = [schemas.PontoDispersao(video_id=p.video_id, x=float(vx), y=p.medida.valor,  # type: ignore[arg-type]
                                     estimado=p.medida.estimado, titulo_curto=p.titulo_curto,
                                     conta_id=p.conta_id, conta=p.rotulo_conta)
              for p in posts if (vx := x(p)) is not None]
    n = len(pontos)
    rho = spearman([q.x for q in pontos], [q.y for q in pontos]) \
        if n >= MIN_CORRELACAO else None
    return schemas.Dispersao(pontos=pontos, correlacao=schemas.Correlacao(
        rho=rho, leitura=leitura_correlacao(rho), amostra=base.amostra(n, MIN_CORRELACAO)))


def linhas(posts: Sequence[PostAnalisado], geral: float | None,
           chaves: Callable[[PostAnalisado], Sequence[tuple[Hashable, str]]], *,
           com_engajamento: bool = False, com_direito: bool = False
           ) -> list[schemas.LinhaRanking]:
    grupos: dict[Hashable, list[PostAnalisado]] = {}
    rotulos: dict[Hashable, str] = {}
    for p in posts:
        for chave, rotulo in chaves(p):
            grupos.setdefault(chave, []).append(p)
            rotulos[chave] = rotulo
    out = []
    for chave, ps in grupos.items():
        med = mediana([p.medida.valor for p in ps])  # type: ignore[misc]
        amostra = base.amostra(len(ps), MIN_GRUPO)
        engs = [p.engajamento for p in ps if p.engajamento is not None]
        canal = ps[0].canal_fonte if com_direito else None
        out.append(schemas.LinhaRanking(
            chave=str(chave), rotulo=rotulos[chave], n=len(ps), mediana=med,
            lift=lift(med, geral) if amostra.suficiente else None, amostra=amostra,
            direito=canal.direito if canal is not None else None,
            engajamento=mediana(engs) if com_engajamento else None))
    return sorted(out, key=lambda linha: (-(linha.mediana or 0), -linha.n, linha.rotulo))


def _padrao(p: PostAnalisado) -> list[tuple[Hashable, str]]:
    if not p.padrao:
        return []
    mn, mx, layout = (p.padrao.get(k) for k in base.PADRAO_CAMPOS)
    return [(f"{mn}-{mx}-{layout}", f"{mn}–{mx} s · {layout}")]


def calcular(db: Session, filtro: Filtro, agora: datetime | None = None
             ) -> schemas.OQueFuncionaOut:
    posts = base.posts(db, filtro, agora=agora)
    medidos = [p for p in posts if p.medido]
    vinculados = [p for p in medidos if p.vinculado]
    geral_vinc = mediana([p.medida.valor for p in vinculados])  # type: ignore[misc]
    geral = mediana([p.medida.valor for p in medidos])  # type: ignore[misc]
    hashtags = [h for h in linhas(medidos, geral, lambda p: [(t, f"#{t}") for t in p.hashtags])
                if h.amostra.suficiente]
    hashtags.sort(key=lambda h: (-(h.lift or 0), -h.n, h.rotulo))
    return schemas.OQueFuncionaOut(
        contexto=base.contexto(filtro, posts),
        dispersoes=schemas.Dispersoes(
            duracao=dispersao(vinculados, lambda p: p.duracao_s),
            gancho=dispersao(vinculados, lambda p: p.gancho_caracteres),
            score=dispersao(vinculados, lambda p: p.score)),
        canais=linhas(vinculados, geral_vinc, lambda p: [(p.canal_fonte.id, p.canal_fonte.titulo)]
                      if p.canal_fonte else [], com_direito=True),
        hashtags=hashtags,
        modos=linhas(vinculados, geral_vinc, lambda p: [(p.modo, MODOS.get(p.modo, p.modo))]
                     if p.modo else [], com_engajamento=True),
        padroes=linhas(vinculados, geral_vinc, _padrao, com_engajamento=True),
        excluidos_sem_vinculo=sum(not p.vinculado for p in posts))
