"""Limpeza de 90 dias das opções não escolhidas (research R12; exceção 1 da constitution 4.3.0).

A trilha `geracao_limpeza` do agendador (`AGENDADOR_GERACAO_LIMPEZA_S`, padrão 1 h) e o CLI
`sociman geracoes limpar [--dry-run]` rodam o mesmo `limpar`. Em lotes de 200 gerações
terminadas (`escolhido`, `descartada`, `cancelada`, `entregue`, `falhou`) há mais de 90 dias e
ainda não limpas:
1. os candidatos que não são o escolhido (todos, se não há escolhido); os com a mídia já nula
   (revogação LGPD da 025) são pulados;
2. cada imagem (inclusive o `image_par_id`) e cada áudio (inclusive o `teste_audio_id`) passa
   pelo `midia_em_uso`: em uso, fica (e o candidato também), contado em `mantidos`;
3. numa transação por geração: apaga as linhas de `geracao_candidatos`, depois as de
   `images`/`audios`, marca `limpa_em` e grava **um** evento `eliminacao_candidatos` (quem,
   quando, contagem, bytes e o motivo `candidatos_90d`);
4. **depois do commit**, apaga os objetos do MinIO pelo `storage.apagar_por_excecao` (um objeto
   órfão é inofensivo; uma linha apontando para objeto apagado, não).

Nunca é disparada por IA, agente ou MCP: não há rota HTTP nem tool (teste-guarda). O escolhido
nunca é apagado. Rodar de novo não apaga nada novo (`limpa_em`).

**Fase 2** (spec 011, R12; exceção 1 ampliada da 4.5.0, `intermediarios_90d`): na mesma volta, os
intermediários de roteiro com `desuso_em` há mais de 90 dias e não protegidos
(`roteiros/retencao.py` seleciona): o vídeo e a miniatura das tomadas locais (e do candidato do
`cena.clipe`, o mesmo objeto), o áudio das narrações e o vídeo das prévias e dos acabamentos. As
linhas ficam, sem a mídia e com `limpa_em` ("arquivo removido"); a linha de `audios` sai (como na
fase 1). Um evento `eliminacao_intermediarios` com as contagens; os objetos saem depois do commit.
"""

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from sociman_api import storage
from sociman_api.auth.deps import Actor
from sociman_api.auth.events import record_event
from sociman_api.geracao.models import TERMINADOS, Audio, Geracao, GeracaoCandidato
from sociman_api.geracao.uso import JANELA, midia_em_uso
from sociman_api.perfis.models import Image

log = logging.getLogger("sociman.agendador")

LOTE = 200
EVENTO = "eliminacao_candidatos"
EXCECAO = "candidatos_90d"
EVENTO_INTERMEDIARIOS = "eliminacao_intermediarios"
EXCECAO_INTERMEDIARIOS = "intermediarios_90d"
AGENDADOR = Actor(kind="system:agendador")


@dataclass
class Resultado:
    geracoes: int = 0
    candidatos: int = 0
    imagens: int = 0
    audios: int = 0
    bytes: int = 0
    mantidos: int = 0
    objetos: list[tuple[storage.Bucket, str]] = field(default_factory=list)
    # Spec 011 (fase 2): os intermediários de roteiro.
    tomadas: int = 0
    narracoes: int = 0


def _vencidas(db: Session, limite: int) -> list[Geracao]:
    return list(db.scalars(
        select(Geracao).where(Geracao.status.in_(TERMINADOS), Geracao.limpa_em.is_(None),
                              Geracao.finished_at < func.now() - JANELA)
        .order_by(Geracao.finished_at, Geracao.id).limit(limite)
        .with_for_update(skip_locked=True)))


def _uma(db: Session, actor: Actor, g: Geracao, dry_run: bool) -> Resultado:
    r = Resultado(geracoes=1)
    stmt = select(GeracaoCandidato).where(GeracaoCandidato.geracao_id == g.id)
    if g.escolhido_id is not None:  # o escolhido nunca
        stmt = stmt.where(GeracaoCandidato.id != g.escolhido_id)
    cands = list(db.scalars(stmt.order_by(GeracaoCandidato.numero)))
    apagar_cands: list[uuid.UUID] = []
    imagens: list[Image] = []
    audios: list[Audio] = []
    for c in cands:
        teste = (c.metricas or {}).get("teste_audio_id")
        img_ids = [i for i in (c.image_id, c.image_par_id) if i is not None]
        aud_ids = [i for i in (c.audio_id, uuid.UUID(teste) if teste else None) if i is not None]
        if not img_ids and not aud_ids:
            continue  # mídia já nula (revogação LGPD da 025) ou passo de texto: pula
        if any(midia_em_uso(db, image_id=i) for i in img_ids) or \
                any(midia_em_uso(db, audio_id=a) for a in aud_ids):
            r.mantidos += 1
            log.info("geração %s: opção %d mantida (arquivo em uso)", g.id, c.numero)
            continue
        apagar_cands.append(c.id)
        imagens += [db.get(Image, i) for i in img_ids]
        audios += [db.get(Audio, a) for a in aud_ids]
    imagens = [i for i in imagens if i is not None]
    audios = [a for a in audios if a is not None]
    r.candidatos, r.imagens, r.audios = len(apagar_cands), len(imagens), len(audios)
    r.bytes = sum(i.bytes for i in imagens) + sum(a.bytes for a in audios)
    if dry_run:
        return r
    if apagar_cands:
        db.execute(delete(GeracaoCandidato).where(GeracaoCandidato.id.in_(apagar_cands)))
    if imagens:
        db.execute(delete(Image).where(Image.id.in_([i.id for i in imagens])))
    if audios:
        db.execute(delete(Audio).where(Audio.id.in_([a.id for a in audios])))
    g.limpa_em = func.now()
    record_event(db, EVENTO, "ok", actor, details={
        "excecao": EXCECAO, "geracaoId": str(g.id),
        "perfilId": str(g.perfil_id) if g.perfil_id else None,
        "candidatos": r.candidatos, "imagens": r.imagens, "audios": r.audios,
        "bytes": r.bytes, "mantidos": r.mantidos})
    r.objetos = [("imagens", i.object_key) for i in imagens] + \
        [("audios", a.object_key) for a in audios]
    return r


def limpar(db: Session, actor: Actor = AGENDADOR, *, dry_run: bool = False,
           lote: int = LOTE) -> Resultado:
    """Uma volta da limpeza. Cada geração é uma transação; os objetos saem depois do commit."""
    total = Resultado()
    vistos: set[uuid.UUID] = set()
    while True:
        gs = [g for g in _vencidas(db, lote) if g.id not in vistos]
        if not gs:
            db.rollback()
            break
        for g in gs:
            vistos.add(g.id)
            try:
                r = _uma(db, actor, g, dry_run)
                if not dry_run:
                    db.commit()
            except Exception:
                db.rollback()
                log.exception("falha ao limpar a geração %s; segue na próxima volta", g.id)
                continue
            for bucket, key in r.objetos:
                try:
                    storage.apagar_por_excecao(key, bucket=bucket, excecao=EXCECAO)
                except Exception:  # objeto órfão é inofensivo; a linha já saiu
                    log.warning("objeto %s/%s não apagado (fica órfão)", bucket, key,
                                exc_info=True)
            for campo in ("geracoes", "candidatos", "imagens", "audios", "bytes", "mantidos"):
                setattr(total, campo, getattr(total, campo) + getattr(r, campo))
        if dry_run or len(gs) < lote:
            db.rollback()
            break
    if total.geracoes and not dry_run:
        log.info("limpeza de 90 dias: %d gerações, %d opções, %d bytes (%d mantidas)",
                 total.geracoes, total.candidatos, total.bytes, total.mantidos)
    try:
        f2 = _intermediarios(db, actor, dry_run, lote)
    except Exception:
        db.rollback()
        log.exception("falha na fase 2 da limpeza (intermediários); segue na próxima volta")
        return total
    for campo in ("candidatos", "audios", "bytes", "mantidos", "tomadas", "narracoes"):
        setattr(total, campo, getattr(total, campo) + getattr(f2, campo))
    return total


def _intermediarios(db: Session, actor: Actor, dry_run: bool, lote: int) -> Resultado:
    """Fase 2 (spec 011, R12). Uma transação; os objetos saem depois do commit."""
    from sociman_api.cenas.models import CenaTomada
    from sociman_api.roteiros import retencao
    from sociman_api.roteiros.models import RoteiroNarracao

    r = Resultado()
    agora = db.scalar(select(func.now()))
    sai, r.mantidos = retencao.filtrar(retencao.elegiveis(db, agora, lote),
                                       retencao.protegidos(db))
    objetos: list[tuple[storage.Bucket, str]] = []
    video_keys: set[str] = set()
    tomadas = list(db.scalars(select(CenaTomada).where(CenaTomada.id.in_(sai.tomadas))
                              .with_for_update(skip_locked=True))) if sai.tomadas else []
    for t in tomadas:
        r.bytes += t.bytes or 0
        objetos += [("videos", t.video_key), ("imagens", t.miniatura_key)]
        video_keys.add(t.video_key)
    cands = list(db.scalars(select(GeracaoCandidato).where(or_(
        GeracaoCandidato.geracao_id.in_(sai.geracoes),
        GeracaoCandidato.video_key.in_(video_keys)), GeracaoCandidato.video_key.is_not(None))))
    for c in cands:
        if c.video_key not in video_keys:
            r.bytes += c.video_bytes or 0
            objetos += [("videos", c.video_key), ("imagens", c.video_miniatura_key)]
    narracoes, audios = [], []
    for n in db.scalars(select(RoteiroNarracao).where(RoteiroNarracao.id.in_(sai.narracoes))
                        .with_for_update(skip_locked=True)) if sai.narracoes else []:
        a = db.get(Audio, n.audio_id) if n.audio_id else None
        # O áudio da narração é sempre o escolhido da própria geração e aparece (pela chave) no
        # `params` das prévias que o usaram: quem decide é a proteção do roteiro (`retencao`).
        if a is not None and midia_em_uso(db, audio_id=a.id,
                                          ignorar=frozenset({"escolhido", "params"})):
            r.mantidos += 1
            continue
        narracoes.append(n)
        if a is not None:
            audios.append(a)
            r.bytes += a.bytes
            objetos.append(("audios", a.object_key))
    r.tomadas, r.narracoes, r.candidatos, r.audios = (len(tomadas), len(narracoes), len(cands),
                                                      len(audios))
    if dry_run or not (tomadas or cands or narracoes):
        db.rollback()
        return r
    for t in tomadas:
        t.video_key = t.miniatura_key = t.bytes = None
        t.limpa_em = agora
    if cands:
        db.execute(update(GeracaoCandidato).where(GeracaoCandidato.id.in_([c.id for c in cands]))
                   .values(video_key=None, video_miniatura_key=None, video_bytes=None))
    audio_ids = [a.id for a in audios]
    for n in narracoes:
        n.audio_id = None
        n.limpa_em = agora
    if audio_ids:
        db.execute(update(GeracaoCandidato).where(GeracaoCandidato.audio_id.in_(audio_ids))
                   .values(audio_id=None))
        db.flush()
        db.execute(delete(Audio).where(Audio.id.in_(audio_ids)))
    record_event(db, EVENTO_INTERMEDIARIOS, "ok", actor, details={
        "excecao": EXCECAO_INTERMEDIARIOS, "tomadas": r.tomadas, "narracoes": r.narracoes,
        "candidatos": r.candidatos, "audios": r.audios, "bytes": r.bytes,
        "mantidos": r.mantidos})
    db.commit()
    for bucket, key in objetos:
        if not key:
            continue
        try:
            storage.apagar_por_excecao(key, bucket=bucket, excecao=EXCECAO_INTERMEDIARIOS)
        except Exception:  # objeto órfão é inofensivo; a linha já ficou sem a mídia
            log.warning("objeto %s/%s não apagado (fica órfão)", bucket, key, exc_info=True)
    log.info("limpeza de 90 dias (roteiros): %d tomadas, %d narrações, %d vídeos, %d bytes "
             "(%d mantidos)", r.tomadas, r.narracoes, r.candidatos, r.bytes, r.mantidos)
    return r


def rodar(db: Session) -> None:
    """A trilha `geracao_limpeza` do agendador."""
    limpar(db, AGENDADOR)
