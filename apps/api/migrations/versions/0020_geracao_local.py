"""geração local com candidatos: gerações, opções e áudios (spec 021)

Na ordem do data-model:
1. tipos `geracao_alvo`, `geracao_motor` e `geracao_status` (com `entregue`, só do `voz.teste`);
2. `audios` (irmã de `images` da 003, imutável), `geracoes` (sem a FK `escolhido_id`) e
   `geracao_candidatos` (com `image_par_id`, o lado direito do par do `avatar.rostos_34`); depois
   a FK `fk_geracoes_escolhido` (ciclo entre as duas tabelas);
3. os CHECKs, os índices (inclusive o `uq_geracoes_gpu_rodando`: um job de GPU por vez, R2) e o
   trigger `geracao_candidatos_midia`, que confere a mídia do candidato pelo passo da geração;
4. `ia_chamadas.geracao_id` (o motor `claude`, R14) com índice parcial.

Downgrade (só dev): recusa se houver linha em `geracoes` ou em `audios`; senão derruba a
coluna, as tabelas, o trigger e os tipos. Nenhum objeto do MinIO é tocado.

Revision ID: 0020_geracao_local
Revises: 0019_aprendizado_fonte_temas
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_geracao_local"
down_revision: str | None = "0019_aprendizado_fonte_temas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A lista do FR-002 (15 passos); `geracao/passos.py` repete e o teste cruzado confere.
PASSOS = (
    "avatar.rosto_origem", "avatar.rosto_frontal", "avatar.rostos_34", "avatar.corpo_base",
    "avatar.look", "avatar.pose", "avatar.identidade",
    "voz.gravacao", "voz.design", "voz.teste",
    "produto.ficha", "produto.recorte", "produto.flat",
    "cenario.cena", "cenario.variacao",
)
SEM_MIDIA = ("produto.ficha", "avatar.identidade")
FINAIS = "('escolhido', 'descartada', 'cancelada', 'entregue', 'falhou')"
ERROS = ("gpu_ocupada", "servico_fora", "sem_memoria", "entrada_invalida", "internal")


def _enum(name: str, *valores: str) -> postgresql.ENUM:
    return postgresql.ENUM(*valores, name=name, create_type=False)


geracao_alvo = _enum("geracao_alvo", "asset", "voz", "produto")
geracao_motor = _enum("geracao_motor", "comfyui", "tts", "claude")
geracao_status = _enum("geracao_status", "na_fila", "rodando", "revisao", "escolhido",
                       "descartada", "cancelada", "entregue", "falhou")
TIPOS = (geracao_alvo, geracao_motor, geracao_status)


def _lista(valores: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


TRIGGER_FN = f"""
CREATE FUNCTION geracao_candidatos_midia() RETURNS trigger AS $$
DECLARE
    v_passo text;
BEGIN
    SELECT passo INTO v_passo FROM geracoes WHERE id = NEW.geracao_id;
    IF v_passo IN ({_lista(SEM_MIDIA)}) THEN
        IF NEW.image_id IS NOT NULL OR NEW.image_par_id IS NOT NULL
                OR NEW.audio_id IS NOT NULL THEN
            RAISE EXCEPTION 'geracao_candidatos: passo % não tem mídia', v_passo
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF v_passo = 'avatar.rostos_34' THEN
        IF NEW.image_id IS NULL OR NEW.image_par_id IS NULL OR NEW.audio_id IS NOT NULL THEN
            RAISE EXCEPTION 'geracao_candidatos: o avatar.rostos_34 exige o par de imagens'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        IF num_nonnulls(NEW.image_id, NEW.audio_id) <> 1 OR NEW.image_par_id IS NOT NULL THEN
            RAISE EXCEPTION 'geracao_candidatos: o passo % exige uma imagem ou um áudio', v_passo
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    bind = op.get_bind()
    ts = sa.DateTime(timezone=True)
    # 1.
    for tipo in TIPOS:
        tipo.create(bind)

    # 2.
    op.create_table(
        "audios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("formato", sa.Text(), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("formato IN ('wav', 'm4a', 'ogg', 'mp3')", name="ck_audios_formato"),
        sa.CheckConstraint("sample_rate > 0", name="ck_audios_sample_rate"),
        sa.CheckConstraint("duracao_ms BETWEEN 1 AND 600000", name="ck_audios_duracao"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_audios_sha256"),
        sa.CheckConstraint("bytes > 0", name="ck_audios_bytes"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_audios_object_key"),
    )
    op.create_index("ix_audios_perfil", "audios", ["perfil_id", sa.text("created_at DESC")])

    op.create_table(
        "geracoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("alvo_tipo", geracao_alvo, nullable=False),
        sa.Column("alvo_id", sa.Uuid(), nullable=False),
        sa.Column("passo", sa.Text(), nullable=False),
        sa.Column("motor", geracao_motor, nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("n_opcoes", sa.SmallInteger(), nullable=False),
        sa.Column("status", geracao_status, server_default="na_fila", nullable=False),
        sa.Column("progress", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("etapa_mensagem", sa.Text(), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", ts, nullable=True),
        sa.Column("heartbeat_at", ts, nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("escolhido_id", sa.Uuid(), nullable=True),
        # "Gerar outras": a geração anterior (`deGeracaoId` do contrato).
        sa.Column("de_geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id"), nullable=True),
        sa.Column("started_at", ts, nullable=True),
        sa.Column("finished_at", ts, nullable=True),
        sa.Column("limpa_em", ts, nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint(f"passo IN ({_lista(PASSOS)})", name="ck_geracoes_passo"),
        sa.CheckConstraint("(status = 'escolhido') = (escolhido_id IS NOT NULL)",
                           name="ck_geracoes_escolhido"),
        sa.CheckConstraint(
            f"(error_code IS NULL OR error_code IN ({_lista(ERROS)})) AND "
            "(error_code IS NULL OR status IN ('falhou', 'na_fila'))",
            name="ck_geracoes_erro"),
        sa.CheckConstraint(f"status NOT IN {FINAIS} OR finished_at IS NOT NULL",
                           name="ck_geracoes_final"),
        sa.CheckConstraint("status <> 'entregue' OR passo = 'voz.teste'",
                           name="ck_geracoes_entregue"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_geracoes_progress"),
        sa.CheckConstraint("n_opcoes BETWEEN 1 AND 4", name="ck_geracoes_n"),
        sa.PrimaryKeyConstraint("id"),
    )
    # FR-019 (R2): no máximo um job de GPU rodando, garantido pelo banco.
    op.create_index("uq_geracoes_gpu_rodando", "geracoes", [sa.text("(true)")], unique=True,
                    postgresql_where=sa.text("status = 'rodando' AND motor IN ('comfyui', 'tts')"))
    op.create_index("ix_geracoes_fila", "geracoes",
                    ["motor", "status", "next_attempt_at", "created_at", "id"],
                    postgresql_where=sa.text("status = 'na_fila'"))
    op.create_index("ix_geracoes_alvo", "geracoes",
                    ["alvo_tipo", "alvo_id", sa.text("created_at DESC")])
    op.create_index("ix_geracoes_perfil", "geracoes",
                    ["perfil_id", sa.text("created_at DESC"), "id"])
    op.create_index("ix_geracoes_limpeza", "geracoes", ["finished_at"],
                    postgresql_where=sa.text(f"limpa_em IS NULL AND status IN {FINAIS}"))

    op.create_table(
        "geracao_candidatos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id"), nullable=False),
        sa.Column("numero", sa.SmallInteger(), nullable=False),
        sa.Column("image_id", sa.Uuid(), sa.ForeignKey("images.id"), nullable=True),
        sa.Column("image_par_id", sa.Uuid(), sa.ForeignKey("images.id"), nullable=True),
        sa.Column("audio_id", sa.Uuid(), sa.ForeignKey("audios.id"), nullable=True),
        sa.Column("seed", sa.BigInteger(), nullable=True),
        sa.Column("metricas", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("numero BETWEEN 1 AND 4", name="ck_candidatos_numero"),
        sa.CheckConstraint("image_par_id IS NULL OR image_id IS NOT NULL",
                           name="ck_candidatos_par"),
        sa.CheckConstraint("num_nonnulls(image_id, audio_id) <= 1", name="ck_candidatos_midia"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("geracao_id", "numero", name="uq_candidatos_numero"),
    )
    op.create_index("ix_candidatos_image", "geracao_candidatos", ["image_id"],
                    postgresql_where=sa.text("image_id IS NOT NULL"))
    op.create_index("ix_candidatos_image_par", "geracao_candidatos", ["image_par_id"],
                    postgresql_where=sa.text("image_par_id IS NOT NULL"))
    op.create_index("ix_candidatos_audio", "geracao_candidatos", ["audio_id"],
                    postgresql_where=sa.text("audio_id IS NOT NULL"))
    op.create_foreign_key("fk_geracoes_escolhido", "geracoes", "geracao_candidatos",
                          ["escolhido_id"], ["id"])

    # 3. O trigger lê o passo da geração (só INSERT: a revogação LGPD da 025 zera a mídia).
    op.execute(TRIGGER_FN)
    op.execute("CREATE TRIGGER geracao_candidatos_midia BEFORE INSERT ON geracao_candidatos "
               "FOR EACH ROW EXECUTE FUNCTION geracao_candidatos_midia()")

    # 4.
    op.add_column("ia_chamadas", sa.Column("geracao_id", sa.Uuid(),
                                           sa.ForeignKey("geracoes.id",
                                                         name="fk_ia_chamadas_geracao"),
                                           nullable=True))
    op.create_index("ix_ia_chamadas_geracao", "ia_chamadas", ["geracao_id"],
                    postgresql_where=sa.text("geracao_id IS NOT NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    tem = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM geracoes) OR EXISTS (SELECT 1 FROM audios)")).scalar()
    if tem:
        raise RuntimeError("downgrade da 0020 recusado: há gerações ou áudios gravados")
    op.drop_index("ix_ia_chamadas_geracao", table_name="ia_chamadas")
    op.drop_constraint("fk_ia_chamadas_geracao", "ia_chamadas", type_="foreignkey")
    op.drop_column("ia_chamadas", "geracao_id")
    op.execute("DROP TRIGGER geracao_candidatos_midia ON geracao_candidatos")
    op.execute("DROP FUNCTION geracao_candidatos_midia()")
    op.drop_constraint("fk_geracoes_escolhido", "geracoes", type_="foreignkey")
    op.drop_table("geracao_candidatos")
    op.drop_table("geracoes")
    op.drop_table("audios")
    for tipo in reversed(TIPOS):
        tipo.drop(bind)
