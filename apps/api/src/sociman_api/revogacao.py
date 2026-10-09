"""Revogação de consentimento de pessoa real (spec 025, research R10 e R10b; exceção 2 da
constitution 4.3.0, princípio VII). **Único** módulo, além da limpeza de 90 dias da 021, que
alcança o `storage.apagar_por_excecao`, faz UPDATE em `geracao_candidatos`, em `geracoes.params`
e em `entity_versions` (`history.redigir_versoes`) — o teste-guarda confere por AST.

Só o dono humano revoga (a rota usa `RequireHumanOwner`), com `confirmo` e a `version`. Numa
transação, na ordem do data-model:
1. cancela as gerações abertas do alvo;
2. nas gerações do alvo, a mídia dos candidatos vira nula (a linha fica: o `escolhido_id` depende
   dela) e os textos do `params` somem (`limpa_em`);
3. apaga as linhas dos arquivos (`asset_files`, `images`, `audios`);
4. esvazia o texto das chamadas de IA do alvo (custo e tokens ficam);
5. zera os campos que descrevem a pessoa, arquiva e grava a versão `revoked`;
6. redige as versões antigas do histórico (`prompt`, `identidade`, `image_rules`, prova; na voz,
   `ref_texto`, `analise` e prova);
7. grava **um** evento `eliminacao_lgpd` (só contagens, nunca o nome nem o texto da pessoa).
Os objetos do MinIO saem **depois** do commit (`apagar_objetos`, numa BackgroundTask da rota).
As cenas da 010 que usam o avatar só são listadas (D2 do dono); a única mudança nelas é soltar o
`avatar_arquivo_id` que apontava para um arquivo apagado (a FK não deixaria apagar), numa versão
da cena com `details.revogacao`, sem tocar no prompt congelado. A voz sai do shop-tts pela linha
`vozes_sync` do gerador (`sincronizada_em` continua preenchida até a remoção).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from sociman_api import history, storage
from sociman_api.assets.models import Asset, AssetFile, AssetTipo
from sociman_api.assets.schemas_padrao import PreviaRevogacao
from sociman_api.auth.deps import Actor
from sociman_api.auth.events import record_event
from sociman_api.cenas.models import Cena
from sociman_api.errors import ApiError
from sociman_api.geracao import service as geracao_service
from sociman_api.geracao.models import FINAIS, Audio, Geracao, GeracaoAlvo, GeracaoCandidato
from sociman_api.ia.models import IaChamada
from sociman_api.perfis.models import Image
from sociman_api.vozes.models import Voz

log = logging.getLogger(__name__)

EVENTO = "eliminacao_lgpd"
EXCECAO = "lgpd_revogacao"
CAMPOS_ASSET = ("prompt", "identidade", "image_rules", "consentimento.prova")
CAMPOS_VOZ = ("ref_texto", "analise", "consentimento.prova")


@dataclass
class Plano:
    imagens: set[uuid.UUID] = field(default_factory=set)
    audios: set[uuid.UUID] = field(default_factory=set)
    geracoes: list[Geracao] = field(default_factory=list)
    candidatos: int = 0


def _confirmar(alvo: Any, version: int, confirmo: bool, label: str) -> None:
    if not confirmo:
        raise ApiError(400, "confirmacao_obrigatoria",
                       "Confirme que entendeu o que será apagado")
    history.check_version(alvo, version, label)
    c = alvo.consentimento or {}
    if not c.get("nome"):
        raise ApiError(409, "sem_consentimento", "Não há consentimento registrado")
    if c.get("revogado_em"):
        raise ApiError(409, "consentimento_revogado", "Este consentimento já foi revogado")


def _geracoes(db: Session, alvo_tipo: GeracaoAlvo, alvo_id: uuid.UUID) -> list[Geracao]:
    return list(db.scalars(select(Geracao).where(Geracao.alvo_tipo == alvo_tipo,
                                                 Geracao.alvo_id == alvo_id)))


def _plano_geracoes(db: Session, gs: list[Geracao], plano: Plano) -> None:
    plano.geracoes = gs
    if not gs:
        return
    cands = list(db.scalars(select(GeracaoCandidato).where(
        GeracaoCandidato.geracao_id.in_([g.id for g in gs]))))
    plano.candidatos = len(cands)
    for c in cands:
        plano.imagens |= {i for i in (c.image_id, c.image_par_id) if i}
        if c.audio_id:
            plano.audios.add(c.audio_id)
        teste = (c.metricas or {}).get("teste_audio_id")
        if teste:
            plano.audios.add(uuid.UUID(teste))


def _prova(c: dict[str, Any] | None, plano: Plano) -> None:
    prova = (c or {}).get("prova") or {}
    if prova.get("image_id"):
        plano.imagens.add(uuid.UUID(prova["image_id"]))
    if prova.get("audio_id"):
        plano.audios.add(uuid.UUID(prova["audio_id"]))


def _bytes(db: Session, plano: Plano) -> int:
    total = 0
    if plano.imagens:
        total += sum(i.bytes for i in db.scalars(select(Image).where(
            Image.id.in_(plano.imagens))))
    if plano.audios:
        total += sum(a.bytes for a in db.scalars(select(Audio).where(
            Audio.id.in_(plano.audios))))
    return total


def _plano_asset(db: Session, asset: Asset) -> Plano:
    plano = Plano()
    plano.imagens |= {f.image_id for f in asset.arquivos}
    _plano_geracoes(db, _geracoes(db, GeracaoAlvo.asset, asset.id), plano)
    _prova(asset.consentimento, plano)
    return plano


def _plano_voz(db: Session, voz: Voz) -> Plano:
    plano = Plano()
    plano.audios |= {a for a in (voz.gravacao_audio_id, voz.ref_audio_id) if a}
    _plano_geracoes(db, _geracoes(db, GeracaoAlvo.voz, voz.id), plano)
    _prova(voz.consentimento, plano)
    return plano


def _cenas(db: Session, asset_id: uuid.UUID) -> list[dict[str, Any]]:
    return [{"id": str(cid), "titulo": nome} for cid, nome in db.execute(
        select(Cena.id, Cena.nome).where(Cena.avatar_id == asset_id).order_by(Cena.nome))]


def _avatares(db: Session, voz_id: uuid.UUID) -> list[dict[str, Any]]:
    return [{"id": str(aid), "name": nome} for aid, nome in db.execute(
        select(Asset.id, Asset.name).where(Asset.voz_id == voz_id).order_by(Asset.name))]


def previa_asset(db: Session, asset: Asset) -> PreviaRevogacao:
    plano = _plano_asset(db, asset)
    return PreviaRevogacao(imagens=len(plano.imagens), audios=len(plano.audios),
                           candidatos=plano.candidatos, geracoes=len(plano.geracoes),
                           bytes=_bytes(db, plano), cenas_afetadas=_cenas(db, asset.id))


def previa_voz(db: Session, voz: Voz) -> PreviaRevogacao:
    plano = _plano_voz(db, voz)
    return PreviaRevogacao(imagens=len(plano.imagens), audios=len(plano.audios),
                           candidatos=plano.candidatos, geracoes=len(plano.geracoes),
                           bytes=_bytes(db, plano), cenas_afetadas=[],
                           avatares_afetados=_avatares(db, voz.id))


def _cancelar_e_limpar(db: Session, actor: Actor, plano: Plano) -> None:
    """1 e 2: as abertas canceladas pela 021; depois a mídia e os textos das gerações."""
    for g in plano.geracoes:
        if g.status not in FINAIS:
            geracao_service.cancelar(db, actor, g.id, g.version)
    db.flush()
    agora = datetime.now(UTC)
    ids = [g.id for g in plano.geracoes]
    if ids:
        for c in db.scalars(select(GeracaoCandidato).where(GeracaoCandidato.geracao_id.in_(ids))):
            c.image_id = c.image_par_id = c.audio_id = None
            c.metricas = {}
    for g in plano.geracoes:
        g.params = {**(g.params or {}), "instrucao": None, "prompt": None, "texto": None,
                    "extras": None}
        g.limpa_em = agora
    db.flush()


def _limpar_chamadas(db: Session, alvo_id: uuid.UUID, plano: Plano) -> int:
    """4: o texto das chamadas de IA do alvo (custo, tokens, modelo e desfecho ficam)."""
    conds = [IaChamada.entity_id == alvo_id]
    if plano.geracoes:
        conds.append(IaChamada.geracao_id.in_([g.id for g in plano.geracoes]))
    rows = list(db.scalars(select(IaChamada).where(or_(*conds))))
    for r in rows:
        r.instrucao, r.entrada, r.proposta, r.explicacao = "", None, None, ""
    return len(rows)


def _apagar_linhas(db: Session, plano: Plano) -> list[tuple[storage.Bucket, str]]:
    """3: as linhas de imagem e áudio (os objetos saem depois do commit)."""
    objetos: list[tuple[storage.Bucket, str]] = []
    if plano.imagens:
        objetos += [("imagens", i.object_key) for i in db.scalars(select(Image).where(
            Image.id.in_(plano.imagens)))]
        db.execute(delete(Image).where(Image.id.in_(plano.imagens)))
    if plano.audios:
        objetos += [("audios", a.object_key) for a in db.scalars(select(Audio).where(
            Audio.id.in_(plano.audios)))]
        db.execute(delete(Audio).where(Audio.id.in_(plano.audios)))
    return objetos


def _soltar_cenas(db: Session, actor: Actor, file_ids: list[uuid.UUID]) -> None:
    """As cenas com o arquivo do avatar apontado: o ponteiro vira nulo (o resto fica)."""
    if not file_ids:
        return
    for cena in db.scalars(select(Cena).where(Cena.avatar_arquivo_id.in_(file_ids))):
        before = history.snapshot(cena)
        cena.avatar_arquivo_id = None
        db.flush()
        history.record(db, actor, "cena", cena, "updated", before, history.snapshot(cena),
                       {"revogacao": {"motivo": EXCECAO}})
    db.flush()


def _marcar_revogado(c: dict[str, Any], actor: Actor) -> dict[str, Any]:
    return {**c, "prova": None, "revogado_em": datetime.now(UTC).isoformat(),
            "revogado_por": str(actor.user_id) if actor.user_id else None}


def _evento(db: Session, actor: Actor, alvo_tipo: str, alvo: Any, plano: Plano, bytes_: int,
            chamadas: int, versoes: int) -> None:
    record_event(db, EVENTO, "ok", actor, details={
        "excecao": EXCECAO, "alvoTipo": alvo_tipo, "alvoId": str(alvo.id),
        "perfilId": str(alvo.perfil_id), "imagens": len(plano.imagens),
        "audios": len(plano.audios), "candidatos": plano.candidatos,
        "geracoes": len(plano.geracoes), "chamadasIa": chamadas, "versoesLimpas": versoes,
        "bytes": bytes_})


def revogar_asset(db: Session, actor: Actor, asset_id: uuid.UUID, version: int,
                  confirmo: bool) -> tuple[Asset, PreviaRevogacao, list]:
    from sociman_api.assets import service as assets_service

    asset = assets_service.get_asset_or_404(db, asset_id, lock=True)
    if asset.tipo != AssetTipo.avatar:
        raise ApiError(400, "invalid_asset", "consentimento: só em avatar",
                       details={"field": "consentimento"})
    _confirmar(asset, version, confirmo, "Este asset")
    plano = _plano_asset(db, asset)
    bytes_ = _bytes(db, plano)
    cenas = _cenas(db, asset.id)
    _cancelar_e_limpar(db, actor, plano)
    # Os campos que descrevem a pessoa e os arquivos saem antes do snapshot da versão `revoked`.
    asset.prompt = asset.identidade = asset.image_rules = None
    asset.primary_file_id = None
    db.flush()
    _soltar_cenas(db, actor, [f.id for f in asset.arquivos])
    db.execute(delete(AssetFile).where(AssetFile.asset_id == asset.id))
    db.expire(asset, ["arquivos"])
    objetos = _apagar_linhas(db, plano)
    chamadas = _limpar_chamadas(db, asset.id, plano)
    asset.consentimento = {**(asset.consentimento or {}), "prova": None}
    before = history.snapshot(asset)
    asset.consentimento = _marcar_revogado(asset.consentimento, actor)
    if not asset.archived:
        asset.archived_at, asset.archived_by = datetime.now(UTC), actor.user_id
    asset.updated_by = actor.user_id
    history.record(db, actor, "asset", asset, "revoked", before, history.snapshot(asset),
                   {"revogacao": {"imagens": len(plano.imagens), "cenas": len(cenas)}})
    db.flush()
    versoes = history.redigir_versoes(db, "asset", asset.id, CAMPOS_ASSET, motivo=EXCECAO,
                                      actor=actor)
    _evento(db, actor, "asset", asset, plano, bytes_, chamadas, versoes)
    previa = PreviaRevogacao(imagens=len(plano.imagens), audios=len(plano.audios),
                             candidatos=plano.candidatos, geracoes=len(plano.geracoes),
                             bytes=bytes_, cenas_afetadas=cenas)
    return asset, previa, objetos


def revogar_voz(db: Session, actor: Actor, voz_id: uuid.UUID, version: int,
                confirmo: bool) -> tuple[Voz, PreviaRevogacao, list]:
    from sociman_api.vozes import service as vozes_service

    voz = vozes_service.get_or_404(db, voz_id, lock=True)
    _confirmar(voz, version, confirmo, "Esta voz")
    plano = _plano_voz(db, voz)
    bytes_ = _bytes(db, plano)
    avatares = _avatares(db, voz.id)
    _cancelar_e_limpar(db, actor, plano)
    # O snapshot antes de zerar (os textos saem de todas as versões pela redação, abaixo); a
    # revogação vem antes de tirar a referência (`ck_vozes_ref` aceita aprovada sem ela só
    # quando revogada).
    before = history.snapshot(voz)
    voz.consentimento = _marcar_revogado(voz.consentimento or {}, actor)
    db.flush()
    voz.gravacao_audio_id = voz.ref_audio_id = None
    voz.ref_texto = voz.analise = None
    db.flush()
    objetos = _apagar_linhas(db, plano)
    chamadas = _limpar_chamadas(db, voz.id, plano)
    if not voz.archived:
        voz.archived_at, voz.archived_by = datetime.now(UTC), actor.user_id
    voz.updated_by = actor.user_id
    history.record(db, actor, "voz", voz, "revoked", before, history.snapshot(voz),
                   {"revogacao": {"audios": len(plano.audios), "avatares": len(avatares)}})
    db.flush()
    versoes = history.redigir_versoes(db, "voz", voz.id, CAMPOS_VOZ, motivo=EXCECAO,
                                      actor=actor)
    _evento(db, actor, "voz", voz, plano, bytes_, chamadas, versoes)
    previa = PreviaRevogacao(imagens=len(plano.imagens), audios=len(plano.audios),
                             candidatos=plano.candidatos, geracoes=len(plano.geracoes),
                             bytes=bytes_, cenas_afetadas=[], avatares_afetados=avatares)
    return voz, previa, objetos


def apagar_objetos(objetos: list[tuple[storage.Bucket, str]]) -> None:
    """Depois do commit: os objetos do MinIO (um órfão é inofensivo; a linha já saiu)."""
    for bucket, key in objetos:
        try:
            storage.apagar_por_excecao(key, bucket=bucket, excecao=EXCECAO)
        except Exception:
            log.warning("objeto %s/%s não apagado (fica órfão)", bucket, key, exc_info=True)
