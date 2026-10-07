"""público do TikTok Studio: gênero, territórios, atividade e espectadores (spec 022)

Na ordem do data-model:
1. as 7 colunas novas em `metricas_studio_importacoes` (`secoes_vazias` com default `'{}'`);
2. a troca de `ck_studio_imp_secoes` (1 a 6 seções), os CHECKs `ck_studio_imp_sha_publico`,
   `ck_studio_imp_foto` e `ck_studio_imp_vazias`, e os 4 índices parciais de SHA;
3. as 3 tabelas só de inserção (`metricas_studio_distribuicoes`, `metricas_studio_atividade` e
   `metricas_studio_espectadores`), com os CHECKs, os índices e os triggers
   `metricas_studio_{dist,atv,esp}_so_insercao`, que reaproveitam a função
   `metricas_recusa_mudanca()` da 0011 (o `TRUNCATE` dos testes e do `reset-db` continua).

Sem backfill: as importações da 020 ficam válidas com as colunas nulas e `secoes_vazias = '{}'`.

Revision ID: 0017_publico
Revises: 0016_importacao
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_publico"
down_revision: str | None = "0016_importacao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMP = "metricas_studio_importacoes"
PUBLICO = ("genero", "territorios", "atividade", "espectadores")
SECOES = ("visao_geral", "seguidores", *PUBLICO)
INDICES = {"genero": "gen", "territorios": "ter", "atividade": "atv", "espectadores": "esp"}
TRIGGERS = {"metricas_studio_distribuicoes": "metricas_studio_dist_so_insercao",
            "metricas_studio_atividade": "metricas_studio_atv_so_insercao",
            "metricas_studio_espectadores": "metricas_studio_esp_so_insercao"}


def _array(valores: Sequence[str]) -> str:
    return "ARRAY[" + ",".join(f"'{v}'" for v in valores) + "]::text[]"


def _fks() -> list[sa.Column]:
    return [sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("importacao_id", sa.Uuid(), sa.ForeignKey(f"{IMP}.id"), nullable=False),
            sa.Column("serie_id", sa.Uuid(), sa.ForeignKey("metricas_series.id"),
                      nullable=False)]


def upgrade() -> None:
    # 1.
    for secao in PUBLICO:
        op.add_column(IMP, sa.Column(f"sha_{secao}", sa.Text(), nullable=True))
    op.add_column(IMP, sa.Column("data_foto", sa.Date(), nullable=True))
    op.add_column(IMP, sa.Column("data_foto_origem", sa.Text(), nullable=True))
    op.add_column(IMP, sa.Column("secoes_vazias", postgresql.ARRAY(sa.Text()),
                                 server_default=sa.text("'{}'::text[]"), nullable=False))

    # 2.
    op.drop_constraint("ck_studio_imp_secoes", IMP, type_="check")
    op.create_check_constraint("ck_studio_imp_secoes", IMP,
                               f"cardinality(secoes) BETWEEN 1 AND 6 AND secoes <@ {_array(SECOES)}")
    op.create_check_constraint("ck_studio_imp_sha_publico", IMP, " AND ".join(
        f"(('{s}' = ANY(secoes)) = (sha_{s} IS NOT NULL))" for s in PUBLICO))
    op.create_check_constraint(
        "ck_studio_imp_foto", IMP,
        "((('genero' = ANY(secoes)) OR ('territorios' = ANY(secoes))) = (data_foto IS NOT NULL)) "
        "AND ((data_foto IS NULL) = (data_foto_origem IS NULL)) "
        "AND (data_foto_origem IS NULL OR data_foto_origem IN ('historico','importacao'))")
    op.create_check_constraint("ck_studio_imp_vazias", IMP,
                               f"secoes_vazias <@ {_array(PUBLICO)} "
                               "AND NOT (secoes && secoes_vazias)")
    for secao, sufixo in INDICES.items():
        op.create_index(f"ix_studio_imp_sha_{sufixo}", IMP, ["serie_id", f"sha_{secao}"],
                        postgresql_where=sa.text("estado = 'ativa'"))

    # 3.
    op.create_table(
        "metricas_studio_distribuicoes",
        *_fks(),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("data_foto", sa.Date(), nullable=False),
        sa.Column("rotulo", sa.Text(), nullable=False),
        sa.Column("pct", sa.Numeric(6, 3), nullable=True),
        sa.CheckConstraint("tipo IN ('genero','territorio')", name="ck_studio_dist_tipo"),
        sa.CheckConstraint("tipo <> 'genero' OR rotulo IN ('masculino','feminino','outro')",
                           name="ck_studio_dist_genero"),
        sa.CheckConstraint("pct IS NULL OR pct BETWEEN 0 AND 100", name="ck_studio_dist_pct"),
        sa.CheckConstraint("length(rotulo) BETWEEN 1 AND 64", name="ck_studio_dist_rotulo"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("importacao_id", "tipo", "rotulo", name="uq_studio_dist_imp"),
    )
    op.create_index("ix_studio_dist_serie", "metricas_studio_distribuicoes",
                    ["serie_id", "tipo", "data_foto"])

    op.create_table(
        "metricas_studio_atividade",
        *_fks(),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("hora", sa.SmallInteger(), nullable=False),
        sa.Column("ativos", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("hora BETWEEN 0 AND 23", name="ck_studio_atv_hora"),
        sa.CheckConstraint("ativos IS NULL OR ativos >= 0", name="ck_studio_atv_naoneg"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("importacao_id", "dia", "hora", name="uq_studio_atv_imp"),
    )
    op.create_index("ix_studio_atv_serie", "metricas_studio_atividade",
                    ["serie_id", "dia", "hora"])

    op.create_table(
        "metricas_studio_espectadores",
        *_fks(),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=True),
        sa.Column("novos", sa.BigInteger(), nullable=True),
        sa.Column("recorrentes", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(" AND ".join(f"({c} IS NULL OR {c} >= 0)"
                                        for c in ("total", "novos", "recorrentes")),
                           name="ck_studio_esp_naoneg"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("importacao_id", "dia", name="uq_studio_esp_imp"),
    )
    op.create_index("ix_studio_esp_serie", "metricas_studio_espectadores", ["serie_id", "dia"])

    for tabela, trigger in TRIGGERS.items():
        op.execute(f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {tabela} "
                   "FOR EACH ROW EXECUTE FUNCTION metricas_recusa_mudanca()")


def downgrade() -> None:
    """Só dev. Recusa se alguma importação tem seção de público (o downgrade não apaga o
    histórico); a função `metricas_recusa_mudanca` fica (é da 0011)."""
    publico = op.get_bind().execute(sa.text(
        f"SELECT count(*) FROM {IMP} WHERE secoes && {_array(PUBLICO)} "
        "OR cardinality(secoes_vazias) > 0")).scalar()
    if publico:
        raise RuntimeError(f"0017_publico: {publico} importação(ões) do Studio têm seções de "
                           "público; o downgrade apagaria o histórico. Nada foi alterado.")
    # 1.
    for tabela, trigger in TRIGGERS.items():
        op.execute(f"DROP TRIGGER {trigger} ON {tabela}")
        op.drop_table(tabela)  # os índices vão junto
    # 2.
    for sufixo in INDICES.values():
        op.drop_index(f"ix_studio_imp_sha_{sufixo}", table_name=IMP)
    for nome in ("ck_studio_imp_vazias", "ck_studio_imp_foto", "ck_studio_imp_sha_publico",
                 "ck_studio_imp_secoes"):
        op.drop_constraint(nome, IMP, type_="check")
    # 3.
    op.create_check_constraint("ck_studio_imp_secoes", IMP,
                               "cardinality(secoes) BETWEEN 1 AND 2 "
                               "AND secoes <@ ARRAY['visao_geral','seguidores']::text[]")
    # 4.
    for coluna in ("secoes_vazias", "data_foto_origem", "data_foto",
                   *(f"sha_{s}" for s in reversed(PUBLICO))):
        op.drop_column(IMP, coluna)
