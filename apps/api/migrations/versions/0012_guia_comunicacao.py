"""guia de comunicação por perfil e conta (spec 017)

Na ordem do data-model:
1. tipo `guia_emojis`;
2. tabela `ia_guias` (uma linha por perfil com `conta_id IS NULL`, no máximo uma por conta), com
   os CHECKs baratos (os limites por item e o total ficam no service, R2);
3. os 2 índices únicos parciais;
4. 4 colunas em `ia_chamadas` (`guia_perfil_version`, `guia_conta_version`, `guia_rascunho`,
   `proibidas`) e o CHECK `ck_ia_chamadas_guia_rascunho`.

Sem backfill: antes da 017 não havia guia (as chamadas antigas ficam com NULL e `'{}'`).

Revision ID: 0012_guia_comunicacao
Revises: 0011_metricas_tiktok
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_guia_comunicacao"
down_revision: str | None = "0011_metricas_tiktok"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

guia_emojis = postgresql.ENUM("nao", "moderado", "livre", name="guia_emojis", create_type=False)
COLUNAS_CHAMADAS = ("guia_perfil_version", "guia_conta_version", "guia_rascunho", "proibidas")


def _lista(name: str) -> sa.Column:
    return sa.Column(name, postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                     nullable=False)


def upgrade() -> None:
    # 1.
    guia_emojis.create(op.get_bind())

    # 2.
    ts = sa.DateTime(timezone=True)
    op.create_table(
        "ia_guias",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("conta_id", sa.Uuid(), sa.ForeignKey("contas.id"), nullable=True),
        sa.Column("tom", sa.Text(), server_default="", nullable=False),
        _lista("faca"),
        _lista("nao_faca"),
        _lista("vocabulario"),
        _lista("proibidas"),
        sa.Column("emojis", guia_emojis, nullable=True),
        _lista("emojis_preferidos"),
        _lista("hashtags_fixas"),
        sa.Column("max_hashtags_fixas", sa.Integer(), nullable=True),
        sa.Column("exemplos", postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("char_length(tom) <= 500", name="ck_ia_guias_tom"),
        sa.CheckConstraint("cardinality(faca) <= 10", name="ck_ia_guias_faca"),
        sa.CheckConstraint("cardinality(nao_faca) <= 10", name="ck_ia_guias_nao_faca"),
        sa.CheckConstraint("cardinality(vocabulario) <= 30", name="ck_ia_guias_vocabulario"),
        sa.CheckConstraint("cardinality(proibidas) <= 30", name="ck_ia_guias_proibidas"),
        sa.CheckConstraint("cardinality(emojis_preferidos) <= 10",
                           name="ck_ia_guias_emojis_preferidos"),
        sa.CheckConstraint("cardinality(hashtags_fixas) <= 8 AND (conta_id IS NOT NULL OR "
                           "cardinality(hashtags_fixas) <= 5)",
                           name="ck_ia_guias_hashtags_fixas"),
        sa.CheckConstraint("max_hashtags_fixas IS NULL OR (conta_id IS NOT NULL AND "
                           "max_hashtags_fixas BETWEEN 0 AND 8)",
                           name="ck_ia_guias_max_hashtags_fixas"),
        sa.CheckConstraint("jsonb_array_length(exemplos) <= 5", name="ck_ia_guias_exemplos"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3.
    op.create_index("uq_ia_guias_perfil", "ia_guias", ["perfil_id"], unique=True,
                    postgresql_where=sa.text("conta_id IS NULL"))
    op.create_index("uq_ia_guias_conta", "ia_guias", ["conta_id"], unique=True,
                    postgresql_where=sa.text("conta_id IS NOT NULL"))

    # 4.
    op.add_column("ia_chamadas", sa.Column("guia_perfil_version", sa.Integer(), nullable=True))
    op.add_column("ia_chamadas", sa.Column("guia_conta_version", sa.Integer(), nullable=True))
    op.add_column("ia_chamadas", sa.Column("guia_rascunho", sa.Text(), nullable=True))
    op.add_column("ia_chamadas", _lista("proibidas"))
    op.create_check_constraint("ck_ia_chamadas_guia_rascunho", "ia_chamadas",
                               "guia_rascunho IS NULL OR guia_rascunho IN ('perfil', 'conta')")


def downgrade() -> None:
    """Só dev: some a tabela dos guias e as 4 colunas das chamadas. As versões `ia_guia` em
    `entity_versions` ficam (são inofensivas)."""
    op.drop_constraint("ck_ia_chamadas_guia_rascunho", "ia_chamadas", type_="check")
    for coluna in reversed(COLUNAS_CHAMADAS):
        op.drop_column("ia_chamadas", coluna)
    op.drop_index("uq_ia_guias_conta", table_name="ia_guias")
    op.drop_index("uq_ia_guias_perfil", table_name="ia_guias")
    op.drop_table("ia_guias")
    guia_emojis.drop(op.get_bind())
