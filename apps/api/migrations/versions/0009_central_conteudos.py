"""central de conteúdos, aprovação e agendamento (spec 014-central-de-conteudos)

- `conteudos` (nova): uma linha por corte, arquivados inclusive, com `id = corte_id = cortes.id`
  (research R1); o vídeo próprio entra depois pela API.
- `postagens` vira o **destino** (R2, R3): `conteudo_id` no lugar de `corte_id`, o estado passa
  a `destino_estado` (`rascunho → pendente`; `agendado`/`postado` ganham a aprovação a partir de
  `updated_at` e do autor), `modo = lembrete` e as colunas de aprovação, pedido e recusa. Os
  CHECKs `ck_postagens_modo_014` e `ck_postagens_estados_015` barram no banco qualquer modo
  automático (princípio I).
- `ia_chamadas.conteudo_id` (= `corte_id`), `contas.intervalo_min_minutos` (30) e dois tipos de
  `notificacao_tipo`.

Nenhuma linha de `entity_versions` é escrita nem alterada: a primeira mutação depois da migração
grava o snapshot novo com todos os campos.

Revision ID: 0009_central_conteudos
Revises: 0008_assistente_ia
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_central_conteudos"
down_revision: str | None = "0008_assistente_ia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORIGENS = ("corte", "video_proprio")
ESTADOS = ("pendente", "aprovacao_pedida", "aprovado", "agendado", "postado",
           "rascunho_criado", "publicado", "falhou")
MODOS = ("lembrete", "criar_rascunho", "publicar", "rascunho_e_publicar")
TIPOS_0008 = ("envio_pronto", "envio_sem_clipes", "envio_falhou", "envio_confirmar_qualidade",
              "openshorts_fora", "hora_de_postar", "cota_youtube", "canal_erro",
              "envio_momentos")
TIPOS_NOVOS = ("aprovacao_pedida", "aprovacao_respondida")

conteudo_origem = postgresql.ENUM(*ORIGENS, name="conteudo_origem", create_type=False)
destino_estado = postgresql.ENUM(*ESTADOS, name="destino_estado", create_type=False)
agendamento_modo = postgresql.ENUM(*MODOS, name="agendamento_modo", create_type=False)

# (nome, expressão) dos CHECKs novos de `postagens`, na ordem do data-model.
CHECKS_POSTAGENS = (
    ("ck_postagens_aprovado",
     ("estado NOT IN ('aprovado','agendado','postado','rascunho_criado','publicado','falhou') "
      "OR aprovado_em IS NOT NULL")),
    ("ck_postagens_pedido", "estado <> 'aprovacao_pedida' OR pedido_em IS NOT NULL"),
    ("ck_postagens_antecedencia",
     ("antecedencia_min IS NULL OR (modo = 'rascunho_e_publicar' "
      "AND antecedencia_min BETWEEN 0 AND 10080)")),
    ("ck_postagens_textos_nota",
     ("(pedido_nota IS NULL OR char_length(pedido_nota) <= 500) AND "
      "(recusa_motivo IS NULL OR char_length(recusa_motivo) BETWEEN 1 AND 500)")),
    # Guardas do princípio I (só na 014; a 015 os remove depois da emenda).
    ("ck_postagens_modo_014", "modo = 'lembrete' AND antecedencia_min IS NULL"),
    ("ck_postagens_estados_015", "estado NOT IN ('rascunho_criado','publicado','falhou')"),
)
USERS_FKS = ("aprovado_por", "pedido_por", "recusado_por")


def _colunas_destino() -> list[sa.Column]:
    ts = sa.DateTime(timezone=True)
    return [
        sa.Column("modo", agendamento_modo, server_default="lembrete", nullable=False),
        sa.Column("antecedencia_min", sa.SmallInteger(), nullable=True),
        sa.Column("falha_motivo", sa.Text(), nullable=True),
        sa.Column("aprovado_por", sa.Uuid(), nullable=True),
        sa.Column("aprovado_em", ts, nullable=True),
        sa.Column("aprovado_video_ref", sa.Text(), nullable=True),
        sa.Column("pedido_por", sa.Uuid(), nullable=True),
        sa.Column("pedido_em", ts, nullable=True),
        sa.Column("pedido_nota", sa.Text(), nullable=True),
        sa.Column("recusado_por", sa.Uuid(), nullable=True),
        sa.Column("recusado_em", ts, nullable=True),
        sa.Column("recusa_motivo", sa.Text(), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for tipo in (conteudo_origem, destino_estado, agendamento_modo):
        tipo.create(bind)

    # 1. conteudos: uma linha por corte (arquivados inclusive), mesmo id.
    op.create_table(
        "conteudos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        sa.Column("origem", conteudo_origem, nullable=False),
        sa.Column("corte_id", sa.Uuid(), nullable=True),
        sa.Column("titulo", sa.Text(), server_default="", nullable=False),
        sa.Column("video_key", sa.Text(), nullable=True),
        sa.Column("video_content_type", sa.Text(), nullable=True),
        sa.Column("video_bytes", sa.BigInteger(), nullable=True),
        sa.Column("video_sha256", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("poster_key", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(origem = 'corte' AND corte_id IS NOT DISTINCT FROM id AND video_key IS NULL"
            " AND archived_at IS NULL)"
            " OR (origem = 'video_proprio' AND corte_id IS NULL AND video_key IS NOT NULL"
            " AND poster_key IS NOT NULL AND duration_ms IS NOT NULL)",
            name="ck_conteudos_origem",
        ),
        sa.CheckConstraint("char_length(titulo) <= 100", name="ck_conteudos_titulo"),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.ForeignKeyConstraint(["corte_id"], ["cortes.id"]),
        sa.ForeignKeyConstraint(["archived_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("corte_id"),
        sa.UniqueConstraint("video_key"),
    )
    op.create_index("ix_conteudos_perfil_created", "conteudos",
                    ["perfil_id", sa.literal_column("created_at DESC"),
                     sa.literal_column("id DESC")])
    op.create_index("ix_conteudos_created", "conteudos",
                    [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")])
    op.execute("""
        INSERT INTO conteudos (id, perfil_id, origem, corte_id, titulo, version, created_at,
                               created_by, updated_at, updated_by)
        SELECT id, perfil_id, 'corte', id,
               left(COALESCE(NULLIF(openshorts_title, ''), NULLIF(hook_text, ''),
                             original_filename), 100),
               1, created_at, created_by, created_at, created_by
        FROM cortes
    """)

    # 2. postagens.conteudo_id no lugar de corte_id (mesmo valor: id do conteúdo = do corte).
    op.add_column("postagens", sa.Column("conteudo_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE postagens SET conteudo_id = corte_id")
    op.alter_column("postagens", "conteudo_id", nullable=False)
    op.create_foreign_key("postagens_conteudo_id_fkey", "postagens", "conteudos",
                          ["conteudo_id"], ["id"])
    op.drop_index("uq_postagens_corte_conta_ativa", table_name="postagens")
    op.create_index("uq_postagens_conteudo_conta_ativa", "postagens",
                    ["conteudo_id", "conta_id"], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    op.drop_column("postagens", "corte_id")  # leva a FK junto

    # 3 e 4. Colunas novas; o estado muda de tipo (um tipo novo evita o ADD VALUE, que não
    # pode ser usado na mesma transação); agendado/postado ganham a aprovação.
    for coluna in _colunas_destino():
        op.add_column("postagens", coluna)
    for coluna in USERS_FKS:
        op.create_foreign_key(f"postagens_{coluna}_fkey", "postagens", "users", [coluna], ["id"])
    op.drop_constraint("ck_postagens_agendado_planned", "postagens", type_="check")
    op.execute("ALTER TABLE postagens ALTER COLUMN estado DROP DEFAULT")
    op.execute("""
        ALTER TABLE postagens ALTER COLUMN estado TYPE destino_estado
        USING (CASE estado::text WHEN 'rascunho' THEN 'pendente' ELSE estado::text END
               )::destino_estado
    """)
    op.execute("ALTER TABLE postagens ALTER COLUMN estado SET DEFAULT 'pendente'")
    op.execute("DROP TYPE postagem_estado")
    op.execute("""
        UPDATE postagens SET aprovado_em = updated_at,
                             aprovado_por = COALESCE(updated_by, created_by)
        WHERE estado IN ('agendado', 'postado')
    """)
    op.create_check_constraint("ck_postagens_agendado_planned", "postagens",
                               "estado <> 'agendado' OR planned_at IS NOT NULL")
    for nome, expr in CHECKS_POSTAGENS:
        op.create_check_constraint(nome, "postagens", expr)
    op.create_index("ix_postagens_conteudo", "postagens", ["conteudo_id"])
    op.create_index("ix_postagens_conta_agenda", "postagens", ["conta_id", "planned_at"],
                    postgresql_where=sa.text("archived_at IS NULL AND estado = 'agendado'"))

    # 5. ia_chamadas.conteudo_id = corte_id.
    op.add_column("ia_chamadas", sa.Column("conteudo_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("ia_chamadas_conteudo_id_fkey", "ia_chamadas", "conteudos",
                          ["conteudo_id"], ["id"])
    op.execute("UPDATE ia_chamadas SET conteudo_id = corte_id WHERE corte_id IS NOT NULL")
    op.create_index("ix_ia_chamadas_conteudo", "ia_chamadas",
                    ["conteudo_id", sa.literal_column("created_at DESC")])

    # 5a. Intervalo mínimo entre posts da conta (Clarifications Q3).
    op.add_column("contas", sa.Column("intervalo_min_minutos", sa.SmallInteger(),
                                      server_default=sa.text("30"), nullable=False))
    op.create_check_constraint("ck_contas_intervalo_min", "contas",
                               "intervalo_min_minutos BETWEEN 0 AND 1440")

    # 6. PG 12+: ADD VALUE roda dentro da transação; o valor novo só não pode ser usado nela.
    for tipo in TIPOS_NOVOS:
        op.execute(f"ALTER TYPE notificacao_tipo ADD VALUE IF NOT EXISTS '{tipo}'")


def downgrade() -> None:
    """Só dev. Recusa com vídeo próprio (não há corte para onde voltar); senão desfaz na ordem
    inversa: `pendente`, `aprovacao_pedida` e `aprovado` voltam a `rascunho`, e as aprovações,
    pedidos, recusas e o intervalo das contas se perdem."""
    bind = op.get_bind()
    proprios = bind.execute(sa.text(
        "SELECT count(*) FROM conteudos WHERE origem <> 'corte'")).scalar()
    if proprios:
        raise RuntimeError(
            f"downgrade recusado: há {proprios} conteúdo(s) de vídeo próprio (spec 014)")

    # 6. O PostgreSQL não remove valor de enum (padrão da 0007).
    lista = ", ".join(repr(t) for t in TIPOS_NOVOS)
    op.execute(f"DELETE FROM notificacoes WHERE tipo::text IN ({lista})")
    op.execute("ALTER TYPE notificacao_tipo RENAME TO notificacao_tipo_old")
    op.execute(f"CREATE TYPE notificacao_tipo AS ENUM ({', '.join(repr(t) for t in TIPOS_0008)})")
    op.execute("ALTER TABLE notificacoes ALTER COLUMN tipo TYPE notificacao_tipo "
               "USING tipo::text::notificacao_tipo")
    op.execute("DROP TYPE notificacao_tipo_old")

    # 5a e 5.
    op.drop_constraint("ck_contas_intervalo_min", "contas", type_="check")
    op.drop_column("contas", "intervalo_min_minutos")
    op.drop_index("ix_ia_chamadas_conteudo", table_name="ia_chamadas")
    op.drop_column("ia_chamadas", "conteudo_id")  # leva a FK junto

    # 3 e 4.
    op.drop_index("ix_postagens_conta_agenda", table_name="postagens")
    op.drop_index("ix_postagens_conteudo", table_name="postagens")
    for nome, _ in reversed(CHECKS_POSTAGENS):
        op.drop_constraint(nome, "postagens", type_="check")
    op.drop_constraint("ck_postagens_agendado_planned", "postagens", type_="check")
    op.execute("CREATE TYPE postagem_estado AS ENUM ('rascunho', 'agendado', 'postado')")
    op.execute("ALTER TABLE postagens ALTER COLUMN estado DROP DEFAULT")
    op.execute("""
        ALTER TABLE postagens ALTER COLUMN estado TYPE postagem_estado
        USING (CASE WHEN estado::text IN ('agendado', 'postado') THEN estado::text
                    ELSE 'rascunho' END)::postagem_estado
    """)
    op.execute("ALTER TABLE postagens ALTER COLUMN estado SET DEFAULT 'rascunho'")
    op.create_check_constraint("ck_postagens_agendado_planned", "postagens",
                               "estado <> 'agendado' OR planned_at IS NOT NULL")
    for coluna in reversed(_colunas_destino()):
        op.drop_column("postagens", coluna.name)  # as FKs de users vão junto

    # 2.
    op.add_column("postagens", sa.Column("corte_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE postagens SET corte_id = conteudo_id")
    op.alter_column("postagens", "corte_id", nullable=False)
    op.create_foreign_key("postagens_corte_id_fkey", "postagens", "cortes", ["corte_id"], ["id"])
    op.drop_index("uq_postagens_conteudo_conta_ativa", table_name="postagens")
    op.create_index("uq_postagens_corte_conta_ativa", "postagens", ["corte_id", "conta_id"],
                    unique=True, postgresql_where=sa.text("archived_at IS NULL"))
    op.drop_column("postagens", "conteudo_id")

    # 1.
    op.drop_index("ix_conteudos_created", table_name="conteudos")
    op.drop_index("ix_conteudos_perfil_created", table_name="conteudos")
    op.drop_table("conteudos")
    for tipo in (agendamento_modo, destino_estado, conteudo_origem):
        tipo.drop(bind)
