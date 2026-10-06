"""histórico do TikTok Studio: importações e dias importados (spec 020)

Na ordem do data-model:
1. tipo `studio_importacao_estado`;
2. `metricas_studio_importacoes` (versionada) e `metricas_studio_dias` (só inserção), com os
   CHECKs e índices;
3. o trigger `metricas_studio_so_insercao` em `metricas_studio_dias`, que reaproveita a função
   `metricas_recusa_mudanca()` da 0011 (o `TRUNCATE` dos testes e do `reset-db` continua).

Sem backfill: antes da 020 não havia importação. Os arquivos enviados nunca são gravados (só os
números de cada dia).

Revision ID: 0013_historico_studio
Revises: 0012_guia_comunicacao
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_historico_studio"
down_revision: str | None = "0012_guia_comunicacao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

estado = postgresql.ENUM("ativa", "desfeita", name="studio_importacao_estado",
                         create_type=False)
NAO_NEGATIVAS = ("views", "visitas_perfil", "likes", "comments", "shares", "seguidores")


def upgrade() -> None:
    # 1.
    estado.create(op.get_bind())

    # 2.
    ts = sa.DateTime(timezone=True)
    op.create_table(
        "metricas_studio_importacoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("serie_id", sa.Uuid(), sa.ForeignKey("metricas_series.id"), nullable=False),
        sa.Column("secoes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("sha_visao_geral", sa.Text(), nullable=True),
        sa.Column("sha_seguidores", sa.Text(), nullable=True),
        sa.Column("periodo_de", sa.Date(), nullable=False),
        sa.Column("periodo_ate", sa.Date(), nullable=False),
        sa.Column("ano_origem", sa.Text(), nullable=False),
        sa.Column("contagens", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("nomes_arquivos", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("estado", estado, server_default="ativa", nullable=False),
        sa.Column("criada_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("criada_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("desfeita_em", ts, nullable=True),
        sa.Column("desfeita_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("cardinality(secoes) BETWEEN 1 AND 2 "
                           "AND secoes <@ ARRAY['visao_geral','seguidores']::text[]",
                           name="ck_studio_imp_secoes"),
        sa.CheckConstraint("(('visao_geral' = ANY(secoes)) = (sha_visao_geral IS NOT NULL)) "
                           "AND (('seguidores' = ANY(secoes)) = (sha_seguidores IS NOT NULL))",
                           name="ck_studio_imp_sha"),
        sa.CheckConstraint("(estado = 'desfeita') = "
                           "(desfeita_em IS NOT NULL AND desfeita_por IS NOT NULL)",
                           name="ck_studio_imp_desfeita"),
        sa.CheckConstraint("periodo_de <= periodo_ate", name="ck_studio_imp_periodo"),
        sa.CheckConstraint("ano_origem IN ('nome_zip','deduzido','misto')",
                           name="ck_studio_imp_ano"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_studio_imp_serie", "metricas_studio_importacoes",
                    ["serie_id", "estado", "criada_em", "id"])
    op.create_index("ix_studio_imp_sha_vg", "metricas_studio_importacoes",
                    ["serie_id", "sha_visao_geral"],
                    postgresql_where=sa.text("estado = 'ativa'"))
    op.create_index("ix_studio_imp_sha_seg", "metricas_studio_importacoes",
                    ["serie_id", "sha_seguidores"],
                    postgresql_where=sa.text("estado = 'ativa'"))

    op.create_table(
        "metricas_studio_dias",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("importacao_id", sa.Uuid(), sa.ForeignKey("metricas_studio_importacoes.id"),
                  nullable=False),
        sa.Column("serie_id", sa.Uuid(), sa.ForeignKey("metricas_series.id"), nullable=False),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("tem_visao_geral", sa.Boolean(), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("visitas_perfil", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("tem_seguidores", sa.Boolean(), nullable=False),
        sa.Column("seguidores", sa.BigInteger(), nullable=True),
        sa.Column("seguidores_dif", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("(tem_visao_geral OR tem_seguidores) "
                           "AND tem_visao_geral = (views IS NOT NULL) "
                           "AND tem_seguidores = (seguidores IS NOT NULL)",
                           name="ck_studio_dias_secao"),
        sa.CheckConstraint(" AND ".join(f"({c} IS NULL OR {c} >= 0)" for c in NAO_NEGATIVAS),
                           name="ck_studio_dias_naoneg"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("importacao_id", "dia", name="uq_studio_dias_imp_dia"),
    )
    op.create_index("ix_studio_dias_serie_dia", "metricas_studio_dias", ["serie_id", "dia"])

    # 3.
    op.execute("CREATE TRIGGER metricas_studio_so_insercao BEFORE UPDATE OR DELETE ON "
               "metricas_studio_dias FOR EACH ROW EXECUTE FUNCTION metricas_recusa_mudanca()")


def downgrade() -> None:
    """Só dev. A função `metricas_recusa_mudanca` fica (é da 0011), e as versões
    `studio_importacao` em `entity_versions` também (histórico imutável, sem FK)."""
    op.execute("DROP TRIGGER metricas_studio_so_insercao ON metricas_studio_dias")
    op.drop_table("metricas_studio_dias")  # os índices vão junto
    op.drop_table("metricas_studio_importacoes")
    estado.drop(op.get_bind())
