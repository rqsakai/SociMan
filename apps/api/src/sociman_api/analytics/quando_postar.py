"""Quando postar (spec 019, US2; FR-016 a FR-018; research R4).

- **Por publicação:** 7 × 24 células (dia da semana × hora local da publicação) com a mediana
  da medida dos posts medidos e o n; `amostraPequena` com 0 < n < `MIN_GRUPO`.
- **Audiência:** para cada par de fotos consecutivas de um vídeo (a 1ª com a âncora da
  publicação, 0 view, como nos marcos da 016), o ganho `max(0, views₂ − views₁)`. Intervalo de
  até 3 h: o ganho se divide pelas horas-relógio cobertas, proporcional aos minutos de cada uma,
  no fuso da casa; intervalo maior: o ganho vai para `semHora`. Só entra a parte dentro do
  período (para `semHora`, o intervalo que termina nele). `n` = intervalos que somaram na célula.
- **Calendário:** por dia do período, os posts publicados e as views ganhas (mesma regra dos
  ganhos da visão geral).

Tudo calculado em Python sobre as fotos do escopo (um SELECT), sem escrita.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from sociman_api.analytics import base, schemas
from sociman_api.analytics.base import PostAnalisado
from sociman_api.analytics.estatistica import MIN_GRUPO, mediana
from sociman_api.analytics.filtros import Filtro, Periodo, fuso

INTERVALO_MAX = timedelta(hours=3)
HORA = timedelta(hours=1)


def por_publicacao(posts: Sequence[PostAnalisado]) -> schemas.Mapa:
    valores: dict[tuple[int, int], list[float]] = {}
    for p in posts:
        if p.medido:
            valores.setdefault((p.dia_semana, p.hora_local), []).append(p.medida.valor)  # type: ignore[arg-type]
    celulas = []
    for dia in range(7):
        for hora in range(24):
            vs = valores.get((dia, hora), [])
            celulas.append(schemas.CelulaMapa(dia=dia, hora=hora, valor=mediana(vs), n=len(vs),
                                              amostra_pequena=0 < len(vs) < MIN_GRUPO))
    return schemas.Mapa(celulas=celulas)


def _hora_cheia(t: datetime, tz: ZoneInfo) -> datetime:
    return t.astimezone(tz).replace(minute=0, second=0, microsecond=0)


def distribuir(t1: datetime, t2: datetime, ganho: float, tz: ZoneInfo
               ) -> list[tuple[datetime, float]]:
    """(início da hora local, parte do ganho) de cada hora-relógio coberta por `[t1, t2)`,
    proporcional ao tempo dentro dela."""
    total = (t2 - t1).total_seconds()
    out = []
    hora = _hora_cheia(t1, tz)
    while hora < t2:
        parte = (min(t2, hora + HORA) - max(t1, hora)).total_seconds()
        if parte > 0:
            out.append((hora, ganho * parte / total))
        hora = hora + HORA
    return out


def audiencia(videos: Sequence[base.VideoEscopo],
              fotos: dict, periodo: Periodo) -> schemas.MapaAudiencia:
    tz = ZoneInfo(fuso())
    soma: dict[tuple[int, int], float] = {}
    n: dict[tuple[int, int], int] = {}
    sem_hora = 0.0
    publicado = {v.video_id: v.publicado_em for v in videos}
    for vid, fs in fotos.items():
        anterior = (publicado[vid], 0)
        for quando, views in fs:
            t1, v1 = anterior
            anterior = (quando, views)
            if quando <= t1 or quando <= periodo.ini or t1 >= periodo.fim:
                continue
            ganho = max(0, views - v1)
            if quando - t1 > INTERVALO_MAX:
                if periodo.ini <= quando < periodo.fim:
                    sem_hora += ganho
                continue
            celulas_do_intervalo = set()
            for hora, parte in distribuir(t1, quando, ganho, tz):
                if periodo.ini <= hora < periodo.fim:
                    chave = (hora.weekday(), hora.hour)
                    soma[chave] = soma.get(chave, 0.0) + parte
                    celulas_do_intervalo.add(chave)
            for chave in celulas_do_intervalo:
                n[chave] = n.get(chave, 0) + 1
    celulas = [schemas.CelulaMapa(dia=d, hora=h, valor=soma.get((d, h)), n=n.get((d, h), 0),
                                  amostra_pequena=False)
               for d in range(7) for h in range(24)]
    return schemas.MapaAudiencia(celulas=celulas, sem_hora=round(sem_hora))


def calendario(posts: Sequence[PostAnalisado], por_dia: dict) -> list[schemas.DiaCalendario]:
    publicados: dict = {}
    for p in posts:
        dia = p.publicado_em.date()
        publicados[dia] = publicados.get(dia, 0) + 1
    return [schemas.DiaCalendario(dia=dia, posts=publicados.get(dia, 0),
                                  views=sum(ganhos.values()))
            for dia, ganhos in sorted(por_dia.items())]


def calcular(db: Session, filtro: Filtro, agora: datetime | None = None
             ) -> schemas.QuandoPostarOut:
    posts = base.posts(db, filtro, agora=agora)
    videos, por_dia = base.ganhos_por_dia(db, filtro)
    fotos = base.fotos_views(db, [v.video_id for v in videos], filtro.atual.fim)
    return schemas.QuandoPostarOut(
        contexto=base.contexto(filtro, posts), por_publicacao=por_publicacao(posts),
        audiencia=audiencia(videos, fotos, filtro.atual),
        calendario=calendario(posts, por_dia))
