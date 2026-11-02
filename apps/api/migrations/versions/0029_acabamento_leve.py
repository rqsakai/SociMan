"""Spec 031 (T059, 2026-10-15): o acabamento do roteiro vira escolha (`leve` padrão, `hd` opcional).

Revision ID: 0029_acabamento_leve
Revises: 0028_video_guiado
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_acabamento_leve"
down_revision: str | None = "0028_video_guiado"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

roteiro_acabamento = postgresql.ENUM("leve", "hd", name="roteiro_acabamento", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    roteiro_acabamento.create(bind, checkfirst=True)
    op.add_column("roteiros", sa.Column("acabamento_modo", roteiro_acabamento, nullable=False,
                                        server_default="leve"))


def downgrade() -> None:
    op.drop_column("roteiros", "acabamento_modo")
    roteiro_acabamento.drop(op.get_bind(), checkfirst=True)
