"""Curvas de crescimento (spec 019, US4; FR-023/FR-024).

- **Curvas:** views por idade (horas desde a publicação) dos até 50 vídeos mais recentes do
  período, uma linha por vídeo com as fotos reais (sem ponto inventado).
- **Meia-vida:** horas até o vídeo alcançar 50% das views do marco de 7 dias (o marco da 016,
  com a interpolação dela). A curva é interpolada linearmente entre as fotos, com a âncora
  (0 h, 0 views); vídeo com menos de 7 dias ou sem o marco → `null` ("ainda não calculável").
- **Distribuição:** mínimo, quartis e máximo da medida do post por conta (posts medidos do
  período), com a amostra (`MIN_GRUPO`).

Só leitura.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, estatistica, schemas
from sociman_api.analytics.filtros import Filtro
from sociman_api.metricas import consulta
from sociman_api.metricas.models import FotoVideo, VideoRede

MAX_CURVAS = 50


def meia_vida_h(pontos: Sequence[tuple[float, int]], views_7d: float | None) -> float | None:
    """Horas até a curva `(idade_h, views)` (ordenada) cruzar metade de `views_7d`, com
    interpolação linear e a âncora (0, 0). None sem o marco, com marco ≤ 0 ou sem cruzamento."""
    if views_7d is None or views_7d <= 0:
        return None
    metade = views_7d / 2
    antes = (0.0, 0)
    for idade, views in pontos:
        if views >= metade:
            a_idade, a_views = antes
            if views == a_views:
                return idade
            return a_idade + (metade - a_views) * (idade - a_idade) / (views - a_views)
        antes = (idade, views)
    return None


def _pontos(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[tuple[float, int]]]:
    out: dict[uuid.UUID, list[tuple[float, int]]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.execute(select(FotoVideo.video_id, FotoVideo.idade_s, FotoVideo.views)
                      .where(FotoVideo.video_id.in_(list(ids)), FotoVideo.views.is_not(None))
                      .order_by(FotoVideo.video_id, FotoVideo.idade_s, FotoVideo.id))
    for vid, idade_s, views in rows:
        out[vid].append((idade_s / 3600, int(views)))
    return out


def curvas(db: Session, posts: Sequence[base.PostAnalisado],
           agora: datetime | None = None) -> list[schemas.Curva]:
    """As curvas dos até 50 posts mais recentes, do mais novo ao mais antigo."""
    agora = agora or datetime.now(ZoneInfo("UTC"))
    recentes = sorted(posts, key=lambda p: (p.publicado_em, str(p.video_id)),
                      reverse=True)[:MAX_CURVAS]
    ids = [p.video_id for p in recentes]
    if not ids:
        return []
    videos = list(db.scalars(select(VideoRede).where(VideoRede.id.in_(ids))))
    marcos = consulta.marcos(db, videos, agora)
    pontos = _pontos(db, ids)
    out = []
    for p in recentes:
        d7 = marcos[p.video_id].d7.views
        out.append(schemas.Curva(
            video_id=p.video_id, titulo_curto=p.titulo_curto, conta_id=p.conta_id,
            conta=p.rotulo_conta,
            pontos=[schemas.PontoCurva(idade_h=round(h, 4), views=v)
                    for h, v in pontos[p.video_id]],
            meia_vida_h=meia_vida_h(pontos[p.video_id], d7.valor)))
    return out


def distribuicao(posts: Sequence[base.PostAnalisado]) -> list[schemas.DistribuicaoConta]:
    """Quartis da medida por conta (anônimas pelo rótulo), na ordem do rótulo."""
    grupos: dict[tuple[uuid.UUID | None, str], list[float]] = {}
    for p in posts:
        valores = grupos.setdefault((p.conta_id, p.rotulo_conta), [])
        if p.medido:
            valores.append(p.medida.valor)  # type: ignore[arg-type] — `medido` garante
    out = []
    for (conta_id, rotulo), valores in sorted(grupos.items(), key=lambda g: g[0][1]):
        q = estatistica.quartis(valores)
        out.append(schemas.DistribuicaoConta(
            conta_id=conta_id, rotulo=rotulo,
            min=q.min if q else None, q1=q.q1 if q else None,
            mediana=q.mediana if q else None, q3=q.q3 if q else None,
            max=q.max if q else None,
            amostra=base.amostra(len(valores), estatistica.MIN_GRUPO)))
    return out


def calcular(db: Session, filtro: Filtro, agora: datetime | None = None) -> schemas.CurvasOut:
    posts = base.posts(db, filtro, agora=agora)
    return schemas.CurvasOut(contexto=base.contexto(filtro, posts),
                             curvas=curvas(db, posts, agora), distribuicao=distribuicao(posts))
