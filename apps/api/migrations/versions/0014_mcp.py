"""servidor MCP: clientes, interruptor, registro, anotações e o autor MCP (spec 009)

Na ordem do data-model:
1. tipos `mcp_escopo`, `mcp_situacao`, `mcp_resultado`, `mcp_via`, `anotacao_alvo`,
   `anotacao_tipo` e `anotacao_situacao`;
2. `mcp_clientes` (nome único sem caixa nem acento pela coluna `nome_normalizado`, `token_id`
   único, hash SHA-256 em `bytea`);
3. `mcp_config` (linha única `id = 1`, desligada);
4. `mcp_chamadas` (só inserção: função `mcp_recusa_mudanca()` e trigger `mcp_chamadas_so_insercao`
   `BEFORE UPDATE OR DELETE`; o `TRUNCATE` do `reset-db` e dos testes continua valendo) e os
   índices;
5. `anotacoes` (CHECKs do autor e da proposta só em destino) e os índices;
6. `actor_mcp_client_id` (FK para `mcp_clientes`) e o CHECK do ator em `entity_versions` e
   `security_events` (R6). As linhas antigas (`user`, `system:*`, `anonymous`) já cumprem o CHECK.

Revision ID: 0014_mcp
Revises: 0013_historico_studio
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_mcp"
down_revision: str | None = "0013_historico_studio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *valores: str) -> postgresql.ENUM:
    return postgresql.ENUM(*valores, name=name, create_type=False)


mcp_escopo = _enum("mcp_escopo", "leitura", "propostas")
mcp_situacao = _enum("mcp_situacao", "ativo", "suspenso", "revogado")
mcp_resultado = _enum("mcp_resultado", "ok", "erro", "recusada", "limite", "nao_autenticado")
mcp_via = _enum("mcp_via", "mcp", "api")
anotacao_alvo = _enum("anotacao_alvo", "perfil", "conta", "canal", "video_fonte", "corte",
                      "conteudo", "destino")
anotacao_tipo = _enum("anotacao_tipo", "observacao", "proposta_texto")
anotacao_situacao = _enum("anotacao_situacao", "aberta", "aplicada", "descartada", "arquivada")
TIPOS = (mcp_escopo, mcp_situacao, mcp_resultado, mcp_via, anotacao_alvo, anotacao_tipo,
         anotacao_situacao)
ATOR = ("(actor_kind = 'mcp_client') = (actor_mcp_client_id IS NOT NULL)")
TABELAS_ATOR = {"entity_versions": "ck_entity_versions_ator",
                "security_events": "ck_security_events_ator"}

FUNCAO = """
CREATE FUNCTION mcp_recusa_mudanca() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'mcp_chamadas é só de inserção (spec 009, R8)';
END;
$$
"""


def _auditoria() -> list[sa.Column]:
    ts = sa.DateTime(timezone=True)
    return [
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    ts = sa.DateTime(timezone=True)
    # 1.
    for tipo in TIPOS:
        tipo.create(bind)

    # 2.
    op.create_table(
        "mcp_clientes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("nome_normalizado", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), server_default="", nullable=False),
        sa.Column("escopo", mcp_escopo, nullable=False),
        sa.Column("situacao", mcp_situacao, server_default="ativo", nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("token_emitido_em", ts, nullable=False),
        sa.Column("expira_em", ts, nullable=True),
        sa.Column("limite_por_minuto", sa.Integer(), server_default=sa.text("60"),
                  nullable=False),
        sa.Column("limite_escritas_dia", sa.Integer(), server_default=sa.text("200"),
                  nullable=False),
        sa.Column("ultimo_uso_em", ts, nullable=True),
        sa.Column("revogado_em", ts, nullable=True),
        sa.Column("revogado_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        *_auditoria(),
        sa.CheckConstraint("char_length(nome) BETWEEN 1 AND 60", name="ck_mcp_clientes_nome"),
        sa.CheckConstraint("char_length(descricao) <= 300", name="ck_mcp_clientes_descricao"),
        sa.CheckConstraint("limite_por_minuto BETWEEN 1 AND 600",
                           name="ck_mcp_clientes_limite_min"),
        sa.CheckConstraint("limite_escritas_dia BETWEEN 0 AND 5000",
                           name="ck_mcp_clientes_limite_dia"),
        sa.CheckConstraint("token_id ~ '^[a-z2-7]{8}$'", name="ck_mcp_clientes_token_id"),
        sa.CheckConstraint("octet_length(token_hash) = 32", name="ck_mcp_clientes_token_hash"),
        sa.CheckConstraint("(situacao = 'revogado') = (revogado_em IS NOT NULL)",
                           name="ck_mcp_clientes_revogado"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome_normalizado", name="uq_mcp_clientes_nome"),
        sa.UniqueConstraint("token_id", name="uq_mcp_clientes_token_id"),
    )

    # 3.
    op.create_table(
        "mcp_config",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("habilitado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_auditoria(),
        sa.CheckConstraint("id = 1", name="ck_mcp_config_unica"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO mcp_config (id, habilitado, version) VALUES (1, false, 1)")

    # 4.
    op.create_table(
        "mcp_chamadas",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ocorreu_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("cliente_id", sa.Uuid(), sa.ForeignKey("mcp_clientes.id"), nullable=True),
        sa.Column("via", mcp_via, nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("metodo", sa.Text(), nullable=False),
        sa.Column("rota", sa.Text(), nullable=False),
        sa.Column("args_resumo", postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("resultado", mcp_resultado, nullable=False),
        sa.Column("status_http", sa.SmallInteger(), nullable=True),
        sa.Column("codigo_erro", sa.Text(), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("escrita", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("entidade_tipo", sa.Text(), nullable=True),
        sa.Column("entidade_id", sa.Uuid(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.CheckConstraint("octet_length(args_resumo::text) <= 4096",
                           name="ck_mcp_chamadas_args"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mcp_chamadas_cliente", "mcp_chamadas",
                    ["cliente_id", sa.text("ocorreu_em DESC")])
    op.create_index("ix_mcp_chamadas_ocorreu", "mcp_chamadas", [sa.text("ocorreu_em DESC")])
    op.create_index("ix_mcp_chamadas_resultado", "mcp_chamadas",
                    ["resultado", sa.text("ocorreu_em DESC")])
    op.execute(FUNCAO)
    op.execute("CREATE TRIGGER mcp_chamadas_so_insercao BEFORE UPDATE OR DELETE ON mcp_chamadas "
               "FOR EACH ROW EXECUTE FUNCTION mcp_recusa_mudanca()")

    # 5.
    op.create_table(
        "anotacoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alvo_tipo", anotacao_alvo, nullable=False),
        sa.Column("alvo_id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=True),
        sa.Column("tipo", anotacao_tipo, nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("campos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("situacao", anotacao_situacao, server_default="aberta", nullable=False),
        sa.Column("autor_kind", sa.Text(), nullable=False),
        sa.Column("autor_mcp_cliente_id", sa.Uuid(), sa.ForeignKey("mcp_clientes.id"),
                  nullable=True),
        sa.Column("autor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolvida_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolvida_em", ts, nullable=True),
        sa.Column("motivo_descarte", sa.Text(), nullable=True),
        *_auditoria(),
        sa.CheckConstraint("char_length(texto) BETWEEN 1 AND 4000", name="ck_anotacoes_texto"),
        sa.CheckConstraint(
            "(autor_kind = 'mcp_client' AND autor_mcp_cliente_id IS NOT NULL "
            "AND autor_user_id IS NULL) OR (autor_kind = 'user' AND autor_user_id IS NOT NULL "
            "AND autor_mcp_cliente_id IS NULL)", name="ck_anotacoes_autor"),
        sa.CheckConstraint("tipo = 'observacao' OR alvo_tipo = 'destino'",
                           name="ck_anotacoes_proposta_em_destino"),
        sa.CheckConstraint("(tipo = 'proposta_texto') = (campos IS NOT NULL)",
                           name="ck_anotacoes_campos"),
        sa.CheckConstraint("motivo_descarte IS NULL OR char_length(motivo_descarte) <= 300",
                           name="ck_anotacoes_motivo"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anotacoes_alvo", "anotacoes", ["alvo_tipo", "alvo_id"])
    op.create_index("ix_anotacoes_situacao", "anotacoes",
                    ["situacao", sa.text("created_at DESC")])
    op.create_index("ix_anotacoes_perfil", "anotacoes", ["perfil_id", sa.text("created_at DESC")])

    # 6.
    for tabela, check in TABELAS_ATOR.items():
        op.add_column(tabela, sa.Column("actor_mcp_client_id", sa.Uuid(),
                                        sa.ForeignKey("mcp_clientes.id",
                                                      name=f"fk_{tabela}_mcp_cliente"),
                                        nullable=True))
        op.create_check_constraint(check, tabela, ATOR)


def downgrade() -> None:
    """Só dev. Desfaz na ordem inversa; as anotações e o registro saem com as tabelas."""
    bind = op.get_bind()
    # 6. Nada do histórico é apagado: o autor MCP vira `system:mcp` (sem o cliente).
    for tabela, check in TABELAS_ATOR.items():
        op.drop_constraint(check, tabela, type_="check")
        op.execute(f"UPDATE {tabela} SET actor_kind = 'system:mcp' "
                   "WHERE actor_mcp_client_id IS NOT NULL")
        op.drop_column(tabela, "actor_mcp_client_id")
    # 5. → 2.
    op.drop_table("anotacoes")
    op.execute("DROP TRIGGER mcp_chamadas_so_insercao ON mcp_chamadas")
    op.execute("DROP FUNCTION mcp_recusa_mudanca()")
    op.drop_table("mcp_chamadas")
    op.drop_table("mcp_config")
    op.drop_table("mcp_clientes")
    # 1.
    for tipo in reversed(TIPOS):
        tipo.drop(bind)
