"""Campos de execução do destino na saída (spec 015, contracts/http-api.md, "Ampliações dos tipos
da 014"): conexão da conta, quem agendou, confirmação de vencido, última tentativa, link do post,
snapshot desatualizado e avisos de vídeo fora das regras da rede.

Tudo em poucas consultas por lote de destinos (sem N+1): a lista, o detalhe e o calendário
chamam `campos_envio` e `conexoes_por_conta` com todos os destinos da página.
"""

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.conteudos import consulta
from sociman_api.conteudos.models import Conteudo, Modo
from sociman_api.cortes.models import Corte
from sociman_api.perfis.models import Conta, Platform
from sociman_api.perfis.service_perfis import user_refs
from sociman_api.postagem.models import Postagem
from sociman_api.publicacao import legenda, registro
from sociman_api.publicacao.models import Conexao, ConexaoEstado, Tentativa
from sociman_api.publicacao.schemas import OpcoesTikTok
from sociman_api.publicacao.service import tentativa_out

# Regras de vídeo da TikTok conferidas ao agendar (R9): só avisos, sem bloquear.
DURACAO_MAX_S = 600
TAMANHO_MAX = 4 * 1024 ** 3
LADO_MIN, LADO_MAX = 360, 4096


def conexoes_por_conta(db: Session, conta_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Conexao]:
    """A conexão viva (não desconectada) de cada conta, numa consulta."""
    ids = list(set(conta_ids))
    if not ids:
        return {}
    return {c.conta_id: c for c in db.scalars(
        select(Conexao).where(Conexao.conta_id.in_(ids),
                              Conexao.estado != ConexaoEstado.desconectada))}


def estado_conexao(conexao: Conexao | None) -> str:
    return conexao.estado.value if conexao is not None else "nao_conectada"


def avisos_rede(modo: Modo, platform: Platform, duracao_ms: int | None, tamanho: int | None,
                largura: int | None, altura: int | None) -> list[str]:
    if modo == Modo.lembrete or platform != Platform.tiktok:
        return []
    avisos = []
    if duracao_ms is not None and duracao_ms / 1000 > DURACAO_MAX_S:
        avisos.append(f"O vídeo tem mais de {DURACAO_MAX_S // 60} minutos; a TikTok pode recusar")
    if tamanho is not None and tamanho > TAMANHO_MAX:
        avisos.append("O vídeo tem mais de 4 GB; a TikTok pode recusar")
    for lado in (largura, altura):
        if lado is not None and not LADO_MIN <= lado <= LADO_MAX:
            avisos.append(f"Os lados do vídeo precisam ficar entre {LADO_MIN} e {LADO_MAX} px")
            break
    return avisos


def _ultimas(db: Session, destino_ids: list[uuid.UUID]) -> dict[uuid.UUID, Tentativa]:
    sub = (select(Tentativa.destino_id, func.max(Tentativa.numero).label("n"))
           .where(Tentativa.destino_id.in_(destino_ids))
           .group_by(Tentativa.destino_id).subquery())
    rows = db.scalars(select(Tentativa).join(
        sub, (sub.c.destino_id == Tentativa.destino_id) & (sub.c.n == Tentativa.numero)))
    return {t.destino_id: t for t in rows}


def ultimas_fases(db: Session, destino_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = list(set(destino_ids))
    if not ids:
        return {}
    return {i: t.fase.value for i, t in _ultimas(db, ids).items()}


def campos_envio(db: Session, destinos: Sequence[Postagem]) -> dict[uuid.UUID, dict[str, Any]]:
    """Os campos da 015 de cada destino (os nomes do schema `Destino`)."""
    if not destinos:
        return {}
    ids = [d.id for d in destinos]
    ultimas = _ultimas(db, ids)
    conexoes = conexoes_por_conta(db, {d.conta_id for d in destinos})
    videos = {r.id: r for r in db.execute(
        consulta.join_corte(select(
            Conteudo.id, consulta.duration_ms().label("dur"),
            func.coalesce(Corte.result_bytes, Conteudo.video_bytes).label("bytes"),
            func.coalesce(Corte.width, Conteudo.width).label("w"),
            func.coalesce(Corte.height, Conteudo.height).label("h")))
        .where(Conteudo.id.in_({d.conteudo_id for d in destinos})))}
    platforms = dict(db.execute(
        select(Conta.id, Conta.platform)
        .where(Conta.id.in_({d.conta_id for d in destinos}))).all())
    users = user_refs(db, [u for d in destinos for u in (d.agendado_por, d.envio_confirmado_por)]
                      + [t.disparado_por for t in ultimas.values()])
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for d in destinos:
        conexao = conexoes.get(d.conta_id)
        v = videos.get(d.conteudo_id)
        t = ultimas.get(d.id)
        url = None
        if d.rede_post_id and conexao is not None:
            url = f"https://www.tiktok.com/@{conexao.username}/video/{d.rede_post_id}"
        snap = d.envio_snapshot or {}
        desatualizado = d.modo == Modo.publicar and bool(snap) \
            and snap.get("legenda") != legenda.legenda_tiktok(d)
        confirmado = None
        if d.envio_confirmado_por in users and d.envio_confirmado_em is not None:
            confirmado = {"por": users[d.envio_confirmado_por], "em": d.envio_confirmado_em}
        out[d.id] = {
            "opcoes_rede": OpcoesTikTok.model_validate(d.opcoes_rede) if d.opcoes_rede else None,
            "agendado_por": users.get(d.agendado_por) if d.agendado_por else None,
            "agendado_em": d.agendado_em,
            "envio_confirmado": confirmado,
            "falha_incerta": bool(d.falha_incerta),
            "rede_post_id": d.rede_post_id,
            "rede_post_url": url,
            "ultima_tentativa": tentativa_out(t, users, registro.executor_para(t.rede))
            if t is not None else None,
            "snapshot_desatualizado": desatualizado,
            "legenda_final": legenda.legenda_tiktok(d)
            if platforms[d.conta_id] == Platform.tiktok else None,
            "avisos_rede": avisos_rede(d.modo, platforms[d.conta_id],
                                       v.dur if v else None, v.bytes if v else None,
                                       v.w if v else None, v.h if v else None),
        }
    return out
