"""Modelos de auth (data-model.md): usuários, tokens de uso único e eventos de segurança."""

import enum
import uuid
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.db import Base


class UserRole(enum.StrEnum):
    dono = "dono"
    membro = "membro"


class TokenPurpose(enum.StrEnum):
    verify_email = "verify_email"
    reset_password = "reset_password"


class AuditMixin:
    """Autoria (FR-016): preenchida a partir do `Actor` da requisição; null = `system:cli`."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class User(AuditMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # nunca expõe o hash
        return f"User(id={self.id}, email={self.email!r}, role={self.role})"


class OneTimeToken(Base):
    __tablename__ = "one_time_tokens"
    __table_args__ = (Index("ix_one_time_tokens_user_purpose", "user_id", "purpose"),)

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    purpose: Mapped[TokenPurpose] = mapped_column(
        Enum(TokenPurpose, name="token_purpose"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SecurityEvent(Base):
    """Imutável: a aplicação só faz INSERT. `details` nunca guarda senha, token nem hash."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)  # ok | denied
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)  # user | anonymous | system:cli
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    ip: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


Index("ix_security_events_occurred_at", SecurityEvent.occurred_at.desc())
Index(
    "ix_security_events_subject_occurred",
    SecurityEvent.subject_user_id,
    SecurityEvent.occurred_at.desc(),
)
Index("ix_security_events_type_occurred", SecurityEvent.type, SecurityEvent.occurred_at.desc())
