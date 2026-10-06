"""cenas para o Flow/Veo: cenas, tomadas, usos e padrões do perfil (spec 010)

Na ordem do data-model:
1. tipos `cena_status`, `cena_modo`, `cena_plano`, `cena_movimento` e `tomada_origem` (só
   `flow_manual`; a 021 poderá acrescentar valores com `ADD VALUE`);
2. `cena_padroes` (uma linha por perfil; sem linha = padrão do código, `version 0`);
3. `cenas` (CHECKs da duração, do congelado e do produto), `cena_tomadas` e a FK deferível
   `cenas.tomada_escolhida_id` (ciclo entre as duas tabelas);
4. `cena_usos` (vínculo cena × conteúdo, um ativo por par) e os índices;
5. `anotacao_alvo` + `cena` e `anotacao_tipo` + `proposta_cena` (`ADD VALUE` fora da transação:
   o valor novo não pode ser usado na mesma transação em que nasce) e a troca dos CHECKs das
   anotações: a proposta de cena vale em perfil ou cena e também tem `campos`.

Downgrade (só dev): recusa se houver anotação de cena; recria os CHECKs antigos e derruba as
tabelas e os tipos. Os valores novos dos enums das anotações ficam (o PG não remove valores).

Revision ID: 0015_cenas
Revises: 0014_mcp
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_cenas"
down_revision: str | None = "0014_mcp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *valores: str) -> postgresql.ENUM:
    return postgresql.ENUM(*valores, name=name, create_type=False)


cena_status = _enum("cena_status", "rascunho", "pronta", "usada")
cena_modo = _enum("cena_modo", "ingredientes", "quadros", "estender")
cena_plano = _enum("cena_plano", "close", "busto", "medio", "americano", "aberto",
                   "detalhe_produto")
cena_movimento = _enum("cena_movimento", "parada", "aproximacao", "afastamento", "panoramica",
                       "camera_na_mao")
tomada_origem = _enum("tomada_origem", "flow_manual")
TIPOS = (cena_status, cena_modo, cena_plano, cena_movimento, tomada_origem)

PROPOSTA_ANTIGA = "tipo = 'observacao' OR alvo_tipo = 'destino'"
PROPOSTA_NOVA = ("tipo = 'observacao' OR (tipo = 'proposta_texto' AND alvo_tipo = 'destino') "
                 "OR (tipo = 'proposta_cena' AND alvo_tipo IN ('perfil', 'cena'))")
CAMPOS_ANTIGO = "(tipo = 'proposta_texto') = (campos IS NOT NULL)"
CAMPOS_NOVO = "(tipo IN ('proposta_texto', 'proposta_cena')) = (campos IS NOT NULL)"


def _auditoria() -> list[sa.Column]:
    ts = sa.DateTime(timezone=True)
    return [
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    ]


def _arquivo() -> list[sa.Column]:
    return [
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    ]


def _max(coluna: str, n: int, tabela: str = "cenas") -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{coluna} IS NULL OR char_length({coluna}) <= {n}",
                              name=f"ck_{tabela}_{coluna}")


def upgrade() -> None:
    bind = op.get_bind()
    ts = sa.DateTime(timezone=True)
    # 1.
    for tipo in TIPOS:
        tipo.create(bind)

    # 2.
    op.create_table(
        "cena_padroes",
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("estilo", sa.Text(), nullable=False),
        sa.Column("negative", sa.Text(), nullable=False),
        *_auditoria(),
        sa.CheckConstraint("char_length(estilo) <= 500", name="ck_cena_padroes_estilo"),
        sa.CheckConstraint("char_length(negative) <= 500", name="ck_cena_padroes_negative"),
        sa.PrimaryKeyConstraint("perfil_id"),
    )

    # 3.
    op.create_table(
        "cenas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("avatar_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("avatar_arquivo_id", sa.Uuid(), sa.ForeignKey("asset_files.id"),
                  nullable=True),
        sa.Column("cenario_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("cenario_arquivo_id", sa.Uuid(), sa.ForeignKey("asset_files.id"),
                  nullable=True),
        sa.Column("plano", cena_plano, nullable=True),
        sa.Column("movimento", cena_movimento, nullable=True),
        sa.Column("camera", sa.Text(), nullable=True),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("fala", sa.Text(), nullable=True),
        sa.Column("texto_tela", sa.Text(), nullable=True),
        sa.Column("estilo", sa.Text(), nullable=True),
        sa.Column("audio", sa.Text(), nullable=True),
        sa.Column("duracao_s", sa.SmallInteger(), server_default=sa.text("8"), nullable=False),
        sa.Column("modo", cena_modo, server_default="ingredientes", nullable=False),
        sa.Column("quadro_inicial", sa.Text(), nullable=True),
        sa.Column("quadro_final", sa.Text(), nullable=True),
        sa.Column("produto_nome", sa.Text(), nullable=True),
        sa.Column("produto_imagem_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("negative", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("notas", sa.Text(), server_default="", nullable=False),
        sa.Column("status", cena_status, server_default="rascunho", nullable=False),
        sa.Column("prompt_congelado", sa.Text(), nullable=True),
        sa.Column("negative_congelado", sa.Text(), nullable=True),
        sa.Column("avatar_version_congelada", sa.Integer(), nullable=True),
        sa.Column("cenario_version_congelada", sa.Integer(), nullable=True),
        sa.Column("tomada_escolhida_id", sa.Uuid(), nullable=True),
        sa.Column("duplicada_de", sa.Uuid(), sa.ForeignKey("cenas.id"), nullable=True),
        *_arquivo(),
        *_auditoria(),
        sa.CheckConstraint("duracao_s IN (4, 6, 8)", name="ck_cenas_duracao"),
        sa.CheckConstraint(
            "(status = 'rascunho') = (prompt_congelado IS NULL) "
            "AND (prompt_congelado IS NULL) = (negative_congelado IS NULL)",
            name="ck_cenas_congelado"),
        sa.CheckConstraint("produto_imagem_id IS NULL OR produto_nome IS NOT NULL",
                           name="ck_cenas_produto"),
        sa.CheckConstraint("char_length(nome) BETWEEN 1 AND 120", name="ck_cenas_nome"),
        sa.CheckConstraint("char_length(acao) BETWEEN 1 AND 1000", name="ck_cenas_acao"),
        sa.CheckConstraint("char_length(notas) <= 2000", name="ck_cenas_notas"),
        sa.CheckConstraint("cardinality(tags) <= 20", name="ck_cenas_tags"),
        _max("camera", 500), _max("fala", 300), _max("texto_tela", 300), _max("estilo", 500),
        _max("audio", 300), _max("quadro_inicial", 500), _max("quadro_final", 500),
        _max("produto_nome", 120), _max("negative", 500),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cenas_perfil_status", "cenas", ["perfil_id", "archived_at", "status"])
    op.create_index("ix_cenas_perfil_avatar", "cenas", ["perfil_id", "avatar_id"])
    op.create_index("ix_cenas_perfil_cenario", "cenas", ["perfil_id", "cenario_id"])
    op.create_index("ix_cenas_perfil_produto", "cenas", ["perfil_id", "produto_imagem_id"])
    op.create_index("ix_cenas_perfil_lista", "cenas",
                    ["perfil_id", sa.text("updated_at DESC"), "id"])
    op.create_index("ix_cenas_tags", "cenas", ["tags"], postgresql_using="gin")

    op.create_table(
        "cena_tomadas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cena_id", sa.Uuid(), sa.ForeignKey("cenas.id"), nullable=False),
        sa.Column("origem", tomada_origem, server_default="flow_manual", nullable=False),
        sa.Column("video_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
        sa.Column("largura", sa.Integer(), nullable=False),
        sa.Column("altura", sa.Integer(), nullable=False),
        sa.Column("miniatura_key", sa.Text(), nullable=False),
        sa.Column("prompt_usado", sa.Text(), nullable=False),
        sa.Column("negative_usado", sa.Text(), nullable=False),
        sa.Column("nota", sa.Text(), server_default="", nullable=False),
        *_arquivo(),
        *_auditoria(),
        sa.CheckConstraint("content_type IN ('video/mp4', 'video/quicktime', 'video/webm')",
                           name="ck_cena_tomadas_content_type"),
        sa.CheckConstraint("duracao_ms BETWEEN 1000 AND 30000", name="ck_cena_tomadas_duracao"),
        sa.CheckConstraint("char_length(nota) <= 300", name="ck_cena_tomadas_nota"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_key", name="uq_cena_tomadas_video_key"),
    )
    op.create_index("ix_cena_tomadas_cena", "cena_tomadas", ["cena_id", "created_at"])
    op.create_foreign_key("fk_cenas_tomada_escolhida", "cenas", "cena_tomadas",
                          ["tomada_escolhida_id"], ["id"], deferrable=True,
                          initially="DEFERRED")

    # 4.
    op.create_table(
        "cena_usos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cena_id", sa.Uuid(), sa.ForeignKey("cenas.id"), nullable=False),
        sa.Column("conteudo_id", sa.Uuid(), sa.ForeignKey("conteudos.id"), nullable=False),
        sa.Column("criado_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("criado_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("desfeito_em", ts, nullable=True),
        sa.Column("desfeito_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_cena_usos_ativo", "cena_usos", ["cena_id", "conteudo_id"], unique=True,
                    postgresql_where=sa.text("desfeito_em IS NULL"))
    op.create_index("ix_cena_usos_conteudo", "cena_usos", ["conteudo_id"],
                    postgresql_where=sa.text("desfeito_em IS NULL"))

    # 5.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE anotacao_alvo ADD VALUE IF NOT EXISTS 'cena'")
        op.execute("ALTER TYPE anotacao_tipo ADD VALUE IF NOT EXISTS 'proposta_cena'")
    op.drop_constraint("ck_anotacoes_proposta_em_destino", "anotacoes", type_="check")
    op.create_check_constraint("ck_anotacoes_proposta_alvo", "anotacoes", PROPOSTA_NOVA)
    op.drop_constraint("ck_anotacoes_campos", "anotacoes", type_="check")
    op.create_check_constraint("ck_anotacoes_campos", "anotacoes", CAMPOS_NOVO)


def downgrade() -> None:
    """Só dev. Recusa se já existe anotação de cena (o CHECK antigo não a aceitaria)."""
    bind = op.get_bind()
    n = bind.execute(sa.text(
        "SELECT count(*) FROM anotacoes WHERE tipo::text = 'proposta_cena' "
        "OR alvo_tipo::text = 'cena'")).scalar()
    if n:
        raise RuntimeError(f"downgrade da 0015 recusado: {n} anotação(ões) de cena")
    # 5.
    op.drop_constraint("ck_anotacoes_campos", "anotacoes", type_="check")
    op.create_check_constraint("ck_anotacoes_campos", "anotacoes", CAMPOS_ANTIGO)
    op.drop_constraint("ck_anotacoes_proposta_alvo", "anotacoes", type_="check")
    op.create_check_constraint("ck_anotacoes_proposta_em_destino", "anotacoes", PROPOSTA_ANTIGA)
    # 4. → 2.
    op.drop_table("cena_usos")
    op.drop_constraint("fk_cenas_tomada_escolhida", "cenas", type_="foreignkey")
    op.drop_table("cena_tomadas")
    op.drop_table("cenas")
    op.drop_table("cena_padroes")
    # 1.
    for tipo in reversed(TIPOS):
        tipo.drop(bind)
