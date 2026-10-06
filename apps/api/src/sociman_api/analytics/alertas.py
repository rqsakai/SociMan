"""Alertas (spec 019, US8; FR-032/FR-033; research R9): calculados na leitura, **nunca
gravados** (somem sozinhos quando a condição deixa de valer).

- **estagnado** (atenção) e **destaque** (positivo): posts do período, de séries vivas, com 6 h
  ou mais. Compara as views da última foto com as dos outros vídeos da mesma série na mesma
  idade (interpolação dos marcos da 016; só entram os que já têm valor nessa idade). Com pelo
  menos `MIN_CONTA_ESTAGNADO` referências: estagnado abaixo de 10% da mediana delas, destaque
  acima de 3×. Com menos: o limite fixo (até 1 view = estagnado) e nenhum destaque.
- **sem_coleta** (atenção): conta com série ativa (`vinculos.serie_ativa`: conectada, escopos,
  coleta ligada) sem coleta há mais de 3 h (ou nunca coletada).
- **vinculo_a_confirmar** (info): destino do escopo com âncora recente (lembrete marcado como
  postado ou rascunho entregue nos últimos 15 dias) e sem vídeo, cujo `vinculos.vinculo` está
  `a_confirmar`.

O escopo (conta, perfil, rede) vale para todos; o período só para os posts. Só leitura.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, estatistica, schemas
from sociman_api.analytics.filtros import Filtro
from sociman_api.conteudos.models import Modo
from sociman_api.metricas import consulta, vinculos
from sociman_api.metricas.consulta import Ponto
from sociman_api.metricas.models import BuscaPost, FotoVideo, Serie, VideoRede
from sociman_api.perfis.models import Conta
from sociman_api.postagem.models import DestinoEstado, Postagem

IDADE_MIN = timedelta(hours=6)
FRACAO_ESTAGNADO = 0.10
DESTAQUE_ACIMA = 3.0
VIEWS_FIXO = 1  # até 1 view = estagnado, sem referências suficientes
SEM_COLETA = timedelta(hours=3)
JANELA_VINCULO = timedelta(days=15)
ORDEM = {"atencao": 0, "info": 1, "positivo": 2}
CONFERIR = ("Confira no app se o post ficou restrito, privado ou com o som bloqueado, e se ele "
            "aparece no perfil.")


def _link_video(video_id: uuid.UUID) -> str:
    return f"/app/metricas/videos/{video_id}"


def _pontos(db: Session, series: set[uuid.UUID]) -> dict[uuid.UUID, tuple[uuid.UUID, list[Ponto]]]:
    """vídeo → (série, fotos em ordem de idade), para todos os vídeos das séries."""
    out: dict[uuid.UUID, tuple[uuid.UUID, list[Ponto]]] = {}
    if not series:
        return out
    rows = db.execute(
        select(VideoRede.id, VideoRede.serie_id, FotoVideo.idade_s, FotoVideo.views,
               FotoVideo.likes, FotoVideo.comments, FotoVideo.shares)
        .join(FotoVideo, FotoVideo.video_id == VideoRede.id)
        .where(VideoRede.serie_id.in_(series), FotoVideo.views.is_not(None))
        .order_by(VideoRede.id, FotoVideo.idade_s, FotoVideo.id))
    for vid, sid, *foto in rows:
        out.setdefault(vid, (sid, []))[1].append(Ponto(*foto))
    return out


def referencias(alvo: uuid.UUID, serie_id: uuid.UUID, idade_s: int,
                pontos: dict[uuid.UUID, tuple[uuid.UUID, list[Ponto]]]) -> list[float]:
    """As views dos outros vídeos da série na idade `idade_s` (os que já têm valor nela)."""
    out = []
    for vid, (sid, fotos) in pontos.items():
        if vid == alvo or sid != serie_id:
            continue
        antes, depois = consulta.vizinhas(fotos, idade_s)
        valor = consulta.interpolar(antes, depois, idade_s, "views")
        if valor is not None:
            out.append(valor)
    return out


def desempenho(posts: Sequence[base.PostAnalisado],
               pontos: dict[uuid.UUID, tuple[uuid.UUID, list[Ponto]]],
               agora: datetime) -> list[schemas.Alerta]:
    out = []
    for p in posts:
        if p.anonima or agora - p.publicado_em < IDADE_MIN or p.video_id not in pontos:
            continue
        serie_id, fotos = pontos[p.video_id]
        ultima = fotos[-1]
        views = ultima.views or 0
        idade_h = round(ultima.idade_s / 3600, 1)
        refs = referencias(p.video_id, serie_id, ultima.idade_s, pontos)
        alvo = schemas.AlvoAlerta(tipo="video", id=p.video_id, rotulo=p.titulo_curto)
        numeros: dict[str, float | None] = {"idadeH": idade_h, "views": views,
                                            "referencias": len(refs)}
        if len(refs) < estatistica.MIN_CONTA_ESTAGNADO:
            if views <= VIEWS_FIXO:
                out.append(schemas.Alerta(
                    tipo="estagnado", severidade="atencao", alvo=alvo, numeros=numeros,
                    motivo=(f"{views} view(s) com {idade_h:g} h de publicado em "
                            f"{p.rotulo_conta}. {CONFERIR}"),
                    link=_link_video(p.video_id)))
            continue
        med = estatistica.mediana(refs)
        numeros["medianaReferencia"] = med
        if views < FRACAO_ESTAGNADO * med:  # type: ignore[operator]
            out.append(schemas.Alerta(
                tipo="estagnado", severidade="atencao", alvo=alvo, numeros=numeros,
                motivo=(f"{views} views com {idade_h:g} h: abaixo de 10% da mediana de "
                        f"{p.rotulo_conta} na mesma idade ({med:.0f}). {CONFERIR}"),
                link=_link_video(p.video_id)))
        elif views > DESTAQUE_ACIMA * med:  # type: ignore[operator]
            out.append(schemas.Alerta(
                tipo="destaque", severidade="positivo", alvo=alvo, numeros=numeros,
                motivo=(f"{views} views com {idade_h:g} h: mais de 3× a mediana de "
                        f"{p.rotulo_conta} na mesma idade ({med:.0f})."),
                link=_link_video(p.video_id)))
    return out


def _contas(db: Session, filtro: Filtro) -> list[tuple[Conta, Serie]]:
    stmt = (select(Conta, Serie).join(Serie, Serie.conta_id == Conta.id)
            .where(Serie.anonimizada_em.is_(None)))
    if filtro.conta_id is not None:
        stmt = stmt.where(Conta.id == filtro.conta_id)
    elif filtro.perfil_id is not None:
        stmt = stmt.where(Conta.perfil_id == filtro.perfil_id)
    if filtro.rede is not None:
        stmt = stmt.where(Serie.rede == filtro.rede)
    return [(conta, serie) for conta, serie in db.execute(stmt.order_by(Conta.handle))]


def sem_coleta(db: Session, contas: Sequence[tuple[Conta, Serie]],
               agora: datetime) -> list[schemas.Alerta]:
    out = []
    for conta, serie in contas:
        if vinculos.serie_ativa(db, conta.id) is None:
            continue
        ultima = serie.ultima_coleta_em
        if ultima is not None and agora - ultima <= SEM_COLETA:
            continue
        horas = round((agora - ultima).total_seconds() / 3600, 1) if ultima else None
        motivo = (f"@{conta.handle} sem coleta há {horas:g} h." if horas is not None
                  else f"@{conta.handle} ainda não teve nenhuma coleta.")
        out.append(schemas.Alerta(
            tipo="sem_coleta", severidade="atencao",
            alvo=schemas.AlvoAlerta(tipo="serie", id=conta.id, rotulo=f"@{conta.handle}"),
            motivo=f"{motivo} Confira a conexão da conta e o estado da coleta nas métricas.",
            numeros={"horasSemColeta": horas},
            link=f"/app/metricas?aba=contas&conta={conta.id}"))
    return out


def a_confirmar(db: Session, filtro: Filtro, agora: datetime) -> list[schemas.Alerta]:
    desde = agora - JANELA_VINCULO
    stmt = (select(Postagem).join(Conta, Conta.id == Postagem.conta_id)
            .where(Postagem.archived_at.is_(None),
                   ~exists().where(VideoRede.destino_id == Postagem.id),
                   or_(and_(Postagem.modo == Modo.lembrete,
                            Postagem.estado == DestinoEstado.postado,
                            Postagem.posted_at >= desde),
                       and_(Postagem.modo == Modo.criar_rascunho,
                            Postagem.estado.in_((DestinoEstado.rascunho_criado,
                                                 DestinoEstado.postado)),
                            exists().where(BuscaPost.destino_id == Postagem.id,
                                           BuscaPost.entregue_em >= desde)))))
    if filtro.conta_id is not None:
        stmt = stmt.where(Postagem.conta_id == filtro.conta_id)
    elif filtro.perfil_id is not None:
        stmt = stmt.where(Conta.perfil_id == filtro.perfil_id)
    if filtro.rede is not None:
        stmt = stmt.where(Conta.platform == filtro.rede)
    out = []
    for d in db.scalars(stmt.order_by(Postagem.posted_at, Postagem.id)):
        v = vinculos.vinculo(db, d, agora)
        if v.estado != "a_confirmar":
            continue
        out.append(schemas.Alerta(
            tipo="vinculo_a_confirmar", severidade="info",
            alvo=schemas.AlvoAlerta(tipo="destino", id=d.id,
                                    rotulo=base.titulo_curto(d.titulo or d.descricao)),
            motivo=(f"Mais de um post pode ser este destino ({len(v.candidatos)} candidatos). "
                    "Escolha o post certo no conteúdo."),
            numeros={"candidatos": len(v.candidatos)},
            link=f"/app/conteudos/{d.conteudo_id}"))
    return out


def calcular(db: Session, filtro: Filtro, agora: datetime | None = None) -> schemas.AlertasOut:
    agora = agora or datetime.now(ZoneInfo("UTC"))
    posts = base.posts(db, filtro, agora=agora)
    series = {p.serie_id for p in posts if not p.anonima}
    alertas = (desempenho(posts, _pontos(db, series), agora)
               + sem_coleta(db, _contas(db, filtro), agora) + a_confirmar(db, filtro, agora))
    alertas.sort(key=lambda a: ORDEM[a.severidade])  # estável: tipo e ordem de cada regra
    contagem = {s: sum(a.severidade == s for a in alertas) for s in ORDEM}
    return schemas.AlertasOut(contexto=base.contexto(filtro, posts), alertas=alertas,
                              contagem=schemas.ContagemAlertas(**contagem))
