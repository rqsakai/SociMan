"""AI Studio: a biblioteca passa a ser da agência, com perfil base opcional (spec 029)

Na ordem do data-model:
1. `perfil_id` passa a aceitar nulo em `assets`, `cenas`, `produtos`, `vozes` (o perfil base),
   `images`, `audios` (arquivo da agência), `geracoes` e `ia_chamadas` (o perfil base usado);
2. o nome de voz fica único na agência: entre as vozes ativas com o mesmo `lower(name)`, a mais
   antiga fica e as outras ganham " (2)", " (3)"… (cada ajuste é uma versão `system:migration`,
   `details.motivo = "nome_unico_029"`); `uq_vozes_nome` vira `(lower(name)) WHERE archived_at IS NULL`;
3. os índices da lista da agência (`ix_*_lista_agencia`); o `ix_geracoes_alvo` já existe (0020).
Nenhum perfil é mudado: os itens existentes ficam com o perfil atual como perfil base.

Downgrade (só dev): recusa se houver `perfil_id` nulo em qualquer das 8 tabelas; senão volta o
`NOT NULL` e o índice de voz por perfil. Os nomes com sufixo não voltam.

Revision ID: 0024_ai_studio
Revises: 0023_cadastro_padronizado
Create Date: 2026-10-09
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_ai_studio"
down_revision: str | None = "0023_cadastro_padronizado"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABELAS = ("assets", "cenas", "produtos", "vozes", "images", "audios", "geracoes", "ia_chamadas")
LISTAS = ("assets", "cenas", "produtos", "vozes")
ACTOR = "system:migration"


def _nome_livre(conn, base: str, n: int) -> str:
    while True:
        nome = f"{base} ({n})"
        usado = conn.execute(sa.text(
            "SELECT 1 FROM vozes WHERE archived_at IS NULL AND lower(name) = lower(:n)"),
            {"n": nome}).first()
        if usado is None and len(nome) <= 60:
            return nome
        if len(nome) > 60:  # nome no limite: corta a base para caber o sufixo
            base = base[: 60 - len(f" ({n})")]
            continue
        n += 1


def _desduplicar_vozes(conn) -> None:
    grupos = conn.execute(sa.text(
        "SELECT lower(name) FROM vozes WHERE archived_at IS NULL "
        "GROUP BY lower(name) HAVING count(*) > 1")).scalars().all()
    for chave in grupos:
        vozes = conn.execute(sa.text(
            "SELECT id, name, version FROM vozes WHERE archived_at IS NULL AND lower(name) = :k "
            "ORDER BY created_at, id"), {"k": chave}).all()
        for i, (voz_id, nome, version) in enumerate(vozes[1:], start=2):
            novo = _nome_livre(conn, nome, i)
            ultima = conn.execute(sa.text(
                "SELECT after FROM entity_versions WHERE entity_type = 'voz' AND entity_id = :id "
                "ORDER BY version DESC LIMIT 1"), {"id": voz_id}).scalar()
            before = dict(ultima or {"name": nome})
            after = {**before, "name": novo}
            conn.execute(sa.text("UPDATE vozes SET name = :n, version = version + 1 WHERE id = :id"),
                         {"n": novo, "id": voz_id})
            conn.execute(sa.text("""
                INSERT INTO entity_versions (entity_type, entity_id, version, action, actor_kind,
                                             before, after, changed_fields, details)
                VALUES ('voz', :id, :v, 'updated', :actor, CAST(:before AS jsonb),
                        CAST(:after AS jsonb), :fields, CAST(:details AS jsonb))
            """), {"id": voz_id, "v": version + 1, "actor": ACTOR,
                   "before": json.dumps(before), "after": json.dumps(after), "fields": ["name"],
                   "details": json.dumps({"motivo": "nome_unico_029", "migracao": revision})})


def upgrade() -> None:
    conn = op.get_bind()
    for tabela in TABELAS:
        op.alter_column(tabela, "perfil_id", nullable=True)
    _desduplicar_vozes(conn)
    op.drop_index("uq_vozes_nome", table_name="vozes")
    op.create_index("uq_vozes_nome", "vozes", [sa.text("lower(name)")], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    for tabela in LISTAS:
        op.create_index(f"ix_{tabela}_lista_agencia", tabela,
                        ["archived_at", sa.text("updated_at DESC"), "id"])


def downgrade() -> None:
    conn = op.get_bind()
    nulos = {t: conn.execute(sa.text(f"SELECT count(*) FROM {t} WHERE perfil_id IS NULL")).scalar()
             for t in TABELAS}
    nulos = {t: n for t, n in nulos.items() if n}
    if nulos:
        raise RuntimeError(f"0024_ai_studio: há itens sem perfil ({nulos}); o downgrade perderia dados")
    for tabela in LISTAS:
        op.drop_index(f"ix_{tabela}_lista_agencia", table_name=tabela)
    op.drop_index("uq_vozes_nome", table_name="vozes")
    op.create_index("uq_vozes_nome", "vozes", ["perfil_id", sa.text("lower(name)")], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    for tabela in TABELAS:
        op.alter_column(tabela, "perfil_id", nullable=False)
