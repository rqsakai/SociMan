"""aprendizado: temas, classificações, preferências, análises, decisões e conferências (spec 023)

Na ordem do data-model:
1. os tipos `aprendizado_origem`, `aprendizado_estilo_gancho`, `aprendizado_analise_estado`,
   `aprendizado_decisao` e `aprendizado_conferencia_resultado`;
2. `aprendizado_temas` (nome único por perfil entre os ativos, pela forma normalizada);
3. `aprendizado_analises` (antes das decisões, que a referenciam) e `aprendizado_preferencias`;
4. `aprendizado_classificacoes`, `aprendizado_decisoes` e `aprendizado_conferencias`;
5. as 3 colunas novas de `ia_chamadas` (as linhas antigas ficam NULL / '{}').

Downgrade (só dev): na ordem inversa.

Revision ID: 0018_aprendizado
Revises: 0017_publico
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_aprendizado"
down_revision: str | None = "0017_publico"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *valores: str) -> postgresql.ENUM:
    return postgresql.ENUM(*valores, name=name, create_type=False)


origem = _enum("aprendizado_origem", "ia", "dono")
estilo = _enum("aprendizado_estilo_gancho", "pergunta", "revelacao", "numero_lista", "polemica",
               "humor", "voce_sabia", "ordem_direta", "outro")
estado_analise = _enum("aprendizado_analise_estado", "pendente", "processando", "pronta", "erro")
decisao = _enum("aprendizado_decisao", "aberta", "aceita", "rejeitada")
resultado = _enum("aprendizado_conferencia_resultado", "ok", "problema", "nao_sei")
TIPOS = (origem, estilo, estado_analise, decisao, resultado)

CHECKLIST = ("restrito", "nao_elegivel_para_voce", "nao_original", "privacidade", "musica",
             "diretrizes")
DECISAO_TIPOS = ("tema_ampliar", "tema_cortar", "hashtag_fixar", "hashtag_evitar",
                 "padrao_gancho", "padrao_duracao", "padrao_horario")


def _auditoria(com_version: bool = True) -> list[sa.Column]:
    ts = sa.DateTime(timezone=True)
    cols = [
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    ]
    if com_version:
        cols.insert(0, sa.Column("version", sa.Integer(), server_default=sa.text("1"),
                                 nullable=False))
    return cols


def _lista(nome: str) -> sa.Column:
    return sa.Column(nome, postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                     nullable=False)


def _in(coluna: str, valores: Sequence[str]) -> str:
    return f"{coluna} IN (" + ", ".join(f"'{v}'" for v in valores) + ")"


def upgrade() -> None:
    bind = op.get_bind()
    ts = sa.DateTime(timezone=True)
    # 1.
    for tipo in TIPOS:
        tipo.create(bind)

    # 2.
    op.create_table(
        "aprendizado_temas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("nome_norm", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), server_default="", nullable=False),
        _lista("palavras_chave"),
        sa.Column("juntado_em_id", sa.Uuid(), sa.ForeignKey("aprendizado_temas.id"),
                  nullable=True),
        sa.Column("archived_at", ts, nullable=True),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        *_auditoria(),
        sa.CheckConstraint("char_length(nome) BETWEEN 1 AND 40",
                           name="ck_aprendizado_temas_nome"),
        sa.CheckConstraint("char_length(descricao) <= 200",
                           name="ck_aprendizado_temas_descricao"),
        sa.CheckConstraint("cardinality(palavras_chave) <= 20",
                           name="ck_aprendizado_temas_palavras"),
        sa.CheckConstraint("juntado_em_id IS NULL OR archived_at IS NOT NULL",
                           name="ck_aprendizado_temas_juntado"),
        sa.CheckConstraint("juntado_em_id IS NULL OR juntado_em_id <> id",
                           name="ck_aprendizado_temas_juntado_outro"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_aprendizado_temas_nome", "aprendizado_temas", ["perfil_id", "nome_norm"],
                    unique=True, postgresql_where=sa.text("archived_at IS NULL"))

    # 3.
    op.create_table(
        "aprendizado_analises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("conta_id", sa.Uuid(), sa.ForeignKey("contas.id"), nullable=True),
        sa.Column("estado", estado_analise, nullable=False),
        sa.Column("medida", sa.Text(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("com_quadros", sa.Boolean(), nullable=False),
        sa.Column("quadros_por_video", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("videos_sem_arquivo", sa.Integer(), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("melhores", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("comparaveis", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("resumo_estatistico", postgresql.JSONB(), nullable=False),
        sa.Column("hipoteses", postgresql.JSONB(), nullable=True),
        sa.Column("custo_estimado_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("chamada_id", sa.Uuid(), sa.ForeignKey("ia_chamadas.id"), nullable=True),
        sa.Column("erro_code", sa.Text(), nullable=True),
        sa.Column("taxonomia_versao", sa.Integer(), nullable=False),
        sa.Column("pedido_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("iniciada_em", ts, nullable=True),
        sa.Column("concluida_em", ts, nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("n BETWEEN 1 AND 15", name="ck_aprendizado_analises_n"),
        sa.CheckConstraint("medida IN ('h1', 'h24', 'd7')",
                           name="ck_aprendizado_analises_medida"),
        sa.CheckConstraint(
            "quadros_por_video IN (0, 4) AND (com_quadros = (quadros_por_video = 4))",
            name="ck_aprendizado_analises_quadros"),
        sa.CheckConstraint("(estado = 'erro') = (erro_code IS NOT NULL)",
                           name="ck_aprendizado_analises_erro"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aprendizado_analises_perfil", "aprendizado_analises",
                    ["perfil_id", sa.text("created_at DESC")])
    op.create_index("ix_aprendizado_analises_fila", "aprendizado_analises",
                    ["estado", "created_at"],
                    postgresql_where=sa.text("estado IN ('pendente', 'processando')"))

    op.create_table(
        "aprendizado_preferencias",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("conta_id", sa.Uuid(), sa.ForeignKey("contas.id"), nullable=True),
        sa.Column("temas", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        _lista("hashtags_evitar"),
        sa.Column("padroes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("taxonomia_versao", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("classificacao_auto", sa.Boolean(), server_default=sa.text("true"),
                  nullable=False),
        sa.Column("usar_desempenho", sa.Boolean(), server_default=sa.text("true"),
                  nullable=False),
        sa.Column("pedido_classificacao_em", ts, nullable=True),
        *_auditoria(),
        sa.CheckConstraint("cardinality(hashtags_evitar) <= 30",
                           name="ck_aprendizado_preferencias_evitar"),
        sa.CheckConstraint("jsonb_array_length(padroes) <= 10",
                           name="ck_aprendizado_preferencias_padroes"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_aprendizado_preferencias_perfil", "aprendizado_preferencias",
                    ["perfil_id"], unique=True, postgresql_where=sa.text("conta_id IS NULL"))
    op.create_index("uq_aprendizado_preferencias_conta", "aprendizado_preferencias",
                    ["conta_id"], unique=True, postgresql_where=sa.text("conta_id IS NOT NULL"))

    # 4.
    op.create_table(
        "aprendizado_classificacoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("metricas_videos.id"), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("tema_id", sa.Uuid(), sa.ForeignKey("aprendizado_temas.id"), nullable=True),
        sa.Column("secundarios", postgresql.ARRAY(sa.Uuid()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("estilo_gancho", estilo, nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.Column("sugestao_tema", sa.Text(), nullable=True),
        sa.Column("origem", origem, nullable=False),
        sa.Column("evidencia_parcial", sa.Boolean(), nullable=False),
        sa.Column("reclassificar", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("taxonomia_versao", sa.Integer(), nullable=False),
        sa.Column("chamada_id", sa.Uuid(), sa.ForeignKey("ia_chamadas.id"), nullable=True),
        *_auditoria(),
        sa.CheckConstraint("cardinality(secundarios) <= 2",
                           name="ck_aprendizado_classificacoes_secundarios"),
        sa.CheckConstraint("tema_id IS NULL OR NOT (tema_id = ANY(secundarios))",
                           name="ck_aprendizado_classificacoes_secundario_principal"),
        sa.CheckConstraint("justificativa IS NULL OR char_length(justificativa) <= 160",
                           name="ck_aprendizado_classificacoes_justificativa"),
        sa.CheckConstraint("sugestao_tema IS NULL OR char_length(sugestao_tema) <= 40",
                           name="ck_aprendizado_classificacoes_sugestao"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", name="uq_aprendizado_classificacoes_video"),
    )
    op.create_index("ix_aprendizado_classificacoes_tema", "aprendizado_classificacoes",
                    ["perfil_id", "tema_id"])
    op.create_index("ix_aprendizado_classificacoes_reclassificar", "aprendizado_classificacoes",
                    ["perfil_id"], postgresql_where=sa.text("reclassificar"))

    op.create_table(
        "aprendizado_decisoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("conta_id", sa.Uuid(), sa.ForeignKey("contas.id"), nullable=True),
        sa.Column("chave", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("analise_id", sa.Uuid(), sa.ForeignKey("aprendizado_analises.id"),
                  nullable=True),
        sa.Column("estado", decisao, nullable=False),
        sa.Column("evidencia", postgresql.JSONB(), nullable=False),
        sa.Column("n_decisao", sa.Integer(), nullable=False),
        sa.Column("faixa_decisao", sa.Text(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("preferencias_version", sa.Integer(), nullable=True),
        sa.Column("decidido_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decidido_em", ts, nullable=True),
        sa.Column("revertida_em", ts, nullable=True),
        sa.Column("revertida_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        *_auditoria(),
        sa.CheckConstraint(_in("tipo", DECISAO_TIPOS), name="ck_aprendizado_decisoes_tipo"),
        sa.CheckConstraint("origem IN ('regra', 'hipotese')",
                           name="ck_aprendizado_decisoes_origem"),
        sa.CheckConstraint("(origem = 'hipotese') = (analise_id IS NOT NULL)",
                           name="ck_aprendizado_decisoes_hipotese"),
        sa.CheckConstraint("estado <> 'aberta' OR origem = 'hipotese'",
                           name="ck_aprendizado_decisoes_aberta"),
        sa.CheckConstraint("texto IS NULL OR char_length(texto) <= 120",
                           name="ck_aprendizado_decisoes_texto"),
        sa.CheckConstraint("motivo IS NULL OR char_length(motivo) <= 300",
                           name="ck_aprendizado_decisoes_motivo"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aprendizado_decisoes_chave", "aprendizado_decisoes",
                    ["perfil_id", "chave", sa.text("decidido_em DESC")])

    op.create_table(
        "aprendizado_conferencias",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("metricas_videos.id"), nullable=False),
        sa.Column("item", sa.Text(), nullable=False),
        sa.Column("resultado", resultado, nullable=False),
        sa.Column("nota", sa.Text(), nullable=True),
        *_auditoria(),
        sa.CheckConstraint(_in("item", CHECKLIST), name="ck_aprendizado_conferencias_item"),
        sa.CheckConstraint("nota IS NULL OR char_length(nota) <= 300",
                           name="ck_aprendizado_conferencias_nota"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", "item", name="uq_aprendizado_conferencias_video_item"),
    )

    # 5.
    op.add_column("ia_chamadas", sa.Column("desempenho_perfil_version", sa.Integer(),
                                           nullable=True))
    op.add_column("ia_chamadas", sa.Column("desempenho_conta_version", sa.Integer(),
                                           nullable=True))
    op.add_column("ia_chamadas", sa.Column("desempenho_exemplos", postgresql.ARRAY(sa.Uuid()),
                                           server_default=sa.text("'{}'"), nullable=False))


def downgrade() -> None:
    op.drop_column("ia_chamadas", "desempenho_exemplos")
    op.drop_column("ia_chamadas", "desempenho_conta_version")
    op.drop_column("ia_chamadas", "desempenho_perfil_version")
    op.drop_table("aprendizado_conferencias")
    op.drop_table("aprendizado_decisoes")
    op.drop_table("aprendizado_classificacoes")
    op.drop_table("aprendizado_preferencias")
    op.drop_table("aprendizado_analises")
    op.drop_table("aprendizado_temas")
    bind = op.get_bind()
    for tipo in reversed(TIPOS):
        tipo.drop(bind)
