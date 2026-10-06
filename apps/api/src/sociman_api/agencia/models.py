"""Importações da agência e os itens de cada uma (data-model.md da spec 013).

- `Importacao`: uma confirmação do dono; versionada (`history`, `entity_type =
  "importacao_agencia"`), de `processando` para `concluida` ou `falhou`, e de `concluida` para
  `desfeita` (sem DELETE). `progresso` e `progresso_em` ficam fora do snapshot (mudam a cada
  arquivo). Só uma `processando` por vez (índice único parcial);
- `ImportacaoItem`: **só inserção** (trigger `agencia_itens_so_insercao` da 0016), exceto as
  marcas do desfazer (`desfeito_em`, `desfazer_motivo`); sem `version` própria (exceção do
  princípio VII, como os dias da 020).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base

ENTITY_TYPE = "importacao_agencia"
TIPOS_ITEM = ("perfil", "conta", "guia", "anotacao", "canal", "vinculo_canal", "imagem_logo",
              "asset", "arquivo_asset", "clipe", "sugestao_bordao", "arquivo")


class ImportacaoEstado(enum.StrEnum):
    processando = "processando"
    concluida = "concluida"
    falhou = "falhou"
    desfeita = "desfeita"


class ItemResultado(enum.StrEnum):
    criado = "criado"
    atualizado = "atualizado"
    mantido = "mantido"
    igual = "igual"
    fora = "fora"
    nao_gravado = "nao_gravado"
    sugestao = "sugestao"


class Importacao(AuditMixin, Base):
    __tablename__ = "agencia_importacoes"
    __table_args__ = (
        CheckConstraint("(estado = 'desfeita') = "
                        "(desfeita_em IS NOT NULL AND desfeita_por IS NOT NULL)",
                        name="ck_agencia_imp_desfeita"),
        CheckConstraint("(estado = 'falhou') = (erro IS NOT NULL)", name="ck_agencia_imp_erro"),
        Index("ux_agencia_imp_processando", "estado", unique=True,
              postgresql_where=text("estado = 'processando'")),
        Index("ix_agencia_imp_criada", text("criada_em DESC"), text("id DESC")),
    )
    # Não há revert genérico: desfazer é a reversão (R10).
    __versioned_fields__ = ("estado", "contagens", "erro", "concluida_em", "desfeita_em",
                            "desfeita_por")
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    estado: Mapped[ImportacaoEstado] = mapped_column(
        Enum(ImportacaoEstado, name="importacao_agencia_estado"), nullable=False,
        default=ImportacaoEstado.processando,
        server_default=ImportacaoEstado.processando.value)
    raiz_shared: Mapped[str] = mapped_column(Text, nullable=False)
    raiz_clipes: Mapped[str] = mapped_column(Text, nullable=False)
    arquivos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # {id: sha256}
    contagens: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                      server_default=text("'{}'::jsonb"))
    progresso: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                      server_default=text("'{}'::jsonb"))
    progresso_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                   server_default=func.now())
    erro: Mapped[str | None] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                server_default=func.now())
    criada_por: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desfeita_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desfeita_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))


class ImportacaoItem(Base):
    """Só inserção (trigger `agencia_itens_so_insercao`), salvo as marcas do desfazer."""

    __tablename__ = "agencia_importacao_itens"
    __table_args__ = (
        CheckConstraint("tipo IN (" + ", ".join(f"'{t}'" for t in TIPOS_ITEM) + ")",
                        name="ck_agencia_item_tipo"),
        CheckConstraint("resultado NOT IN ('criado', 'atualizado') OR (entity_type IS NOT NULL "
                        "AND entity_id IS NOT NULL AND entity_version IS NOT NULL)",
                        name="ck_agencia_item_entidade"),
        Index("ix_agencia_item_imp", "importacao_id", "ordem"),
        Index("ix_agencia_item_chave", "chave", "importacao_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    importacao_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agencia_importacoes.id"), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    perfil_slug: Mapped[str | None] = mapped_column(Text)
    arquivo: Mapped[str] = mapped_column(Text, nullable=False)
    trecho: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    linha: Mapped[int | None] = mapped_column(Integer)
    chave: Mapped[str] = mapped_column(Text, nullable=False)
    impressao: Mapped[str] = mapped_column(Text, nullable=False)
    situacao: Mapped[str] = mapped_column(Text, nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text)
    escolha: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                    server_default=text("'{}'::jsonb"))
    resultado: Mapped[ItemResultado] = mapped_column(
        Enum(ItemResultado, name="importacao_item_resultado"), nullable=False)
    resultado_motivo: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    entity_version: Mapped[int | None] = mapped_column(Integer)
    desfeito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desfazer_motivo: Mapped[str | None] = mapped_column(Text)
