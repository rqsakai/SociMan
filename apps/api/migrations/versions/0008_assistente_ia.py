"""assistente de IA para textos: regras por tipo e registro das chamadas (spec 008-assistente-ia)

- `ia_regras` (nova): a personalização das regras de cada tipo de campo (sem linha = padrão).
- `sugestoes_texto` (006) é **renomeada** para `ia_chamadas` e ampliada, com os mesmos ids: a
  FK `postagens.sugestao_id` segue a tabela. As linhas da 006 viram `postagem.textos` (R3).

Revision ID: 0008_assistente_ia
Revises: 0007_envio_progresso
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_assistente_ia"
down_revision: str | None = "0007_envio_progresso"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DESFECHOS = ("sem_acao", "aplicada", "editada", "descartada", "erro")
ia_desfecho = postgresql.ENUM(*DESFECHOS, name="ia_desfecho", create_type=False)

# Preço do Sonnet 5.5 (US$ por milhão de tokens; `ia/custo.py`, R7) para o custo das linhas da 006.
PRECOS_VERSAO = "2026-09"
SONNET = {"entrada": 2.00, "saida": 10.00, "cache_escrita": 2.50, "cache_leitura": 0.20}

# (antigo, novo): PK e FKs que a 006 criou com o nome da tabela.
CONSTRAINTS = (
    ("sugestoes_texto_pkey", "ia_chamadas_pkey"),
    ("sugestoes_texto_corte_id_fkey", "ia_chamadas_corte_id_fkey"),
    ("sugestoes_texto_created_by_fkey", "ia_chamadas_created_by_fkey"),
)
INDICES = ("ix_ia_chamadas_created", "ix_ia_chamadas_perfil_created",
           "ix_ia_chamadas_tipo_created", "ix_ia_chamadas_sessao")
FKS_NOVAS = (("perfil_id", "perfis"), ("conta_id", "contas"), ("desfecho_por", "users"))


def _array(name: str, item: sa.types.TypeEngine) -> sa.Column:
    return sa.Column(name, postgresql.ARRAY(item), server_default=sa.text("'{}'"),
                     nullable=False)


def _colunas_novas() -> list[sa.Column]:
    return [
        sa.Column("tipo_campo", sa.Text(), nullable=True),  # NOT NULL depois do backfill
        sa.Column("perfil_id", sa.Uuid(), nullable=True),  # idem
        sa.Column("entity_type", sa.Text(), nullable=True),  # idem
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("conta_id", sa.Uuid(), nullable=True),
        sa.Column("sessao_id", sa.Uuid(), nullable=True),
        _array("anteriores", sa.Uuid()),
        _array("aceitos", sa.Text()),
        _array("rejeitados", sa.Text()),
        sa.Column("instrucao", sa.Text(), server_default="", nullable=False),
        sa.Column("entrada", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        _array("contexto_faltante", sa.Text()),
        sa.Column("explicacao", sa.Text(), server_default="", nullable=False),
        _array("avisos", sa.Text()),
        sa.Column("excede", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("model_servido", sa.Text(), nullable=True),
        sa.Column("regras_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("padrao_versao", sa.Integer(), nullable=True),
        sa.Column("erro_status", sa.Integer(), nullable=True),
        sa.Column("cache_creation_tokens", sa.Integer(), nullable=True),
        sa.Column("custo_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("precos_versao", sa.Text(), nullable=True),
        sa.Column("desfecho", ia_desfecho, server_default="sem_acao", nullable=False),
        sa.Column("desfecho_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("desfecho_por", sa.Uuid(), nullable=True),
        sa.Column("aplicada_versao", sa.Integer(), nullable=True),
        sa.Column("itens_aplicados", postgresql.ARRAY(sa.Text()), nullable=True),
    ]


def upgrade() -> None:
    ia_desfecho.create(op.get_bind())

    op.create_table(
        "ia_regras",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tipo_campo", sa.Text(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("padrao_versao", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("texto IS NULL OR char_length(texto) BETWEEN 1 AND 8000",
                           name="ck_ia_regras_texto"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tipo_campo", name="uq_ia_regras_tipo_campo"),
    )

    # sugestoes_texto → ia_chamadas (a FK de postagens.sugestao_id segue a tabela).
    op.rename_table("sugestoes_texto", "ia_chamadas")
    for antigo, novo in CONSTRAINTS:
        op.execute(f"ALTER TABLE ia_chamadas RENAME CONSTRAINT {antigo} TO {novo}")
    op.alter_column("ia_chamadas", "resultado", new_column_name="proposta")
    op.alter_column("ia_chamadas", "corte_id", nullable=True)
    op.alter_column("ia_chamadas", "plataforma", nullable=True)
    for coluna in _colunas_novas():
        op.add_column("ia_chamadas", coluna)
    for coluna, tabela in FKS_NOVAS:
        op.create_foreign_key(f"ia_chamadas_{coluna}_fkey", "ia_chamadas", tabela, [coluna],
                              ["id"])

    # Backfill das linhas da 006 (R3).
    p = SONNET
    op.execute(f"""
        UPDATE ia_chamadas AS c
        SET tipo_campo = 'postagem.textos', entity_type = 'corte', entity_id = c.corte_id,
            perfil_id = k.perfil_id, regras_version = 0,
            desfecho = CASE
                WHEN c.erro_code IS NOT NULL THEN 'erro'
                WHEN c.id IN (SELECT sugestao_id FROM postagens WHERE sugestao_id IS NOT NULL)
                    THEN 'aplicada'
                ELSE 'sem_acao' END::ia_desfecho,
            custo_usd = CASE
                WHEN coalesce(c.input_tokens, c.output_tokens, c.cache_read_tokens) IS NULL
                    THEN NULL
                ELSE round((coalesce(c.input_tokens, 0) * {p['entrada']}
                            + coalesce(c.output_tokens, 0) * {p['saida']}
                            + coalesce(c.cache_read_tokens, 0) * {p['cache_leitura']}
                           ) / 1000000.0, 6) END,
            precos_versao = CASE
                WHEN coalesce(c.input_tokens, c.output_tokens, c.cache_read_tokens) IS NULL
                    THEN NULL
                ELSE '{PRECOS_VERSAO}' END
        FROM cortes AS k
        WHERE k.id = c.corte_id
    """)
    for coluna in ("tipo_campo", "perfil_id", "entity_type"):
        op.alter_column("ia_chamadas", coluna, nullable=False)
    op.create_check_constraint("ck_ia_chamadas_erro_desfecho", "ia_chamadas",
                               "(erro_code IS NOT NULL) = (desfecho = 'erro')")
    op.create_index("ix_ia_chamadas_created", "ia_chamadas",
                    [sa.literal_column("created_at DESC"), "id"])
    op.create_index("ix_ia_chamadas_perfil_created", "ia_chamadas",
                    ["perfil_id", sa.literal_column("created_at DESC")])
    op.create_index("ix_ia_chamadas_tipo_created", "ia_chamadas",
                    ["tipo_campo", sa.literal_column("created_at DESC")])
    op.create_index("ix_ia_chamadas_sessao", "ia_chamadas", ["sessao_id"],
                    postgresql_where=sa.text("sessao_id IS NOT NULL"))


def downgrade() -> None:
    """Só dev: **apaga** as chamadas que não são da 006 (outros tipos de campo) e as regras
    personalizadas, e volta o nome, as colunas e as restrições da `sugestoes_texto`."""
    op.execute("""
        UPDATE postagens SET sugestao_id = NULL
        WHERE sugestao_id IN (SELECT id FROM ia_chamadas
                              WHERE tipo_campo <> 'postagem.textos' OR corte_id IS NULL
                                 OR plataforma IS NULL)
    """)
    op.execute("DELETE FROM ia_chamadas WHERE tipo_campo <> 'postagem.textos' "
               "OR corte_id IS NULL OR plataforma IS NULL")

    for nome in INDICES:
        op.drop_index(nome, table_name="ia_chamadas")
    op.drop_constraint("ck_ia_chamadas_erro_desfecho", "ia_chamadas", type_="check")
    for coluna, _ in FKS_NOVAS:
        op.drop_constraint(f"ia_chamadas_{coluna}_fkey", "ia_chamadas", type_="foreignkey")
    for coluna in reversed(_colunas_novas()):
        op.drop_column("ia_chamadas", coluna.name)
    op.alter_column("ia_chamadas", "plataforma", nullable=False)
    op.alter_column("ia_chamadas", "corte_id", nullable=False)
    op.alter_column("ia_chamadas", "proposta", new_column_name="resultado")
    for antigo, novo in CONSTRAINTS:
        op.execute(f"ALTER TABLE ia_chamadas RENAME CONSTRAINT {novo} TO {antigo}")
    op.rename_table("ia_chamadas", "sugestoes_texto")

    op.drop_table("ia_regras")
    ia_desfecho.drop(op.get_bind())
