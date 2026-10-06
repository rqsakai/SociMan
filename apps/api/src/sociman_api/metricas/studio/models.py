"""Importações e dias importados do Studio (data-model.md da spec 020).

- `Importacao`: uma confirmação do dono para uma série da 016; versionada (`history`,
  `entity_type = "studio_importacao"`), de `ativa` para `desfeita` (sem DELETE). Os
  `nomes_arquivos` (com o @) ficam fora do snapshot e somem na anonimização;
- `DiaStudio`: **só inserção** (trigger `metricas_studio_so_insercao` da 0013), sem `version`
  (exceção do princípio VII, como as fotos da 016). Quem decide o valor que vale é
  `efetivo` (a importação ativa mais antiga).
"""

import enum
import uuid
from datetime import date, datetime
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
from sociman_api.metricas import models as _metricas_models  # noqa: F401 — FK para séries

SECOES = ("visao_geral", "seguidores")
ANO_ORIGENS = ("nome_zip", "deduzido", "misto")
ENTITY_TYPE = "studio_importacao"


class ImportacaoEstado(enum.StrEnum):
    ativa = "ativa"
    desfeita = "desfeita"


class Importacao(AuditMixin, Base):
    __tablename__ = "metricas_studio_importacoes"
    __table_args__ = (
        CheckConstraint("cardinality(secoes) BETWEEN 1 AND 2 "
                        "AND secoes <@ ARRAY['visao_geral','seguidores']::text[]",
                        name="ck_studio_imp_secoes"),
        CheckConstraint("(('visao_geral' = ANY(secoes)) = (sha_visao_geral IS NOT NULL)) "
                        "AND (('seguidores' = ANY(secoes)) = (sha_seguidores IS NOT NULL))",
                        name="ck_studio_imp_sha"),
        CheckConstraint("(estado = 'desfeita') = "
                        "(desfeita_em IS NOT NULL AND desfeita_por IS NOT NULL)",
                        name="ck_studio_imp_desfeita"),
        CheckConstraint("periodo_de <= periodo_ate", name="ck_studio_imp_periodo"),
        CheckConstraint("ano_origem IN ('nome_zip','deduzido','misto')",
                        name="ck_studio_imp_ano"),
        Index("ix_studio_imp_serie", "serie_id", "estado", "criada_em", "id"),
        Index("ix_studio_imp_sha_vg", "serie_id", "sha_visao_geral",
              postgresql_where=text("estado = 'ativa'")),
        Index("ix_studio_imp_sha_seg", "serie_id", "sha_seguidores",
              postgresql_where=text("estado = 'ativa'")),
    )
    # Sem nome de arquivo nem handle (FR-017). Não há revert genérico: desfazer é a reversão.
    __versioned_fields__ = ("estado", "secoes", "periodo_de", "periodo_ate", "ano_origem",
                            "contagens", "sha_visao_geral", "sha_seguidores", "desfeita_em",
                            "desfeita_por")
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    serie_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("metricas_series.id"),
                                                nullable=False)
    secoes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    sha_visao_geral: Mapped[str | None] = mapped_column(Text)  # SHA-256 dos bytes do CSV
    sha_seguidores: Mapped[str | None] = mapped_column(Text)
    periodo_de: Mapped[date] = mapped_column(Date, nullable=False)
    periodo_ate: Mapped[date] = mapped_column(Date, nullable=False)
    ano_origem: Mapped[str] = mapped_column(Text, nullable=False)  # ver ANO_ORIGENS
    contagens: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    nomes_arquivos: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    estado: Mapped[ImportacaoEstado] = mapped_column(
        Enum(ImportacaoEstado, name="studio_importacao_estado"), nullable=False,
        default=ImportacaoEstado.ativa, server_default=ImportacaoEstado.ativa.value)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                server_default=func.now())
    criada_por: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    desfeita_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desfeita_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))


class DiaStudio(Base):
    """Só inserção (trigger `metricas_studio_so_insercao`)."""

    __tablename__ = "metricas_studio_dias"
    __table_args__ = (
        UniqueConstraint("importacao_id", "dia", name="uq_studio_dias_imp_dia"),
        CheckConstraint("(tem_visao_geral OR tem_seguidores) "
                        "AND tem_visao_geral = (views IS NOT NULL) "
                        "AND tem_seguidores = (seguidores IS NOT NULL)",
                        name="ck_studio_dias_secao"),
        CheckConstraint(" AND ".join(f"({c} IS NULL OR {c} >= 0)" for c in (
            "views", "visitas_perfil", "likes", "comments", "shares", "seguidores")),
            name="ck_studio_dias_naoneg"),
        Index("ix_studio_dias_serie_dia", "serie_id", "dia"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    importacao_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("metricas_studio_importacoes.id"), nullable=False)
    serie_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("metricas_series.id"),
                                                nullable=False)
    dia: Mapped[date] = mapped_column(Date, nullable=False)  # dia de calendário do arquivo
    tem_visao_geral: Mapped[bool] = mapped_column(Boolean, nullable=False)
    views: Mapped[int | None] = mapped_column(BigInteger)
    visitas_perfil: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    tem_seguidores: Mapped[bool] = mapped_column(Boolean, nullable=False)
    seguidores: Mapped[int | None] = mapped_column(BigInteger)
    seguidores_dif: Mapped[int | None] = mapped_column(BigInteger)  # pode ser negativa
