"""Vozes (spec 025, contracts/http-api.md, research R9, R11, R14, R15; spec 029: da agência, com
perfil base opcional e o nome único na agência inteira entre as ativas).

Toda mutação trava a voz, confere a `version`, recusa voz revogada e grava
**uma** versão (`entity_type = "voz"`). Nada é apagado: arquivar e restaurar; reverter só pelo
dono, sem voltar a uma referência apagada. A geração dos candidatos é a da 021 (`voz.gravacao`,
`voz.design`), pedida pela rota genérica de gerações; o status da voz muda pelo gancho do
aplicador (`geracao/aplicadores_voz.py`).

Spec 029: criar com perfil base arquivado continua recusado (`perfil_archived`), mas a voz de um
perfil arquivado segue editável (FR-010); o perfil base muda pelo PATCH, numa versão.
"""

import base64
import binascii
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.assets import service_padrao
from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.estudio.nomes import perfil_nomes
from sociman_api.geracao.models import Audio, Geracao, GeracaoAlvo, GeracaoStatus
from sociman_api.perfis import base as perfil_base
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import (
    apply_archived,
    get_perfil_or_404,
    target_state,
    user_refs,
    versions_out,
)
from sociman_api.vozes import schemas
from sociman_api.vozes.models import ENTITY, Voz, VozOrigem, VozStatus
from sociman_api.vozes.tts_id import tts_id

LABEL = "Esta voz"
NOT_FOUND = "Voz não encontrada"
NOME_EM_USO = "Já existe uma voz ativa com esse nome"
LIMITE_PADRAO = 20
LIMITE_MAX = 50


def get_or_404(db: Session, voz_id: uuid.UUID, lock: bool = False) -> Voz:
    voz = db.get(Voz, voz_id, with_for_update=lock)
    if voz is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return voz


def _invalida(field: str, message: str) -> ApiError:
    return ApiError(400, "entrada_invalida", f"{field}: {message}", details={"field": field})


def _perfil_ativo(db: Session, perfil_id: uuid.UUID | None) -> None:
    """O perfil base de uma voz nova: sem perfil passa; arquivado é recusado."""
    if perfil_id is None:
        return
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")


def perfil_base_novo(db: Session, perfil_id: uuid.UUID | None) -> None:
    """O `perfilId` da rota da agência: inexistente → 400 `perfil_invalido`; arquivado → 409."""
    if perfil_base.perfil_existente(db, perfil_id) is not None:
        _perfil_ativo(db, perfil_id)


def _editavel(db: Session, voz_id: uuid.UUID, version: int) -> Voz:
    voz = get_or_404(db, voz_id, lock=True)
    history.check_version(voz, version, LABEL)
    if voz.revogada:
        raise service_padrao.consentimento_revogado()
    if voz.archived:
        raise ApiError(409, "voz_arquivada", "Restaure a voz antes de editar")
    return voz


def _flush_nome(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        if "uq_vozes_nome" in str(exc.orig):
            raise ApiError(409, "voz_nome_em_uso", NOME_EM_USO) from exc
        raise


def _nome_em_uso(db: Session, nome: str, exceto: uuid.UUID | None = None) -> bool:
    """Spec 029 (FR-022): o nome é único entre as vozes ativas da agência inteira."""
    stmt = select(Voz.id).where(Voz.archived_at.is_(None), func.lower(Voz.name) == nome.lower())
    if exceto is not None:
        stmt = stmt.where(Voz.id != exceto)
    return db.scalar(stmt) is not None


def gravar(db: Session, actor: Actor, voz: Voz, action: str, before: dict[str, Any] | None,
           details: dict[str, Any] | None = None) -> bool:
    _flush_nome(db)
    after = history.snapshot(voz)
    if before is not None and after == before:
        return False
    voz.updated_by = actor.user_id
    history.record(db, actor, ENTITY, voz, action, before, after, details)
    return True


# ---- leitura ----

def _sincronizacao(voz: Voz) -> str:
    if voz.revogada:
        return "removendo" if voz.sincronizada_em else "nao_se_aplica"
    if voz.ref_audio_id is None:
        return "nao_se_aplica"
    return "ok" if voz.sincronizada_em else "pendente"


def _usada_por(db: Session, voz_id: uuid.UUID) -> list[schemas.UsadaPor]:
    return [schemas.UsadaPor(id=i, name=n) for i, n in db.execute(
        select(Asset.id, Asset.name).where(Asset.voz_id == voz_id, Asset.archived_at.is_(None))
        .order_by(Asset.name))]


def _resumo_campos(voz: Voz, n_usada: int, nomes: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": voz.id, "perfil_id": voz.perfil_id,
        "perfil_nome": nomes.get(voz.perfil_id) if voz.perfil_id else None,
        "name": voz.name, "origem": voz.origem,
        "tom": voz.tom, "descricao": voz.descricao, "tts_id": tts_id(voz.id),
        "status": voz.status,
        "trocando_referencia": voz.status in (VozStatus.gerando, VozStatus.revisao)
        and voz.ref_audio_id is not None,
        "sincronizada_em": voz.sincronizada_em, "sincronizacao": _sincronizacao(voz),
        "n_usada_por": n_usada, "revogada": voz.revogada, "archived": voz.archived,
        "version": voz.version, "created_at": voz.created_at, "updated_at": voz.updated_at,
    }


def _ultima(db: Session, voz_id: uuid.UUID, passos: Sequence[str],
            abertas: bool) -> Geracao | None:
    from sociman_api.geracao.models import FINAIS

    stmt = select(Geracao).where(Geracao.alvo_tipo == GeracaoAlvo.voz, Geracao.alvo_id == voz_id,
                                 Geracao.passo.in_(list(passos)))
    if abertas:
        stmt = stmt.where(Geracao.status.not_in(FINAIS))
    return db.scalar(stmt.order_by(Geracao.created_at.desc()).limit(1))


def voz_out(db: Session, voz: Voz, actor: Actor | None = None) -> schemas.Voz:
    from sociman_api.geracao import audios as audios_mod
    from sociman_api.geracao import service as geracao_service

    db.flush()
    db.refresh(voz)
    audios = {a.id: a for a in db.scalars(select(Audio).where(Audio.id.in_(
        [i for i in (voz.gravacao_audio_id, voz.ref_audio_id) if i])))}
    users = user_refs(db, [voz.created_by, *(a.created_by for a in audios.values())])
    usada = _usada_por(db, voz.id)
    aberta = _ultima(db, voz.id, ("voz.gravacao", "voz.design"), abertas=True)
    teste = _ultima(db, voz.id, ("voz.teste",), abertas=False)
    return schemas.Voz(
        **_resumo_campos(voz, len(usada), perfil_nomes(db, [voz.perfil_id])),
        gravacao=audios_mod.audio_out(audios[voz.gravacao_audio_id], users)
        if voz.gravacao_audio_id in audios else None,
        referencia=audios_mod.audio_out(audios[voz.ref_audio_id], users)
        if voz.ref_audio_id in audios else None,
        ref_texto=voz.ref_texto, analise=voz.analise,
        consentimento=service_padrao.consentimento_out(
            db, voz.consentimento, para_mcp=actor is not None and actor.kind == "mcp_client"),
        usada_por=usada,
        geracao_aberta=geracao_service.resumo_out(db, aberta) if aberta else None,
        ultimo_teste=geracao_service.resumo_out(db, teste) if teste else None,
        created_by=users.get(voz.created_by) if voz.created_by else None)


def detalhe(db: Session, voz_id: uuid.UUID, actor: Actor | None = None) -> schemas.Voz:
    return voz_out(db, get_or_404(db, voz_id), actor)


def versoes(db: Session, voz_id: uuid.UUID) -> VersionsList:
    get_or_404(db, voz_id)
    return versions_out(db, ENTITY, voz_id)


def _encode(ts: datetime, vid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{ts.isoformat()}|{vid}".encode()).rstrip(b"=").decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, vid = raw.split("|")
        return datetime.fromisoformat(ts), uuid.UUID(vid)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ApiError(400, "validation_error", "cursor: inválido") from None


def listar(db: Session, perfil_id: uuid.UUID, **kw) -> schemas.VozesLista:
    """A lista por perfil (025, obsoleta na 029): a da agência com aquele perfil base."""
    get_perfil_or_404(db, perfil_id)
    return listar_agencia(db, perfil_id, **kw)


def listar_agencia(db: Session, filtro: perfil_base.Filtro, *,
                   status: Sequence[VozStatus] = (), arquivadas: bool = False,
                   q: str | None = None, cursor: str | None = None,
                   limite: int = LIMITE_PADRAO) -> schemas.VozesLista:
    """Spec 029: `filtro` None = todas; `sem` = sem perfil base; ou um perfil."""
    stmt = perfil_base.aplicar_filtro(select(Voz), Voz.perfil_id, filtro)
    stmt = stmt.where(Voz.archived_at.is_not(None) if arquivadas else Voz.archived_at.is_(None))
    if status:
        stmt = stmt.where(Voz.status.in_(list(status)))
    if q and q.strip():
        termo = q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(func.lower(Voz.name).like(f"%{termo}%", escape="\\"))
    if cursor:
        ts, last = _decode(cursor)
        stmt = stmt.where(or_(Voz.updated_at < ts, and_(Voz.updated_at == ts, Voz.id > last)))
    limite = max(1, min(limite, LIMITE_MAX))
    rows = list(db.scalars(stmt.order_by(Voz.updated_at.desc(), Voz.id).limit(limite + 1)))
    page, mais = rows[:limite], len(rows) > limite
    contagem = dict(db.execute(select(Asset.voz_id, func.count()).where(
        Asset.voz_id.in_([v.id for v in page]), Asset.archived_at.is_(None))
        .group_by(Asset.voz_id)).all()) if page else {}
    nomes = perfil_nomes(db, [v.perfil_id for v in page])
    return schemas.VozesLista(
        itens=[schemas.VozResumo(**_resumo_campos(v, contagem.get(v.id, 0), nomes))
               for v in page],
        proximo=_encode(page[-1].updated_at, page[-1].id) if mais else None)


# ---- escritas ----

def criar(db: Session, actor: Actor, perfil_id: uuid.UUID | None, body: schemas.VozIn) -> Voz:
    _perfil_ativo(db, perfil_id)
    if body.origem == VozOrigem.sintetica and not body.descricao:
        raise _invalida("descricao", "descreva a voz sintética em inglês")
    if body.origem == VozOrigem.gravacao and body.descricao:
        raise _invalida("descricao", "só na voz sintética")
    service_padrao.checar_menoridade(body.descricao, body.name, body.tom)
    if _nome_em_uso(db, body.name):
        raise ApiError(409, "voz_nome_em_uso", NOME_EM_USO)
    voz = Voz(perfil_id=perfil_id, name=body.name, origem=body.origem, tom=body.tom,
              descricao=body.descricao, created_by=actor.user_id, updated_by=actor.user_id)
    db.add(voz)
    db.flush()
    gravar(db, actor, voz, "created", None)
    return voz


def editar(db: Session, actor: Actor, voz_id: uuid.UUID, body: schemas.VozPatch) -> Voz:
    voz = _editavel(db, voz_id, body.version)
    mudancas = body.model_dump(exclude_unset=True, exclude={"version"})
    if "perfil_id" in mudancas:  # spec 029: o perfil base (arquivado é aceito)
        perfil_base.perfil_existente(db, mudancas["perfil_id"])
    before = history.snapshot(voz)
    if "perfil_id" in mudancas:
        voz.perfil_id = mudancas["perfil_id"]
    if mudancas.get("name") and mudancas["name"] != voz.name:
        if _nome_em_uso(db, mudancas["name"], exceto=voz.id):
            raise ApiError(409, "voz_nome_em_uso", NOME_EM_USO)
        voz.name = mudancas["name"]
    if mudancas.get("tom"):
        voz.tom = mudancas["tom"]
    if "descricao" in mudancas:
        if voz.origem != VozOrigem.sintetica:
            raise _invalida("descricao", "só na voz sintética")
        if not mudancas["descricao"]:
            raise _invalida("descricao", "a voz sintética precisa da descrição")
        service_padrao.checar_menoridade(mudancas["descricao"])
        voz.descricao = mudancas["descricao"]
    if "gravacao_audio_id" in mudancas:
        if voz.origem != VozOrigem.gravacao:
            raise _invalida("gravacaoAudioId", "só na voz de gravação")
        audio = db.get(Audio, mudancas["gravacao_audio_id"]) \
            if mudancas["gravacao_audio_id"] else None
        if audio is None:  # spec 029: o áudio pode ser de qualquer perfil base
            raise _invalida("gravacaoAudioId", "envie o áudio antes")
        if service_padrao.midia_de_outra_pessoa(db, alvo_tipo="voz", alvo_id=voz.id,
                                                audio_id=audio.id):
            raise _invalida("gravacaoAudioId", "esse áudio é a voz de outro item: envie a "
                            "gravação desta pessoa")
        voz.gravacao_audio_id = audio.id
    gravar(db, actor, voz, "updated", before)
    return voz


def registrar_consentimento(db: Session, actor: Actor, voz_id: uuid.UUID, version: int,
                            nome: str, data, observacao: str,
                            prova: dict[str, Any] | None) -> Voz:
    voz = _editavel(db, voz_id, version)
    if voz.origem != VozOrigem.gravacao:
        raise _invalida("consentimento", "só na voz de gravação")
    before = history.snapshot(voz)
    voz.consentimento = service_padrao.montar_consentimento(db, actor, voz.perfil_id, nome,
                                                            data, observacao, prova,
                                                            alvo_tipo="voz", alvo_id=voz.id)
    gravar(db, actor, voz, "consentimento", before)
    return voz


def arquivar(db: Session, actor: Actor, voz_id: uuid.UUID, version: int) -> Voz:
    voz = get_or_404(db, voz_id, lock=True)
    history.check_version(voz, version, LABEL)
    if voz.archived:
        raise ApiError(409, "conflict", "Esta voz já está arquivada")
    before = history.snapshot(voz)
    voz.archived_at, voz.archived_by = datetime.now(UTC), actor.user_id
    gravar(db, actor, voz, "archived", before)
    return voz


def restaurar(db: Session, actor: Actor, voz_id: uuid.UUID, version: int) -> Voz:
    voz = get_or_404(db, voz_id, lock=True)
    history.check_version(voz, version, LABEL)
    if voz.revogada:
        raise service_padrao.consentimento_revogado()
    if not voz.archived:
        raise ApiError(409, "conflict", "Esta voz não está arquivada")
    if _nome_em_uso(db, voz.name, exceto=voz.id):
        raise ApiError(409, "voz_nome_em_uso", NOME_EM_USO)
    before = history.snapshot(voz)
    voz.archived_at = voz.archived_by = None
    gravar(db, actor, voz, "restored", before)
    return voz


def reverter(db: Session, actor: Actor, voz_id: uuid.UUID, version: int,
             to_version: int) -> Voz:
    voz = get_or_404(db, voz_id, lock=True)
    history.check_version(voz, version, LABEL)
    if voz.revogada:
        raise service_padrao.consentimento_revogado()
    state = target_state(db, ENTITY, voz, to_version)
    for campo in ("gravacao_audio_id", "ref_audio_id"):
        if state.get(campo) and db.get(Audio, uuid.UUID(state[campo])) is None:
            raise ApiError(409, "revert_midia_apagada", "Essa versão usa arquivos apagados")
    before = history.snapshot(voz)
    voz.name, voz.tom, voz.descricao = state["name"], state["tom"], state["descricao"]
    if "perfil_id" in state:  # spec 029: o perfil base da versão alvo (as antigas não têm)
        voz.perfil_id = uuid.UUID(state["perfil_id"]) if state["perfil_id"] else None
    for campo in ("gravacao_audio_id", "ref_audio_id"):
        setattr(voz, campo, uuid.UUID(state[campo]) if state.get(campo) else None)
    referencia_mudou = before["ref_audio_id"] != state.get("ref_audio_id")
    voz.ref_texto = state["ref_texto"]
    voz.status = VozStatus(state["status"])
    if referencia_mudou:
        voz.sincronizada_em = None  # a linha `vozes_sync` importa a referência de volta
    apply_archived(voz, state["archived"], actor)
    if history.snapshot(voz) == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    gravar(db, actor, voz, "reverted", before, {"from_version": to_version})
    return voz


# ---- estados pelo gancho da 021 (geracao/aplicadores_voz.py) ----

def status_pelo_gancho(db: Session, voz: Voz, para: GeracaoStatus, outra_aberta: bool,
                       analise: dict[str, Any] | None = None) -> None:
    """R11: `gerando` ao pedir; `revisao` com opções; de volta ao anterior na falha ou no
    cancelamento sem outra geração aberta. Sem versão (estado técnico da geração)."""
    if para == GeracaoStatus.na_fila:
        voz.status = VozStatus.gerando
    elif para == GeracaoStatus.revisao:
        voz.status = VozStatus.revisao
        if analise:
            voz.analise = analise
    elif para in (GeracaoStatus.falhou, GeracaoStatus.cancelada, GeracaoStatus.descartada) \
            and not outra_aberta:
        voz.status = VozStatus.aprovada if voz.ref_audio_id else VozStatus.rascunho
