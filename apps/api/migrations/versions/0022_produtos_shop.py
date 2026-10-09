"""produtos do TikTok Shop: catálogo do perfil com variantes e ponte com as cenas (spec 012)

Na ordem do data-model:
1. o valor `produto` em `image_kind` (fotos, recortes e flats) e em `anotacao_alvo` (a
   `observacao` dos agentes), fora da transação (`autocommit_block`), como a 0015;
2. os tipos `produto_status` (sem `arquivado`: é efetivo, R4) e `produto_ficha_por`; as tabelas
   `produtos` e `produto_variantes`, com CHECKs e índices;
3. `cenas.produto_id` e `cenas.produto_variante_id` (o catálogo, R13), com os CHECKs
   `ck_cenas_produto_variante` e `ck_cenas_produto_modo` e o índice; os campos leves da 010
   (`produto_nome`, `produto_imagem_id`) continuam.

Downgrade (só dev): recusa se houver produto, cena ligada ao catálogo, imagem `produto` ou
anotação de produto; senão derruba colunas, tabelas e tipos. Os valores `produto` dos enums
`image_kind` e `anotacao_alvo` ficam (como na 0015: recriar o tipo esbarra nos CHECKs que
comparam o alvo com literais, e um valor sem uso é inofensivo). Nenhum objeto do MinIO é tocado.

Revision ID: 0022_produtos_shop
Revises: 0021_geracao_interrupcoes
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_produtos_shop"
down_revision: str | None = "0021_geracao_interrupcoes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *valores: str) -> postgresql.ENUM:
    return postgresql.ENUM(*valores, name=name, create_type=False)


produto_status = _enum("produto_status", "rascunho", "gerando", "revisao", "aprovado")
produto_ficha_por = _enum("produto_ficha_por", "ia", "ia_editada", "humano")
TIPOS = (produto_status, produto_ficha_por)

APROVADO = ("status <> 'aprovado' OR (ficha_por IS NOT NULL AND nome_comercial IS NOT NULL AND "
            "material_en IS NOT NULL AND formato_corte IS NOT NULL AND tamanho_relativo IS NOT "
            "NULL AND descricao_prompt IS NOT NULL AND descricao_venda IS NOT NULL AND "
            "categoria IS NOT NULL AND material_pt IS NOT NULL)")


def _max(coluna: str, n: int, tabela: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{coluna} IS NULL OR char_length({coluna}) <= {n}",
                              name=f"ck_{tabela}_{coluna}")


def upgrade() -> None:
    # 1.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'produto'")
        op.execute("ALTER TYPE anotacao_alvo ADD VALUE IF NOT EXISTS 'produto'")

    # 2.
    bind = op.get_bind()
    for tipo in TIPOS:
        tipo.create(bind, checkfirst=True)
    ts = sa.DateTime(timezone=True)
    op.create_table(
        "produtos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("nome_comercial", sa.Text()),
        sa.Column("categoria", sa.Text()),
        sa.Column("material_en", sa.Text()),
        sa.Column("material_pt", sa.Text()),
        sa.Column("formato_corte", sa.Text()),
        sa.Column("detalhes_visiveis", postgresql.ARRAY(sa.Text()),
                  server_default=sa.text("'{}'"), nullable=False),
        sa.Column("tamanho_relativo", sa.Text()),
        sa.Column("descricao_prompt", sa.Text()),
        sa.Column("cuidados", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("descricao_venda", sa.Text()),
        sa.Column("precisa_flat", sa.Boolean()),
        sa.Column("obs", sa.Text(), server_default="", nullable=False),
        sa.Column("url_loja", sa.Text()),
        sa.Column("status", produto_status, server_default="rascunho", nullable=False),
        sa.Column("ficha_por", produto_ficha_por),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", ts),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 80 AND name = btrim(name)",
                           name="ck_produtos_name"),
        _max("nome_comercial", 120, "produtos"), _max("categoria", 120, "produtos"),
        _max("material_en", 60, "produtos"), _max("material_pt", 60, "produtos"),
        _max("formato_corte", 300, "produtos"), _max("tamanho_relativo", 300, "produtos"),
        _max("descricao_prompt", 500, "produtos"), _max("descricao_venda", 600, "produtos"),
        _max("url_loja", 500, "produtos"),
        sa.CheckConstraint("char_length(obs) <= 2000", name="ck_produtos_obs"),
        sa.CheckConstraint("cardinality(detalhes_visiveis) <= 12 AND "
                           "cardinality(cuidados) <= 12", name="ck_produtos_listas"),
        sa.CheckConstraint("ficha_por IS NULL OR precisa_flat IS NOT NULL",
                           name="ck_produtos_ficha"),
        sa.CheckConstraint(APROVADO, name="ck_produtos_aprovado"),
    )
    op.create_index("ix_produtos_perfil_lista", "produtos",
                    ["perfil_id", "archived_at", sa.text("updated_at DESC"), "id"])
    op.create_index("ix_produtos_perfil_status", "produtos", ["perfil_id", "status"],
                    postgresql_where=sa.text("archived_at IS NULL"))
    op.create_index("ix_produtos_perfil_lower_name", "produtos",
                    ["perfil_id", sa.text("lower(name)")])
    op.create_index("ix_produtos_perfil_lower_nome_comercial", "produtos",
                    ["perfil_id", sa.text("lower(nome_comercial)")])

    op.create_table(
        "produto_variantes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("cor_en", sa.Text()),
        sa.Column("cor_pt", sa.Text()),
        sa.Column("original_image_id", sa.Uuid(), sa.ForeignKey("images.id"), nullable=False,
                  unique=True),
        sa.Column("recorte_image_id", sa.Uuid(), sa.ForeignKey("images.id")),
        sa.Column("flat_image_id", sa.Uuid(), sa.ForeignKey("images.id")),
        sa.Column("flat_geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id")),
        sa.Column("archived_at", ts),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint("position >= 0", name="ck_variantes_position"),
        _max("cor_en", 40, "variantes"), _max("cor_pt", 40, "variantes"),
        sa.CheckConstraint("(flat_image_id IS NULL) = (flat_geracao_id IS NULL)",
                           name="ck_variantes_flat"),
    )
    op.create_index("ix_produto_variantes_produto", "produto_variantes",
                    ["produto_id", "archived_at", "position"])

    # 3.
    op.add_column("cenas", sa.Column("produto_id", sa.Uuid(),
                                     sa.ForeignKey("produtos.id", name="fk_cenas_produto")))
    op.add_column("cenas", sa.Column("produto_variante_id", sa.Uuid(),
                                     sa.ForeignKey("produto_variantes.id",
                                                   name="fk_cenas_produto_variante")))
    op.create_check_constraint("ck_cenas_produto_variante", "cenas",
                               "produto_variante_id IS NULL OR produto_id IS NOT NULL")
    op.create_check_constraint("ck_cenas_produto_modo", "cenas",
                               "produto_id IS NULL OR (produto_nome IS NULL AND "
                               "produto_imagem_id IS NULL)")
    op.create_index("ix_cenas_perfil_catalogo", "cenas", ["perfil_id", "produto_id"])


def downgrade() -> None:
    bind = op.get_bind()
    tem = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM produtos) "
        "OR EXISTS (SELECT 1 FROM cenas WHERE produto_id IS NOT NULL) "
        "OR EXISTS (SELECT 1 FROM images WHERE kind::text = 'produto') "
        "OR EXISTS (SELECT 1 FROM anotacoes WHERE alvo_tipo::text = 'produto')")).scalar()
    if tem:
        raise RuntimeError("downgrade da 0022 recusado: há produtos, imagens ou cenas ligadas")
    op.drop_index("ix_cenas_perfil_catalogo", table_name="cenas")
    op.drop_constraint("ck_cenas_produto_modo", "cenas", type_="check")
    op.drop_constraint("ck_cenas_produto_variante", "cenas", type_="check")
    op.drop_column("cenas", "produto_variante_id")
    op.drop_column("cenas", "produto_id")
    op.drop_table("produto_variantes")
    op.drop_table("produtos")
    for tipo in reversed(TIPOS):
        tipo.drop(bind)
