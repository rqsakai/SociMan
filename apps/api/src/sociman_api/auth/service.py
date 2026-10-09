"""Regras de autenticação (contracts/http-api.md). O router só traduz HTTP; a lógica fica aqui.

Eventos de negação são commitados antes do erro: `get_db` faz rollback quando a requisição
termina em exceção, e o registro de uma tentativa recusada não pode se perder (FR-017).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.auth import rate_limit, tokens
from sociman_api.auth.deps import ANONYMOUS, Actor
from sociman_api.auth.email import EmailSender, reset_email, verification_email
from sociman_api.auth.events import record_event
from sociman_api.auth.models import TokenPurpose, User
from sociman_api.auth.one_time import INVALID_LINK, consume_token, issue_token
from sociman_api.auth.passwords import (
    equalize_timing,
    hash_password,
    needs_rehash,
    validate_password_policy,
    verify_password,
)
from sociman_api.errors import ApiError
from sociman_api.redis import get_redis

INVALID_CREDENTIALS = "E-mail ou senha incorretos"
EMAIL_NOT_VERIFIED = "Confirme seu e-mail antes de entrar"
INVALID_SESSION = "Sessão inválida ou expirada"
WRONG_CURRENT_PASSWORD = "Senha atual incorreta"


# ---- auxiliares ----

def client_ip(request: Request) -> str:
    """Chave de IP para o limite de tentativas (o uvicorn já resolve o X-Forwarded-For)."""
    return request.client.host if request.client else "unknown"


def _user_actor(user: User) -> Actor:
    return Actor(kind="user", user_id=user.id, user=user)


def _get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(func.lower(User.email) == email.lower())).first()


def _get_user(db: Session, user_id: str) -> User | None:
    try:
        return db.get(User, uuid.UUID(user_id))
    except ValueError:
        return None


def _deny(
    db: Session,
    error: ApiError,
    type: str,
    request: Request,
    reason: str,
    subject: User | None = None,
    actor: Actor = ANONYMOUS,
) -> ApiError:
    """Grava o evento de negação, commita e devolve o erro para o chamador levantar."""
    record_event(db, type, "denied", actor, subject.id if subject else None, request,
                 {"reason": reason})
    db.commit()
    return error


# ---- login ----

def login(
    db: Session, email: str, password: str, request: Request
) -> tuple[User, str, str, str]:
    """Abre uma sessão. Devolve `(user, access, refresh, fam)`.

    E-mail inexistente, senha errada e usuário inativo dão o mesmo 401 (FR-006); o 403 de e-mail
    não verificado só aparece depois da senha certa, para não revelar quais contas existem.
    """
    rate_limit.check("login", client_ip(request), email)

    user = _get_user_by_email(db, email)
    invalid = ApiError(401, "invalid_credentials", INVALID_CREDENTIALS)
    if user is None:
        equalize_timing()
        raise _deny(db, invalid, "login_failed", request, "unknown_email")
    if not verify_password(password, user.password_hash):
        raise _deny(db, invalid, "login_failed", request, "wrong_password", user)
    if not user.is_active:
        raise _deny(db, invalid, "login_failed", request, "inactive", user)
    if user.email_verified_at is None:
        raise _deny(db, ApiError(403, "email_not_verified", EMAIL_NOT_VERIFIED),
                    "login_failed", request, "email_not_verified", user)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    access, refresh_token, fam = tokens.create_family(str(user.id))
    record_event(db, "login_succeeded", "ok", _user_actor(user), user.id, request)
    return user, access, refresh_token, fam


# ---- renovação ----

def _family_owner(refresh_token: str) -> str | None:
    """Dono da família antes da rotação (o reuso apaga a família, e o evento precisa do sujeito)."""
    fam = refresh_token.partition(".")[0]
    return get_redis().hget(tokens._family_key(fam), "userId") if fam else None


def refresh(
    db: Session, refresh_token: str, request: Request
) -> tuple[User, str, str, int]:
    """Rotaciona o token de renovação. Devolve `(user, access, refresh, segundos_restantes)`.

    Qualquer falha é 401 `invalid_token`: token desconhecido ou expirado, reuso (a família já foi
    revogada pela rotação) e usuário inativo ou apagado (a família é revogada aqui, FR-014).
    O token anterior dentro da carência (duas abas renovando juntas) recebe o token atual e grava
    `refresh_concorrente` (informativo): não é reuso.
    """
    invalid = ApiError(401, "invalid_token", INVALID_SESSION)
    owner_id = _family_owner(refresh_token)
    result = tokens.rotate(refresh_token)
    if not result.ok:
        if result.reason == "reused":
            owner = _get_user(db, owner_id) if owner_id else None
            raise _deny(db, invalid, "refresh_reuse_detected", request, "reused", owner)
        raise invalid

    user = _get_user(db, result.user_id)
    if user is None or not user.is_active:
        tokens.revoke_family(result.fam)
        raise invalid
    if result.concurrent:
        record_event(db, "refresh_concorrente", "ok", _user_actor(user), user.id, request)
    return user, result.access, result.refresh, result.remaining_seconds


# ---- logout ----

def logout(db: Session, bearer: str | None, request: Request) -> None:
    """Revoga a família do Bearer, mesmo expirado (o cookie só vai para /refresh). Nunca falha."""
    if not bearer:
        return
    claims = tokens.decode_access(bearer, allow_expired=True)
    if not claims:
        return
    tokens.revoke_family(claims["fam"])
    user = _get_user(db, claims["sub"])
    if user is not None:
        record_event(db, "logout", "ok", _user_actor(user), user.id, request)


# ---- verificação e troca de senha ----

@dataclass(frozen=True)
class OutgoingEmail:
    """E-mail pronto para envio adiado (ex.: BackgroundTask)."""

    to: str
    subject: str
    text: str
    html: str


def send_verification(
    db: Session, user: User, request: Request | None, actor: Actor, sender: EmailSender
) -> bool:
    """Emite um link de verificação (invalida os anteriores) e envia. Devolve se o envio deu certo.

    Uma falha de SMTP não desfaz nada: o token fica emitido e o dono pode reenviar (FR-020).
    """
    raw = issue_token(db, user, TokenPurpose.verify_email)
    sent = sender.send(user.email, *verification_email(user.name, raw))
    record_event(db, "email_verification_sent", "ok", actor, user.id, request,
                 {"emailSent": sent})
    return sent


def verify_email(db: Session, raw: str, request: Request) -> User:
    """Confirma o e-mail pelo link. Não abre sessão: o usuário faz login em seguida."""
    rate_limit.check("verify", client_ip(request))
    user = consume_token(db, raw, TokenPurpose.verify_email)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        user.updated_by = user.id  # autor da mutação: o próprio usuário (FR-016)
    record_event(db, "email_verified", "ok", _user_actor(user), user.id, request)
    return user


def resend_verification(db: Session, email: str, request: Request) -> OutgoingEmail | None:
    """Prepara o reenvio do link, só para conta ativa e ainda não verificada (FR-021).

    A resposta pública é sempre a mesma (FR-006). Para o TEMPO de resposta também não revelar se
    a conta existe, o envio SMTP não acontece aqui: devolvemos o e-mail pronto e a rota o envia
    depois da resposta (BackgroundTask). O token é commitado antes, para o link já valer.
    """
    rate_limit.check("resend", client_ip(request), email)
    user = _get_user_by_email(db, email)
    if user is None or not user.is_active or user.email_verified_at is not None:
        return None
    raw = issue_token(db, user, TokenPurpose.verify_email)
    record_event(db, "email_verification_sent", "ok", ANONYMOUS, user.id, request,
                 {"emailSent": None, "deferred": True})
    db.commit()
    return OutgoingEmail(user.email, *verification_email(user.name, raw))


def change_password(
    db: Session, actor: Actor, current: str, new: str, request: Request
) -> tuple[User, str]:
    """Troca a senha do próprio usuário. Devolve `(user, access)`.

    A sessão atual continua (novo access token para a mesma família) e as outras são encerradas
    (FR-015). Também encerra a troca obrigatória da senha provisória (FR-012a).
    """
    user = actor.user
    assert user is not None and actor.fam is not None
    rate_limit.check("change", client_ip(request), str(user.id))

    if not verify_password(current, user.password_hash):
        raise _deny(db, ApiError(400, "invalid_credentials", WRONG_CURRENT_PASSWORD),
                    "password_changed", request, "wrong_current_password", user, actor)
    validate_password_policy(new, current)

    user.password_hash = hash_password(new)
    user.password_changed_at = datetime.now(UTC)
    user.must_change_password = False
    user.updated_by = user.id
    record_event(db, "password_changed", "ok", actor, user.id, request)
    db.commit()  # grava antes de revogar: se o commit falhar, ninguém é deslogado à toa
    tokens.revoke_all_for_user(str(user.id), except_fam=actor.fam)
    return user, tokens.sign_access(str(user.id), actor.fam)


# ---- recuperação de senha ----

def request_password_reset(db: Session, email: str, request: Request) -> OutgoingEmail | None:
    """Prepara o link de redefinição, só para conta existente e ativa (FR-019).

    Mesmo padrão de `resend_verification`: resposta pública sempre igual (FR-006) e envio SMTP
    adiado para a rota, para o tempo de resposta não revelar se a conta existe. Um pedido novo
    invalida o link anterior (`issue_token`).
    """
    rate_limit.check("forgot", client_ip(request), email)
    user = _get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    raw = issue_token(db, user, TokenPurpose.reset_password)
    record_event(db, "password_reset_requested", "ok", ANONYMOUS, user.id, request,
                 {"deferred": True})
    db.commit()
    return OutgoingEmail(user.email, *reset_email(user.name, raw))


def reset_password(db: Session, raw: str, new_password: str, request: Request) -> User:
    """Troca a senha pelo link, encerra TODAS as sessões e a troca obrigatória (FR-012a).

    A política é validada antes de consumir o token: senha fraca não queima o link.
    """
    rate_limit.check("reset", client_ip(request))
    validate_password_policy(new_password)
    user = consume_token(db, raw, TokenPurpose.reset_password)
    if not user.is_active:  # link emitido antes da desativação
        raise ApiError(400, "invalid_token", INVALID_LINK)

    user.password_hash = hash_password(new_password)
    user.password_changed_at = datetime.now(UTC)
    user.must_change_password = False
    user.updated_by = user.id
    record_event(db, "password_reset_completed", "ok", _user_actor(user), user.id, request)
    db.commit()  # grava antes de revogar: se o commit falhar, ninguém é deslogado à toa
    tokens.revoke_all_for_user(str(user.id))
    return user
