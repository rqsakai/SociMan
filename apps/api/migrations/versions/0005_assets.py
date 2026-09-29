"""biblioteca de assets: assets, asset_files, image_kind 'avatar'/'imagem' (spec 007)

Cria as tabelas e faz o backfill das imagens de marca d'água e de fundo da 004 (research R2,
SC-003): um asset por imagem, com os mesmos ids de imagem. A 006 encadeia a
`0006_cortes_openshorts` sobre esta (research R11).

Revision ID: 0005_assets
Revises: 0004_fundo_imagem
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from sociman_api.assets.backfill import ACTOR_KIND, backfill

revision: str = "0005_assets"
down_revision: str | None = "0004_fundo_imagem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

asset_tipo = postgresql.ENUM(
    "avatar", "cenario", "fundo", "sticker", "marca_dagua", "imagem", name="asset_tipo",
    create_type=False,
)
asset_file_role = postgresql.ENUM(
    "referencia", "pose", "arquivo", name="asset_file_role", create_type=False
)
ENUMS = (asset_tipo, asset_file_role)


def _ts(name: str, *, nullable: bool = False, now: bool = False) -> sa.Column:
    default = sa.text("now()") if now else None
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _text(name: str, *, nullable: bool = True, default: str | None = None) -> sa.Column:
    return sa.Column(name, sa.Text(), server_default=default, nullable=nullable)


def upgrade() -> None:
    # PG 12+: ADD VALUE roda dentro da transação; os valores novos só não podem ser usados
    # nela (o backfill só usa 'watermark' e 'fundo').
    op.execute("ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'avatar'")
    op.execute("ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'imagem'")
    for enum in ENUMS:
        enum.create(op.get_bind())

    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", asset_tipo, nullable=False),
        _text("name", nullable=False),
        _text("description", nullable=False, default=""),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        _text("prompt"),
        _text("voice_tone"),
        _text("image_rules"),
        sa.Column("primary_file_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _ts("archived_at", nullable=True),
        sa.Column("archived_by", sa.Uuid(), nullable=True),
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _ts("updated_at", now=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(tipo IN ('avatar', 'cenario') OR prompt IS NULL) AND "
            "(tipo = 'avatar' OR (voice_tone IS NULL AND image_rules IS NULL))",
            name="ck_assets_campos_por_tipo",
        ),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.ForeignKeyConstraint(["archived_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assets_perfil_lista", "assets",
        ["perfil_id", "archived_at", sa.literal_column("updated_at DESC"), "id"],
    )
    op.create_index("ix_assets_tags", "assets", ["tags"], postgresql_using="gin")
    op.create_index("ix_assets_perfil_lower_name", "assets",
                    ["perfil_id", sa.literal_column("lower(name)")])

    op.create_table(
        "asset_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("role", asset_file_role, nullable=False),
        _text("look"),
        _text("uso"),
        _text("label"),
        _text("quando_usar"),
        _text("notes", nullable=False, default=""),
        sa.Column("position", sa.Integer(), nullable=False),
        _ts("archived_at", nullable=True),
        sa.Column("archived_by", sa.Uuid(), nullable=True),
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(role = 'pose' OR (label IS NULL AND quando_usar IS NULL)) AND "
            "(role <> 'pose' OR label IS NOT NULL) AND "
            "(role = 'referencia' OR (look IS NULL AND uso IS NULL))",
            name="ck_asset_files_campos_por_papel",
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"]),
        sa.ForeignKeyConstraint(["archived_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_id"),
    )
    op.create_index(
        "uq_asset_files_pose_label", "asset_files",
        ["asset_id", sa.literal_column("lower(label)")], unique=True,
        postgresql_where=sa.text("role = 'pose' AND archived_at IS NULL"),
    )
    op.create_index("ix_asset_files_asset_role_position", "asset_files",
                    ["asset_id", "role", "position"])
    op.create_foreign_key("fk_assets_primary_file_id", "assets", "asset_files",
                          ["primary_file_id"], ["id"])

    backfill(op.get_bind())


def downgrade() -> None:
    conn = op.get_bind()
    # Só volta se a biblioteca tiver apenas o que a migração criou: nada feito pela API
    # (nenhuma versão de asset fora da migração) nem imagem dos kinds novos.
    edited = conn.execute(sa.text(
        "SELECT count(*) FROM entity_versions WHERE entity_type = 'asset' "
        "AND actor_kind <> :actor"), {"actor": ACTOR_KIND}).scalar()
    new_images = conn.execute(sa.text(
        "SELECT count(*) FROM images WHERE kind::text IN ('avatar', 'imagem')")).scalar()
    if edited or new_images:
        raise RuntimeError(
            "0005_assets: a biblioteca tem assets criados ou editados depois da migração "
            f"({edited} versões, {new_images} imagens avatar/imagem); o downgrade perderia dados"
        )
    op.execute("DELETE FROM entity_versions WHERE entity_type = 'asset'")
    op.drop_constraint("fk_assets_primary_file_id", "assets", type_="foreignkey")
    op.drop_table("asset_files")  # os índices caem junto com as tabelas
    op.drop_table("assets")
    for enum in reversed(ENUMS):
        enum.drop(op.get_bind())
    # O PostgreSQL não remove valor de enum: recria o tipo sem 'avatar' e 'imagem'. Nada de
    # objeto no MinIO é apagado.
    op.execute("ALTER TYPE image_kind RENAME TO image_kind_old")
    op.execute("CREATE TYPE image_kind AS ENUM ('logo', 'banner', 'watermark', 'fundo')")
    op.execute(
        "ALTER TABLE images ALTER COLUMN kind TYPE image_kind USING kind::text::image_kind"
    )
    op.execute("DROP TYPE image_kind_old")
