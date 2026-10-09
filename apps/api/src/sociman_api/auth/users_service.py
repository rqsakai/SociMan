"""Gestão de usuários pelo dono (T040, contracts/http-api.md "Só dono").

Fica fora de `service.py` para não colidir com a verificação e a troca de senha. Toda mutação grava
`updated_by` e um evento de segurança. As recusas (404, 409) são checadas antes de qualquer
alteração, para que nada fique pela metade.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api.auth import tokens
from sociman_api.auth.deps import Actor
from sociman_api.auth.email import EmailSender
from sociman_api.auth.events import record_event
from sociman_api.auth.models import User, UserRole
from sociman_api.auth.passwords import hash_password, validate_password_policy
from sociman_api.auth.schemas import CreateUserIn, UpdateUserIn
from sociman_api.auth.service import send_verification
from sociman_api.errors import ApiError

EMAIL_IN_USE = "Já existe um usuário com esse e-mail"
LAST_OWNER = "É preciso manter pelo menos um dono ativo"
NOT_FOUND = "Usuário não encontrado"
# Sem código próprio no contrato: 409 genérico `conflict` (o SPA mostra a mensagem).
ALREADY_VERIFIED = "E-mail já verificado"


# ---- auxiliares ----

def _email_in_use() -> ApiError:
    return ApiError(409, "email_in_use", EMAIL_IN_USE)


def _email_taken(db: Session, email: str, except_id: uuid.UUID | None = None) -> bool:
    query = select(User.id).where(func.lower(User.email) == email.lower())
    if except_id is not None:
        query = query.where(User.id != except_id)
    return db.scalars(query).first() is not None


def _get_or_404(db: Session, user_id: uuid.UUID, lock: bool = False) -> User:
    user = db.get(User, user_id, with_for_update=lock)
    if user is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return user


def _flush_or_email_in_use(db: Session) -> None:
    """Corrida entre a checagem e o INSERT/UPDATE: o UNIQUE do banco decide, com o mesmo 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        raise _email_in_use() from exc


def _guard_last_owner(db: Session, actor: Actor, user: User, request: Request,
                      event: str) -> None:
    """Recusa com 409 `last_owner` se `user` é o único dono ativo.

    Trava as linhas dos donos ativos (`SELECT … FOR UPDATE`) até o fim da transação, para que dois
    rebaixamentos simultâneos não deixem a casa sem dono. A negação é commitada antes do erro,
    como em `service._deny` (`get_db` faz rollback quando a requisição termina em exceção).
    """
    owners = db.scalars(
        select(User.id)
        .where(User.role == UserRole.dono, User.is_active.is_(True))
        .with_for_update()
    ).all()
    if user.id in owners and len(owners) <= 1:
        record_event(db, event, "denied", actor, user.id, request, {"reason": "last_owner"})
        db.commit()
        raise ApiError(409, "last_owner", LAST_OWNER)


# ---- consultas ----

def list_users(db: Session) -> list[User]:
    """Todos os usuários, inclusive os inativos, na ordem de criação."""
    return list(db.scalars(select(User).order_by(User.created_at, User.email)))


# ---- mutações ----

def create_user(
    db: Session, actor: Actor, data: CreateUserIn, request: Request, sender: EmailSender
) -> tuple[User, bool]:
    """Cria o usuário com troca de senha obrigatória e envia a verificação.

    Devolve `(user, email_sent)`. Falha no envio não desfaz o cadastro (o dono pode reenviar).
    """
    if _email_taken(db, data.email):
        raise _email_in_use()
    validate_password_policy(data.provisional_password)

    now = datetime.now(UTC)
    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.provisional_password),
        role=UserRole(data.role),
        is_active=True,
        email_verified_at=None,
        must_change_password=True,
        password_changed_at=now,
        created_by=actor.user_id,
        updated_by=actor.user_id,
    )
    db.add(user)
    _flush_or_email_in_use(db)
    record_event(db, "user_created", "ok", actor, user.id, request,
                 {"after": {"name": user.name, "email": user.email, "role": user.role.value}})
    email_sent = send_verification(db, user, request, actor, sender)
    return user, email_sent


def update_user(
    db: Session,
    actor: Actor,
    user_id: uuid.UUID,
    data: UpdateUserIn,
    request: Request,
    sender: EmailSender,
) -> tuple[User, bool | None]:
    """Altera nome, e-mail, papel e situação. Devolve `(user, email_sent)`.

    `email_sent` é None quando o e-mail não mudou. Trocar o e-mail zera a verificação, reenvia o
    link e encerra as sessões (FR-013b); desativar encerra as sessões (FR-014).
    """
    changes: dict[str, Any] = data.model_dump(exclude_unset=True)
    user = _get_or_404(db, user_id, lock=True)

    new_name = changes.get("name")
    new_email = changes.get("email")
    new_role = UserRole(changes["role"]) if changes.get("role") is not None else None
    new_active = changes.get("is_active")
    name_changed = new_name is not None and new_name != user.name
    email_changed = new_email is not None and new_email != user.email
    role_changed = new_role is not None and new_role != user.role
    active_changed = new_active is not None and new_active != user.is_active

    # Recusas primeiro: nada é alterado se alguma delas acontecer.
    if email_changed and _email_taken(db, new_email, except_id=user.id):
        raise _email_in_use()
    if user.role == UserRole.dono and user.is_active:
        if role_changed:
            _guard_last_owner(db, actor, user, request, "role_changed")
        if active_changed and not new_active:
            _guard_last_owner(db, actor, user, request, "user_deactivated")

    revoke = False
    email_sent: bool | None = None

    if name_changed:
        record_event(db, "user_updated", "ok", actor, user.id, request,
                     {"before": {"name": user.name}, "after": {"name": new_name}})
        user.name = new_name
    if role_changed:
        record_event(db, "role_changed", "ok", actor, user.id, request,
                     {"before": {"role": user.role.value}, "after": {"role": new_role.value}})
        user.role = new_role
    if active_changed:
        record_event(db, "user_deactivated" if not new_active else "user_reactivated", "ok",
                     actor, user.id, request,
                     {"before": {"isActive": user.is_active}, "after": {"isActive": new_active}})
        user.is_active = new_active
        revoke = revoke or not new_active
    if email_changed:
        record_event(db, "email_changed", "ok", actor, user.id, request,
                     {"before": {"email": user.email}, "after": {"email": new_email}})
        user.email = new_email
        user.email_verified_at = None
        revoke = True

    user.updated_by = actor.user_id
    _flush_or_email_in_use(db)
    if revoke:
        db.commit()  # grava antes de revogar as sessões
        tokens.revoke_all_for_user(str(user.id))
    if email_changed:
        email_sent = send_verification(db, user, request, actor, sender)
    db.refresh(user)
    return user, email_sent


def set_provisional_password(
    db: Session, actor: Actor, user_id: uuid.UUID, password: str, request: Request
) -> User:
    """Define uma senha provisória (FR-013a): troca obrigatória e sessões encerradas."""
    user = _get_or_404(db, user_id, lock=True)
    validate_password_policy(password)

    user.password_hash = hash_password(password)
    user.password_changed_at = datetime.now(UTC)
    user.must_change_password = True
    user.updated_by = actor.user_id
    record_event(db, "password_set_by_owner", "ok", actor, user.id, request)
    db.commit()  # grava antes de revogar as sessões
    tokens.revoke_all_for_user(str(user.id))
    db.refresh(user)
    return user


def resend_user_verification(
    db: Session, actor: Actor, user_id: uuid.UUID, request: Request, sender: EmailSender
) -> bool:
    """Reenvia o link de verificação. Devolve `email_sent`; 409 `conflict` se já verificado."""
    user = _get_or_404(db, user_id)
    if user.email_verified_at is not None:
        raise ApiError(409, "conflict", ALREADY_VERIFIED)
    return send_verification(db, user, request, actor, sender)
