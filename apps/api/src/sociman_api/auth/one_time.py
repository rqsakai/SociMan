"""Tokens de uso único: verificação de e-mail e redefinição de senha (data-model.md).

Só o sha256 do token vai para o banco. Um token novo do mesmo propósito invalida os anteriores,
e o token só vale para o e-mail que o usuário tinha quando ele foi emitido (troca de e-mail
invalida o link antigo).
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sociman_api.auth.models import OneTimeToken, TokenPurpose, User
from sociman_api.config import get_settings
from sociman_api.errors import ApiError

INVALID_LINK = "Link inválido ou expirado — peça um novo"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _ttl(purpose: TokenPurpose) -> int:
    settings = get_settings()
    return settings.verify_ttl if purpose == TokenPurpose.verify_email else settings.reset_ttl


def issue_token(db: Session, user: User, purpose: TokenPurpose) -> str:
    """Emite um token novo (devolve o valor bruto, para o link) e invalida os anteriores."""
    now = datetime.now(UTC)
    db.execute(
        update(OneTimeToken)
        .where(OneTimeToken.user_id == user.id, OneTimeToken.purpose == purpose,
               OneTimeToken.used_at.is_(None))
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    db.add(OneTimeToken(token_hash=_hash(raw), user_id=user.id, purpose=purpose, email=user.email,
                        expires_at=now + timedelta(seconds=_ttl(purpose)), created_at=now))
    db.flush()
    return raw


def consume_token(db: Session, raw: str, purpose: TokenPurpose) -> User:
    """Valida e marca como usado. Qualquer problema vira 400 `invalid_token` (mesma mensagem)."""
    invalid = ApiError(400, "invalid_token", INVALID_LINK)
    if not raw:
        raise invalid
    now = datetime.now(UTC)
    token = db.execute(
        select(OneTimeToken).where(OneTimeToken.token_hash == _hash(raw)).with_for_update()
    ).scalar_one_or_none()
    if token is None or token.purpose != purpose or token.used_at is not None \
            or token.expires_at <= now:
        raise invalid
    user = db.get(User, token.user_id)
    if user is None or user.email != token.email:
        raise invalid
    token.used_at = now
    db.flush()
    return user
