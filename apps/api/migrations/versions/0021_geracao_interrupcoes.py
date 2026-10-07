"""geração local: contador próprio de interrupções (spec 021, FR-018 e FR-023)

`geracoes.interrupcoes` conta as vezes em que o gerador parou no meio (sem heartbeat há 120 s,
`requeue_stale`). Fica separado de `attempts`, que é o orçamento das esperas por memória e por
serviço fora (6 esperas, R8): uma interrupção não gasta esse orçamento, e só a 3ª interrupção
leva a `falhou`. Aditiva (padrão 0); o downgrade só tira a coluna.

Revision ID: 0021_geracao_interrupcoes
Revises: 0020_geracao_local
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_geracao_interrupcoes"
down_revision: str | None = "0020_geracao_local"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("geracoes", sa.Column("interrupcoes", sa.SmallInteger(),
                                        server_default=sa.text("0"), nullable=False))
    op.create_check_constraint("ck_geracoes_interrupcoes", "geracoes", "interrupcoes >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_geracoes_interrupcoes", "geracoes", type_="check")
    op.drop_column("geracoes", "interrupcoes")
