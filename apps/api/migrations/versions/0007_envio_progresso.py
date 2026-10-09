"""progresso real do envio no OpenShorts (emenda de 2026-09-29 da spec 006, FR-010a)

Colunas anuláveis em `envios` (etapa, % da etapa, clipe N de M e a frase em pt-BR) e o aviso
`envio_momentos` ("momentos escolhidos") em `notificacao_tipo`. O % geral continua em `progress`
e a posição na fila em `openshorts_queue_pos`.

Revision ID: 0007_envio_progresso
Revises: 0006_cortes_openshorts
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_envio_progresso"
down_revision: str | None = "0006_cortes_openshorts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ETAPAS = ("fila", "baixando", "transcrevendo", "escolhendo_momentos", "processando_clipes",
          "legendas", "importando", "concluido", "erro")
TIPOS_0006 = ("envio_pronto", "envio_sem_clipes", "envio_falhou", "envio_confirmar_qualidade",
              "openshorts_fora", "hora_de_postar", "cota_youtube", "canal_erro")


def upgrade() -> None:
    op.add_column("envios", sa.Column("etapa", sa.Text(), nullable=True))
    op.add_column("envios", sa.Column("etapa_pct", sa.SmallInteger(), nullable=True))
    op.add_column("envios", sa.Column("clipe_atual", sa.SmallInteger(), nullable=True))
    op.add_column("envios", sa.Column("clipes_previstos", sa.SmallInteger(), nullable=True))
    op.add_column("envios", sa.Column("etapa_mensagem", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_envios_etapa", "envios",
        f"etapa IS NULL OR etapa IN ({', '.join(repr(e) for e in ETAPAS)})",
    )
    op.create_check_constraint("ck_envios_etapa_pct", "envios",
                               "etapa_pct IS NULL OR etapa_pct BETWEEN 0 AND 100")
    # PG 12+: ADD VALUE roda dentro da transação; o valor novo só não pode ser usado nela.
    op.execute("ALTER TYPE notificacao_tipo ADD VALUE IF NOT EXISTS 'envio_momentos'")


def downgrade() -> None:
    # O PostgreSQL não remove valor de enum: os avisos "momentos escolhidos" saem e o tipo é
    # recriado sem o valor.
    op.execute("DELETE FROM notificacoes WHERE tipo = 'envio_momentos'")
    op.execute("ALTER TYPE notificacao_tipo RENAME TO notificacao_tipo_old")
    op.execute(f"CREATE TYPE notificacao_tipo AS ENUM ({', '.join(repr(t) for t in TIPOS_0006)})")
    op.execute("ALTER TABLE notificacoes ALTER COLUMN tipo TYPE notificacao_tipo "
               "USING tipo::text::notificacao_tipo")
    op.execute("DROP TYPE notificacao_tipo_old")
    op.drop_constraint("ck_envios_etapa_pct", "envios", type_="check")
    op.drop_constraint("ck_envios_etapa", "envios", type_="check")
    for col in ("etapa_mensagem", "clipes_previstos", "clipe_atual", "etapa_pct", "etapa"):
        op.drop_column("envios", col)
