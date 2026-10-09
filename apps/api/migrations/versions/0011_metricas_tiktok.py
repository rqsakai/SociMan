"""métricas do TikTok: séries, vídeos, fotos só de inserção e buscas de post (spec 016)

Na ordem do data-model:
1. tipo `vinculo_metodo`; `notificacao_tipo` + `post_detectado` e `vinculo_a_confirmar`, em
   bloco `autocommit` (como na 0010; `IF NOT EXISTS` para subir de novo depois de um downgrade);
2. sequência `metricas_anonima_seq` (o N de "Conta anônima N");
3. as 5 tabelas, com CHECKs e índices;
4. função `metricas_recusa_mudanca()` e o trigger `metricas_so_insercao` (`BEFORE UPDATE OR
   DELETE … FOR EACH ROW`) nas duas tabelas de fotos (research R7). O `TRUNCATE` não dispara
   trigger de linha: os testes e o `reset-db` continuam limpando.

Não há backfill: as séries nascem na 1ª volta da trilha `metricas` depois da reconexão.

Revision ID: 0011_metricas_tiktok
Revises: 0010_publicacao_tiktok
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_metricas_tiktok"
down_revision: str | None = "0010_publicacao_tiktok"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

METODOS = ("envio", "casamento", "link", "escolha")
TIPOS_0010 = ("envio_pronto", "envio_sem_clipes", "envio_falhou", "envio_confirmar_qualidade",
              "openshorts_fora", "hora_de_postar", "cota_youtube", "canal_erro",
              "envio_momentos", "aprovacao_pedida", "aprovacao_respondida", "rascunho_criado",
              "envio_publicado", "envio_rede_falhou", "envio_aguardando_vaga",
              "conexao_precisa_reconectar")
TIPOS_NOVOS = ("post_detectado", "vinculo_a_confirmar")
FOTOS = ("metricas_video_fotos", "metricas_conta_fotos")
TABELAS = ("metricas_buscas_post", "metricas_conta_fotos", "metricas_video_fotos",
           "metricas_videos", "metricas_series")  # ordem das FKs para o DROP

vinculo_metodo = postgresql.ENUM(*METODOS, name="vinculo_metodo", create_type=False)
platform = postgresql.ENUM(name="platform", create_type=False)

FUNCAO = """
CREATE FUNCTION metricas_recusa_mudanca() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'metricas: fotos são só de inserção';
END;
$$
"""


def upgrade() -> None:
    bind = op.get_bind()
    # 1.
    vinculo_metodo.create(bind)
    with op.get_context().autocommit_block():
        for tipo in TIPOS_NOVOS:
            op.execute(f"ALTER TYPE notificacao_tipo ADD VALUE IF NOT EXISTS '{tipo}'")

    # 2.
    op.execute("CREATE SEQUENCE metricas_anonima_seq")

    # 3.
    ts = sa.DateTime(timezone=True)
    op.create_table(
        "metricas_series",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rede", platform, nullable=False),
        sa.Column("conta_id", sa.Uuid(), sa.ForeignKey("contas.id"), nullable=True),
        sa.Column("rotulo", sa.Text(), nullable=True),
        sa.Column("anonima_n", sa.Integer(), nullable=True),
        sa.Column("criada_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("varredura_cursor", sa.BigInteger(), nullable=True),
        sa.Column("varredura_concluida_em", ts, nullable=True),
        sa.Column("lista_proxima_em", ts, nullable=True),
        sa.Column("conta_proxima_em", ts, nullable=True),
        sa.Column("ultima_coleta_em", ts, nullable=True),
        sa.Column("ultimo_erro_codigo", sa.Text(), nullable=True),
        sa.Column("ultimo_erro_motivo", sa.Text(), nullable=True),
        sa.Column("ultimo_erro_em", ts, nullable=True),
        sa.Column("adiar_ate", ts, nullable=True),
        sa.Column("sem_permissao_desde", ts, nullable=True),
        sa.Column("anonimizada_em", ts, nullable=True),
        sa.Column("anonimizada_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint(
            "((anonimizada_em IS NULL) = (conta_id IS NOT NULL)) AND (anonimizada_em IS NULL "
            "OR (rotulo IS NOT NULL AND anonima_n IS NOT NULL))",
            name="ck_metricas_series_anonima"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_metricas_series_conta_viva", "metricas_series", ["conta_id"],
                    unique=True, postgresql_where=sa.text("anonimizada_em IS NULL"))
    op.create_index("ix_metricas_series_ativas", "metricas_series", ["lista_proxima_em"],
                    postgresql_where=sa.text("anonimizada_em IS NULL"))

    op.create_table(
        "metricas_videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("serie_id", sa.Uuid(), sa.ForeignKey("metricas_series.id"), nullable=False),
        sa.Column("rede_video_id", sa.Text(), nullable=True),
        sa.Column("share_url", sa.Text(), nullable=True),
        sa.Column("legenda", sa.Text(), nullable=True),
        sa.Column("titulo", sa.Text(), nullable=True),
        sa.Column("duracao_s", sa.Integer(), nullable=False),
        sa.Column("largura", sa.Integer(), nullable=True),
        sa.Column("altura", sa.Integer(), nullable=True),
        sa.Column("publicado_em", ts, nullable=False),
        sa.Column("descoberto_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("disponivel", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("indisponivel_desde", ts, nullable=True),
        sa.Column("proxima_coleta_em", ts, nullable=True),
        sa.Column("ultima_foto_em", ts, nullable=True),
        sa.Column("destino_id", sa.Uuid(), sa.ForeignKey("postagens.id"), nullable=True),
        sa.Column("vinculo_metodo", vinculo_metodo, nullable=True),
        sa.Column("vinculado_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("vinculado_em", ts, nullable=True),
        sa.Column("vinculo_automatico", sa.Boolean(), server_default=sa.text("true"),
                  nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=True),
        sa.Column("anonimizado_em", ts, nullable=True),
        sa.CheckConstraint(
            "((destino_id IS NULL) = (vinculo_metodo IS NULL)) "
            "AND (destino_id IS NULL OR vinculado_em IS NOT NULL)",
            name="ck_metricas_videos_vinculo"),
        sa.CheckConstraint(
            "anonimizado_em IS NULL OR (rede_video_id IS NULL AND share_url IS NULL "
            "AND legenda IS NULL AND titulo IS NULL AND destino_id IS NULL "
            "AND vinculado_por IS NULL AND proxima_coleta_em IS NULL AND features IS NOT NULL)",
            name="ck_metricas_videos_anonimo"),
        sa.CheckConstraint("disponivel OR indisponivel_desde IS NOT NULL",
                           name="ck_metricas_videos_indisponivel"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_metricas_videos_rede_id", "metricas_videos",
                    ["serie_id", "rede_video_id"], unique=True,
                    postgresql_where=sa.text("rede_video_id IS NOT NULL"))
    op.create_index("uq_metricas_videos_destino", "metricas_videos", ["destino_id"],
                    unique=True, postgresql_where=sa.text("destino_id IS NOT NULL"))
    op.create_index("ix_metricas_videos_fila", "metricas_videos", ["proxima_coleta_em"],
                    postgresql_where=sa.text("proxima_coleta_em IS NOT NULL"))
    op.create_index("ix_metricas_videos_serie_pub", "metricas_videos",
                    ["serie_id", sa.literal_column("publicado_em DESC"),
                     sa.literal_column("id DESC")])

    op.create_table(
        "metricas_video_fotos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("metricas_videos.id"), nullable=False),
        sa.Column("coletado_em", ts, nullable=False),
        sa.Column("idade_s", sa.Integer(), nullable=False),
        sa.Column("alvo_idade_min", sa.Integer(), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("fonte", sa.Text(), server_default="display", nullable=False),
        sa.CheckConstraint("idade_s >= 0 AND alvo_idade_min >= 0",
                           name="ck_metricas_video_fotos_idade"),
        sa.CheckConstraint("fonte IN ('display','business')",
                           name="ck_metricas_video_fotos_fonte"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", "alvo_idade_min", name="uq_metricas_video_fotos_janela"),
    )
    op.create_index("ix_metricas_video_fotos_idade", "metricas_video_fotos",
                    ["video_id", "idade_s"])
    op.create_index("ix_metricas_video_fotos_coletado", "metricas_video_fotos",
                    ["coletado_em"])

    op.create_table(
        "metricas_conta_fotos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("serie_id", sa.Uuid(), sa.ForeignKey("metricas_series.id"), nullable=False),
        sa.Column("coletado_em", ts, nullable=False),
        sa.Column("janela_em", ts, nullable=False),
        sa.Column("seguidores", sa.BigInteger(), nullable=True),
        sa.Column("seguindo", sa.BigInteger(), nullable=True),
        sa.Column("curtidas", sa.BigInteger(), nullable=True),
        sa.Column("videos", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serie_id", "janela_em", name="uq_metricas_conta_fotos_janela"),
    )

    op.create_table(
        "metricas_buscas_post",
        sa.Column("destino_id", sa.Uuid(), sa.ForeignKey("postagens.id"), nullable=False),
        sa.Column("tentativa_id", sa.Uuid(), sa.ForeignKey("publicacao_tentativas.id"),
                  nullable=False),
        sa.Column("entregue_em", ts, nullable=False),
        sa.Column("proxima_em", ts, nullable=True),
        sa.Column("consultas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("ultimo_status", sa.Text(), nullable=True),
        sa.Column("post_id", sa.Text(), nullable=True),
        sa.Column("encerrada_em", ts, nullable=True),
        sa.Column("fim", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "((encerrada_em IS NULL) = (fim IS NULL)) "
            "AND (encerrada_em IS NULL OR proxima_em IS NULL)",
            name="ck_metricas_buscas_fim"),
        sa.CheckConstraint(
            "fim IS NULL OR fim IN "
            "('vinculado','prazo','falhou','desfeito','anonimizada','cancelada')",
            name="ck_metricas_buscas_fim_valor"),
        sa.PrimaryKeyConstraint("destino_id"),
    )
    op.create_index("ix_metricas_buscas_fila", "metricas_buscas_post", ["proxima_em"],
                    postgresql_where=sa.text("encerrada_em IS NULL"))

    # 4.
    op.execute(FUNCAO)
    for tabela in FOTOS:
        op.execute(f"CREATE TRIGGER metricas_so_insercao BEFORE UPDATE OR DELETE ON {tabela} "
                   "FOR EACH ROW EXECUTE FUNCTION metricas_recusa_mudanca()")


def downgrade() -> None:
    """Só dev. Desfaz na ordem inversa; as fotos, os vídeos e as séries saem com as tabelas."""
    bind = op.get_bind()
    # 4.
    for tabela in FOTOS:
        op.execute(f"DROP TRIGGER metricas_so_insercao ON {tabela}")
    op.execute("DROP FUNCTION metricas_recusa_mudanca()")

    # 3.
    for tabela in TABELAS:
        op.drop_table(tabela)  # os índices vão junto

    # 2.
    op.execute("DROP SEQUENCE metricas_anonima_seq")

    # 1. Padrão da 0007/0010: os avisos dos tipos novos saem e o tipo é recriado sem eles.
    vinculo_metodo.drop(bind)
    lista = ", ".join(repr(t) for t in TIPOS_NOVOS)
    op.execute(f"DELETE FROM notificacoes WHERE tipo::text IN ({lista})")
    op.execute("ALTER TYPE notificacao_tipo RENAME TO notificacao_tipo_old")
    op.execute(f"CREATE TYPE notificacao_tipo AS ENUM ({', '.join(repr(t) for t in TIPOS_0010)})")
    op.execute("ALTER TABLE notificacoes ALTER COLUMN tipo TYPE notificacao_tipo "
               "USING tipo::text::notificacao_tipo")
    op.execute("DROP TYPE notificacao_tipo_old")
