"""União dos heads da 029 (`0024_ai_studio`) e da 026 (`0025_mercado_shop`) e a ligação da 026
com a 012 (spec 026, quickstart §5): `produtos.mercado_produto_id` (FK → `mercado_produtos`,
índice parcial) e a FK `mercado_interesses.produto_id → produtos.id`.

Idempotente: num banco onde a `0025` já encontrou a tabela `produtos` (e criou coluna e FKs),
nada é refeito. Downgrade só tira o que esta migration criou.

Revision ID: 0026_uniao_mercado
Revises: 0024_ai_studio, 0025_mercado_shop
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_uniao_mercado"
down_revision: str | Sequence[str] | None = ("0024_ai_studio", "0025_mercado_shop")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _coluna_existe(tabela: str, coluna: str) -> bool:
    return any(c["name"] == coluna for c in sa.inspect(op.get_bind()).get_columns(tabela))


def _fk_existe(tabela: str, nome: str) -> bool:
    return any(fk["name"] == nome for fk in sa.inspect(op.get_bind()).get_foreign_keys(tabela))


def _indice_existe(tabela: str, nome: str) -> bool:
    return any(i["name"] == nome for i in sa.inspect(op.get_bind()).get_indexes(tabela))


def upgrade() -> None:
    if not _coluna_existe("produtos", "mercado_produto_id"):
        op.add_column("produtos", sa.Column("mercado_produto_id", sa.Uuid(), nullable=True))
    if not _fk_existe("produtos", "fk_produtos_mercado_produto"):
        op.create_foreign_key("fk_produtos_mercado_produto", "produtos", "mercado_produtos",
                              ["mercado_produto_id"], ["id"])
    if not _indice_existe("produtos", "ix_produtos_mercado_produto"):
        op.create_index("ix_produtos_mercado_produto", "produtos", ["mercado_produto_id"],
                        postgresql_where=sa.text("mercado_produto_id IS NOT NULL"))
    if not _fk_existe("mercado_interesses", "fk_mercado_interesses_produto"):
        op.create_foreign_key("fk_mercado_interesses_produto", "mercado_interesses", "produtos",
                              ["produto_id"], ["id"])


def downgrade() -> None:
    if _fk_existe("mercado_interesses", "fk_mercado_interesses_produto"):
        op.drop_constraint("fk_mercado_interesses_produto", "mercado_interesses", type_="foreignkey")
    if _indice_existe("produtos", "ix_produtos_mercado_produto"):
        op.drop_index("ix_produtos_mercado_produto", table_name="produtos")
    if _fk_existe("produtos", "fk_produtos_mercado_produto"):
        op.drop_constraint("fk_produtos_mercado_produto", "produtos", type_="foreignkey")
    if _coluna_existe("produtos", "mercado_produto_id"):
        op.drop_column("produtos", "mercado_produto_id")
