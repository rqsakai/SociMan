"""Modelos da biblioteca de assets (data-model.md da spec 007, research R1 e R4).

`assets` é o item da biblioteca; `asset_files` liga o asset a uma linha de `images` (da 003,
imutável) e guarda o papel da imagem no asset. O asset é o agregado do histórico
(`entity_type = "asset"`): os arquivos entram no snapshot pela propriedade `files`, então
enviar, editar, reordenar ou arquivar um arquivo é uma versão do asset. Nada é apagado.
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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.perfis.models import _Versioned


class AssetTipo(enum.StrEnum):
    avatar = "avatar"
    cenario = "cenario"
    fundo = "fundo"
    sticker = "sticker"
    marca_dagua = "marca_dagua"
    imagem = "imagem"


class FileRole(enum.StrEnum):
    referencia = "referencia"
    pose = "pose"
    arquivo = "arquivo"


_ROLE_ORDER = {role: i for i, role in enumerate(FileRole)}


class Asset(_Versioned, AuditMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "(tipo IN ('avatar', 'cenario') OR prompt IS NULL) AND "
            "(tipo = 'avatar' OR (voice_tone IS NULL AND image_rules IS NULL))",
            name="ck_assets_campos_por_tipo",
        ),
    )
    # O tipo entra só para exibição: é imutável (trocar o tipo é criar outro asset).
    __versioned_fields__ = (
        "tipo", "name", "description", "tags", "prompt", "voice_tone", "image_rules",
        "primary_file_id", "archived", "files",
    )
    __immutable_fields__ = ("tipo",)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    tipo: Mapped[AssetTipo] = mapped_column(Enum(AssetTipo, name="asset_tipo"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    # Guardado exatamente como enviado (sem trim): é copiado para o Flow/Veo (FR-009).
    prompt: Mapped[str | None] = mapped_column(Text)
    voice_tone: Mapped[str | None] = mapped_column(Text)
    image_rules: Mapped[str | None] = mapped_column(Text)
    # use_alter: asset_files.asset_id aponta de volta para assets (ciclo de FKs).
    primary_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("asset_files.id", use_alter=True, name="fk_assets_primary_file_id")
    )

    arquivos: Mapped[list["AssetFile"]] = relationship(
        primaryjoin="Asset.id == AssetFile.asset_id", foreign_keys="AssetFile.asset_id",
        lazy="selectin",
    )

    @property
    def files(self) -> list[dict[str, Any]]:
        """Os arquivos do snapshot: por papel, ativos antes dos arquivados, e pela ordem."""
        return [
            {"id": f.id, "image_id": f.image_id, "role": f.role, "look": f.look, "uso": f.uso,
             "label": f.label, "quando_usar": f.quando_usar, "notes": f.notes,
             "position": f.position, "archived": f.archived}
            for f in sorted_files(self.arquivos)
        ]

    def active_files(self, role: FileRole | None = None) -> list["AssetFile"]:
        return [f for f in sorted_files(self.arquivos)
                if not f.archived and (role is None or f.role == role)]


Index("ix_assets_perfil_lista", Asset.perfil_id, Asset.archived_at, Asset.updated_at.desc(),
      Asset.id)
Index("ix_assets_tags", Asset.tags, postgresql_using="gin")
Index("ix_assets_perfil_lower_name", Asset.perfil_id, func.lower(Asset.name))


class AssetFile(Base):
    """Sem `version` própria: toda mudança aqui é uma versão do asset (R4)."""

    __tablename__ = "asset_files"
    __table_args__ = (
        CheckConstraint(
            "(role = 'pose' OR (label IS NULL AND quando_usar IS NULL)) AND "
            "(role <> 'pose' OR label IS NOT NULL) AND "
            "(role = 'referencia' OR (look IS NULL AND uso IS NULL))",
            name="ck_asset_files_campos_por_papel",
        ),
        # 409 pose_label_in_use: o rótulo não se repete entre as poses ativas do avatar.
        Index(
            "uq_asset_files_pose_label",
            "asset_id", func.lower(text("label")),
            unique=True,
            postgresql_where=text("role = 'pose' AND archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("assets.id"), nullable=False)
    # Uma imagem está em no máximo um asset.
    image_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("images.id"), nullable=False, unique=True
    )
    role: Mapped[FileRole] = mapped_column(Enum(FileRole, name="asset_file_role"),
                                           nullable=False)
    look: Mapped[str | None] = mapped_column(Text)
    uso: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    quando_usar: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))

    @property
    def archived(self) -> bool:
        return self.archived_at is not None


Index("ix_asset_files_asset_role_position", AssetFile.asset_id, AssetFile.role,
      AssetFile.position)


def sorted_files(files: list[AssetFile]) -> list[AssetFile]:
    return sorted(files, key=lambda f: (_ROLE_ORDER[f.role], f.archived_at is not None,
                                        f.position, str(f.id)))
