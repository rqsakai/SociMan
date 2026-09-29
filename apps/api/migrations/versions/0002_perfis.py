"""perfis: perfis, contas, images e entity_versions (spec 003-contas-sociais)

Revision ID: 0002_perfis
Revises: 0001_auth
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_perfis"
down_revision: str | None = "0001_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

perfil_status = postgresql.ENUM(
    "em_preparacao", "ativo", "pausado", name="perfil_status", create_type=False
)
platform = postgresql.ENUM(
    "tiktok", "youtube", "instagram", "kwai", "facebook", "x", "outra",
    name="platform", create_type=False,
)
conta_status = postgresql.ENUM(
    "planejada", "ativa", "pausada", "encerrada", name="conta_status", create_type=False
)
image_kind = postgresql.ENUM("logo", "banner", name="image_kind", create_type=False)
ENUMS = (perfil_status, platform, conta_status, image_kind)


def _ts(name: str, *, nullable: bool = False, now: bool = False) -> sa.Column:
    default = sa.text("now()") if now else None
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _text(name: str, default: str | None = None) -> sa.Column:
    return sa.Column(name, sa.Text(), server_default=default, nullable=False)


def _versioned_and_audit() -> list:
    """`version`, arquivamento e AuditMixin, comuns a perfis e contas."""
    return [
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _ts("archived_at", nullable=True),
        sa.Column("archived_by", sa.Uuid(), nullable=True),
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _ts("updated_at", now=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["archived_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
    ]


def upgrade() -> None:
    for enum in ENUMS:
        enum.create(op.get_bind())

    op.create_table(
        "entity_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        _text("entity_type"),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        _text("action"),
        _text("actor_kind"),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        _ts("occurred_at", now=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_fields", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "version", name="uq_entity_versions_entity_version"
        ),
    )
    op.create_index(
        "ix_entity_versions_entity_version",
        "entity_versions",
        ["entity_type", "entity_id", sa.literal_column("version DESC")],
    )

    # As FKs de logo/banner → images entram depois de `images` existir (ciclo de FKs).
    op.create_table(
        "perfis",
        sa.Column("id", sa.Uuid(), nullable=False),
        _text("slug"),
        _text("name"),
        _text("niche", ""),
        _text("bio", ""),
        _text("language", "pt-BR"),
        sa.Column("status", perfil_status, server_default="em_preparacao", nullable=False),
        sa.Column("logo_image_id", sa.Uuid(), nullable=True),
        sa.Column("banner_image_id", sa.Uuid(), nullable=True),
        *_versioned_and_audit(),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) BETWEEN 2 AND 60",
            name="ck_perfis_slug_format",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_perfis_archived_status", "perfis", ["archived_at", "status"])
    op.create_index("ix_perfis_lower_name", "perfis", [sa.literal_column("lower(name)")])

    op.create_table(
        "contas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        sa.Column("platform", platform, nullable=False),
        _text("platform_name", ""),
        _text("handle"),
        _text("url"),
        sa.Column("status", conta_status, server_default="planejada", nullable=False),
        _text("notes", ""),
        *_versioned_and_audit(),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform", "platform_name", "handle", name="uq_contas_platform_handle"
        ),
    )
    op.create_index(
        "uq_contas_perfil_platform_ativa",
        "contas",
        ["perfil_id", "platform", "platform_name"],
        unique=True,
        postgresql_where=sa.text("status = 'ativa' AND archived_at IS NULL"),
    )

    op.create_table(
        "images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        sa.Column("kind", image_kind, nullable=False),
        _text("object_key"),
        _text("content_type"),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        _text("sha256"),
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_foreign_key(
        "fk_perfis_logo_image_id", "perfis", "images", ["logo_image_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_perfis_banner_image_id", "perfis", "images", ["banner_image_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_perfis_banner_image_id", "perfis", type_="foreignkey")
    op.drop_constraint("fk_perfis_logo_image_id", "perfis", type_="foreignkey")
    op.drop_table("images")  # os índices caem junto com as tabelas
    op.drop_table("contas")
    op.drop_table("perfis")
    op.drop_table("entity_versions")
    for enum in reversed(ENUMS):
        enum.drop(op.get_bind())
