"""Postagens preparadas e sugestões de texto (data-model.md da spec 006, R9 e R10).

O SociMan nunca publica (princípio I): `postado` só é marcado pela rota humana. Uma postagem
por corte e conta de destino (a conta dá a plataforma). O snapshot versionado é o histórico dos
textos (US5-2). `sugestoes_texto` é o log imutável de cada chamada ao Claude (só INSERT).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.perfis.models import Platform, _Versioned


class EstadoPostagem(enum.StrEnum):
    rascunho = "rascunho"
    agendado = "agendado"
    postado = "postado"


class SugestaoTexto(Base):
    """Só INSERT: o que o Claude devolveu (validado), com custo e duração."""

    __tablename__ = "sugestoes_texto"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    corte_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cortes.id"), nullable=False)
    plataforma: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform"), nullable=False
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)  # ex.: textos/1
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {titulo, descricao, hashtags}
    ajustes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    erro_code: Mapped[str | None] = mapped_column(Text)  # timeout|refusal|invalid|api_error
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class Postagem(_Versioned, AuditMixin, Base):
    __tablename__ = "postagens"
    __table_args__ = (
        CheckConstraint("char_length(titulo) <= 100", name="ck_postagens_titulo"),
        CheckConstraint("char_length(descricao) <= 2000", name="ck_postagens_descricao"),
        CheckConstraint("estado <> 'agendado' OR planned_at IS NOT NULL",
                        name="ck_postagens_agendado_planned"),
        # Uma postagem ativa por corte e conta (409 postagem_exists).
        Index("uq_postagens_corte_conta_ativa", "corte_id", "conta_id", unique=True,
              postgresql_where=text("archived_at IS NULL")),
    )
    __versioned_fields__ = (
        "conta_id", "titulo", "descricao", "hashtags", "estado", "planned_at", "posted_url",
        "archived",
    )
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    corte_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cortes.id"), nullable=False)
    conta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contas.id"), nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    hashtags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    estado: Mapped[EstadoPostagem] = mapped_column(
        Enum(EstadoPostagem, name="postagem_estado"),
        nullable=False,
        default=EstadoPostagem.rascunho,
        server_default=EstadoPostagem.rascunho.value,
    )
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lembrado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_url: Mapped[str | None] = mapped_column(Text)
    sugestao_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sugestoes_texto.id")
    )


Index("ix_postagens_estado_planned", Postagem.estado, Postagem.planned_at)
