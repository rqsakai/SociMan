"""Registro de eventos de segurança (FR-017). Só faz `db.add`; quem commita é `get_db`."""

import ipaddress
import uuid
from typing import Any, Protocol

from fastapi import Request
from sqlalchemy.orm import Session

from sociman_api.auth.models import SecurityEvent

USER_AGENT_MAX = 300
_SENSITIVE = ("password", "token", "hash")


class ActorLike(Protocol):
    """Qualquer objeto com `kind` ('user'|'anonymous'|'system:cli') e `user_id` (ex.: deps.Actor)."""

    kind: str
    user_id: uuid.UUID | None


def _scrub(value: Any) -> Any:
    """Remove recursivamente as chaves que contêm 'password', 'token' ou 'hash'."""
    if isinstance(value, dict):
        return {
            k: _scrub(v)
            for k, v in value.items()
            if not any(s in str(k).lower() for s in _SENSITIVE)
        }
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


def _client_ip(request: Request | None) -> str | None:
    """IP do cliente, ou None se não for um endereço válido (ex.: 'testclient' do TestClient)."""
    if request is None or request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None


def record_event(
    db: Session,
    type: str,
    outcome: str,
    actor: ActorLike,
    subject_user_id: uuid.UUID | None = None,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
) -> SecurityEvent:
    user_agent = request.headers.get("user-agent") if request is not None else None
    event = SecurityEvent(
        type=type,
        outcome=outcome,
        actor_user_id=actor.user_id,
        actor_kind=actor.kind,
        subject_user_id=subject_user_id,
        ip=_client_ip(request),
        user_agent=user_agent[:USER_AGENT_MAX] if user_agent else None,
        details=_scrub(details or {}),
    )
    db.add(event)
    return event
