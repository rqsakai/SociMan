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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sociman_api.assets import padrao
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
    kit = "kit"  # spec 025: um arquivo por slot do kit padrão
    variacao = "variacao"  # spec 025: variação da cena do cenário


class AssetOrigem(enum.StrEnum):
    upload = "upload"
    sintetico = "sintetico"
    pessoa_real = "pessoa_real"


class KitStatus(enum.StrEnum):
    incompleto = "incompleto"
    completo = "completo"
    atencao = "atencao"


# O `kit` primeiro (na ordem dos slots), depois os papéis da 007 e a variação.
_ROLE_ORDER = {FileRole.kit: 0, FileRole.referencia: 1, FileRole.pose: 2, FileRole.arquivo: 3,
               FileRole.variacao: 4}
_SLOT_ORDER = {s: i for i, s in enumerate(padrao.SLOTS)}


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
        "origem", "consentimento", "voz_id", "identidade", "kit_status",  # spec 025
        "perfil_id",  # spec 029: o perfil base
    )
    __immutable_fields__ = ("tipo",)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("perfis.id"))  # 029: opcional
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
    # Spec 025: o cadastro padronizado (só avatar; `kit_status` também no cenário).
    origem: Mapped[AssetOrigem | None] = mapped_column(Enum(AssetOrigem, name="asset_origem"))
    consentimento: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    voz_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("vozes.id", use_alter=True, name="fk_assets_voz"))
    identidade: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    kit_status: Mapped[KitStatus | None] = mapped_column(Enum(KitStatus, name="asset_kit_status"))

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
             "position": f.position, "archived": f.archived, "slot": f.slot,
             "geracao_id": f.geracao_id}
            for f in sorted_files(self.arquivos)
        ]

    def active_files(self, role: FileRole | None = None) -> list["AssetFile"]:
        return [f for f in sorted_files(self.arquivos)
                if not f.archived and (role is None or f.role == role)]

    def slot_ativo(self, slot: str) -> "AssetFile | None":
        return next((f for f in self.active_files(FileRole.kit) if f.slot == slot), None)

    def slots_ativos(self) -> set[str]:
        return {f.slot for f in self.active_files(FileRole.kit) if f.slot}

    @property
    def revogado(self) -> bool:
        return bool((self.consentimento or {}).get("revogado_em"))


Index("ix_assets_perfil_lista", Asset.perfil_id, Asset.archived_at, Asset.updated_at.desc(),
      Asset.id)
Index("ix_assets_tags", Asset.tags, postgresql_using="gin")
Index("ix_assets_lista_agencia", Asset.archived_at, Asset.updated_at.desc(), Asset.id)  # 029
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
    # Spec 025: o slot do kit e a geração de onde veio (null = enviado à mão).
    slot: Mapped[str | None] = mapped_column(Text)
    geracao_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("geracoes.id", use_alter=True, name="fk_asset_files_geracao"))
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
                                        _SLOT_ORDER.get(f.slot or "", 99), f.position,
                                        str(f.id)))


# Spec 025: as FKs `assets.voz_id` → `vozes` e `asset_files.geracao_id` → `geracoes`.
from sociman_api.geracao import models as _geracao_models  # noqa: F401
from sociman_api.vozes import models as _vozes_models  # noqa: F401
