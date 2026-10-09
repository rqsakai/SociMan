"""Schemas da biblioteca de assets (contracts/http-api.md da 007). JSON em camelCase.

Aqui ficam formato e limites (data-model.md). As regras que dependem do tipo do asset ou do
papel do arquivo (`check_campos`, `check_file_campos`) dão 400 `invalid_asset` com `field`,
como o `invalid_kit`, e o service as chama.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, ConfigDict, Field, StringConstraints

from sociman_api.assets import tipos
from sociman_api.assets.models import AssetTipo, FileRole
from sociman_api.auth.schemas import CamelModel
from sociman_api.errors import ApiError
from sociman_api.ia.aplicacao import IaAplicacoes
from sociman_api.perfis.schemas import ImageRef, UserRef, VersionNumber

MAX_TAGS = 20
MAX_TAG_LEN = 30

AssetName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
# Sem strip: o texto é copiado exatamente como foi escrito (FR-009).
Prompt = Annotated[str, StringConstraints(max_length=2000)]
VoiceTone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
ImageRules = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Look = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Uso = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
QuandoUsar = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


def normalize_tags(values: list[str]) -> list[str]:
    """Minúsculas, sem espaço nas pontas, 1..30 caracteres, sem repetição, até 20."""
    out: list[str] = []
    for raw in values:
        tag = raw.strip().lower()
        if not tag:
            raise ValueError("tag vazia")
        if len(tag) > MAX_TAG_LEN:
            raise ValueError(f"cada tag tem até {MAX_TAG_LEN} caracteres")
        if tag not in out:
            out.append(tag)
    if len(out) > MAX_TAGS:
        raise ValueError(f"no máximo {MAX_TAGS} tags")
    return out


Tags = Annotated[list[str], AfterValidator(normalize_tags)]


def invalid(field: str, message: str) -> ApiError:
    return ApiError(400, "invalid_asset", f"{field}: {message}", details={"field": field})


_CAMEL = {"voice_tone": "voiceTone", "image_rules": "imageRules", "quando_usar": "quandoUsar"}


def check_campos(tipo: AssetTipo, values: dict[str, Any]) -> None:
    """Campos de avatar só no avatar; `prompt` também no cenário (valor nulo sempre passa)."""
    for field, allowed in tipos.FIELD_TIPOS.items():
        if values.get(field) is not None and tipo not in allowed:
            raise invalid(_CAMEL.get(field, field), "campo não se aplica a este tipo")


def check_file_campos(tipo: AssetTipo, role: FileRole, values: dict[str, Any]) -> None:
    """Papel compatível com o tipo e campos do arquivo compatíveis com o papel."""
    if role not in tipos.ROLES[tipo]:
        raise invalid("role", "papel não se aplica a este tipo")
    for field, roles in tipos.FILE_FIELD_ROLES.items():
        if values.get(field) is not None and role not in roles:
            raise invalid(_CAMEL.get(field, field), "campo não se aplica a este papel")
    if values.get("look") is not None and tipo != AssetTipo.avatar:
        raise invalid("look", "campo não se aplica a este tipo")


# ---- entradas ----

class AssetCreate(CamelModel):
    model_config = ConfigDict(extra="forbid")

    tipo: AssetTipo
    name: AssetName
    description: Description = Field(default_factory=str)  # opcional no TS gerado
    tags: Tags = Field(default_factory=list)
    prompt: Prompt | None = None
    voice_tone: VoiceTone | None = None
    image_rules: ImageRules | None = None


class AssetPatch(CamelModel):
    # extra="forbid": o tipo é imutável; mandá-lo dá 400, não é ignorado.
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    name: AssetName | None = None
    description: Description | None = None
    tags: Tags | None = None
    prompt: Prompt | None = None
    voice_tone: VoiceTone | None = None
    image_rules: ImageRules | None = None
    primary_file_id: UUID | None = None
    # Spec 008: campos aplicados de uma chamada da IA (marca "com ajuda da IA" na versão).
    ia: IaAplicacoes | None = None


class FilePatch(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    look: Look | None = None
    uso: Uso | None = None
    label: Label | None = None
    quando_usar: QuandoUsar | None = None
    notes: Notes | None = None


class Ordem(CamelModel):
    version: VersionNumber
    role: FileRole
    file_ids: list[UUID] = Field(max_length=500)


# ---- saídas ----

class AssetFile(CamelModel):
    id: UUID
    role: FileRole
    look: str | None
    uso: str | None
    label: str | None
    quando_usar: str | None
    notes: str
    position: int
    archived: bool
    image: ImageRef
    preview_url: str  # imgproxy 1024×1024 (fit)
    content_type: str
    bytes: int
    has_alpha: bool  # images.kind = watermark (miniatura sobre xadrez)
    link: str  # /api/midia/{token}, sem validade e estável (R7)
    download_url: str  # o mesmo com ?download=1
    created_at: datetime
    created_by: UserRef | None


class AssetSummary(CamelModel):
    id: UUID
    perfil_id: UUID
    tipo: AssetTipo
    name: str
    tags: list[str]
    cover: ImageRef | None
    file_count: int  # arquivos ativos
    in_use: bool
    archived: bool
    version: int
    updated_at: datetime


class Asset(AssetSummary):
    description: str
    prompt: str | None
    voice_tone: str | None
    image_rules: str | None
    primary_file_id: UUID | None
    files: list[AssetFile]  # ativos e arquivados, por papel e ordem
    created_at: datetime
    created_by: UserRef | None
    updated_by: UserRef | None


class Uso(CamelModel):
    origem: str  # "kit" | "corte" (futuro: "roteiro", "cena")
    rotulo: str
    campo: str | None
    file_id: UUID
    bloqueia: bool
    href: str | None


class TagCount(CamelModel):
    tag: str
    count: int


class LibraryImage(CamelModel):
    image: ImageRef
    asset_id: UUID
    asset_name: str
    asset_tipo: AssetTipo
    file_id: UUID
    label: str | None
    has_alpha: bool


class AssetOut(CamelModel):
    asset: Asset


class AssetDetail(CamelModel):
    asset: Asset
    usos: list[Uso]


class AssetFileOut(CamelModel):
    asset: Asset
    file: AssetFile


class AssetsList(CamelModel):
    items: list[AssetSummary]  # mais recentes primeiro (updatedAt)
    next_cursor: str | None
    tags: list[TagCount]


class LibraryImagesList(CamelModel):
    items: list[LibraryImage]  # mais recentes primeiro


ArchivedFilter = Literal["false", "true", "all"]
