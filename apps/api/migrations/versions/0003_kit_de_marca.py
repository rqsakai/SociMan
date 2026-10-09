"""kit de marca: brand_kits, brand_fonts, cortes e image_kind 'watermark' (spec 004-kit-de-marca)

Revision ID: 0003_kit_de_marca
Revises: 0002_perfis
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_kit_de_marca"
down_revision: str | None = "0002_perfis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

font_format = postgresql.ENUM("ttf", "otf", name="font_format", create_type=False)
corte_status = postgresql.ENUM(
    "na_fila", "processando", "pronto", "falhou", name="corte_status", create_type=False
)
ENUMS = (font_format, corte_status)


def _ts(name: str, *, nullable: bool = False, now: bool = False) -> sa.Column:
    default = sa.text("now()") if now else None
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _text(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _jsonb(name: str, default: str | None = None) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(astext_type=sa.Text()),
                     server_default=sa.text(default) if default else None, nullable=False)


def _version() -> sa.Column:
    return sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False)


def _audit() -> list:
    return [
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _ts("updated_at", now=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
    ]


def upgrade() -> None:
    # PG 12+: ADD VALUE roda dentro da transação; o valor novo só não pode ser usado nela.
    op.execute("ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'watermark'")
    for enum in ENUMS:
        enum.create(op.get_bind())

    op.create_table(
        "brand_kits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        _jsonb("palette"),
        _jsonb("caption"),
        _jsonb("hook"),
        _jsonb("watermark"),
        _jsonb("end_card"),
        _jsonb("catchphrases", "'[]'::jsonb"),
        _jsonb("series", "'[]'::jsonb"),
        _version(),
        *_audit(),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("perfil_id"),
    )

    op.create_table(
        "brand_fonts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        _text("name"),
        _text("family"),
        _text("style"),
        sa.Column("format", font_format, nullable=False),
        _text("object_key"),
        sa.Column("bytes", sa.Integer(), nullable=False),
        _text("sha256"),
        _version(),
        _ts("archived_at", nullable=True),
        sa.Column("archived_by", sa.Uuid(), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(["archived_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        "uq_brand_fonts_perfil_lower_name",
        "brand_fonts",
        ["perfil_id", sa.literal_column("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "cortes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        _text("hook_text"),
        sa.Column("kit_version", sa.Integer(), nullable=False),
        _jsonb("kit_tokens"),
        sa.Column("status", corte_status, server_default="na_fila", nullable=False),
        sa.Column("progress", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        _text("error_code", nullable=True),
        _text("error_message", nullable=True),
        _ts("queued_at", now=True),
        _ts("started_at", nullable=True),
        _ts("heartbeat_at", nullable=True),
        _ts("finished_at", nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        _text("original_filename"),
        _text("original_key"),
        _text("original_content_type"),
        sa.Column("original_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fps", sa.Numeric(6, 3), nullable=False),
        _text("video_codec"),
        _text("audio_codec", nullable=True),
        _text("original_sha256"),
        _text("result_key", nullable=True),
        sa.Column("result_bytes", sa.BigInteger(), nullable=True),
        _text("poster_key", nullable=True),
        _version(),
        *_audit(),
        sa.CheckConstraint("status <> 'pronto' OR result_key IS NOT NULL",
                           name="ck_cortes_pronto_result"),
        sa.CheckConstraint("status <> 'falhou' OR error_message IS NOT NULL",
                           name="ck_cortes_falhou_message"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_cortes_progress"),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("original_key"),
        sa.UniqueConstraint("result_key"),
    )
    op.create_index("ix_cortes_status_queued_at", "cortes", ["status", "queued_at"])
    op.create_index(
        "ix_cortes_perfil_created_at", "cortes",
        ["perfil_id", sa.literal_column("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("cortes")  # os índices caem junto com as tabelas
    op.drop_table("brand_fonts")
    op.drop_table("brand_kits")
    for enum in reversed(ENUMS):
        enum.drop(op.get_bind())
    # O PostgreSQL não remove valor de enum: recria o tipo sem 'watermark'. Se existir imagem
    # de marca d'água, o cast falha e o downgrade para (nada é apagado).
    op.execute("ALTER TYPE image_kind RENAME TO image_kind_old")
    op.execute("CREATE TYPE image_kind AS ENUM ('logo', 'banner')")
    op.execute(
        "ALTER TABLE images ALTER COLUMN kind TYPE image_kind USING kind::text::image_kind"
    )
    op.execute("DROP TYPE image_kind_old")
