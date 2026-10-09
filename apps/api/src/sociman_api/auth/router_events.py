"""Eventos de segurança para o dono (T050, FR-017a; contracts/http-api.md "Só dono").

Paginação keyset por `(occurred_at desc, id desc)`. O cursor é opaco: base64url (sem `=`) de
`"<occurred_at ISO 8601>|<id>"` do último item da página.
"""

import base64
import binascii
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import aliased

from sociman_api.auth.deps import RequireOwner
from sociman_api.auth.models import SecurityEvent as EventRow
from sociman_api.auth.models import User as UserRow
from sociman_api.auth.schemas import McpClienteRef, SecurityEvent, SecurityEventPage
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope

router = APIRouter(prefix="/api/security-events")

Db = DbSession


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def encode_cursor(occurred_at: datetime, event_id: int) -> str:
    raw = f"{occurred_at.isoformat()}|{event_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        at, _, event_id = raw.partition("|")
        occurred_at = datetime.fromisoformat(at)
        if occurred_at.tzinfo is None:
            raise ValueError("cursor sem fuso")
        return occurred_at, int(event_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ApiError(400, "validation_error", "cursor: inválido") from exc


def _clientes_mcp(db, ids: set[UUID | None]) -> dict[UUID, McpClienteRef]:
    """Spec 009: nome do cliente MCP de cada evento (recusas e gestão de clientes)."""
    from sociman_api.mcp.models import McpCliente

    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(McpCliente.id, McpCliente.nome).where(McpCliente.id.in_(wanted)))
    return {cid: McpClienteRef(id=cid, nome=nome) for cid, nome in rows}


@router.get("", operation_id="security_events_list", response_model=SecurityEventPage,
            responses=_errors(400, 401, 403))
def list_events(
    actor: RequireOwner,
    db: Db,
    user_id: Annotated[UUID | None, Query(alias="userId")] = None,
    type: Annotated[str | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SecurityEventPage:
    actor_user = aliased(UserRow)
    subject_user = aliased(UserRow)
    query = (
        select(EventRow, actor_user.name, subject_user.name)
        .outerjoin(actor_user, actor_user.id == EventRow.actor_user_id)
        .outerjoin(subject_user, subject_user.id == EventRow.subject_user_id)
    )
    if user_id is not None:
        query = query.where(or_(EventRow.actor_user_id == user_id,
                                EventRow.subject_user_id == user_id))
    if type is not None:
        query = query.where(EventRow.type == type)
    if from_ is not None:
        query = query.where(EventRow.occurred_at >= from_)
    if to is not None:
        query = query.where(EventRow.occurred_at <= to)
    if cursor is not None:
        query = query.where(tuple_(EventRow.occurred_at, EventRow.id) < decode_cursor(cursor))

    rows = db.execute(
        query.order_by(EventRow.occurred_at.desc(), EventRow.id.desc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    clientes = _clientes_mcp(db, {e.actor_mcp_client_id for e, _, _ in page})
    items = [
        SecurityEvent(
            id=event.id,
            occurred_at=event.occurred_at,
            type=event.type,
            outcome=event.outcome,
            actor_kind=event.actor_kind,
            actor_user_id=event.actor_user_id,
            actor_name=actor_name,
            actor_mcp_client=clientes.get(event.actor_mcp_client_id),
            subject_user_id=event.subject_user_id,
            subject_name=subject_name,
            ip=str(event.ip) if event.ip is not None else None,
            details=event.details,
        )
        for event, actor_name, subject_name in page
    ]
    last = page[-1][0] if page else None
    next_cursor = (encode_cursor(last.occurred_at, last.id)
                   if len(rows) > limit and last is not None else None)
    return SecurityEventPage(items=items, next_cursor=next_cursor)
