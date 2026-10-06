"""importação da agência: importações e itens (spec 013)

Na ordem do data-model:
1. tipos `importacao_agencia_estado` e `importacao_item_resultado`;
2. `agencia_importacoes` (versionada) e `agencia_importacao_itens` (só inserção), com os CHECKs
   e índices (o único parcial deixa só uma importação `processando` por vez);
3. a função e o trigger `agencia_itens_so_insercao`: `UPDATE` só preenche `desfeito_em` e
   `desfazer_motivo` (de NULL para valor); `DELETE` levanta erro. O `TRUNCATE` dos testes e do
   `reset-db` continua valendo (trigger de linha).

Nenhuma coluna nova em tabela de domínio: a origem fica em `entity_versions.details.importacao`.

Revision ID: 0016_importacao
Revises: 0015_cenas
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_importacao"
down_revision: str | None = "0015_cenas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

estado = postgresql.ENUM("processando", "concluida", "falhou", "desfeita",
                         name="importacao_agencia_estado", create_type=False)
resultado = postgresql.ENUM("criado", "atualizado", "mantido", "igual", "fora", "nao_gravado",
                            "sugestao", name="importacao_item_resultado", create_type=False)
TIPOS_ITEM = ("perfil", "conta", "guia", "anotacao", "canal", "vinculo_canal", "imagem_logo",
              "asset", "arquivo_asset", "clipe", "sugestao_bordao", "arquivo")

SO_INSERCAO = """
CREATE FUNCTION agencia_itens_so_insercao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'agencia_importacao_itens: só inserção (DELETE recusado)';
    END IF;
    IF OLD.desfeito_em IS NOT NULL OR OLD.desfazer_motivo IS NOT NULL
       OR (NEW.desfeito_em IS NULL AND NEW.desfazer_motivo IS NULL)
       OR ROW(NEW.id, NEW.importacao_id, NEW.ordem, NEW.tipo, NEW.perfil_slug, NEW.arquivo,
              NEW.trecho, NEW.linha, NEW.chave, NEW.impressao, NEW.situacao, NEW.motivo,
              NEW.escolha, NEW.resultado, NEW.resultado_motivo, NEW.entity_type,
              NEW.entity_id, NEW.entity_version)
          IS DISTINCT FROM
          ROW(OLD.id, OLD.importacao_id, OLD.ordem, OLD.tipo, OLD.perfil_slug, OLD.arquivo,
              OLD.trecho, OLD.linha, OLD.chave, OLD.impressao, OLD.situacao, OLD.motivo,
              OLD.escolha, OLD.resultado, OLD.resultado_motivo, OLD.entity_type,
              OLD.entity_id, OLD.entity_version) THEN
        RAISE EXCEPTION 'agencia_importacao_itens: só as marcas do desfazer mudam, uma vez';
    END IF;
    RETURN NEW;
END;
$$
"""


def upgrade() -> None:
    # 1.
    bind = op.get_bind()
    estado.create(bind)
    resultado.create(bind)

    # 2.
    ts = sa.DateTime(timezone=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "agencia_importacoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("estado", estado, server_default="processando", nullable=False),
        sa.Column("raiz_shared", sa.Text(), nullable=False),
        sa.Column("raiz_clipes", sa.Text(), nullable=False),
        sa.Column("arquivos", jsonb, nullable=False),
        sa.Column("contagens", jsonb, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("progresso", jsonb, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("progresso_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("criada_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("criada_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("concluida_em", ts, nullable=True),
        sa.Column("desfeita_em", ts, nullable=True),
        sa.Column("desfeita_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("(estado = 'desfeita') = "
                           "(desfeita_em IS NOT NULL AND desfeita_por IS NOT NULL)",
                           name="ck_agencia_imp_desfeita"),
        sa.CheckConstraint("(estado = 'falhou') = (erro IS NOT NULL)",
                           name="ck_agencia_imp_erro"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_agencia_imp_processando", "agencia_importacoes", ["estado"],
                    unique=True, postgresql_where=sa.text("estado = 'processando'"))
    op.create_index("ix_agencia_imp_criada", "agencia_importacoes",
                    [sa.text("criada_em DESC"), sa.text("id DESC")])

    op.create_table(
        "agencia_importacao_itens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("importacao_id", sa.Uuid(), sa.ForeignKey("agencia_importacoes.id"),
                  nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("perfil_slug", sa.Text(), nullable=True),
        sa.Column("arquivo", sa.Text(), nullable=False),
        sa.Column("trecho", sa.Text(), server_default="", nullable=False),
        sa.Column("linha", sa.Integer(), nullable=True),
        sa.Column("chave", sa.Text(), nullable=False),
        sa.Column("impressao", sa.Text(), nullable=False),
        sa.Column("situacao", sa.Text(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("escolha", jsonb, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("resultado", resultado, nullable=False),
        sa.Column("resultado_motivo", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("entity_version", sa.Integer(), nullable=True),
        sa.Column("desfeito_em", ts, nullable=True),
        sa.Column("desfazer_motivo", sa.Text(), nullable=True),
        sa.CheckConstraint("tipo IN (" + ", ".join(f"'{t}'" for t in TIPOS_ITEM) + ")",
                           name="ck_agencia_item_tipo"),
        sa.CheckConstraint("resultado NOT IN ('criado', 'atualizado') OR (entity_type IS NOT "
                           "NULL AND entity_id IS NOT NULL AND entity_version IS NOT NULL)",
                           name="ck_agencia_item_entidade"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agencia_item_imp", "agencia_importacao_itens",
                    ["importacao_id", "ordem"])
    op.create_index("ix_agencia_item_chave", "agencia_importacao_itens",
                    ["chave", "importacao_id"])

    # 3.
    op.execute(SO_INSERCAO)
    op.execute("CREATE TRIGGER agencia_itens_so_insercao BEFORE UPDATE OR DELETE ON "
               "agencia_importacao_itens FOR EACH ROW EXECUTE FUNCTION "
               "agencia_itens_so_insercao()")


def downgrade() -> None:
    """Só dev. As versões `importacao_agencia` em `entity_versions` ficam (histórico imutável,
    sem FK)."""
    op.execute("DROP TRIGGER agencia_itens_so_insercao ON agencia_importacao_itens")
    op.execute("DROP FUNCTION agencia_itens_so_insercao()")
    op.drop_table("agencia_importacao_itens")  # os índices vão junto
    op.drop_table("agencia_importacoes")
    bind = op.get_bind()
    resultado.drop(bind)
    estado.drop(bind)
