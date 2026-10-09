"""Lago, operação e interesse do mercado (data-model.md da spec 026).

Três camadas, três regras:
- **Lago** (`mercado_categorias`, `mercado_lojas`, `mercado_loja_fotos`, `mercado_produtos`,
  `mercado_produto_fichas`, `mercado_imagens`, `mercado_produto_imagens`, `mercado_produto_fotos`,
  `mercado_ranking_fotos`, `mercado_ranking_foto_itens`, `mercado_avaliacoes`,
  `mercado_produto_videos`): global e permanente, **sem** `perfil_id`, `conta_id`, `tenant_id`,
  `created_by` ou `user_id` (guarda FR-057). Fotos, fichas, itens, avaliações, vídeos e imagens são
  **só inserção** (trigger `mercado_so_insercao`, função `metricas_recusa_mudanca()` da 0011);
  as identidades só mudam em "último visto" e no estado técnico de coleta.
- **Operação** (`mercado_fila`, `mercado_coletas`, `mercado_coleta_itens`): estado de job (UPDATE
  de estado e contadores); itens só inserção. `mercado_fila.perfil_id` é a **exceção nominal** do
  guarda de neutralidade: diz para que perfil a tarefa foi gerada (revezamento), não é dono do
  dado e nunca filtra a leitura do lago. `coleta_eventos` fica em `coleta/models.py`.
- **Interesse** (`mercado_interesses`, `mercado_perfil_config`): por perfil, versionado com
  `history.py`. É a camada que receberá o `tenant_id` na spec de multi-tenant.

Nada daqui é apagado por nenhuma rotina (FR-002); "esfriar" só muda a cadência.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.mercado.mercados import Turno
from sociman_api.perfis.models import Platform

MERCADO_CHECK = "mercado ~ '^[A-Z]{2}$'"
MOEDA_CHECK = "moeda ~ '^[A-Z]{3}$'"
FILA_TIPOS = ("produto", "ranking", "categorias", "vitrine", "loja", "avaliacoes",
              "produto_videos", "busca_assunto", "video")  # os 2 últimos reservados (027)
FILA_TIPOS_026 = FILA_TIPOS[:7]
FILA_FONTES = ("pagina_publica", "affiliate", "ambas")
RANKING_JANELAS = ("1d", "7d", "30d", "total")
IMAGEM_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "image/avif", "image/gif")
IMAGEM_ORIGENS = ("produto", "avaliacao")


def _in(coluna: str, valores: tuple[str, ...]) -> str:
    return f"{coluna} IN ({', '.join(repr(v) for v in valores)})"


# ---- enums ----

class Calor(enum.StrEnum):
    quente = "quente"
    morna = "morna"  # "semanal" na spec (FR-040)
    parada = "parada"


class Fonte(enum.StrEnum):
    pagina_publica = "pagina_publica"
    affiliate = "affiliate"


class RankingTipo(enum.StrEnum):
    mais_vendidos = "mais_vendidos"
    em_alta = "em_alta"
    novos = "novos"
    alta_comissao = "alta_comissao"


class FilaEstado(enum.StrEnum):
    pendente = "pendente"
    reservada = "reservada"
    recebida = "recebida"
    falhou = "falhou"
    expirada = "expirada"


class ColetaEstado(enum.StrEnum):
    ativa = "ativa"
    pausada_captcha = "pausada_captcha"
    pausada_login = "pausada_login"
    interrompida = "interrompida"
    encerrada = "encerrada"
    abortada = "abortada"


COLETA_ABERTAS = (ColetaEstado.ativa, ColetaEstado.pausada_captcha, ColetaEstado.pausada_login)
COLETA_PAUSADAS = (ColetaEstado.pausada_captcha, ColetaEstado.pausada_login)


class ItemStatus(enum.StrEnum):
    gravado = "gravado"
    repetido = "repetido"
    invalido = "invalido"
    erro = "erro"
    captcha = "captcha"


class InteresseOrigem(enum.StrEnum):
    manual = "manual"
    vitrine = "vitrine"
    ranking = "ranking"
    video = "video"  # 027
    loja = "loja"
    categoria = "categoria"


ORIGENS_AUTOMATICAS = (InteresseOrigem.ranking, InteresseOrigem.loja, InteresseOrigem.categoria)


class InteresseSituacao(enum.StrEnum):
    ativo = "ativo"
    pausado = "pausado"
    encerrado = "encerrado"


def _platform() -> Enum:
    return Enum(Platform, name="platform")


def _ts() -> DateTime:
    return DateTime(timezone=True)


# ---- lago ----

class Categoria(Base):
    __tablename__ = "mercado_categorias"
    __table_args__ = (
        UniqueConstraint("rede", "mercado", "rede_categoria_id", name="uq_mercado_categorias"),
        CheckConstraint(MERCADO_CHECK, name="ck_mercado_categorias_mercado"),
        CheckConstraint("nivel BETWEEN 1 AND 3", name="ck_mercado_categorias_nivel"),
        CheckConstraint("(nivel = 1) = (pai_id IS NULL)", name="ck_mercado_categorias_pai"),
        Index("ix_mercado_categorias_pai", "pai_id"),
        Index("ix_mercado_categorias_ativas", "rede", "mercado", "nivel",
              postgresql_where=text("ativa")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rede: Mapped[Platform] = mapped_column(_platform(), nullable=False)
    mercado: Mapped[str] = mapped_column(Text, nullable=False)
    rede_categoria_id: Mapped[str] = mapped_column(Text, nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    nivel: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    pai_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_categorias.id"))
    caminho: Mapped[str] = mapped_column(Text, nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                        server_default=text("true"))
    primeira_vez_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    ultimo_visto_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    coleta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"))


class Loja(Base):
    __tablename__ = "mercado_lojas"
    __table_args__ = (
        UniqueConstraint("rede", "mercado", "rede_loja_id", name="uq_mercado_lojas"),
        CheckConstraint(MERCADO_CHECK, name="ck_mercado_lojas_mercado"),
        Index("ix_mercado_lojas_nome", "rede", "mercado", func.lower(text("nome"))),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rede: Mapped[Platform] = mapped_column(_platform(), nullable=False)
    mercado: Mapped[str] = mapped_column(Text, nullable=False)
    rede_loja_id: Mapped[str] = mapped_column(Text, nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    oficial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                          server_default=text("false"))
    url: Mapped[str | None] = mapped_column(Text)
    primeira_vez_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    ultimo_visto_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    ultima_foto_em: Mapped[date | None] = mapped_column(Date)
    proxima_coleta_em: Mapped[datetime | None] = mapped_column(_ts())
    coleta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"))


class FotoLoja(Base):
    """Só inserção (trigger)."""

    __tablename__ = "mercado_loja_fotos"
    __table_args__ = (
        UniqueConstraint("loja_id", "data_local", "fonte", name="uq_mercado_loja_fotos"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    loja_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_lojas.id"),
                                               nullable=False)
    data_local: Mapped[date] = mapped_column(Date, nullable=False)
    fonte: Mapped[Fonte] = mapped_column(Enum(Fonte, name="mercado_fonte"), nullable=False)
    nota: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    seguidores: Mapped[int | None] = mapped_column(BigInteger)
    envio_no_prazo_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    tempo_resposta_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    n_produtos: Mapped[int | None] = mapped_column(Integer)
    vendidos_total: Mapped[int | None] = mapped_column(BigInteger)
    vendidos_total_min: Mapped[int | None] = mapped_column(BigInteger)
    vendidos_total_max: Mapped[int | None] = mapped_column(BigInteger)
    vendidos_total_exato: Mapped[bool | None] = mapped_column(Boolean)
    campos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                   server_default=text("'{}'::jsonb"))
    bruto_ref: Mapped[str | None] = mapped_column(Text)
    esquema_versao: Mapped[str] = mapped_column(Text, nullable=False)
    coleta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"),
                                                 nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)


class Produto(Base):
    __tablename__ = "mercado_produtos"
    __table_args__ = (
        UniqueConstraint("rede", "mercado", "rede_produto_id", name="uq_mercado_produtos"),
        CheckConstraint(MERCADO_CHECK, name="ck_mercado_produtos_mercado"),
        CheckConstraint("fotos_por_dia BETWEEN 1 AND 2", name="ck_mercado_produtos_fotos_dia"),
        Index("ix_mercado_produtos_fila", "calor", "proxima_coleta_em",
              postgresql_where=text("calor <> 'parada'")),
        Index("ix_mercado_produtos_loja", "loja_id"),
        Index("ix_mercado_produtos_categoria", "categoria_id"),
        Index("ix_mercado_produtos_primeira", "rede", "mercado", text("primeira_vez_em DESC")),
        Index("ix_mercado_produtos_titulo",
              text("to_tsvector('portuguese', coalesce(titulo_atual, ''))"),
              postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rede: Mapped[Platform] = mapped_column(_platform(), nullable=False)
    mercado: Mapped[str] = mapped_column(Text, nullable=False)
    rede_produto_id: Mapped[str] = mapped_column(Text, nullable=False)
    url_canonica: Mapped[str] = mapped_column(Text, nullable=False)
    titulo_atual: Mapped[str | None] = mapped_column(Text)
    loja_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_lojas.id"))
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                           ForeignKey("mercado_categorias.id"))
    # A FK para `mercado_produto_fichas` fica na migration (`use_alter`): o ORM só guarda o id.
    ficha_atual_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    primeira_vez_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    lancado_em: Mapped[date | None] = mapped_column(Date)
    ultimo_visto_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    ultima_foto_em: Mapped[date | None] = mapped_column(Date)
    ultima_foto_affiliate_em: Mapped[date | None] = mapped_column(Date)
    ultimas_avaliacoes_em: Mapped[date | None] = mapped_column(Date)
    ultimos_videos_em: Mapped[date | None] = mapped_column(Date)
    indisponivel_desde: Mapped[date | None] = mapped_column(Date)
    calor: Mapped[Calor] = mapped_column(Enum(Calor, name="mercado_calor"), nullable=False,
                                         default=Calor.quente, server_default=Calor.quente.value)
    fotos_por_dia: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1,
                                               server_default=text("1"))
    proxima_coleta_em: Mapped[datetime | None] = mapped_column(_ts())
    ultimo_erro_codigo: Mapped[str | None] = mapped_column(Text)
    ultimo_erro_em: Mapped[datetime | None] = mapped_column(_ts())
    imagens_pendentes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                    server_default=text("false"))
    fonte_descoberta: Mapped[InteresseOrigem] = mapped_column(
        Enum(InteresseOrigem, name="mercado_interesse_origem"), nullable=False)
    ultimo_ranking_em: Mapped[date | None] = mapped_column(Date)
    coleta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"))


class Ficha(Base):
    """Só inserção: uma versão por conteúdo (FR-004)."""

    __tablename__ = "mercado_produto_fichas"
    __table_args__ = (
        UniqueConstraint("produto_id", "hash_conteudo", name="uq_mercado_fichas_conteudo"),
        Index("ix_mercado_fichas_produto", "produto_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_produtos.id"),
                                                  nullable=False)
    hash_conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    atributos: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    variantes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    argumentos: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list,
                                                  server_default=text("'{}'"))
    selos: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list,
                                             server_default=text("'{}'"))
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                           ForeignKey("mercado_categorias.id"))
    loja_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_lojas.id"))
    imagens_sha: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list,
                                                   server_default=text("'{}'"))
    esquema_versao: Mapped[str] = mapped_column(Text, nullable=False)
    bruto_ref: Mapped[str | None] = mapped_column(Text)
    coleta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"),
                                                 nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(_ts(), nullable=False,
                                                 server_default=func.now())


class Imagem(Base):
    """Arquivo original, deduplicado por conteúdo, imutável e global (FR-005)."""

    __tablename__ = "mercado_imagens"
    __table_args__ = (
        CheckConstraint(_in("content_type", IMAGEM_CONTENT_TYPES),
                        name="ck_mercado_imagens_content_type"),
        CheckConstraint(_in("origem", IMAGEM_ORIGENS), name="ck_mercado_imagens_origem"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sha256: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    origem: Mapped[str] = mapped_column(Text, nullable=False)
    coleta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"),
                                                 nullable=False)
    created_at: Mapped[datetime] = mapped_column(_ts(), nullable=False,
                                                 server_default=func.now())


class ProdutoImagem(Base):
    """A ordem das imagens numa ficha; só inserção."""

    __tablename__ = "mercado_produto_imagens"
    __table_args__ = (
        UniqueConstraint("ficha_id", "posicao", name="uq_mercado_produto_imagens_posicao"),
        Index("ix_mercado_produto_imagens_imagem", "imagem_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_produtos.id"),
                                                  nullable=False)
    ficha_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_produto_fichas.id"),
                                                nullable=False)
    imagem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_imagens.id"),
                                                 nullable=False)
    posicao: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class FotoProduto(Base):
    """Medição por dia, turno e fonte; só inserção (FR-006)."""

    __tablename__ = "mercado_produto_fotos"
    __table_args__ = (
        UniqueConstraint("produto_id", "data_local", "turno", "fonte",
                         name="uq_mercado_produto_fotos"),
        CheckConstraint(MOEDA_CHECK, name="ck_mercado_fotos_moeda"),
        CheckConstraint("vendidos_min IS NULL OR vendidos_max IS NULL OR "
                        "vendidos_min <= vendidos_max", name="ck_mercado_fotos_vendidos"),
        CheckConstraint("preco_min_centavos IS NULL OR preco_max_centavos IS NULL OR "
                        "preco_min_centavos <= preco_max_centavos",
                        name="ck_mercado_fotos_preco"),
        CheckConstraint("(fonte = 'affiliate') OR (comissao_bp IS NULL AND n_criadores IS NULL "
                        "AND vendas_7d IS NULL AND vendas_30d IS NULL)",
                        name="ck_mercado_fotos_affiliate"),
        Index("ix_mercado_fotos_serie", "produto_id", text("data_local DESC"),
              text("turno DESC"), "fonte"),
        Index("ix_mercado_fotos_dia", "data_local", "fonte"),
        Index("ix_mercado_fotos_affiliate", "produto_id", text("data_local DESC"),
              postgresql_where=text("fonte = 'affiliate'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_produtos.id"),
                                                  nullable=False)
    data_local: Mapped[date] = mapped_column(Date, nullable=False)
    turno: Mapped[Turno] = mapped_column(Enum(Turno, name="mercado_turno"), nullable=False)
    fonte: Mapped[Fonte] = mapped_column(Enum(Fonte, name="mercado_fonte"), nullable=False)
    vendidos: Mapped[int | None] = mapped_column(BigInteger)
    vendidos_min: Mapped[int | None] = mapped_column(BigInteger)
    vendidos_max: Mapped[int | None] = mapped_column(BigInteger)
    vendidos_exato: Mapped[bool | None] = mapped_column(Boolean)
    preco_min_centavos: Mapped[int | None] = mapped_column(Integer)
    preco_max_centavos: Mapped[int | None] = mapped_column(Integer)
    preco_original_centavos: Mapped[int | None] = mapped_column(Integer)
    moeda: Mapped[str] = mapped_column(Text, nullable=False)
    nota: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    n_avaliacoes: Mapped[int | None] = mapped_column(Integer)
    comissao_bp: Mapped[int | None] = mapped_column(Integer)
    n_criadores: Mapped[int | None] = mapped_column(Integer)
    vendas_7d: Mapped[int | None] = mapped_column(BigInteger)
    vendas_30d: Mapped[int | None] = mapped_column(BigInteger)
    estoque_visivel: Mapped[int | None] = mapped_column(Integer)
    disponivel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                             server_default=text("true"))
    campos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                   server_default=text("'{}'::jsonb"))
    esquema_versao: Mapped[str] = mapped_column(Text, nullable=False)
    bruto_ref: Mapped[str | None] = mapped_column(Text)
    coleta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"),
                                                 nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)


class FotoRanking(Base):
    """A lista de um ranking num dia; só inserção (FR-009)."""

    __tablename__ = "mercado_ranking_fotos"
    __table_args__ = (
        CheckConstraint(MERCADO_CHECK, name="ck_mercado_ranking_fotos_mercado"),
        CheckConstraint(_in("janela", RANKING_JANELAS), name="ck_mercado_ranking_fotos_janela"),
        Index("uq_mercado_ranking_fotos", "rede", "mercado", "fonte",
              text("coalesce(categoria_id, '00000000-0000-0000-0000-000000000000'::uuid)"), "tipo", "janela", "data_local",
              unique=True),
        Index("ix_mercado_ranking_fotos_cat", "categoria_id", "tipo", "janela",
              text("data_local DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rede: Mapped[Platform] = mapped_column(_platform(), nullable=False)
    mercado: Mapped[str] = mapped_column(Text, nullable=False)
    fonte: Mapped[Fonte] = mapped_column(Enum(Fonte, name="mercado_fonte"), nullable=False)
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                           ForeignKey("mercado_categorias.id"))
    tipo: Mapped[RankingTipo] = mapped_column(Enum(RankingTipo, name="mercado_ranking_tipo"),
                                              nullable=False)
    janela: Mapped[str] = mapped_column(Text, nullable=False)
    data_local: Mapped[date] = mapped_column(Date, nullable=False)
    n_itens: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    esquema_versao: Mapped[str] = mapped_column(Text, nullable=False)
    bruto_ref: Mapped[str | None] = mapped_column(Text)
    coleta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"),
                                                 nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)


class ItemRanking(Base):
    """Só inserção."""

    __tablename__ = "mercado_ranking_foto_itens"
    __table_args__ = (
        UniqueConstraint("ranking_foto_id", "posicao", name="uq_mercado_ranking_itens_posicao"),
        Index("ix_mercado_ranking_itens_produto", "produto_id", "ranking_foto_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    ranking_foto_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("mercado_ranking_fotos.id"), nullable=False)
    posicao: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_produtos.id"),
                                                  nullable=False)
    valor_exibido: Mapped[str | None] = mapped_column(Text)
    valor_num: Mapped[Decimal | None] = mapped_column(Numeric)
    campos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                   server_default=text("'{}'::jsonb"))


class Avaliacao(Base):
    """Só inserção; o autor é só um hash com pepper (FR-010)."""

    __tablename__ = "mercado_avaliacoes"
    __table_args__ = (
        CheckConstraint("nota IS NULL OR nota BETWEEN 1 AND 5", name="ck_mercado_avaliacoes_nota"),
        Index("uq_mercado_avaliacoes_rede_id", "produto_id", "rede_avaliacao_id", unique=True,
              postgresql_where=text("rede_avaliacao_id IS NOT NULL")),
        Index("uq_mercado_avaliacoes_conteudo", "produto_id", "autor_hash", "texto_hash",
              text("coalesce(data_avaliacao, '0001-01-01')"), unique=True,
              postgresql_where=text("rede_avaliacao_id IS NULL")),
        Index("ix_mercado_avaliacoes_produto", "produto_id", text("data_avaliacao DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_produtos.id"),
                                                  nullable=False)
    rede_avaliacao_id: Mapped[str | None] = mapped_column(Text)
    autor_hash: Mapped[str] = mapped_column(Text, nullable=False)
    texto: Mapped[str | None] = mapped_column(Text)
    texto_hash: Mapped[str] = mapped_column(Text, nullable=False)
    nota: Mapped[int | None] = mapped_column(SmallInteger)
    data_avaliacao: Mapped[date | None] = mapped_column(Date)
    variante: Mapped[str | None] = mapped_column(Text)
    imagens_sha: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list,
                                                   server_default=text("'{}'"))
    curtidas: Mapped[int | None] = mapped_column(Integer)
    campos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                   server_default=text("'{}'::jsonb"))
    esquema_versao: Mapped[str] = mapped_column(Text, nullable=False)
    bruto_ref: Mapped[str | None] = mapped_column(Text)
    coleta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"),
                                                 nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)

    def __repr__(self) -> str:  # nunca o texto nem o hash
        return f"Avaliacao(id={self.id}, produto_id={self.produto_id})"


class VideoProduto(Base):
    """Vídeos top que promovem o produto; só inserção, uma linha por dia visto (FR-011)."""

    __tablename__ = "mercado_produto_videos"
    __table_args__ = (
        UniqueConstraint("produto_id", "rede_video_id", "data_local",
                         name="uq_mercado_produto_videos"),
        CheckConstraint(MERCADO_CHECK, name="ck_mercado_produto_videos_mercado"),
        Index("ix_mercado_videos_produto", "produto_id", text("data_local DESC"),
              text("views DESC")),
        Index("ix_mercado_videos_rede", "rede", "mercado", "rede_video_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_produtos.id"),
                                                  nullable=False)
    rede: Mapped[Platform] = mapped_column(_platform(), nullable=False)
    mercado: Mapped[str] = mapped_column(Text, nullable=False)
    rede_video_id: Mapped[str] = mapped_column(Text, nullable=False)
    autor_handle: Mapped[str] = mapped_column(Text, nullable=False)
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comentarios: Mapped[int | None] = mapped_column(BigInteger)
    compartilhamentos: Mapped[int | None] = mapped_column(BigInteger)
    legenda: Mapped[str | None] = mapped_column(Text)
    publicado_em: Mapped[datetime | None] = mapped_column(_ts())
    data_local: Mapped[date] = mapped_column(Date, nullable=False)
    posicao: Mapped[int | None] = mapped_column(SmallInteger)
    campos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                   server_default=text("'{}'::jsonb"))
    esquema_versao: Mapped[str] = mapped_column(Text, nullable=False)
    bruto_ref: Mapped[str | None] = mapped_column(Text)
    coleta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"),
                                                 nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)


# ---- operação da coleta ----

class Tarefa(Base):
    """`mercado_fila`: o que o servidor pediu ao coletor. Nunca apagada; estado de job."""

    __tablename__ = "mercado_fila"
    __table_args__ = (
        CheckConstraint(_in("tipo", FILA_TIPOS), name="ck_mercado_fila_tipo"),
        CheckConstraint(_in("fonte", FILA_FONTES), name="ck_mercado_fila_fonte"),
        CheckConstraint(MERCADO_CHECK, name="ck_mercado_fila_mercado"),
        CheckConstraint("nivel BETWEEN 1 AND 8", name="ck_mercado_fila_nivel"),
        # `NULLS NOT DISTINCT`: duas tarefas sem turno no mesmo dia são a mesma tarefa.
        Index("uq_mercado_fila_viva", "tipo", "chave", "data_local", "turno", unique=True,
              postgresql_nulls_not_distinct=True,
              postgresql_where=text("estado IN ('pendente', 'reservada')")),
        Index("ix_mercado_fila_entrega", "estado", "data_local", "nivel", "prioridade",
              postgresql_where=text("estado = 'pendente'")),
        Index("ix_mercado_fila_lease", "reservada_ate",
              postgresql_where=text("estado = 'reservada'")),
        Index("ix_mercado_fila_produto", "produto_id", text("data_local DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    rede: Mapped[Platform] = mapped_column(_platform(), nullable=False)
    mercado: Mapped[str] = mapped_column(Text, nullable=False)
    fonte: Mapped[str] = mapped_column(Text, nullable=False)
    chave: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    nivel: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    prioridade: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Exceção nominal do guarda de neutralidade: operacional (revezamento), não é dono do dado.
    perfil_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("perfis.id"))
    produto_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_produtos.id"))
    loja_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_lojas.id"))
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                           ForeignKey("mercado_categorias.id"))
    data_local: Mapped[date] = mapped_column(Date, nullable=False)
    turno: Mapped[Turno | None] = mapped_column(Enum(Turno, name="mercado_turno"))
    estado: Mapped[FilaEstado] = mapped_column(
        Enum(FilaEstado, name="mercado_fila_estado"), nullable=False,
        default=FilaEstado.pendente, server_default=FilaEstado.pendente.value)
    reservada_ate: Mapped[datetime | None] = mapped_column(_ts())
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("coleta_clientes.id"))
    # A FK para `mercado_coletas` fica na migration (ciclo fila ↔ coletas, `use_alter`).
    coleta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    tentativas: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0,
                                            server_default=text("0"))
    resultado_status: Mapped[ItemStatus | None] = mapped_column(
        Enum(ItemStatus, name="mercado_coleta_item_status"))
    erro_codigo: Mapped[str | None] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(_ts(), nullable=False, server_default=func.now())
    recebida_em: Mapped[datetime | None] = mapped_column(_ts())
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                  server_default=text("'{}'::jsonb"))


class Coleta(Base):
    """`mercado_coletas`: uma rodada do coletor (estado de job)."""

    __tablename__ = "mercado_coletas"
    __table_args__ = (
        CheckConstraint(MERCADO_CHECK, name="ck_mercado_coletas_mercado"),
        CheckConstraint("estado IN ('ativa', 'pausada_captcha', 'pausada_login') "
                        "OR terminada_em IS NOT NULL", name="ck_mercado_coletas_terminada"),
        Index("uq_mercado_coletas_aberta", "cliente_id", unique=True,
              postgresql_where=text("estado IN ('ativa', 'pausada_captcha', 'pausada_login')")),
        Index("ix_mercado_coletas_cliente", "cliente_id", text("iniciada_em DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("coleta_clientes.id"),
                                                  nullable=False)
    rede: Mapped[Platform] = mapped_column(_platform(), nullable=False)
    mercado: Mapped[str] = mapped_column(Text, nullable=False)
    iniciada_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    batimento_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    terminada_em: Mapped[datetime | None] = mapped_column(_ts())
    estado: Mapped[ColetaEstado] = mapped_column(
        Enum(ColetaEstado, name="mercado_coleta_estado"), nullable=False,
        default=ColetaEstado.ativa, server_default=ColetaEstado.ativa.value)
    # FK para `mercado_fila` na migration (`use_alter`).
    tarefa_atual_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    paginas: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                         server_default=text("0"))
    imagens: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                         server_default=text("0"))
    itens_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                          server_default=text("0"))
    itens_erro: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                            server_default=text("0"))
    itens_repetidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                                 server_default=text("0"))
    versao_coletor: Mapped[str] = mapped_column(Text, nullable=False)
    chrome_versao: Mapped[str | None] = mapped_column(Text)
    protocolo: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    resumo: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                   server_default=text("'{}'::jsonb"))


class ColetaItem(Base):
    """`mercado_coleta_itens`: um por item recebido, inclusive repetidos e inválidos; só inserção."""

    __tablename__ = "mercado_coleta_itens"
    __table_args__ = (
        CheckConstraint(_in("tipo", FILA_TIPOS), name="ck_mercado_coleta_itens_tipo"),
        Index("ix_mercado_coleta_itens_coleta", "coleta_id", "recebido_em"),
        Index("ix_mercado_coleta_itens_tarefa", "tarefa_id"),
        Index("ix_mercado_coleta_itens_dia", "data_local", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    coleta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"),
                                                 nullable=False)
    tarefa_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_fila.id"))
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    fonte: Mapped[Fonte | None] = mapped_column(Enum(Fonte, name="mercado_fonte"))
    status: Mapped[ItemStatus] = mapped_column(
        Enum(ItemStatus, name="mercado_coleta_item_status"), nullable=False)
    erro_codigo: Mapped[str | None] = mapped_column(Text)
    erro_campo: Mapped[str | None] = mapped_column(Text)
    duracao_ms: Mapped[int | None] = mapped_column(Integer)
    recebido_em: Mapped[datetime] = mapped_column(_ts(), nullable=False,
                                                  server_default=func.now())
    coletado_em: Mapped[datetime] = mapped_column(_ts(), nullable=False)
    data_local: Mapped[date] = mapped_column(Date, nullable=False)
    turno: Mapped[Turno | None] = mapped_column(Enum(Turno, name="mercado_turno"))
    esquema_versao: Mapped[str | None] = mapped_column(Text)
    bruto_ref: Mapped[str | None] = mapped_column(Text)
    bruto_bytes: Mapped[int | None] = mapped_column(Integer)
    reprocessado_de: Mapped[int | None] = mapped_column(BigInteger,
                                                        ForeignKey("mercado_coleta_itens.id"))


# ---- interesse (por perfil; versionado) ----

class Interesse(AuditMixin, Base):
    __tablename__ = "mercado_interesses"
    __table_args__ = (
        CheckConstraint("(perfil_id IS NULL) = (origem = 'vitrine')",
                        name="ck_mercado_interesses_vitrine"),
        CheckConstraint("char_length(nota) <= 2000", name="ck_mercado_interesses_nota"),
        Index("uq_mercado_interesses_vivo", text("coalesce(perfil_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
              "mercado_produto_id", "origem", unique=True,
              postgresql_where=text("situacao IN ('ativo', 'pausado')")),
        Index("ix_mercado_interesses_perfil", "perfil_id", "situacao", text("created_at DESC")),
        Index("ix_mercado_interesses_produto", "mercado_produto_id", "situacao"),
        Index("ix_mercado_interesses_auto_dia", "perfil_id", "created_at",
              postgresql_where=text("origem IN ('ranking', 'loja', 'categoria')")),
    )
    __versioned_fields__ = ("situacao", "nota", "produto_id", "tema_id")
    __immutable_fields__ = ("perfil_id", "mercado_produto_id", "origem", "motivo")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("perfis.id"))
    mercado_produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mercado_produtos.id"),
                                                          nullable=False)
    origem: Mapped[InteresseOrigem] = mapped_column(
        Enum(InteresseOrigem, name="mercado_interesse_origem"), nullable=False)
    situacao: Mapped[InteresseSituacao] = mapped_column(
        Enum(InteresseSituacao, name="mercado_interesse_situacao"), nullable=False,
        default=InteresseSituacao.ativo, server_default=InteresseSituacao.ativo.value)
    motivo: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                   server_default=text("'{}'::jsonb"))
    nota: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # FK para `produtos` (012) só na migration, e só se a tabela existir.
    produto_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    tema_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("aprendizado_temas.id"))
    pausado_em: Mapped[datetime | None] = mapped_column(_ts())
    encerrado_em: Mapped[datetime | None] = mapped_column(_ts())
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))


class PerfilConfig(AuditMixin, Base):
    __tablename__ = "mercado_perfil_config"
    __table_args__ = (
        CheckConstraint(MERCADO_CHECK, name="ck_mercado_perfil_config_mercado"),
        CheckConstraint("cardinality(categoria_ids) <= 5",
                        name="ck_mercado_perfil_config_categorias"),
        CheckConstraint("max_relacionados_dia BETWEEN 0 AND 50",
                        name="ck_mercado_perfil_config_relacionados"),
    )
    __versioned_fields__ = ("mercado", "categoria_ids", "lojas_seguidas", "max_relacionados_dia",
                            "avisar_novo_em_alta")

    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), primary_key=True)
    mercado: Mapped[str] = mapped_column(Text, nullable=False, default="BR", server_default="BR")
    categoria_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), nullable=False, default=list, server_default=text("'{}'"))
    lojas_seguidas: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), nullable=False, default=list, server_default=text("'{}'"))
    max_relacionados_dia: Mapped[int] = mapped_column(Integer, nullable=False, default=10,
                                                      server_default=text("10"))
    avisar_novo_em_alta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                                      server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))

    @property
    def id(self) -> uuid.UUID:  # o `history.record` usa `entity.id`
        return self.perfil_id


SO_INSERCAO = ("mercado_loja_fotos", "mercado_produto_fichas", "mercado_imagens",
               "mercado_produto_imagens", "mercado_produto_fotos", "mercado_ranking_fotos",
               "mercado_ranking_foto_itens", "mercado_avaliacoes", "mercado_produto_videos",
               "mercado_coleta_itens", "coleta_eventos")
LAGO = ("mercado_categorias", "mercado_lojas", "mercado_loja_fotos", "mercado_produtos",
        "mercado_produto_fichas", "mercado_imagens", "mercado_produto_imagens",
        "mercado_produto_fotos", "mercado_ranking_fotos", "mercado_ranking_foto_itens",
        "mercado_avaliacoes", "mercado_produto_videos")
