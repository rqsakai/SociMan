"""aprendizado: casamento dos vídeos-fonte com os temas do perfil (spec 023, plano B do R9)

O casamento por palavra-chave em título + descrição custa segundos por requisição com dezenas de
milhares de vídeos-fonte; a trilha `aprendizado` grava o resultado aqui (refeito a cada versão
de taxonomia e incremental para os vídeos novos), e o Descobrir e o Mercado só leem.

1. `aprendizado_fonte_temas (perfil_id, video_fonte_id, tema_id)`;
2. em `aprendizado_preferencias` (linha do perfil): `fonte_temas_versao` (a taxonomia casada) e
   `fonte_temas_em` (até onde os vídeos novos já foram casados).

Revision ID: 0019_aprendizado_fonte_temas
Revises: 0018_aprendizado
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_aprendizado_fonte_temas"
down_revision: str | None = "0018_aprendizado"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aprendizado_fonte_temas",
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("video_fonte_id", sa.Uuid(), sa.ForeignKey("videos_fonte.id"), nullable=False),
        sa.Column("tema_id", sa.Uuid(), sa.ForeignKey("aprendizado_temas.id"), nullable=False),
        sa.PrimaryKeyConstraint("perfil_id", "video_fonte_id", "tema_id"),
    )
    op.create_index("ix_aprendizado_fonte_temas_tema", "aprendizado_fonte_temas",
                    ["perfil_id", "tema_id"])
    op.add_column("aprendizado_preferencias",
                  sa.Column("fonte_temas_versao", sa.Integer(), nullable=True))
    op.add_column("aprendizado_preferencias",
                  sa.Column("fonte_temas_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("aprendizado_preferencias", "fonte_temas_em")
    op.drop_column("aprendizado_preferencias", "fonte_temas_versao")
    op.drop_table("aprendizado_fonte_temas")
