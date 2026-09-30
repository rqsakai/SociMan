"""publicação no TikTok: conexões, credenciais, interruptor e tentativas (spec 015)

Na ordem do data-model:
1. tipos `conexao_estado` e `tentativa_fase`;
2. `destino_estado` + `enviando` e os cinco tipos novos de `notificacao_tipo`, em bloco
   `autocommit` (o valor novo não pode ser usado na transação que o cria, e os CHECKs do passo 4
   citam `'enviando'`). `IF NOT EXISTS` porque o downgrade deixa `enviando` no enum;
3. tabelas `conexoes`, `conexao_credenciais`, `publicacao_config` (com a linha `id = 1`,
   desligada) e `publicacao_tentativas`;
4. `postagens`: colunas da execução; os CHECKs `ck_postagens_modo_014` e
   `ck_postagens_estados_015` dão lugar a `ck_postagens_modo_015`, `ck_postagens_execucao`,
   `ck_postagens_auto_decisao` e `ck_postagens_publicar_snapshot` (R17); `ck_postagens_aprovado`
   ganha `enviando`; índice `ix_postagens_auto_vencidos`;
5. dados: nenhum destino muda (todos são `lembrete` na 014) e nenhuma linha de
   `entity_versions` é escrita.

Revision ID: 0010_publicacao_tiktok
Revises: 0009_central_conteudos
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_publicacao_tiktok"
down_revision: str | None = "0009_central_conteudos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONEXAO_ESTADOS = ("conectada", "precisa_reconectar", "desconectada")
FASES = ("iniciando", "enviando_partes", "processando", "entregue", "publicada", "recusada",
         "incerta", "sem_vaga")
TIPOS_0009 = ("envio_pronto", "envio_sem_clipes", "envio_falhou", "envio_confirmar_qualidade",
              "openshorts_fora", "hora_de_postar", "cota_youtube", "canal_erro",
              "envio_momentos", "aprovacao_pedida", "aprovacao_respondida")
TIPOS_NOVOS = ("rascunho_criado", "envio_publicado", "envio_rede_falhou",
               "envio_aguardando_vaga", "conexao_precisa_reconectar")

conexao_estado = postgresql.ENUM(*CONEXAO_ESTADOS, name="conexao_estado", create_type=False)
tentativa_fase = postgresql.ENUM(*FASES, name="tentativa_fase", create_type=False)
platform = postgresql.ENUM(name="platform", create_type=False)
agendamento_modo = postgresql.ENUM(name="agendamento_modo", create_type=False)

ABERTAS = "fase IN ('iniciando','enviando_partes','processando')"

# CHECKs da 014 que a 0010 troca (o downgrade os recria).
CHECKS_014 = (
    ("ck_postagens_aprovado",
     ("estado NOT IN ('aprovado','agendado','postado','rascunho_criado','publicado','falhou') "
      "OR aprovado_em IS NOT NULL")),
    ("ck_postagens_modo_014", "modo = 'lembrete' AND antecedencia_min IS NULL"),
    ("ck_postagens_estados_015", "estado NOT IN ('rascunho_criado','publicado','falhou')"),
)
CHECKS_015 = (
    ("ck_postagens_aprovado",
     ("estado NOT IN ('aprovado','agendado','enviando','postado','rascunho_criado',"
      "'publicado','falhou') OR aprovado_em IS NOT NULL")),
    ("ck_postagens_modo_015",
     "modo IN ('lembrete','criar_rascunho','publicar') AND antecedencia_min IS NULL"),
    ("ck_postagens_execucao",
     "estado NOT IN ('enviando','rascunho_criado','publicado','falhou') OR modo <> 'lembrete'"),
    ("ck_postagens_auto_decisao",
     ("modo = 'lembrete' OR estado NOT IN ('agendado','enviando') "
      "OR (aprovado_por IS NOT NULL AND agendado_por IS NOT NULL)")),
    ("ck_postagens_publicar_snapshot",
     ("modo <> 'publicar' OR estado NOT IN ('agendado','enviando') "
      "OR (opcoes_rede IS NOT NULL AND envio_snapshot IS NOT NULL)")),
)
USERS_FKS = ("agendado_por", "envio_confirmado_por")


def _colunas_postagens() -> list[sa.Column]:
    ts = sa.DateTime(timezone=True)
    return [
        sa.Column("agendado_por", sa.Uuid(), nullable=True),
        sa.Column("agendado_em", ts, nullable=True),
        sa.Column("envio_confirmado_por", sa.Uuid(), nullable=True),
        sa.Column("envio_confirmado_em", ts, nullable=True),
        sa.Column("opcoes_rede", postgresql.JSONB(), nullable=True),
        sa.Column("envio_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("falha_incerta", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("rede_post_id", sa.Text(), nullable=True),
    ]


def _auditoria() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    # 1.
    conexao_estado.create(bind)
    tentativa_fase.create(bind)

    # 2. Antes de qualquer uso (os CHECKs do passo 4 citam 'enviando').
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE destino_estado ADD VALUE IF NOT EXISTS 'enviando'")
        for tipo in TIPOS_NOVOS:
            op.execute(f"ALTER TYPE notificacao_tipo ADD VALUE IF NOT EXISTS '{tipo}'")

    # 3.
    op.create_table(
        "conexoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conta_id", sa.Uuid(), sa.ForeignKey("contas.id"), nullable=False),
        sa.Column("rede", platform, nullable=False),
        sa.Column("open_id", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), server_default="", nullable=False),
        sa.Column("avatar_key", sa.Text(), nullable=True),
        sa.Column("escopos", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("estado", conexao_estado, nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("conectado_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conectado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("desconectado_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("desconectado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("avisado_vencimento_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        *_auditoria(),
        sa.CheckConstraint("estado <> 'desconectada' OR (desconectado_em IS NOT NULL)",
                           name="ck_conexoes_desconectada"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_conexoes_conta_viva", "conexoes", ["conta_id"], unique=True,
                    postgresql_where=sa.text("estado <> 'desconectada'"))
    op.create_index("uq_conexoes_open_id_vivo", "conexoes", ["rede", "open_id"], unique=True,
                    postgresql_where=sa.text("estado <> 'desconectada'"))

    op.create_table(
        "conexao_credenciais",
        sa.Column("conexao_id", sa.Uuid(), sa.ForeignKey("conexoes.id"), nullable=False),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("access_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column("access_expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("renovado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renovacoes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("conexao_id"),
    )

    op.create_table(
        "publicacao_config",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("envios_habilitados", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_auditoria(),
        sa.CheckConstraint("id = 1", name="ck_publicacao_config_unica"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO publicacao_config (id, envios_habilitados) VALUES (1, false)")

    op.create_table(
        "publicacao_tentativas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("destino_id", sa.Uuid(), sa.ForeignKey("postagens.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("conexao_id", sa.Uuid(), sa.ForeignKey("conexoes.id"), nullable=False),
        sa.Column("rede", platform, nullable=False),
        sa.Column("modo", agendamento_modo, nullable=False),
        sa.Column("fase", tentativa_fase, nullable=False),
        sa.Column("disparo", sa.Text(), nullable=False),
        sa.Column("disparado_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("video_ref", sa.Text(), nullable=False),
        sa.Column("video_etag", sa.Text(), nullable=False),
        sa.Column("video_bytes", sa.BigInteger(), nullable=False),
        sa.Column("video_sha256", sa.Text(), nullable=True),
        sa.Column("chunk_size", sa.BigInteger(), nullable=False),
        sa.Column("total_partes", sa.Integer(), nullable=False),
        sa.Column("partes_enviadas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("init_enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_id", sa.Text(), nullable=True),
        sa.Column("upload_url_cifrado", sa.LargeBinary(), nullable=True),
        sa.Column("upload_url_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_rede", sa.Text(), nullable=True),
        sa.Column("codigo_rede", sa.Text(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("rede_post_id", sa.Text(), nullable=True),
        sa.Column("proxima_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.CheckConstraint(
            "fase NOT IN ('enviando_partes','processando','entregue','publicada') "
            "OR publish_id IS NOT NULL",
            name="ck_tentativas_publish_id",
        ),
        sa.CheckConstraint(f"{ABERTAS} OR concluida_em IS NOT NULL",
                           name="ck_tentativas_final"),
        sa.CheckConstraint("partes_enviadas BETWEEN 0 AND total_partes",
                           name="ck_tentativas_partes"),
        sa.CheckConstraint("disparo IN ('agendador','tentar_de_novo','confirmado')",
                           name="ck_tentativas_disparo"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("destino_id", "numero", name="uq_tentativas_destino_numero"),
        sa.UniqueConstraint("publish_id", name="uq_tentativas_publish_id"),
    )
    op.create_index("uq_tentativas_destino_aberta", "publicacao_tentativas", ["destino_id"],
                    unique=True, postgresql_where=sa.text(ABERTAS))
    op.create_index("ix_tentativas_abertas", "publicacao_tentativas", ["proxima_em"],
                    postgresql_where=sa.text(ABERTAS))
    op.create_index("ix_tentativas_conexao_init", "publicacao_tentativas",
                    ["conexao_id", "init_enviado_em"],
                    postgresql_where=sa.text(
                        "modo = 'criar_rascunho' AND init_enviado_em IS NOT NULL"))
    op.create_index("ix_tentativas_destino", "publicacao_tentativas",
                    ["destino_id", sa.literal_column("numero DESC")])

    # 4.
    for coluna in _colunas_postagens():
        op.add_column("postagens", coluna)
    for coluna in USERS_FKS:
        op.create_foreign_key(f"postagens_{coluna}_fkey", "postagens", "users", [coluna], ["id"])
    for nome, _ in CHECKS_014:
        op.drop_constraint(nome, "postagens", type_="check")
    for nome, expr in CHECKS_015:
        op.create_check_constraint(nome, "postagens", expr)
    op.create_index("ix_postagens_auto_vencidos", "postagens", ["planned_at"],
                    postgresql_where=sa.text(
                        "estado = 'agendado' AND modo <> 'lembrete' AND archived_at IS NULL"))
    # 5. Nenhum dado muda.


def downgrade() -> None:
    """Só dev. Recusa com conexão, tentativa ou destino em modo automático; senão desfaz na
    ordem inversa, com os CHECKs da 014 de volta. O valor `enviando` fica no `destino_estado`
    (o PostgreSQL não remove valor de enum e nenhuma linha o usa)."""
    bind = op.get_bind()
    motivos = []
    for sql, texto in (
        ("SELECT count(*) FROM conexoes", "conexão(ões)"),
        ("SELECT count(*) FROM publicacao_tentativas", "tentativa(s) de envio"),
        ("SELECT count(*) FROM postagens WHERE modo <> 'lembrete'",
         "destino(s) em modo automático"),
    ):
        n = bind.execute(sa.text(sql)).scalar()
        if n:
            motivos.append(f"{n} {texto}")
    if motivos:
        raise RuntimeError(f"downgrade recusado (spec 015): há {', '.join(motivos)}")

    # 4.
    op.drop_index("ix_postagens_auto_vencidos", table_name="postagens")
    for nome, _ in reversed(CHECKS_015):
        op.drop_constraint(nome, "postagens", type_="check")
    for nome, expr in CHECKS_014:
        op.create_check_constraint(nome, "postagens", expr)
    for coluna in reversed(_colunas_postagens()):
        op.drop_column("postagens", coluna.name)  # as FKs de users vão junto

    # 3.
    op.drop_index("ix_tentativas_destino", table_name="publicacao_tentativas")
    op.drop_index("ix_tentativas_conexao_init", table_name="publicacao_tentativas")
    op.drop_index("ix_tentativas_abertas", table_name="publicacao_tentativas")
    op.drop_index("uq_tentativas_destino_aberta", table_name="publicacao_tentativas")
    op.drop_table("publicacao_tentativas")
    op.drop_table("publicacao_config")
    op.drop_table("conexao_credenciais")
    op.drop_index("uq_conexoes_open_id_vivo", table_name="conexoes")
    op.drop_index("uq_conexoes_conta_viva", table_name="conexoes")
    op.drop_table("conexoes")

    # 2. Padrão da 0007: os avisos dos tipos novos saem e o tipo é recriado sem eles.
    lista = ", ".join(repr(t) for t in TIPOS_NOVOS)
    op.execute(f"DELETE FROM notificacoes WHERE tipo::text IN ({lista})")
    op.execute("ALTER TYPE notificacao_tipo RENAME TO notificacao_tipo_old")
    op.execute(f"CREATE TYPE notificacao_tipo AS ENUM ({', '.join(repr(t) for t in TIPOS_0009)})")
    op.execute("ALTER TABLE notificacoes ALTER COLUMN tipo TYPE notificacao_tipo "
               "USING tipo::text::notificacao_tipo")
    op.execute("DROP TYPE notificacao_tipo_old")

    # 1.
    tentativa_fase.drop(bind)
    conexao_estado.drop(bind)
