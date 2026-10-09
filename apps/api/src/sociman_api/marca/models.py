"""Modelos do kit de marca e das fontes próprias (data-model.md da spec 004).

O kit é um por perfil e preguiçoso (R10): sem linha, a API devolve o kit padrão com
`version: 0`. Cada seção fica numa coluna JSONB, validada antes pelo `KitTokens`
(`marca.tokens`), para o histórico dizer qual seção mudou. Fontes nunca são apagadas, só
arquivadas (FR-009).
"""

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Index, Integer, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.perfis.models import _Versioned

# Seções do kit, na ordem do snapshot do histórico.
KIT_SECTIONS = ("palette", "caption", "hook", "watermark", "end_card", "catchphrases", "series")


class FontFormat(enum.StrEnum):
    ttf = "ttf"
    otf = "otf"


class BrandKit(AuditMixin, Base):
    """Sem `archived_at`: o kit não é arquivado (o perfil é)."""

    __tablename__ = "brand_kits"
    __versioned_fields__ = KIT_SECTIONS
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("perfis.id"), nullable=False, unique=True
    )
    palette: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    caption: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hook: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    watermark: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    end_card: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    catchphrases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    series: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class BrandFont(_Versioned, AuditMixin, Base):
    """O arquivo é imutável: trocar o arquivo é enviar outra fonte."""

    __tablename__ = "brand_fonts"
    __table_args__ = (
        # 409 font_name_in_use: o nome não se repete entre as fontes ativas do perfil.
        Index(
            "uq_brand_fonts_perfil_lower_name",
            "perfil_id", func.lower(text("name")),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )
    __versioned_fields__ = ("name", "archived")
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    family: Mapped[str] = mapped_column(Text, nullable=False)  # getname()[0]
    style: Mapped[str] = mapped_column(Text, nullable=False)  # getname()[1]
    format: Mapped[FontFormat] = mapped_column(
        Enum(FontFormat, name="font_format"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
