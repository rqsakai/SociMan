"""Busca, filtros e paginação da biblioteca (research R8, FR-005, SC-002).

- `tipo`: vários valores (OU); `tag`: vários valores (E, `tags @> ARRAY[…]`);
- `q`: nome contém (sem diferenciar maiúsculas) ou tag igual a `lower(q)`;
- `archived`: `false` (padrão), `true` ou `all`;
- ordem `updated_at desc, id`, com cursor opaco `base64url("updated_at|id")`.
"""

import base64
import binascii
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select, text
from sqlalchemy.orm import Session

from sociman_api.assets import schemas
from sociman_api.assets.models import Asset, AssetTipo
from sociman_api.assets.service import escape_like, summaries_out
from sociman_api.errors import ApiError
from sociman_api.perfis.service_perfis import get_perfil_or_404

DEFAULT_LIMIT = 48
MAX_LIMIT = 100


def encode_cursor(updated_at: datetime, asset_id: uuid.UUID) -> str:
    raw = f"{updated_at.isoformat()}|{asset_id}".encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, asset_id = raw.split("|")
        return datetime.fromisoformat(ts), uuid.UUID(asset_id)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ApiError(400, "validation_error", "cursor: inválido") from None


def _filtered(stmt: Select, perfil_id: uuid.UUID, tipos: Sequence[AssetTipo],
              tags: Sequence[str], q: str | None, archived: str) -> Select:
    stmt = stmt.where(Asset.perfil_id == perfil_id)
    if archived == "false":
        stmt = stmt.where(Asset.archived_at.is_(None))
    elif archived == "true":
        stmt = stmt.where(Asset.archived_at.is_not(None))
    if tipos:
        stmt = stmt.where(Asset.tipo.in_(list(tipos)))
    wanted = [t.strip().lower() for t in tags if t.strip()]
    if wanted:
        stmt = stmt.where(Asset.tags.contains(wanted))
    term = (q or "").strip().lower()
    if term:
        stmt = stmt.where(or_(
            func.lower(Asset.name).like(f"%{escape_like(term)}%", escape="\\"),
            Asset.tags.contains([term]),
        ))
    return stmt


def tag_counts(db: Session, perfil_id: uuid.UUID, archived: str) -> list[schemas.TagCount]:
    """Todas as tags do perfil (no filtro de arquivados), com contagem, para os chips."""
    where = {"false": "AND archived_at IS NULL", "true": "AND archived_at IS NOT NULL",
             "all": ""}[archived]
    rows = db.execute(text(
        "SELECT tag, count(*) AS n FROM assets, unnest(tags) AS tag "
        f"WHERE perfil_id = :p {where} GROUP BY tag ORDER BY n DESC, tag"
    ), {"p": perfil_id})
    return [schemas.TagCount(tag=tag, count=n) for tag, n in rows]


def list_assets(db: Session, perfil_id: uuid.UUID, *, tipos: Sequence[AssetTipo] = (),
                tags: Sequence[str] = (), q: str | None = None, archived: str = "false",
                limit: int = DEFAULT_LIMIT, cursor: str | None = None) -> schemas.AssetsList:
    get_perfil_or_404(db, perfil_id)
    stmt = _filtered(select(Asset), perfil_id, tipos, tags, q, archived)
    if cursor:
        ts, last_id = decode_cursor(cursor)
        stmt = stmt.where(or_(Asset.updated_at < ts,
                              and_(Asset.updated_at == ts, Asset.id > last_id)))
    rows = list(db.scalars(stmt.order_by(Asset.updated_at.desc(), Asset.id).limit(limit + 1)))
    page, more = rows[:limit], len(rows) > limit
    next_cursor = encode_cursor(page[-1].updated_at, page[-1].id) if more else None
    return schemas.AssetsList(items=summaries_out(db, perfil_id, page), next_cursor=next_cursor,
                              tags=tag_counts(db, perfil_id, archived))
