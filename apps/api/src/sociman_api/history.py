"""Histórico genérico de versões (research R1, princípio VII): `entity_versions` e helpers.

Como uma entidade de domínio usa este módulo:
- o modelo tem a coluna `version` (controle otimista, R2) e declara `__versioned_fields__`, os
  campos do snapshot (nunca `version`, timestamps de auditoria nem segredos). Campos só
  informativos, que a reversão ignora, vão em `__immutable_fields__` (ex.: o `slug` do perfil);
- cada mutação faz `check_version`, tira `snapshot` antes e depois e chama `record` na mesma
  sessão (e portanto na mesma transação) da mutação.
"""

import enum
import uuid
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from sociman_api.db import Base
from sociman_api.errors import ApiError

ACTIONS = ("created", "updated", "archived", "restored", "reverted")


class EntityVersion(Base):
    """Imutável: a aplicação só faz INSERT."""

    __tablename__ = "entity_versions"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version",
                         name="uq_entity_versions_entity_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)  # perfil | conta | …
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)  # ver ACTIONS
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)  # user | system:cli
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


Index(
    "ix_entity_versions_entity_version",
    EntityVersion.entity_type,
    EntityVersion.entity_id,
    EntityVersion.version.desc(),
)


class ActorLike(Protocol):
    """O `Actor` da auth (ou qualquer objeto com `kind` e `user_id`)."""

    kind: str
    user_id: uuid.UUID | None


def _jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def snapshot(entity: Any) -> dict[str, Any]:
    """Só os campos versionados da entidade (`__versioned_fields__`), já serializáveis em JSON."""
    return {f: _jsonable(getattr(entity, f)) for f in entity.__versioned_fields__}


def diff(before: Mapping[str, Any] | None, after: Mapping[str, Any]) -> list[str]:
    """Campos que mudaram, na ordem do `after`. Sem `before` (criação), todos os do `after`."""
    if before is None:
        return list(after)
    keys = list(after) + [k for k in before if k not in after]
    return [k for k in keys if before.get(k) != after.get(k)]


def record(
    db: Session,
    actor: ActorLike,
    entity_type: str,
    entity: Any,
    action: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    details: Mapping[str, Any] | None = None,
) -> EntityVersion:
    """Grava a próxima versão da entidade e atualiza `entity.version` (sem commit).

    `created` é sempre a versão 1; as demais ações incrementam a versão atual. A entidade
    precisa ter `id` (o chamador faz `flush` antes, se o id vier do banco).
    """
    if action not in ACTIONS:
        raise ValueError(f"ação de histórico desconhecida: {action}")
    if action == "created":
        entity.version = 1
    else:
        entity.version += 1
    before_json = _jsonable(before) if before is not None else None
    after_json = _jsonable(after)
    row = EntityVersion(
        entity_type=entity_type,
        entity_id=entity.id,
        version=entity.version,
        action=action,
        actor_kind=actor.kind,
        actor_user_id=actor.user_id,
        before=before_json,
        after=after_json,
        changed_fields=diff(before_json, after_json),
        details=_jsonable(details or {}),
    )
    db.add(row)
    return row


def list_versions(db: Session, entity_type: str, entity_id: uuid.UUID) -> list[EntityVersion]:
    """Versões da entidade, da mais recente para a mais antiga."""
    stmt = (
        select(EntityVersion)
        .where(EntityVersion.entity_type == entity_type, EntityVersion.entity_id == entity_id)
        .order_by(EntityVersion.version.desc())
    )
    return list(db.scalars(stmt))


def version_state(
    db: Session, entity_type: str, entity_id: uuid.UUID, n: int
) -> dict[str, Any] | None:
    """O snapshot `after` da versão `n`, ou None se ela não existe."""
    stmt = select(EntityVersion.after).where(
        EntityVersion.entity_type == entity_type,
        EntityVersion.entity_id == entity_id,
        EntityVersion.version == n,
    )
    return db.scalar(stmt)


def check_version(entity: Any, expected: int, label: str) -> None:
    """Controle otimista (R2). `label` é o sujeito da frase: "Este perfil", "Esta conta".

    O particípio concorda com o pronome: "Esta conta foi alterada…".
    """
    if entity.version != expected:
        feminine = label.split(maxsplit=1)[0].lower() in ("esta", "essa")
        verb = "alterada" if feminine else "alterado"
        raise ApiError(409, "version_conflict",
                       f"{label} foi {verb} por outra pessoa; recarregue")
