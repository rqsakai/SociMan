"""Contas do perfil em cada plataforma (US2, contracts/http-api.md "Contas").

Toda mutação checa a versão (R2), grava o histórico na mesma transação (R1) e respeita os dois
índices únicos da FR-005 (R8). As recusas são checadas antes de alterar a conta, para a mensagem
sair boa ("Esse @ já pertence ao perfil X"); a corrida entre a checagem e o INSERT/UPDATE cai no
índice do banco e vira o mesmo 409.
"""

import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.perfis import schemas
from sociman_api.perfis.models import Conta, ContaStatus, Perfil, Platform
from sociman_api.perfis.platforms import PLATFORMS, handle_from_url, normalize_handle, url_for
from sociman_api.perfis.service_perfis import (
    apply_archived,
    get_perfil_or_404,
    target_state,
    versions_out,
)

ENTITY = "conta"
LABEL = "Esta conta"
CONTA_NOT_FOUND = "Conta não encontrada"
UQ_HANDLE = "uq_contas_platform_handle"
UQ_ACTIVE = "uq_contas_perfil_platform_ativa"


# ---- consultas ----

def list_versions(db: Session, conta_id: uuid.UUID) -> schemas.VersionsList:
    get_conta(db, conta_id)
    return versions_out(db, ENTITY, conta_id)


# ---- auxiliares ----

def _invalid(message: str) -> ApiError:
    return ApiError(400, "validation_error", message)


def get_conta(db: Session, conta_id: uuid.UUID, lock: bool = False) -> Conta:
    conta = db.get(Conta, conta_id, with_for_update=lock)
    if conta is None:
        raise ApiError(404, "not_found", CONTA_NOT_FOUND)
    return conta


def _platform_label(platform: Platform, platform_name: str) -> str:
    return platform_name if platform == Platform.outra else PLATFORMS[platform].label


def _handle_in_use(db: Session, platform: Platform, platform_name: str, handle: str) -> ApiError:
    with db.no_autoflush:
        owner = db.scalar(
            select(Perfil.name)
            .join(Conta, Conta.perfil_id == Perfil.id)
            .where(Conta.platform == platform, Conta.platform_name == platform_name,
                   Conta.handle == handle)
        )
    suffix = f" {owner}" if owner else ""
    return ApiError(409, "handle_in_use", f"Esse @ já pertence ao perfil{suffix}")


def _active_exists(platform: Platform, platform_name: str) -> ApiError:
    label = _platform_label(platform, platform_name)
    return ApiError(409, "active_platform_exists",
                    f"Este perfil já tem uma conta ativa no {label}")


def _check_unique(db: Session, conta: Conta) -> None:
    """Checagem prévia dos dois índices únicos (FR-005), ignorando a própria conta.

    Sem autoflush: a conta já alterada não pode ir ao banco antes da checagem.
    """
    with db.no_autoflush:
        _check_unique_queries(db, conta)


def _check_unique_queries(db: Session, conta: Conta) -> None:
    others = select(Conta.id).where(
        Conta.id != conta.id,
        Conta.platform == conta.platform,
        Conta.platform_name == conta.platform_name,
    )
    if db.scalars(others.where(Conta.handle == conta.handle)).first() is not None:
        raise _handle_in_use(db, conta.platform, conta.platform_name, conta.handle)
    if conta.status == ContaStatus.ativa and not conta.archived:
        active = others.where(Conta.perfil_id == conta.perfil_id,
                              Conta.status == ContaStatus.ativa, Conta.archived_at.is_(None))
        if db.scalars(active).first() is not None:
            raise _active_exists(conta.platform, conta.platform_name)


def _flush_unique(db: Session, conta: Conta) -> None:
    """Corrida entre a checagem e a escrita: o índice do banco decide, com o mesmo 409.

    A requisição vai falhar de qualquer jeito: o rollback deixa a sessão usável para montar a
    mensagem. (Um SAVEPOINT não serviria: `begin_nested` faz flush do pendente antes de abri-lo.)
    Os valores são lidos antes, porque o rollback expira a conta.
    """
    platform, platform_name, handle = conta.platform, conta.platform_name, conta.handle
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == UQ_HANDLE:
            raise _handle_in_use(db, platform, platform_name, handle) from exc
        if constraint == UQ_ACTIVE:
            raise _active_exists(platform, platform_name) from exc
        raise


def _normalize(raw: str) -> str:
    try:
        return normalize_handle(raw)
    except ValueError as exc:
        raise _invalid(str(exc)) from exc


def _handle_from_any_url(platform: Platform, url: str) -> str | None:
    """Plataforma conhecida: regex da R8. "Outra": último trecho do caminho do link."""
    if platform != Platform.outra:
        return handle_from_url(platform, url)
    segments = [s for s in urlsplit(url).path.split("/") if s]
    if not segments:
        return None
    try:
        return normalize_handle(segments[-1])
    except ValueError:
        return None


def _resolve_create(body: schemas.CreateContaIn) -> tuple[str, str]:
    """(handle, url) a partir do que veio: extrai um do outro (R8)."""
    if body.handle is not None:
        handle = _normalize(body.handle)
    else:
        assert body.url is not None  # garantido pelo schema
        handle = _handle_from_any_url(body.platform, body.url)
        if handle is None:
            raise _invalid("Não deu para tirar o @ desse link; informe o @")
    url = body.url or url_for(body.platform, handle)
    if url is None:  # só "outra", que o schema já obriga a ter link
        raise _invalid("informe o link da conta")
    return handle, url


def _touch(conta: Conta, actor: Actor) -> None:
    conta.updated_by = actor.user_id


# ---- mutações ----

def create_conta(
    db: Session, actor: Actor, perfil_id: uuid.UUID, body: schemas.CreateContaIn
) -> Conta:
    perfil = get_perfil_or_404(db, perfil_id)
    handle, url = _resolve_create(body)
    conta = Conta(
        id=uuid.uuid4(),
        perfil_id=perfil.id,
        platform=body.platform,
        platform_name=body.platform_name,
        handle=handle,
        url=url,
        status=body.status,
        notes=body.notes,
        created_by=actor.user_id,
        updated_by=actor.user_id,
    )
    _check_unique(db, conta)
    db.add(conta)
    history.record(db, actor, ENTITY, conta, "created", None, history.snapshot(conta))
    _flush_unique(db, conta)
    return conta


def update_conta(
    db: Session, actor: Actor, conta_id: uuid.UUID, body: schemas.UpdateContaIn
) -> Conta:
    conta = get_conta(db, conta_id, lock=True)
    history.check_version(conta, body.version, LABEL)
    before = history.snapshot(conta)

    if body.platform_name is not None:
        if conta.platform == Platform.outra and not body.platform_name:
            raise _invalid("informe o nome da plataforma")
        if conta.platform != Platform.outra and body.platform_name:
            raise _invalid("o nome da plataforma só vale para \"outra\"")
        conta.platform_name = body.platform_name
    if body.handle is not None:
        conta.handle = _normalize(body.handle)
    if body.url is not None:
        conta.url = body.url
        if body.handle is None:
            conta.handle = handle_from_url(conta.platform, body.url) or conta.handle
    elif body.handle is not None and conta.handle != before["handle"]:
        # O link sugerido acompanha o @ novo; em "outra" o link digitado fica.
        conta.url = url_for(conta.platform, conta.handle) or conta.url
    if body.status is not None:
        conta.status = body.status
    if body.notes is not None:
        conta.notes = body.notes

    after = history.snapshot(conta)
    if not history.diff(before, after):
        return conta
    _check_unique(db, conta)
    _touch(conta, actor)
    history.record(db, actor, ENTITY, conta, "updated", before, after)
    _flush_unique(db, conta)
    return conta


def archive_conta(db: Session, actor: Actor, conta_id: uuid.UUID, version: int) -> Conta:
    conta = get_conta(db, conta_id, lock=True)
    history.check_version(conta, version, LABEL)
    if conta.archived:
        raise ApiError(409, "conflict", "Esta conta já está arquivada")
    before = history.snapshot(conta)
    conta.archived_at = datetime.now(UTC)
    conta.archived_by = actor.user_id
    _touch(conta, actor)
    history.record(db, actor, ENTITY, conta, "archived", before, history.snapshot(conta))
    db.flush()
    return conta


def restore_conta(db: Session, actor: Actor, conta_id: uuid.UUID, version: int) -> Conta:
    conta = get_conta(db, conta_id, lock=True)
    history.check_version(conta, version, LABEL)
    if not conta.archived:
        raise ApiError(409, "conflict", "Esta conta não está arquivada")
    before = history.snapshot(conta)
    conta.archived_at = None
    conta.archived_by = None
    # Uma conta ativa restaurada não pode virar a segunda ativa da plataforma no perfil.
    _check_unique(db, conta)
    _touch(conta, actor)
    history.record(db, actor, ENTITY, conta, "restored", before, history.snapshot(conta))
    _flush_unique(db, conta)
    return conta


def revert_conta(
    db: Session, actor: Actor, conta_id: uuid.UUID, version: int, to_version: int
) -> Conta:
    """Volta a conta ao estado da versão alvo (FR-013), respeitando a unicidade (FR-005)."""
    conta = get_conta(db, conta_id, lock=True)
    history.check_version(conta, version, LABEL)
    state = target_state(db, ENTITY, conta, to_version)
    before = history.snapshot(conta)

    conta.platform = Platform(state["platform"])
    conta.platform_name = state["platform_name"]
    conta.handle = state["handle"]
    conta.url = state["url"]
    conta.status = ContaStatus(state["status"])
    conta.notes = state["notes"]
    apply_archived(conta, state["archived"], actor)

    after = history.snapshot(conta)
    if after == before:
        raise _invalid("Essa versão é igual à atual")
    _check_unique(db, conta)
    _touch(conta, actor)
    history.record(db, actor, ENTITY, conta, "reverted", before, after,
                   {"from_version": to_version})
    _flush_unique(db, conta)
    return conta
