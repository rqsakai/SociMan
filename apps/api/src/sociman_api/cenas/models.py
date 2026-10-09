"""Cenas para o Flow/Veo (data-model.md da spec 010, research R1).

- `cenas`: a tomada reutilizável de um perfil (`entity_type = "cena"`). Referencia os assets da
  007 por id (avatar com o arquivo de look ou pose, cenário e foto do produto), sem copiar
  arquivos. O prompt é montado ao vivo em `rascunho` e **congelado** em `pronta`/`usada`
  (`ck_cenas_congelado`, Q3);
- `cena_tomadas`: os vídeos gerados no Flow (`entity_type = "cena_tomada"`), no bucket de vídeos,
  cada um com o prompt congelado do momento do envio;
- `cena_usos`: o vínculo cena × conteúdo vídeo próprio (Q2), sem `version` própria: o histórico
  fica na cena e no conteúdo (research R7);
- `cena_padroes`: estilo e negative padrão do perfil (`entity_type = "cena_padroes"`); sem linha =
  padrão do código, `version 0`.

Nada é apagado: cenas e tomadas são arquivadas, e o vínculo é desfeito (`desfeito_em`).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.assets import models as _assets_models  # noqa: F401 — FKs para assets
from sociman_api.auth.models import AuditMixin
from sociman_api.conteudos import models as _conteudos_models  # noqa: F401 — FK conteudos
from sociman_api.db import Base
from sociman_api.perfis.models import _Versioned
from sociman_api.produtos import models as _produtos_models  # noqa: F401 — FKs (spec 012)

ESTILO_PADRAO = "vertical 9:16, natural soft light, realistic, warm retro color grading"
NEGATIVE_PADRAO = "text, subtitles, watermark, logo changes, extra fingers, distorted product"


class TomadaOrigem(enum.StrEnum):
    """Como a tomada nasceu. Ponto de extensão: a 021 (geração local) poderá acrescentar valores."""

    flow_manual = "flow_manual"


class CenaStatus(enum.StrEnum):
    rascunho = "rascunho"
    pronta = "pronta"
    usada = "usada"


class CenaModo(enum.StrEnum):
    ingredientes = "ingredientes"
    quadros = "quadros"
    estender = "estender"


class CenaPlano(enum.StrEnum):
    close = "close"
    busto = "busto"
    medio = "medio"
    americano = "americano"
    aberto = "aberto"
    detalhe_produto = "detalhe_produto"


class CenaMovimento(enum.StrEnum):
    parada = "parada"
    aproximacao = "aproximacao"
    afastamento = "afastamento"
    panoramica = "panoramica"
    camera_na_mao = "camera_na_mao"


# Editáveis da cena (o corpo de `CenaIn`), na ordem do contrato.
CAMPOS_EDITAVEIS = (
    "nome", "avatar_id", "avatar_arquivo_id", "cenario_id", "cenario_arquivo_id", "plano",
    "movimento", "camera", "acao", "fala", "texto_tela", "estilo", "audio", "duracao_s", "modo",
    "quadro_inicial", "quadro_final", "produto_nome", "produto_imagem_id", "produto_id",
    "produto_variante_id", "negative", "tags", "notas",
)
# Editar um destes numa cena `pronta` a devolve a `rascunho`; numa `usada`, 409 `cena_usada`.
CAMPOS_PROMPT = frozenset({
    "avatar_id", "avatar_arquivo_id", "cenario_id", "cenario_arquivo_id", "plano", "movimento",
    "camera", "acao", "fala", "estilo", "audio", "duracao_s", "modo", "quadro_inicial",
    "quadro_final", "produto_nome", "produto_imagem_id", "produto_id", "produto_variante_id",
    "negative",
})


class Cena(_Versioned, AuditMixin, Base):
    __tablename__ = "cenas"
    __table_args__ = (
        CheckConstraint("duracao_s IN (4, 6, 8)", name="ck_cenas_duracao"),
        CheckConstraint(
            "(status = 'rascunho') = (prompt_congelado IS NULL) "
            "AND (prompt_congelado IS NULL) = (negative_congelado IS NULL)",
            name="ck_cenas_congelado"),
        CheckConstraint("produto_imagem_id IS NULL OR produto_nome IS NOT NULL",
                        name="ck_cenas_produto"),
    )
    __versioned_fields__ = (
        *CAMPOS_EDITAVEIS, "status", "prompt_congelado", "negative_congelado",
        "avatar_version_congelada", "cenario_version_congelada", "tomada_escolhida_id",
        "archived", "perfil_id", "duplicada_de",
    )
    __immutable_fields__ = ("perfil_id", "duplicada_de")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id"))
    avatar_arquivo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                                ForeignKey("asset_files.id"))
    cenario_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id"))
    cenario_arquivo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                                 ForeignKey("asset_files.id"))
    plano: Mapped[CenaPlano | None] = mapped_column(Enum(CenaPlano, name="cena_plano"))
    movimento: Mapped[CenaMovimento | None] = mapped_column(
        Enum(CenaMovimento, name="cena_movimento"))
    camera: Mapped[str | None] = mapped_column(Text)
    acao: Mapped[str] = mapped_column(Text, nullable=False)
    fala: Mapped[str | None] = mapped_column(Text)
    texto_tela: Mapped[str | None] = mapped_column(Text)
    estilo: Mapped[str | None] = mapped_column(Text)
    audio: Mapped[str | None] = mapped_column(Text)
    duracao_s: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=8,
                                           server_default=text("8"))
    modo: Mapped[CenaModo] = mapped_column(Enum(CenaModo, name="cena_modo"), nullable=False,
                                           default=CenaModo.ingredientes,
                                           server_default=CenaModo.ingredientes.value)
    quadro_inicial: Mapped[str | None] = mapped_column(Text)
    quadro_final: Mapped[str | None] = mapped_column(Text)
    produto_nome: Mapped[str | None] = mapped_column(Text)
    produto_imagem_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id"))
    # Spec 012 (R13): o produto do catálogo, no lugar da referência leve (`ck_cenas_produto_modo`).
    produto_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("produtos.id"))
    produto_variante_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("produto_variantes.id"))
    negative: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list,
                                            server_default=text("'{}'"))
    notas: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[CenaStatus] = mapped_column(
        Enum(CenaStatus, name="cena_status"), nullable=False, default=CenaStatus.rascunho,
        server_default=CenaStatus.rascunho.value)
    prompt_congelado: Mapped[str | None] = mapped_column(Text)
    negative_congelado: Mapped[str | None] = mapped_column(Text)
    avatar_version_congelada: Mapped[int | None] = mapped_column(Integer)
    cenario_version_congelada: Mapped[int | None] = mapped_column(Integer)
    # FK deferível para `cena_tomadas` (ciclo); criada na migration.
    tomada_escolhida_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cena_tomadas.id", use_alter=True, name="fk_cenas_tomada_escolhida",
                         deferrable=True, initially="DEFERRED"))
    duplicada_de: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cenas.id"))


class CenaTomada(_Versioned, AuditMixin, Base):
    __tablename__ = "cena_tomadas"
    __table_args__ = (
        CheckConstraint("duracao_ms BETWEEN 1000 AND 30000", name="ck_cena_tomadas_duracao"),
    )
    __versioned_fields__ = ("nota", "archived", "origem")
    __immutable_fields__ = ("origem",)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cena_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cenas.id"), nullable=False)
    origem: Mapped[TomadaOrigem] = mapped_column(
        Enum(TomadaOrigem, name="tomada_origem"), nullable=False,
        default=TomadaOrigem.flow_manual, server_default=TomadaOrigem.flow_manual.value)
    video_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    duracao_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    largura: Mapped[int] = mapped_column(Integer, nullable=False)
    altura: Mapped[int] = mapped_column(Integer, nullable=False)
    miniatura_key: Mapped[str] = mapped_column(Text, nullable=False)  # bucket `sociman`
    prompt_usado: Mapped[str] = mapped_column(Text, nullable=False)
    negative_usado: Mapped[str] = mapped_column(Text, nullable=False)
    nota: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")


class CenaUso(Base):
    __tablename__ = "cena_usos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cena_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cenas.id"), nullable=False)
    conteudo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conteudos.id"),
                                                   nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                server_default=func.now())
    criado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    desfeito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desfeito_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class CenaPadroes(AuditMixin, Base):
    __tablename__ = "cena_padroes"
    __versioned_fields__ = ("estilo", "negative")

    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"),
                                                 primary_key=True)
    estilo: Mapped[str] = mapped_column(Text, nullable=False)
    negative: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))

    @property
    def id(self) -> uuid.UUID:  # o `history.record` usa `entity.id`
        return self.perfil_id
