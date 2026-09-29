"""Modelos de perfis, contas e imagens (data-model.md da spec 003).

Nada aqui é apagado (FR-014): perfis e contas são arquivados (`archived_at`), e imagens são
imutáveis (FR-010). Toda mutação de perfil ou conta gera uma versão em `entity_versions`
(`sociman_api.history`).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class PerfilStatus(enum.StrEnum):
    em_preparacao = "em_preparacao"
    ativo = "ativo"
    pausado = "pausado"


class Platform(enum.StrEnum):
    tiktok = "tiktok"
    youtube = "youtube"
    instagram = "instagram"
    kwai = "kwai"
    facebook = "facebook"
    x = "x"
    outra = "outra"


class ContaStatus(enum.StrEnum):
    planejada = "planejada"
    ativa = "ativa"
    pausada = "pausada"
    encerrada = "encerrada"


class ImageKind(enum.StrEnum):
    logo = "logo"
    banner = "banner"
    watermark = "watermark"  # imagem própria de marca d'água (spec 004)
    fundo = "fundo"  # imagem de fundo do gancho e do card final (spec 004, FR-005b)
    avatar = "avatar"  # referência e pose de avatar (spec 007)
    imagem = "imagem"  # imagem genérica da biblioteca (spec 007)


class _Versioned:
    """Controle otimista (R2) + arquivamento (R3). `version` é também o nº da versão atual."""

    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))

    @property
    def archived(self) -> bool:
        return self.archived_at is not None


class Perfil(_Versioned, AuditMixin, Base):
    __tablename__ = "perfis"
    __table_args__ = (
        CheckConstraint(
            f"slug ~ '{SLUG_PATTERN}' AND char_length(slug) BETWEEN 2 AND 60",
            name="ck_perfis_slug_format",
        ),
    )
    # Snapshot do histórico. O slug entra só para exibição: é imutável (FR-002a), e a
    # reversão o ignora.
    __versioned_fields__ = (
        "slug", "name", "niche", "bio", "language", "status", "logo_image_id",
        "banner_image_id", "archived",
    )
    __immutable_fields__ = ("slug",)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    niche: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    bio: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    language: Mapped[str] = mapped_column(
        Text, nullable=False, default="pt-BR", server_default="pt-BR"
    )
    status: Mapped[PerfilStatus] = mapped_column(
        Enum(PerfilStatus, name="perfil_status"),
        nullable=False,
        default=PerfilStatus.em_preparacao,
        server_default=PerfilStatus.em_preparacao.value,
    )
    # use_alter: images.perfil_id aponta de volta para perfis (ciclo de FKs).
    logo_image_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("images.id", use_alter=True, name="fk_perfis_logo_image_id")
    )
    banner_image_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("images.id", use_alter=True, name="fk_perfis_banner_image_id")
    )


Index("ix_perfis_archived_status", Perfil.archived_at, Perfil.status)
Index("ix_perfis_lower_name", func.lower(Perfil.name))


class Conta(_Versioned, AuditMixin, Base):
    __tablename__ = "contas"
    __table_args__ = (
        # FR-005: o mesmo @ não se repete na plataforma, contando também as arquivadas.
        UniqueConstraint("platform", "platform_name", "handle",
                         name="uq_contas_platform_handle"),
        # FR-005: no máximo uma conta ativa por plataforma em cada perfil.
        Index(
            "uq_contas_perfil_platform_ativa",
            "perfil_id", "platform", "platform_name",
            unique=True,
            postgresql_where=text("status = 'ativa' AND archived_at IS NULL"),
        ),
    )
    __versioned_fields__ = (
        "platform", "platform_name", "handle", "url", "status", "notes", "archived",
    )
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    # Obrigatório (1..40) quando platform = outra; vazio nas demais (validado no service).
    platform_name: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    handle: Mapped[str] = mapped_column(Text, nullable=False)  # normalizado, sem @
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ContaStatus] = mapped_column(
        Enum(ContaStatus, name="conta_status"),
        nullable=False,
        default=ContaStatus.planejada,
        server_default=ContaStatus.planejada.value,
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")


class Image(Base):
    """Imutável e nunca apagada (FR-010); o objeto no MinIO também fica."""

    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    kind: Mapped[ImageKind] = mapped_column(Enum(ImageKind, name="image_kind"), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
