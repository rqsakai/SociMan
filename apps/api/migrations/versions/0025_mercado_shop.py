"""mercado do TikTok Shop: lago, operação da coleta, interesse e infra do dono (spec 026)

Na ordem do data-model ("Migração 0025_mercado_shop"):
1. os 11 tipos novos e os 6 valores novos de `notificacao_tipo` (`autocommit_block`, como a 0011);
2. infra do dono: `coleta_clientes`, `coleta_config`;
3. o lago, na ordem das FKs (`mercado_coletas` antes de `mercado_produtos`; a FK
   `mercado_produtos.ficha_atual_id` entra depois da tabela de fichas);
4. operação: `mercado_fila`, `mercado_coleta_itens`, `coleta_eventos` e a FK
   `mercado_coletas.tarefa_atual_id` (ciclo fila ↔ coletas);
5. interesse: `mercado_interesses` (a FK para `produtos` da 012 **só se a tabela existir**) e
   `mercado_perfil_config`;
6. o trigger `mercado_so_insercao` (função `metricas_recusa_mudanca()` da 0011) nas 11 tabelas
   só de inserção;
7. `produtos.mercado_produto_id` + FK + índice, **só se a tabela `produtos` existir** (a 012 é
   implementada em outra sessão; sem ela, a coluna fica para a migration de ligação).

Downgrade (só dev): recusa com dados em `mercado_produtos`, `mercado_coletas` ou
`coleta_clientes`; senão remove na ordem inversa e tira os 6 avisos novos de `notificacoes`.
Nenhum objeto do MinIO é tocado.

Revision ID: 0025_mercado_shop
Revises: 0021_geracao_interrupcoes
Create Date: 2026-10-09
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_mercado_shop"
down_revision: str | None = "0021_geracao_interrupcoes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

TIPOS_NOTIFICACAO = ("coleta_captcha", "coleta_login", "coleta_bloqueio", "coleta_layout",
                     "coleta_parada", "mercado_interesse_auto")
# Os tipos até a 0021 (a 0011 trouxe os seus e a 0018/0020 não acrescentaram): recriados no
# downgrade, no padrão da 0011.
TIPOS_ANTERIORES = ("envio_pronto", "envio_sem_clipes", "envio_falhou", "envio_confirmar_qualidade",
                    "openshorts_fora", "hora_de_postar", "cota_youtube", "canal_erro",
                    "envio_momentos", "aprovacao_pedida", "aprovacao_respondida",
                    "rascunho_criado", "envio_publicado", "envio_rede_falhou",
                    "envio_aguardando_vaga", "conexao_precisa_reconectar", "post_detectado",
                    "vinculo_a_confirmar")

ENUMS = {
    "mercado_calor": ("quente", "morna", "parada"),
    "mercado_turno": ("manha", "noite"),
    "mercado_fonte": ("pagina_publica", "affiliate"),
    "mercado_ranking_tipo": ("mais_vendidos", "em_alta", "novos", "alta_comissao"),
    "mercado_fila_estado": ("pendente", "reservada", "recebida", "falhou", "expirada"),
    "mercado_coleta_estado": ("ativa", "pausada_captcha", "pausada_login", "interrompida",
                              "encerrada", "abortada"),
    "mercado_coleta_item_status": ("gravado", "repetido", "invalido", "erro", "captcha"),
    "coleta_evento_tipo": ("captcha", "login_perdido", "bloqueio_suspeito", "layout_mudou",
                           "parar_local", "retomou", "iniciado", "parado"),
    "mercado_interesse_origem": ("manual", "vitrine", "ranking", "video", "loja", "categoria"),
    "mercado_interesse_situacao": ("ativo", "pausado", "encerrado"),
    "coleta_situacao": ("ativo", "suspenso", "revogado"),
}
FILA_TIPOS = ("produto", "ranking", "categorias", "vitrine", "loja", "avaliacoes",
              "produto_videos", "busca_assunto", "video")
FILA_FONTES = ("pagina_publica", "affiliate", "ambas")
RANKING_JANELAS = ("1d", "7d", "30d", "total")
IMAGEM_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "image/avif", "image/gif")
MERCADO_CHECK = "mercado ~ '^[A-Z]{2}$'"

SO_INSERCAO = ("mercado_loja_fotos", "mercado_produto_fichas", "mercado_imagens",
               "mercado_produto_imagens", "mercado_produto_fotos", "mercado_ranking_fotos",
               "mercado_ranking_foto_itens", "mercado_avaliacoes", "mercado_produto_videos",
               "mercado_coleta_itens", "coleta_eventos")
# Ordem do DROP (as que dependem primeiro).
TABELAS = ("mercado_perfil_config", "mercado_interesses", "coleta_eventos",
           "mercado_coleta_itens", "mercado_fila", "mercado_produto_videos",
           "mercado_avaliacoes", "mercado_ranking_foto_itens", "mercado_ranking_fotos",
           "mercado_loja_fotos", "mercado_produto_fotos", "mercado_produto_imagens",
           "mercado_imagens", "mercado_produto_fichas", "mercado_produtos", "mercado_coletas",
           "mercado_lojas", "mercado_categorias", "coleta_config", "coleta_clientes")


def _enum(nome: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[nome], name=nome, create_type=False)


def _in(coluna: str, valores: tuple[str, ...]) -> str:
    return f"{coluna} IN ({', '.join(repr(v) for v in valores)})"


platform = postgresql.ENUM(name="platform", create_type=False)
ts = sa.DateTime(timezone=True)


def _jsonb(default: str = "{}") -> sa.Column:
    return sa.Column("campos", postgresql.JSONB(), server_default=sa.text(f"'{default}'::jsonb"),
                     nullable=False)


def _bruto() -> list[sa.Column]:
    return [sa.Column("esquema_versao", sa.Text(), nullable=False),
            sa.Column("bruto_ref", sa.Text(), nullable=True),
            sa.Column("coleta_id", sa.Uuid(), sa.ForeignKey("mercado_coletas.id"),
                      nullable=False),
            sa.Column("coletado_em", ts, nullable=False)]


def _auditoria() -> list[sa.Column]:
    return [sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False)]


def _tem_produtos() -> bool:
    return sa.inspect(op.get_bind()).has_table("produtos")


def upgrade() -> None:
    bind = op.get_bind()
    # 1. tipos
    for nome, valores in ENUMS.items():
        postgresql.ENUM(*valores, name=nome).create(bind, checkfirst=True)
    with op.get_context().autocommit_block():
        for tipo in TIPOS_NOTIFICACAO:
            op.execute(f"ALTER TYPE notificacao_tipo ADD VALUE IF NOT EXISTS '{tipo}'")

    # 2. infra do dono
    op.create_table(
        "coleta_clientes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("nome_normalizado", sa.Text(), nullable=False, unique=True),
        sa.Column("descricao", sa.Text(), server_default="", nullable=False),
        sa.Column("rede", platform, server_default="tiktok", nullable=False),
        sa.Column("mercado", sa.Text(), nullable=False),
        sa.Column("situacao", _enum("coleta_situacao"), server_default="ativo", nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False, unique=True),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("token_emitido_em", ts, nullable=False),
        sa.Column("expira_em", ts, nullable=True),
        sa.Column("limite_por_minuto", sa.Integer(), server_default=sa.text("120"),
                  nullable=False),
        sa.Column("ultimo_contato_em", ts, nullable=True),
        sa.Column("versao_coletor", sa.Text(), nullable=True),
        sa.Column("chrome_versao", sa.Text(), nullable=True),
        sa.Column("revogado_em", ts, nullable=True),
        sa.Column("revogado_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        *_auditoria(),
        sa.CheckConstraint("char_length(nome) BETWEEN 1 AND 60", name="ck_coleta_clientes_nome"),
        sa.CheckConstraint("char_length(descricao) <= 300", name="ck_coleta_clientes_descricao"),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_coleta_clientes_mercado"),
        sa.CheckConstraint("limite_por_minuto BETWEEN 1 AND 600",
                           name="ck_coleta_clientes_limite_min"),
    )
    op.create_table(
        "coleta_config",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("habilitada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("risco_aceito_em", ts, nullable=True),
        sa.Column("risco_aceito_por", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("risco_texto_versao", sa.Text(), nullable=True),
        sa.Column("janela_inicio", sa.SmallInteger(), server_default=sa.text("8"),
                  nullable=False),
        sa.Column("janela_fim", sa.SmallInteger(), server_default=sa.text("23"), nullable=False),
        sa.Column("paginas_dia", sa.Integer(), server_default=sa.text("300"), nullable=False),
        sa.Column("imagens_dia", sa.Integer(), server_default=sa.text("1500"), nullable=False),
        sa.Column("imagens_por_produto", sa.SmallInteger(), server_default=sa.text("9"),
                  nullable=False),
        sa.Column("itens_por_coleta", sa.SmallInteger(), server_default=sa.text("40"),
                  nullable=False),
        sa.Column("pausa_min_s", sa.SmallInteger(), server_default=sa.text("5"), nullable=False),
        sa.Column("pausa_max_s", sa.SmallInteger(), server_default=sa.text("40"), nullable=False),
        sa.Column("pausada_ate", ts, nullable=True),
        sa.Column("continuar_em", ts, nullable=True),
        *_auditoria(),
        sa.CheckConstraint("id = 1", name="ck_coleta_config_unica"),
        sa.CheckConstraint("NOT habilitada OR risco_aceito_em IS NOT NULL",
                           name="ck_coleta_config_risco"),
        sa.CheckConstraint("janela_inicio BETWEEN 0 AND 23 AND janela_fim BETWEEN 0 AND 23 "
                           "AND janela_inicio < janela_fim", name="ck_coleta_config_janela"),
        sa.CheckConstraint("paginas_dia BETWEEN 1 AND 2000", name="ck_coleta_config_paginas"),
        sa.CheckConstraint("imagens_dia BETWEEN 0 AND 20000", name="ck_coleta_config_imagens"),
        sa.CheckConstraint("imagens_por_produto BETWEEN 0 AND 20",
                           name="ck_coleta_config_imagens_produto"),
        sa.CheckConstraint("itens_por_coleta BETWEEN 1 AND 50", name="ck_coleta_config_itens"),
        sa.CheckConstraint("1 <= pausa_min_s AND pausa_min_s <= pausa_max_s AND "
                           "pausa_max_s <= 600", name="ck_coleta_config_pausas"),
    )

    # 3. lago
    op.create_table(
        "mercado_categorias",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rede", platform, nullable=False),
        sa.Column("mercado", sa.Text(), nullable=False),
        sa.Column("rede_categoria_id", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("nivel", sa.SmallInteger(), nullable=False),
        sa.Column("pai_id", sa.Uuid(), sa.ForeignKey("mercado_categorias.id"), nullable=True),
        sa.Column("caminho", sa.Text(), nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("primeira_vez_em", ts, nullable=False),
        sa.Column("ultimo_visto_em", ts, nullable=False),
        sa.Column("coleta_id", sa.Uuid(), nullable=True),  # FK depois de mercado_coletas
        sa.UniqueConstraint("rede", "mercado", "rede_categoria_id", name="uq_mercado_categorias"),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_mercado_categorias_mercado"),
        sa.CheckConstraint("nivel BETWEEN 1 AND 3", name="ck_mercado_categorias_nivel"),
        sa.CheckConstraint("(nivel = 1) = (pai_id IS NULL)", name="ck_mercado_categorias_pai"),
    )
    op.create_index("ix_mercado_categorias_pai", "mercado_categorias", ["pai_id"])
    op.create_index("ix_mercado_categorias_ativas", "mercado_categorias",
                    ["rede", "mercado", "nivel"], postgresql_where=sa.text("ativa"))

    op.create_table(
        "mercado_lojas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rede", platform, nullable=False),
        sa.Column("mercado", sa.Text(), nullable=False),
        sa.Column("rede_loja_id", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("oficial", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("primeira_vez_em", ts, nullable=False),
        sa.Column("ultimo_visto_em", ts, nullable=False),
        sa.Column("ultima_foto_em", sa.Date(), nullable=True),
        sa.Column("proxima_coleta_em", ts, nullable=True),
        sa.Column("coleta_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("rede", "mercado", "rede_loja_id", name="uq_mercado_lojas"),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_mercado_lojas_mercado"),
    )
    op.create_index("ix_mercado_lojas_nome", "mercado_lojas",
                    ["rede", "mercado", sa.text("lower(nome)")])

    op.create_table(
        "mercado_coletas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cliente_id", sa.Uuid(), sa.ForeignKey("coleta_clientes.id"), nullable=False),
        sa.Column("rede", platform, nullable=False),
        sa.Column("mercado", sa.Text(), nullable=False),
        sa.Column("iniciada_em", ts, nullable=False),
        sa.Column("batimento_em", ts, nullable=False),
        sa.Column("terminada_em", ts, nullable=True),
        sa.Column("estado", _enum("mercado_coleta_estado"), server_default="ativa",
                  nullable=False),
        sa.Column("tarefa_atual_id", sa.Uuid(), nullable=True),  # FK depois de mercado_fila
        sa.Column("paginas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("imagens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("itens_ok", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("itens_erro", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("itens_repetidos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("versao_coletor", sa.Text(), nullable=False),
        sa.Column("chrome_versao", sa.Text(), nullable=True),
        sa.Column("protocolo", sa.SmallInteger(), nullable=False),
        sa.Column("resumo", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_mercado_coletas_mercado"),
        sa.CheckConstraint("estado IN ('ativa', 'pausada_captcha', 'pausada_login') "
                           "OR terminada_em IS NOT NULL", name="ck_mercado_coletas_terminada"),
    )
    op.create_index("uq_mercado_coletas_aberta", "mercado_coletas", ["cliente_id"], unique=True,
                    postgresql_where=sa.text(
                        "estado IN ('ativa', 'pausada_captcha', 'pausada_login')"))
    op.create_index("ix_mercado_coletas_cliente", "mercado_coletas",
                    ["cliente_id", sa.text("iniciada_em DESC")])
    for tabela in ("mercado_categorias", "mercado_lojas"):
        op.create_foreign_key(f"fk_{tabela}_coleta", tabela, "mercado_coletas", ["coleta_id"],
                              ["id"])

    op.create_table(
        "mercado_produtos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rede", platform, nullable=False),
        sa.Column("mercado", sa.Text(), nullable=False),
        sa.Column("rede_produto_id", sa.Text(), nullable=False),
        sa.Column("url_canonica", sa.Text(), nullable=False),
        sa.Column("titulo_atual", sa.Text(), nullable=True),
        sa.Column("loja_id", sa.Uuid(), sa.ForeignKey("mercado_lojas.id"), nullable=True),
        sa.Column("categoria_id", sa.Uuid(), sa.ForeignKey("mercado_categorias.id"),
                  nullable=True),
        sa.Column("ficha_atual_id", sa.Uuid(), nullable=True),  # FK depois das fichas
        sa.Column("primeira_vez_em", ts, nullable=False),
        sa.Column("lancado_em", sa.Date(), nullable=True),
        sa.Column("ultimo_visto_em", ts, nullable=False),
        sa.Column("ultima_foto_em", sa.Date(), nullable=True),
        sa.Column("ultima_foto_affiliate_em", sa.Date(), nullable=True),
        sa.Column("ultimas_avaliacoes_em", sa.Date(), nullable=True),
        sa.Column("ultimos_videos_em", sa.Date(), nullable=True),
        sa.Column("indisponivel_desde", sa.Date(), nullable=True),
        sa.Column("calor", _enum("mercado_calor"), server_default="quente", nullable=False),
        sa.Column("fotos_por_dia", sa.SmallInteger(), server_default=sa.text("1"),
                  nullable=False),
        sa.Column("proxima_coleta_em", ts, nullable=True),
        sa.Column("ultimo_erro_codigo", sa.Text(), nullable=True),
        sa.Column("ultimo_erro_em", ts, nullable=True),
        sa.Column("imagens_pendentes", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("fonte_descoberta", _enum("mercado_interesse_origem"), nullable=False),
        sa.Column("ultimo_ranking_em", sa.Date(), nullable=True),
        sa.Column("coleta_id", sa.Uuid(), sa.ForeignKey("mercado_coletas.id"), nullable=True),
        sa.UniqueConstraint("rede", "mercado", "rede_produto_id", name="uq_mercado_produtos"),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_mercado_produtos_mercado"),
        sa.CheckConstraint("fotos_por_dia BETWEEN 1 AND 2", name="ck_mercado_produtos_fotos_dia"),
    )
    op.create_index("ix_mercado_produtos_fila", "mercado_produtos", ["calor", "proxima_coleta_em"],
                    postgresql_where=sa.text("calor <> 'parada'"))
    op.create_index("ix_mercado_produtos_loja", "mercado_produtos", ["loja_id"])
    op.create_index("ix_mercado_produtos_categoria", "mercado_produtos", ["categoria_id"])
    op.create_index("ix_mercado_produtos_primeira", "mercado_produtos",
                    ["rede", "mercado", sa.text("primeira_vez_em DESC")])
    op.create_index("ix_mercado_produtos_titulo", "mercado_produtos",
                    [sa.text("to_tsvector('portuguese', coalesce(titulo_atual, ''))")],
                    postgresql_using="gin")

    op.create_table(
        "mercado_produto_fichas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("mercado_produtos.id"), nullable=False),
        sa.Column("hash_conteudo", sa.Text(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), server_default="", nullable=False),
        sa.Column("atributos", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("variantes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("argumentos", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("selos", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("categoria_id", sa.Uuid(), sa.ForeignKey("mercado_categorias.id"),
                  nullable=True),
        sa.Column("loja_id", sa.Uuid(), sa.ForeignKey("mercado_lojas.id"), nullable=True),
        sa.Column("imagens_sha", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        *_bruto(),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("produto_id", "hash_conteudo", name="uq_mercado_fichas_conteudo"),
    )
    op.create_index("ix_mercado_fichas_produto", "mercado_produto_fichas",
                    ["produto_id", sa.text("created_at DESC")])
    op.create_foreign_key("fk_mercado_produtos_ficha_atual", "mercado_produtos",
                          "mercado_produto_fichas", ["ficha_atual_id"], ["id"])

    op.create_table(
        "mercado_imagens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sha256", sa.Text(), nullable=False, unique=True),
        sa.Column("object_key", sa.Text(), nullable=False, unique=True),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("coleta_id", sa.Uuid(), sa.ForeignKey("mercado_coletas.id"), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in("content_type", IMAGEM_CONTENT_TYPES),
                           name="ck_mercado_imagens_content_type"),
        sa.CheckConstraint("origem IN ('produto', 'avaliacao')", name="ck_mercado_imagens_origem"),
    )
    op.create_table(
        "mercado_produto_imagens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("mercado_produtos.id"), nullable=False),
        sa.Column("ficha_id", sa.Uuid(), sa.ForeignKey("mercado_produto_fichas.id"),
                  nullable=False),
        sa.Column("imagem_id", sa.Uuid(), sa.ForeignKey("mercado_imagens.id"), nullable=False),
        sa.Column("posicao", sa.SmallInteger(), nullable=False),
        sa.UniqueConstraint("ficha_id", "posicao", name="uq_mercado_produto_imagens_posicao"),
    )
    op.create_index("ix_mercado_produto_imagens_imagem", "mercado_produto_imagens", ["imagem_id"])

    op.create_table(
        "mercado_produto_fotos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("mercado_produtos.id"), nullable=False),
        sa.Column("data_local", sa.Date(), nullable=False),
        sa.Column("turno", _enum("mercado_turno"), nullable=False),
        sa.Column("fonte", _enum("mercado_fonte"), nullable=False),
        sa.Column("vendidos", sa.BigInteger(), nullable=True),
        sa.Column("vendidos_min", sa.BigInteger(), nullable=True),
        sa.Column("vendidos_max", sa.BigInteger(), nullable=True),
        sa.Column("vendidos_exato", sa.Boolean(), nullable=True),
        sa.Column("preco_min_centavos", sa.Integer(), nullable=True),
        sa.Column("preco_max_centavos", sa.Integer(), nullable=True),
        sa.Column("preco_original_centavos", sa.Integer(), nullable=True),
        sa.Column("moeda", sa.Text(), nullable=False),
        sa.Column("nota", sa.Numeric(3, 2), nullable=True),
        sa.Column("n_avaliacoes", sa.Integer(), nullable=True),
        sa.Column("comissao_bp", sa.Integer(), nullable=True),
        sa.Column("n_criadores", sa.Integer(), nullable=True),
        sa.Column("vendas_7d", sa.BigInteger(), nullable=True),
        sa.Column("vendas_30d", sa.BigInteger(), nullable=True),
        sa.Column("estoque_visivel", sa.Integer(), nullable=True),
        sa.Column("disponivel", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _jsonb(),
        *_bruto(),
        sa.UniqueConstraint("produto_id", "data_local", "turno", "fonte",
                            name="uq_mercado_produto_fotos"),
        sa.CheckConstraint("moeda ~ '^[A-Z]{3}$'", name="ck_mercado_fotos_moeda"),
        sa.CheckConstraint("vendidos_min IS NULL OR vendidos_max IS NULL OR "
                           "vendidos_min <= vendidos_max", name="ck_mercado_fotos_vendidos"),
        sa.CheckConstraint("preco_min_centavos IS NULL OR preco_max_centavos IS NULL OR "
                           "preco_min_centavos <= preco_max_centavos",
                           name="ck_mercado_fotos_preco"),
        sa.CheckConstraint("(fonte = 'affiliate') OR (comissao_bp IS NULL AND n_criadores IS NULL"
                           " AND vendas_7d IS NULL AND vendas_30d IS NULL)",
                           name="ck_mercado_fotos_affiliate"),
    )
    op.create_index("ix_mercado_fotos_serie", "mercado_produto_fotos",
                    ["produto_id", sa.text("data_local DESC"), sa.text("turno DESC"), "fonte"])
    op.create_index("ix_mercado_fotos_dia", "mercado_produto_fotos", ["data_local", "fonte"])
    op.create_index("ix_mercado_fotos_affiliate", "mercado_produto_fotos",
                    ["produto_id", sa.text("data_local DESC")],
                    postgresql_where=sa.text("fonte = 'affiliate'"))

    op.create_table(
        "mercado_loja_fotos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("loja_id", sa.Uuid(), sa.ForeignKey("mercado_lojas.id"), nullable=False),
        sa.Column("data_local", sa.Date(), nullable=False),
        sa.Column("fonte", _enum("mercado_fonte"), nullable=False),
        sa.Column("nota", sa.Numeric(3, 2), nullable=True),
        sa.Column("seguidores", sa.BigInteger(), nullable=True),
        sa.Column("envio_no_prazo_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("tempo_resposta_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("n_produtos", sa.Integer(), nullable=True),
        sa.Column("vendidos_total", sa.BigInteger(), nullable=True),
        sa.Column("vendidos_total_min", sa.BigInteger(), nullable=True),
        sa.Column("vendidos_total_max", sa.BigInteger(), nullable=True),
        sa.Column("vendidos_total_exato", sa.Boolean(), nullable=True),
        _jsonb(),
        *_bruto(),
        sa.UniqueConstraint("loja_id", "data_local", "fonte", name="uq_mercado_loja_fotos"),
    )

    op.create_table(
        "mercado_ranking_fotos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rede", platform, nullable=False),
        sa.Column("mercado", sa.Text(), nullable=False),
        sa.Column("fonte", _enum("mercado_fonte"), nullable=False),
        sa.Column("categoria_id", sa.Uuid(), sa.ForeignKey("mercado_categorias.id"),
                  nullable=True),
        sa.Column("tipo", _enum("mercado_ranking_tipo"), nullable=False),
        sa.Column("janela", sa.Text(), nullable=False),
        sa.Column("data_local", sa.Date(), nullable=False),
        sa.Column("n_itens", sa.SmallInteger(), nullable=False),
        *_bruto(),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_mercado_ranking_fotos_mercado"),
        sa.CheckConstraint(_in("janela", RANKING_JANELAS), name="ck_mercado_ranking_fotos_janela"),
    )
    op.create_index("uq_mercado_ranking_fotos", "mercado_ranking_fotos",
                    ["rede", "mercado", "fonte", sa.text("coalesce(categoria_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
                     "tipo", "janela", "data_local"], unique=True)
    op.create_index("ix_mercado_ranking_fotos_cat", "mercado_ranking_fotos",
                    ["categoria_id", "tipo", "janela", sa.text("data_local DESC")])

    op.create_table(
        "mercado_ranking_foto_itens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("ranking_foto_id", sa.Uuid(), sa.ForeignKey("mercado_ranking_fotos.id"),
                  nullable=False),
        sa.Column("posicao", sa.SmallInteger(), nullable=False),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("mercado_produtos.id"), nullable=False),
        sa.Column("valor_exibido", sa.Text(), nullable=True),
        sa.Column("valor_num", sa.Numeric(), nullable=True),
        _jsonb(),
        sa.UniqueConstraint("ranking_foto_id", "posicao", name="uq_mercado_ranking_itens_posicao"),
    )
    op.create_index("ix_mercado_ranking_itens_produto", "mercado_ranking_foto_itens",
                    ["produto_id", "ranking_foto_id"])

    op.create_table(
        "mercado_avaliacoes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("mercado_produtos.id"), nullable=False),
        sa.Column("rede_avaliacao_id", sa.Text(), nullable=True),
        sa.Column("autor_hash", sa.Text(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("texto_hash", sa.Text(), nullable=False),
        sa.Column("nota", sa.SmallInteger(), nullable=True),
        sa.Column("data_avaliacao", sa.Date(), nullable=True),
        sa.Column("variante", sa.Text(), nullable=True),
        sa.Column("imagens_sha", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("curtidas", sa.Integer(), nullable=True),
        _jsonb(),
        *_bruto(),
        sa.CheckConstraint("nota IS NULL OR nota BETWEEN 1 AND 5",
                           name="ck_mercado_avaliacoes_nota"),
    )
    op.create_index("uq_mercado_avaliacoes_rede_id", "mercado_avaliacoes",
                    ["produto_id", "rede_avaliacao_id"], unique=True,
                    postgresql_where=sa.text("rede_avaliacao_id IS NOT NULL"))
    op.create_index("uq_mercado_avaliacoes_conteudo", "mercado_avaliacoes",
                    ["produto_id", "autor_hash", "texto_hash",
                     sa.text("coalesce(data_avaliacao, '0001-01-01')")], unique=True,
                    postgresql_where=sa.text("rede_avaliacao_id IS NULL"))
    op.create_index("ix_mercado_avaliacoes_produto", "mercado_avaliacoes",
                    ["produto_id", sa.text("data_avaliacao DESC")])

    op.create_table(
        "mercado_produto_videos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("mercado_produtos.id"), nullable=False),
        sa.Column("rede", platform, nullable=False),
        sa.Column("mercado", sa.Text(), nullable=False),
        sa.Column("rede_video_id", sa.Text(), nullable=False),
        sa.Column("autor_handle", sa.Text(), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comentarios", sa.BigInteger(), nullable=True),
        sa.Column("compartilhamentos", sa.BigInteger(), nullable=True),
        sa.Column("legenda", sa.Text(), nullable=True),
        sa.Column("publicado_em", ts, nullable=True),
        sa.Column("data_local", sa.Date(), nullable=False),
        sa.Column("posicao", sa.SmallInteger(), nullable=True),
        _jsonb(),
        *_bruto(),
        sa.UniqueConstraint("produto_id", "rede_video_id", "data_local",
                            name="uq_mercado_produto_videos"),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_mercado_produto_videos_mercado"),
    )
    op.create_index("ix_mercado_videos_produto", "mercado_produto_videos",
                    ["produto_id", sa.text("data_local DESC"), sa.text("views DESC")])
    op.create_index("ix_mercado_videos_rede", "mercado_produto_videos",
                    ["rede", "mercado", "rede_video_id"])

    # 4. operação
    op.create_table(
        "mercado_fila",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("rede", platform, nullable=False),
        sa.Column("mercado", sa.Text(), nullable=False),
        sa.Column("fonte", sa.Text(), nullable=False),
        sa.Column("chave", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("nivel", sa.SmallInteger(), nullable=False),
        sa.Column("prioridade", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=True),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("mercado_produtos.id"), nullable=True),
        sa.Column("loja_id", sa.Uuid(), sa.ForeignKey("mercado_lojas.id"), nullable=True),
        sa.Column("categoria_id", sa.Uuid(), sa.ForeignKey("mercado_categorias.id"),
                  nullable=True),
        sa.Column("data_local", sa.Date(), nullable=False),
        sa.Column("turno", _enum("mercado_turno"), nullable=True),
        sa.Column("estado", _enum("mercado_fila_estado"), server_default="pendente",
                  nullable=False),
        sa.Column("reservada_ate", ts, nullable=True),
        sa.Column("cliente_id", sa.Uuid(), sa.ForeignKey("coleta_clientes.id"), nullable=True),
        sa.Column("coleta_id", sa.Uuid(), sa.ForeignKey("mercado_coletas.id"), nullable=True),
        sa.Column("tentativas", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("resultado_status", _enum("mercado_coleta_item_status"), nullable=True),
        sa.Column("erro_codigo", sa.Text(), nullable=True),
        sa.Column("criada_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("recebida_em", ts, nullable=True),
        sa.Column("extra", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.CheckConstraint(_in("tipo", FILA_TIPOS), name="ck_mercado_fila_tipo"),
        sa.CheckConstraint(_in("fonte", FILA_FONTES), name="ck_mercado_fila_fonte"),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_mercado_fila_mercado"),
        sa.CheckConstraint("nivel BETWEEN 1 AND 8", name="ck_mercado_fila_nivel"),
    )
    op.create_index("uq_mercado_fila_viva", "mercado_fila",
                    ["tipo", "chave", "data_local", "turno"], unique=True,
                    postgresql_nulls_not_distinct=True,
                    postgresql_where=sa.text("estado IN ('pendente', 'reservada')"))
    op.create_index("ix_mercado_fila_entrega", "mercado_fila",
                    ["estado", "data_local", "nivel", "prioridade"],
                    postgresql_where=sa.text("estado = 'pendente'"))
    op.create_index("ix_mercado_fila_lease", "mercado_fila", ["reservada_ate"],
                    postgresql_where=sa.text("estado = 'reservada'"))
    op.create_index("ix_mercado_fila_produto", "mercado_fila",
                    ["produto_id", sa.text("data_local DESC")])
    op.create_foreign_key("fk_mercado_coletas_tarefa_atual", "mercado_coletas", "mercado_fila",
                          ["tarefa_atual_id"], ["id"])

    op.create_table(
        "mercado_coleta_itens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("coleta_id", sa.Uuid(), sa.ForeignKey("mercado_coletas.id"), nullable=False),
        sa.Column("tarefa_id", sa.Uuid(), sa.ForeignKey("mercado_fila.id"), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("fonte", _enum("mercado_fonte"), nullable=True),
        sa.Column("status", _enum("mercado_coleta_item_status"), nullable=False),
        sa.Column("erro_codigo", sa.Text(), nullable=True),
        sa.Column("erro_campo", sa.Text(), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=True),
        sa.Column("recebido_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("coletado_em", ts, nullable=False),
        sa.Column("data_local", sa.Date(), nullable=False),
        sa.Column("turno", _enum("mercado_turno"), nullable=True),
        sa.Column("esquema_versao", sa.Text(), nullable=True),
        sa.Column("bruto_ref", sa.Text(), nullable=True),
        sa.Column("bruto_bytes", sa.Integer(), nullable=True),
        sa.Column("reprocessado_de", sa.BigInteger(), sa.ForeignKey("mercado_coleta_itens.id"),
                  nullable=True),
        sa.CheckConstraint(_in("tipo", FILA_TIPOS), name="ck_mercado_coleta_itens_tipo"),
    )
    op.create_index("ix_mercado_coleta_itens_coleta", "mercado_coleta_itens",
                    ["coleta_id", "recebido_em"])
    op.create_index("ix_mercado_coleta_itens_tarefa", "mercado_coleta_itens", ["tarefa_id"])
    op.create_index("ix_mercado_coleta_itens_dia", "mercado_coleta_itens",
                    ["data_local", "status"])

    op.create_table(
        "coleta_eventos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("tipo", _enum("coleta_evento_tipo"), nullable=False),
        sa.Column("cliente_id", sa.Uuid(), sa.ForeignKey("coleta_clientes.id"), nullable=False),
        sa.Column("coleta_id", sa.Uuid(), sa.ForeignKey("mercado_coletas.id"), nullable=True),
        sa.Column("tarefa_id", sa.Uuid(), sa.ForeignKey("mercado_fila.id"), nullable=True),
        sa.Column("detalhe", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.Column("ocorreu_em", ts, nullable=False),
        sa.Column("recebido_em", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("notificacao_dedupe", sa.Text(), nullable=True),
    )
    op.create_index("ix_coleta_eventos_recentes", "coleta_eventos", [sa.text("recebido_em DESC")])
    op.create_index("ix_coleta_eventos_coleta", "coleta_eventos", ["coleta_id"])

    # 5. interesse
    tem_produtos = _tem_produtos()
    op.create_table(
        "mercado_interesses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=True),
        sa.Column("mercado_produto_id", sa.Uuid(), sa.ForeignKey("mercado_produtos.id"),
                  nullable=False),
        sa.Column("origem", _enum("mercado_interesse_origem"), nullable=False),
        sa.Column("situacao", _enum("mercado_interesse_situacao"), server_default="ativo",
                  nullable=False),
        sa.Column("motivo", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.Column("nota", sa.Text(), server_default="", nullable=False),
        sa.Column("produto_id", sa.Uuid(), nullable=True),  # FK para `produtos` (012) abaixo
        sa.Column("tema_id", sa.Uuid(), sa.ForeignKey("aprendizado_temas.id"), nullable=True),
        sa.Column("pausado_em", ts, nullable=True),
        sa.Column("encerrado_em", ts, nullable=True),
        *_auditoria(),
        sa.CheckConstraint("(perfil_id IS NULL) = (origem = 'vitrine')",
                           name="ck_mercado_interesses_vitrine"),
        sa.CheckConstraint("char_length(nota) <= 2000", name="ck_mercado_interesses_nota"),
    )
    op.create_index("uq_mercado_interesses_vivo", "mercado_interesses",
                    [sa.text("coalesce(perfil_id, '00000000-0000-0000-0000-000000000000'::uuid)"), "mercado_produto_id", "origem"],
                    unique=True, postgresql_where=sa.text("situacao IN ('ativo', 'pausado')"))
    op.create_index("ix_mercado_interesses_perfil", "mercado_interesses",
                    ["perfil_id", "situacao", sa.text("created_at DESC")])
    op.create_index("ix_mercado_interesses_produto", "mercado_interesses",
                    ["mercado_produto_id", "situacao"])
    op.create_index("ix_mercado_interesses_auto_dia", "mercado_interesses",
                    ["perfil_id", "created_at"],
                    postgresql_where=sa.text("origem IN ('ranking', 'loja', 'categoria')"))
    if tem_produtos:
        op.create_foreign_key("fk_mercado_interesses_produto", "mercado_interesses", "produtos",
                              ["produto_id"], ["id"])

    op.create_table(
        "mercado_perfil_config",
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), primary_key=True),
        sa.Column("mercado", sa.Text(), server_default="BR", nullable=False),
        sa.Column("categoria_ids", postgresql.ARRAY(sa.Uuid()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("lojas_seguidas", postgresql.ARRAY(sa.Uuid()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("max_relacionados_dia", sa.Integer(), server_default=sa.text("10"),
                  nullable=False),
        sa.Column("avisar_novo_em_alta", sa.Boolean(), server_default=sa.text("true"),
                  nullable=False),
        *_auditoria(),
        sa.CheckConstraint(MERCADO_CHECK, name="ck_mercado_perfil_config_mercado"),
        sa.CheckConstraint("cardinality(categoria_ids) <= 5",
                           name="ck_mercado_perfil_config_categorias"),
        sa.CheckConstraint("max_relacionados_dia BETWEEN 0 AND 50",
                           name="ck_mercado_perfil_config_relacionados"),
    )

    # 6. só inserção (a função `metricas_recusa_mudanca()` existe desde a 0011)
    for tabela in SO_INSERCAO:
        op.execute(f"CREATE TRIGGER mercado_so_insercao BEFORE UPDATE OR DELETE ON {tabela} "
                   "FOR EACH ROW EXECUTE FUNCTION metricas_recusa_mudanca()")

    # 7. a coluna da 012
    if tem_produtos:
        op.add_column("produtos", sa.Column("mercado_produto_id", sa.Uuid(), nullable=True))
        op.create_foreign_key("fk_produtos_mercado_produto", "produtos", "mercado_produtos",
                              ["mercado_produto_id"], ["id"])
        op.create_index("ix_produtos_mercado_produto", "produtos", ["mercado_produto_id"],
                        postgresql_where=sa.text("mercado_produto_id IS NOT NULL"))
    else:
        log.info("012 ausente: a coluna produtos.mercado_produto_id fica para a migration de "
                 "ligação")


def downgrade() -> None:
    bind = op.get_bind()
    tem = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM mercado_produtos) OR EXISTS (SELECT 1 FROM mercado_coletas)"
        " OR EXISTS (SELECT 1 FROM coleta_clientes)")).scalar()
    if tem:
        raise RuntimeError("downgrade da 0025 recusado: há dados de mercado ou da coleta")
    insp = sa.inspect(bind)
    if insp.has_table("produtos") and any(
            c["name"] == "mercado_produto_id" for c in insp.get_columns("produtos")):
        op.drop_index("ix_produtos_mercado_produto", table_name="produtos")
        op.drop_constraint("fk_produtos_mercado_produto", "produtos", type_="foreignkey")
        op.drop_column("produtos", "mercado_produto_id")
    for tabela in SO_INSERCAO:
        op.execute(f"DROP TRIGGER mercado_so_insercao ON {tabela}")
    op.drop_constraint("fk_mercado_coletas_tarefa_atual", "mercado_coletas", type_="foreignkey")
    op.drop_constraint("fk_mercado_produtos_ficha_atual", "mercado_produtos", type_="foreignkey")
    for tabela in ("mercado_categorias", "mercado_lojas"):
        op.drop_constraint(f"fk_{tabela}_coleta", tabela, type_="foreignkey")
    for tabela in TABELAS:
        op.drop_table(tabela)
    for nome in ENUMS:
        postgresql.ENUM(name=nome).drop(bind, checkfirst=True)
    # Os 6 avisos novos saem de `notificacoes` e o tipo é recriado sem eles (padrão da 0011).
    tipos = ", ".join(f"'{t}'" for t in TIPOS_NOTIFICACAO)
    op.execute(f"DELETE FROM notificacoes WHERE tipo::text IN ({tipos})")
    op.execute("ALTER TYPE notificacao_tipo RENAME TO notificacao_tipo_old")
    novo = postgresql.ENUM(*TIPOS_ANTERIORES, name="notificacao_tipo")
    novo.create(bind)
    op.execute("ALTER TABLE notificacoes ALTER COLUMN tipo TYPE notificacao_tipo "
               "USING tipo::text::notificacao_tipo")
    op.execute("DROP TYPE notificacao_tipo_old")
