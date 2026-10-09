"""auth: users, one_time_tokens e security_events (spec 001-auth)

Revision ID: 0001_auth
Revises:
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_auth"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM("dono", "membro", name="user_role", create_type=False)
token_purpose = postgresql.ENUM(
    "verify_email", "reset_password", name="token_purpose", create_type=False
)


def _ts(name: str, *, nullable: bool = False, now: bool = False) -> sa.Column:
    default = sa.text("now()") if now else None
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def upgrade() -> None:
    user_role.create(op.get_bind())
    token_purpose.create(op.get_bind())

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _ts("email_verified_at", nullable=True),
        sa.Column(
            "must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        _ts("password_changed_at"),
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _ts("updated_at", now=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "one_time_tokens",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", token_purpose, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        _ts("expires_at"),
        _ts("used_at", nullable=True),
        _ts("created_at", now=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_one_time_tokens_user_purpose", "one_time_tokens", ["user_id", "purpose"])

    op.create_table(
        "security_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        _ts("occurred_at", now=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_kind", sa.Text(), nullable=False),
        sa.Column("subject_user_id", sa.Uuid(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    occurred_desc = sa.literal_column("occurred_at DESC")
    op.create_index("ix_security_events_occurred_at", "security_events", [occurred_desc])
    op.create_index(
        "ix_security_events_subject_occurred", "security_events", ["subject_user_id", occurred_desc]
    )
    op.create_index("ix_security_events_type_occurred", "security_events", ["type", occurred_desc])


def downgrade() -> None:
    op.drop_table("security_events")  # os índices caem junto com a tabela
    op.drop_table("one_time_tokens")
    op.drop_table("users")
    token_purpose.drop(op.get_bind())
    user_role.drop(op.get_bind())
