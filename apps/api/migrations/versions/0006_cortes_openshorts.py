"""canais-fonte, vídeos, envios ao OpenShorts, postagens e notificações (spec 006-cortes-openshorts)

Amplia `cortes` (004): status `revisao`, origem OpenShorts, trecho, textos do gerador,
transcrição e arquivamento; `kit_version`/`kit_tokens` passam a anuláveis (só em `revisao`).

Revision ID: 0006_cortes_openshorts
Revises: 0005_assets
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_cortes_openshorts"
down_revision: str | None = "0005_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


canal_direito = _enum("canal_direito", "proprio", "parceiro", "programa_de_cortes", "sem_acordo")
canal_sync = _enum("canal_sync", "pendente", "sincronizando", "ok", "pausado_cota", "erro")
video_live = _enum("video_live", "nenhum", "ao_vivo", "agendado")
envio_origem = _enum("envio_origem", "canal", "avulso_link", "avulso_arquivo")
envio_status = _enum(
    "envio_status", "selecionado", "na_fila", "aguardando_openshorts", "confirmar_qualidade",
    "processando", "importando", "pronto", "sem_clipes", "falhou", "descartado",
)
direito_envio = _enum(
    "direito_envio", "proprio", "parceiro", "programa_de_cortes", "sem_acordo", "avulso"
)
corte_origem = _enum("corte_origem", "upload", "openshorts")
postagem_estado = _enum("postagem_estado", "rascunho", "agendado", "postado")
notificacao_tipo = _enum(
    "notificacao_tipo", "envio_pronto", "envio_sem_clipes", "envio_falhou",
    "envio_confirmar_qualidade", "openshorts_fora", "hora_de_postar", "cota_youtube",
    "canal_erro",
)
platform = _enum("platform", "tiktok", "youtube", "instagram", "kwai", "facebook", "x", "outra")
ENUMS = (canal_direito, canal_sync, video_live, envio_origem, envio_status, direito_envio,
         corte_origem, postagem_estado, notificacao_tipo)

CORTE_COLUMNS = ("origem", "envio_id", "clip_index", "source_start_ms", "source_end_ms",
                 "openshorts_title", "openshorts_description", "openshorts_score", "transcript",
                 "legenda", "archived_at", "archived_by")


def _ts(name: str, *, nullable: bool = False, now: bool = False) -> sa.Column:
    default = sa.text("now()") if now else None
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _text(name: str, *, nullable: bool = False, default: str | None = None) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=nullable,
                     server_default=default)


def _bool(name: str, default: str | None = None) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False,
                     server_default=sa.text(default) if default else None)


def _jsonb(name: str, *, nullable: bool = False, default: str | None = None) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=nullable,
                     server_default=sa.text(default) if default else None)


def _small(name: str, *, nullable: bool = False, default: str | None = None) -> sa.Column:
    return sa.Column(name, sa.SmallInteger(), nullable=nullable,
                     server_default=sa.text(default) if default else None)


def _version() -> sa.Column:
    return sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False)


def _archive() -> list:
    return [
        _ts("archived_at", nullable=True),
        sa.Column("archived_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["archived_by"], ["users.id"]),
    ]


def _audit() -> list:
    return [
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _ts("updated_at", now=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
    ]


def upgrade() -> None:
    # PG 12+: ADD VALUE roda dentro da transação; o valor novo só não pode ser usado nela (por
    # isso o check de `cortes` abaixo compara `status::text`).
    op.execute("ALTER TYPE corte_status ADD VALUE IF NOT EXISTS 'revisao' BEFORE 'na_fila'")
    for enum in ENUMS:
        enum.create(op.get_bind())

    op.create_table(
        "canais_fonte",
        sa.Column("id", sa.Uuid(), nullable=False),
        _text("youtube_channel_id"),
        _text("handle", nullable=True),
        _text("title"),
        _text("avatar_url", nullable=True),
        sa.Column("subscribers", sa.BigInteger(), nullable=True),
        sa.Column("video_count", sa.Integer(), nullable=True),
        _text("uploads_playlist_id"),
        sa.Column("direito", canal_direito, server_default="sem_acordo", nullable=False),
        _text("direito_evidencia_url", nullable=True),
        _text("direito_evidencia_nota", default=""),
        sa.Column("sync_status", canal_sync, server_default="pendente", nullable=False),
        _jsonb("sync_progress", default="'{}'::jsonb"),
        _text("sync_error", nullable=True),
        _ts("full_synced_at", nullable=True),
        _ts("last_synced_at", nullable=True),
        _ts("next_sync_at", now=True),
        _version(),
        *_archive(),
        *_audit(),
        sa.CheckConstraint("youtube_channel_id ~ '^UC[0-9A-Za-z_-]{22}$'",
                           name="ck_canais_fonte_channel_id"),
        sa.CheckConstraint(
            "direito_evidencia_url IS NULL OR (direito_evidencia_url ~ '^https?://' "
            "AND char_length(direito_evidencia_url) <= 500)",
            name="ck_canais_fonte_evidencia_url",
        ),
        sa.CheckConstraint("char_length(direito_evidencia_nota) <= 2000",
                           name="ck_canais_fonte_evidencia_nota"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("youtube_channel_id"),
    )
    op.create_index("ix_canais_fonte_next_sync_at", "canais_fonte", ["next_sync_at"])

    op.create_table(
        "canal_perfis",
        sa.Column("canal_id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["canal_id"], ["canais_fonte.id"]),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("canal_id", "perfil_id"),
    )

    op.create_table(
        "videos_fonte",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canal_id", sa.Uuid(), nullable=False),
        _text("youtube_video_id"),
        _text("title"),
        _text("description", default=""),
        _text("thumbnail_url", nullable=True),
        _ts("published_at"),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("live", video_live, server_default="nenhum", nullable=False),
        _bool("disponivel", "true"),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        _ts("metrics_at", nullable=True),
        _ts("next_metrics_at"),
        sa.Column("vph_recente", sa.Numeric(14, 2), nullable=True),
        sa.Column("score", sa.Numeric(5, 1), server_default=sa.text("0"), nullable=False),
        _text("score_reason", default=""),
        _jsonb("score_detail", default="'{}'::jsonb"),
        _bool("recomendavel", "false"),
        _ts("first_seen_at", now=True),
        sa.CheckConstraint("char_length(youtube_video_id) = 11",
                           name="ck_videos_fonte_video_id"),
        sa.CheckConstraint("char_length(description) <= 5000",
                           name="ck_videos_fonte_description"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_videos_fonte_score"),
        sa.ForeignKeyConstraint(["canal_id"], ["canais_fonte.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("youtube_video_id"),
    )
    op.create_index("ix_videos_fonte_canal_published", "videos_fonte",
                    ["canal_id", sa.literal_column("published_at DESC")])
    op.create_index("ix_videos_fonte_recomendavel_score", "videos_fonte",
                    ["recomendavel", sa.literal_column("score DESC")])
    op.create_index("ix_videos_fonte_next_metrics_at", "videos_fonte", ["next_metrics_at"])

    op.create_table(
        "video_metricas",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        _ts("observed_at"),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["videos_fonte.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_metricas_video_observed", "video_metricas",
                    ["video_id", sa.literal_column("observed_at DESC")])

    op.create_table(
        "youtube_cota",
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("unidades", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _bool("aviso_enviado", "false"),
        sa.PrimaryKeyConstraint("dia"),
    )

    op.create_table(
        "padroes_corte",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        _small("clip_min_s"),
        _small("clip_max_s"),
        _small("quantidade", nullable=True),
        _text("layout"),
        _text("formato"),
        _text("legenda"),
        _bool("marca_automatica"),
        sa.Column("conta_padrao_id", sa.Uuid(), nullable=True),
        _version(),
        *_audit(),
        sa.CheckConstraint("clip_min_s BETWEEN 5 AND 175", name="ck_padroes_corte_clip_min"),
        sa.CheckConstraint("clip_max_s BETWEEN 10 AND 180 AND clip_max_s >= clip_min_s + 5",
                           name="ck_padroes_corte_clip_max"),
        sa.CheckConstraint("quantidade IS NULL OR quantidade BETWEEN 1 AND 15",
                           name="ck_padroes_corte_quantidade"),
        sa.CheckConstraint("layout IN ('auto', 'none', 'split', 'screencast', 'speaker_cut')",
                           name="ck_padroes_corte_layout"),
        sa.CheckConstraint("formato IN ('vertical', 'square')", name="ck_padroes_corte_formato"),
        sa.CheckConstraint("legenda IN ('kit', 'gerador', 'nenhuma')",
                           name="ck_padroes_corte_legenda"),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.ForeignKeyConstraint(["conta_padrao_id"], ["contas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("perfil_id"),
    )

    op.create_table(
        "envios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), nullable=False),
        sa.Column("origem", envio_origem, nullable=False),
        sa.Column("video_fonte_id", sa.Uuid(), nullable=True),
        sa.Column("canal_fonte_id", sa.Uuid(), nullable=True),
        _text("source_url", nullable=True),
        _text("source_title"),
        _text("upload_key", nullable=True),
        sa.Column("upload_bytes", sa.BigInteger(), nullable=True),
        sa.Column("upload_duration_ms", sa.Integer(), nullable=True),
        _text("upload_sha256", nullable=True),
        sa.Column("status", envio_status, server_default="selecionado", nullable=False),
        _jsonb("config", nullable=True),
        sa.Column("direito_no_envio", direito_envio, nullable=True),
        _bool("aviso_confirmado", "false"),
        _bool("force_low_quality", "false"),
        _text("openshorts_job_id", nullable=True),
        _small("openshorts_queue_pos", nullable=True),
        _small("progress", default="0"),
        _small("clips_total", nullable=True),
        _small("clips_importados", default="0"),
        _small("attempts", default="0"),
        _ts("next_attempt_at", nullable=True),
        _ts("last_polled_at", nullable=True),
        _text("error_code", nullable=True),
        _text("error_message", nullable=True),
        _ts("sent_at", nullable=True),
        _ts("started_at", nullable=True),
        _ts("finished_at", nullable=True),
        _version(),
        *_archive(),
        *_audit(),
        sa.CheckConstraint(
            "origem <> 'canal' OR (video_fonte_id IS NOT NULL AND source_url IS NOT NULL)",
            name="ck_envios_origem_canal",
        ),
        sa.CheckConstraint("origem <> 'avulso_link' OR source_url IS NOT NULL",
                           name="ck_envios_origem_link"),
        sa.CheckConstraint("origem <> 'avulso_arquivo' OR upload_key IS NOT NULL",
                           name="ck_envios_origem_arquivo"),
        sa.CheckConstraint(
            "status IN ('selecionado', 'descartado') "
            "OR (config IS NOT NULL AND direito_no_envio IS NOT NULL)",
            name="ck_envios_enviado_config",
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_envios_progress"),
        sa.CheckConstraint("char_length(source_title) BETWEEN 1 AND 200",
                           name="ck_envios_source_title"),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfis.id"]),
        sa.ForeignKeyConstraint(["video_fonte_id"], ["videos_fonte.id"]),
        sa.ForeignKeyConstraint(["canal_fonte_id"], ["canais_fonte.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_key"),
    )
    op.create_index("ix_envios_status_next_attempt", "envios", ["status", "next_attempt_at"])
    op.create_index("ix_envios_perfil_created", "envios",
                    ["perfil_id", sa.literal_column("created_at DESC")])
    op.create_index("ix_envios_perfil_video_ativo", "envios", ["perfil_id", "video_fonte_id"],
                    postgresql_where=sa.text("archived_at IS NULL"))

    # ---- cortes (004), ampliada: as linhas antigas ficam com origem = 'upload'.
    op.add_column("cortes", sa.Column("origem", corte_origem, server_default="upload",
                                      nullable=False))
    op.add_column("cortes", sa.Column("envio_id", sa.Uuid(), nullable=True))
    op.add_column("cortes", _small("clip_index", nullable=True))
    op.add_column("cortes", sa.Column("source_start_ms", sa.Integer(), nullable=True))
    op.add_column("cortes", sa.Column("source_end_ms", sa.Integer(), nullable=True))
    op.add_column("cortes", _text("openshorts_title", nullable=True))
    op.add_column("cortes", _text("openshorts_description", nullable=True))
    op.add_column("cortes", _small("openshorts_score", nullable=True))
    op.add_column("cortes", _text("transcript", nullable=True))
    op.add_column("cortes", _text("legenda", nullable=True))
    op.add_column("cortes", _ts("archived_at", nullable=True))
    op.add_column("cortes", sa.Column("archived_by", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_cortes_envio_id", "cortes", "envios", ["envio_id"], ["id"])
    op.create_foreign_key("fk_cortes_archived_by", "cortes", "users", ["archived_by"], ["id"])
    op.create_unique_constraint("uq_cortes_envio_clip", "cortes", ["envio_id", "clip_index"])
    op.alter_column("cortes", "kit_version", nullable=True)
    op.alter_column("cortes", "kit_tokens", nullable=True)
    op.create_check_constraint(
        "ck_cortes_kit", "cortes",
        "status::text = 'revisao' OR (kit_version IS NOT NULL AND kit_tokens IS NOT NULL)",
    )
    op.create_check_constraint("ck_cortes_origem_envio", "cortes",
                               "origem <> 'openshorts' OR envio_id IS NOT NULL")
    op.create_check_constraint(
        "ck_cortes_legenda", "cortes",
        "legenda IS NULL OR legenda IN ('kit', 'gerador', 'nenhuma', 'sem_fala')",
    )

    op.create_table(
        "sugestoes_texto",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corte_id", sa.Uuid(), nullable=False),
        sa.Column("plataforma", platform, nullable=False),
        _text("model"),
        _text("prompt_version"),
        _jsonb("resultado", nullable=True),
        sa.Column("ajustes", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        _text("erro_code", nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        _ts("created_at", now=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["corte_id"], ["cortes.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "postagens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corte_id", sa.Uuid(), nullable=False),
        sa.Column("conta_id", sa.Uuid(), nullable=False),
        _text("titulo", default=""),
        _text("descricao", default=""),
        sa.Column("hashtags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("estado", postagem_estado, server_default="rascunho", nullable=False),
        _ts("planned_at", nullable=True),
        _ts("lembrado_em", nullable=True),
        _ts("posted_at", nullable=True),
        _text("posted_url", nullable=True),
        sa.Column("sugestao_id", sa.Uuid(), nullable=True),
        _version(),
        *_archive(),
        *_audit(),
        sa.CheckConstraint("char_length(titulo) <= 100", name="ck_postagens_titulo"),
        sa.CheckConstraint("char_length(descricao) <= 2000", name="ck_postagens_descricao"),
        sa.CheckConstraint("estado <> 'agendado' OR planned_at IS NOT NULL",
                           name="ck_postagens_agendado_planned"),
        sa.ForeignKeyConstraint(["corte_id"], ["cortes.id"]),
        sa.ForeignKeyConstraint(["conta_id"], ["contas.id"]),
        sa.ForeignKeyConstraint(["sugestao_id"], ["sugestoes_texto.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_postagens_corte_conta_ativa", "postagens", ["corte_id", "conta_id"],
                    unique=True, postgresql_where=sa.text("archived_at IS NULL"))
    op.create_index("ix_postagens_estado_planned", "postagens", ["estado", "planned_at"])

    op.create_table(
        "notificacoes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", notificacao_tipo, nullable=False),
        _text("titulo"),
        _text("corpo", default=""),
        _text("link"),
        _text("entity_type", nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        _text("dedupe_key"),
        _ts("created_at", now=True),
        _ts("lida_em", nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notificacoes_user_dedupe"),
    )
    op.create_index("ix_notificacoes_user_id_desc", "notificacoes",
                    ["user_id", sa.literal_column("id DESC")])
    op.create_index("ix_notificacoes_user_nao_lidas", "notificacoes", ["user_id"],
                    postgresql_where=sa.text("lida_em IS NULL"))


def downgrade() -> None:
    # Os índices caem junto com as tabelas.
    op.drop_table("notificacoes")
    op.drop_table("postagens")
    op.drop_table("sugestoes_texto")

    # cortes: sem as colunas da 006. Se existir corte em `revisao` (sem kit), o NOT NULL ou o
    # cast falha e o downgrade para (nada é apagado).
    for name in ("ck_cortes_legenda", "ck_cortes_origem_envio", "ck_cortes_kit"):
        op.drop_constraint(name, "cortes", type_="check")
    op.drop_constraint("uq_cortes_envio_clip", "cortes", type_="unique")
    op.drop_constraint("fk_cortes_archived_by", "cortes", type_="foreignkey")
    op.drop_constraint("fk_cortes_envio_id", "cortes", type_="foreignkey")
    for column in reversed(CORTE_COLUMNS):
        op.drop_column("cortes", column)
    op.alter_column("cortes", "kit_tokens", nullable=False)
    op.alter_column("cortes", "kit_version", nullable=False)

    # O PostgreSQL não remove valor de enum: recria `corte_status` sem 'revisao'. Os checks que
    # comparam `status` com literais do tipo são recriados em volta da troca.
    op.drop_constraint("ck_cortes_pronto_result", "cortes", type_="check")
    op.drop_constraint("ck_cortes_falhou_message", "cortes", type_="check")
    op.execute("ALTER TABLE cortes ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE corte_status RENAME TO corte_status_old")
    op.execute("CREATE TYPE corte_status AS ENUM ('na_fila', 'processando', 'pronto', 'falhou')")
    op.execute(
        "ALTER TABLE cortes ALTER COLUMN status TYPE corte_status "
        "USING status::text::corte_status"
    )
    op.execute("ALTER TABLE cortes ALTER COLUMN status SET DEFAULT 'na_fila'")
    op.execute("DROP TYPE corte_status_old")
    op.create_check_constraint("ck_cortes_pronto_result", "cortes",
                               "status <> 'pronto' OR result_key IS NOT NULL")
    op.create_check_constraint("ck_cortes_falhou_message", "cortes",
                               "status <> 'falhou' OR error_message IS NOT NULL")

    op.drop_table("envios")
    op.drop_table("padroes_corte")
    op.drop_table("youtube_cota")
    op.drop_table("video_metricas")
    op.drop_table("videos_fonte")
    op.drop_table("canal_perfis")
    op.drop_table("canais_fonte")
    for enum in reversed(ENUMS):
        enum.drop(op.get_bind())
