"""fundo com imagem: image_kind 'fundo' (spec 004-kit-de-marca, FR-005a e FR-005b)

Os campos novos do gancho e do card final (`fundo_tipo`, `fundo_imagem_id`, `opacidade_fundo`)
ficam no JSONB de `brand_kits` e têm padrão no schema: os kits já salvos continuam válidos sem
migração de dados.

Revision ID: 0004_fundo_imagem
Revises: 0003_kit_de_marca
Create Date: 2026-09-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_fundo_imagem"
down_revision: str | None = "0003_kit_de_marca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PG 12+: ADD VALUE roda dentro da transação; o valor novo só não pode ser usado nela.
    op.execute("ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'fundo'")


def downgrade() -> None:
    # O PostgreSQL não remove valor de enum: recria o tipo sem 'fundo'. Se existir imagem de
    # fundo, o cast falha e o downgrade para (nada é apagado).
    op.execute("ALTER TYPE image_kind RENAME TO image_kind_old")
    op.execute("CREATE TYPE image_kind AS ENUM ('logo', 'banner', 'watermark')")
    op.execute(
        "ALTER TABLE images ALTER COLUMN kind TYPE image_kind USING kind::text::image_kind"
    )
    op.execute("DROP TYPE image_kind_old")
