"""cadastro padronizado: kit do avatar, cenário padrão, vozes e consentimento (spec 025)

Na ordem do data-model:
1. tipos `asset_origem`, `asset_kit_status`, `voz_origem`, `voz_status`;
2. `asset_file_role` + `kit` e `variacao` (fora da transação, `autocommit_block`, antes dos CHECKs
   e índices que citam os valores novos);
3. a tabela `vozes`, com CHECKs e índices;
4. `assets.origem`, `consentimento`, `voz_id` (FK `vozes`), `identidade`, `kit_status`; recria o
   `ck_assets_campos_por_tipo` e cria o `ck_assets_pessoa_real` e o `ix_assets_voz`;
5. `asset_files.slot` e `geracao_id` (FK `geracoes`); recria o `ck_asset_files_campos_por_papel`;
   cria `uq_asset_files_slot`, `uq_asset_files_variacao_label` e `ix_asset_files_geracao`.
Sem backfill: os assets da 007 ficam com as colunas novas nulas.

Downgrade (só dev): recusa se houver voz, arquivo `kit`/`variacao`, asset com algum campo novo ou
evento `eliminacao_lgpd`; senão remove o que criou e recria os CHECKs da 007. Os valores `kit` e
`variacao` do `asset_file_role` ficam (como a 0015 e a 0022: um valor sem uso é inofensivo).
Nenhum objeto do MinIO é tocado.

Revision ID: 0023_cadastro_padronizado
Revises: 0022_produtos_shop
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_cadastro_padronizado"
down_revision: str | None = "0022_produtos_shop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *valores: str) -> postgresql.ENUM:
    return postgresql.ENUM(*valores, name=name, create_type=False)


asset_origem = _enum("asset_origem", "upload", "sintetico", "pessoa_real")
asset_kit_status = _enum("asset_kit_status", "incompleto", "completo", "atencao")
voz_origem = _enum("voz_origem", "gravacao", "sintetica")
voz_status = _enum("voz_status", "rascunho", "gerando", "revisao", "aprovada")
TIPOS = (asset_origem, asset_kit_status, voz_origem, voz_status)

SLOTS = ("rosto_origem", "rosto_frontal", "rosto_34_esq", "rosto_34_dir", "corpo_base", "cena")

ASSETS_007 = ("(tipo IN ('avatar', 'cenario') OR prompt IS NULL) AND "
              "(tipo = 'avatar' OR (voice_tone IS NULL AND image_rules IS NULL))")
ASSETS_025 = (f"{ASSETS_007} AND (tipo = 'avatar' OR (origem IS NULL AND consentimento IS NULL "
              "AND voz_id IS NULL AND identidade IS NULL)) AND "
              "(tipo IN ('avatar', 'cenario') OR kit_status IS NULL)")
FILES_007 = ("(role = 'pose' OR (label IS NULL AND quando_usar IS NULL)) AND "
             "(role <> 'pose' OR label IS NOT NULL) AND "
             "(role = 'referencia' OR (look IS NULL AND uso IS NULL))")
FILES_025 = ("(role IN ('pose', 'variacao') OR label IS NULL) AND "
             "(role = 'pose' OR quando_usar IS NULL) AND "
             "(role NOT IN ('pose', 'variacao') OR label IS NOT NULL) AND "
             "(role = 'referencia' OR (look IS NULL AND uso IS NULL)) AND "
             "((role = 'kit') = (slot IS NOT NULL)) AND "
             f"(slot IS NULL OR slot IN ({', '.join(repr(s) for s in SLOTS)}))")
REVOGADA = "(consentimento->>'revogado_em') IS NOT NULL"


def upgrade() -> None:
    bind = op.get_bind()
    # 1.
    for tipo in TIPOS:
        tipo.create(bind, checkfirst=True)
    # 2.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE asset_file_role ADD VALUE IF NOT EXISTS 'kit'")
        op.execute("ALTER TYPE asset_file_role ADD VALUE IF NOT EXISTS 'variacao'")

    # 3.
    ts = sa.DateTime(timezone=True)
    op.create_table(
        "vozes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("origem", voz_origem, nullable=False),
        sa.Column("descricao", sa.Text()),
        sa.Column("tom", sa.Text(), nullable=False),
        sa.Column("gravacao_audio_id", sa.Uuid(), sa.ForeignKey("audios.id")),
        sa.Column("ref_audio_id", sa.Uuid(), sa.ForeignKey("audios.id")),
        sa.Column("ref_texto", sa.Text()),
        sa.Column("analise", postgresql.JSONB()),
        sa.Column("consentimento", postgresql.JSONB()),
        sa.Column("status", voz_status, server_default="rascunho", nullable=False),
        sa.Column("sincronizada_em", ts),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", ts),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60 AND name = btrim(name)",
                           name="ck_vozes_name"),
        sa.CheckConstraint("char_length(tom) BETWEEN 1 AND 60", name="ck_vozes_tom"),
        sa.CheckConstraint("descricao IS NULL OR char_length(descricao) <= 1000",
                           name="ck_vozes_descricao"),
        sa.CheckConstraint("((origem = 'sintetica') = (descricao IS NOT NULL)) AND "
                           "(origem = 'gravacao' OR (gravacao_audio_id IS NULL AND "
                           "consentimento IS NULL))", name="ck_vozes_por_origem"),
        sa.CheckConstraint(f"((ref_audio_id IS NULL) = (ref_texto IS NULL)) AND "
                           f"(status <> 'aprovada' OR ref_audio_id IS NOT NULL OR {REVOGADA})",
                           name="ck_vozes_ref"),
    )
    op.create_index("uq_vozes_nome", "vozes", ["perfil_id", sa.text("lower(name)")], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    op.create_index("ix_vozes_perfil", "vozes",
                    ["perfil_id", "archived_at", sa.text("updated_at DESC"), "id"])
    op.create_index("ix_vozes_sync", "vozes", ["id"], postgresql_where=sa.text(
        "sincronizada_em IS NULL AND ref_audio_id IS NOT NULL"))
    op.create_index("ix_vozes_remover", "vozes", ["id"], postgresql_where=sa.text(
        f"sincronizada_em IS NOT NULL AND {REVOGADA}"))

    # 4.
    op.add_column("assets", sa.Column("origem", asset_origem))
    op.add_column("assets", sa.Column("consentimento", postgresql.JSONB()))
    op.add_column("assets", sa.Column("voz_id", sa.Uuid(),
                                      sa.ForeignKey("vozes.id", name="fk_assets_voz")))
    op.add_column("assets", sa.Column("identidade", postgresql.JSONB()))
    op.add_column("assets", sa.Column("kit_status", asset_kit_status))
    op.drop_constraint("ck_assets_campos_por_tipo", "assets", type_="check")
    op.create_check_constraint("ck_assets_campos_por_tipo", "assets", ASSETS_025)
    op.create_check_constraint("ck_assets_pessoa_real", "assets",
                               "origem IS DISTINCT FROM 'pessoa_real' OR consentimento IS NOT NULL")
    op.create_index("ix_assets_voz", "assets", ["voz_id"],
                    postgresql_where=sa.text("voz_id IS NOT NULL"))

    # 5.
    op.add_column("asset_files", sa.Column("slot", sa.Text()))
    op.add_column("asset_files", sa.Column("geracao_id", sa.Uuid(), sa.ForeignKey(
        "geracoes.id", name="fk_asset_files_geracao")))
    op.drop_constraint("ck_asset_files_campos_por_papel", "asset_files", type_="check")
    op.create_check_constraint("ck_asset_files_campos_por_papel", "asset_files", FILES_025)
    op.create_index("uq_asset_files_slot", "asset_files", ["asset_id", "slot"], unique=True,
                    postgresql_where=sa.text("role = 'kit' AND archived_at IS NULL"))
    op.create_index("uq_asset_files_variacao_label", "asset_files",
                    ["asset_id", sa.text("lower(label)")], unique=True,
                    postgresql_where=sa.text("role = 'variacao' AND archived_at IS NULL"))
    op.create_index("ix_asset_files_geracao", "asset_files", ["geracao_id"],
                    postgresql_where=sa.text("geracao_id IS NOT NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    tem = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM vozes) "
        "OR EXISTS (SELECT 1 FROM asset_files WHERE role::text IN ('kit', 'variacao') "
        "OR slot IS NOT NULL OR geracao_id IS NOT NULL) "
        "OR EXISTS (SELECT 1 FROM assets WHERE origem IS NOT NULL OR consentimento IS NOT NULL "
        "OR voz_id IS NOT NULL OR identidade IS NOT NULL OR kit_status IS NOT NULL) "
        "OR EXISTS (SELECT 1 FROM security_events WHERE type = 'eliminacao_lgpd')")).scalar()
    if tem:
        raise RuntimeError("downgrade da 0023 recusado: há vozes, kit ou consentimento gravados")
    op.drop_index("ix_asset_files_geracao", table_name="asset_files")
    op.drop_index("uq_asset_files_variacao_label", table_name="asset_files")
    op.drop_index("uq_asset_files_slot", table_name="asset_files")
    op.drop_constraint("ck_asset_files_campos_por_papel", "asset_files", type_="check")
    op.create_check_constraint("ck_asset_files_campos_por_papel", "asset_files", FILES_007)
    op.drop_column("asset_files", "geracao_id")
    op.drop_column("asset_files", "slot")
    op.drop_index("ix_assets_voz", table_name="assets")
    op.drop_constraint("ck_assets_pessoa_real", "assets", type_="check")
    op.drop_constraint("ck_assets_campos_por_tipo", "assets", type_="check")
    op.create_check_constraint("ck_assets_campos_por_tipo", "assets", ASSETS_007)
    for col in ("kit_status", "identidade", "voz_id", "consentimento", "origem"):
        op.drop_column("assets", col)
    op.drop_table("vozes")
    for tipo in reversed(TIPOS):
        tipo.drop(bind)
