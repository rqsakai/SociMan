"""Modelos Pydantic das rotas do kit (contracts/http-api.md da 004). Raiz em camelCase; as
seções do kit seguem `marca.tokens` (snake_case, como no data-model)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from sociman_api.auth.schemas import CamelModel
from sociman_api.marca.tokens import KitTokens
from sociman_api.perfis.schemas import UserRef

__all__ = [
    "ExportAsset", "ExportAssets", "ExportKitMeta", "ExportPerfil", "FontOption", "Kit",
    "KitExport", "KitGet", "KitIn", "KitOut", "OpenShorts", "OpenShortsHook",
    "OpenShortsSubtitle",
]


class KitIn(KitTokens):
    """PUT do kit inteiro. `version: 0` cria a v1 (o kit nunca foi salvo)."""

    version: int = Field(ge=0)


class Kit(KitTokens):
    perfil_id: UUID
    version: int  # 0 = padrão ainda não salvo
    persisted: bool
    updated_at: datetime | None
    updated_by: UserRef | None


class FontOption(CamelModel):
    ref: str  # FonteRef
    name: str
    family: str
    url: str  # fonte padrão: pública; do perfil: link assinado de 1 h


class KitGet(CamelModel):
    kit: Kit
    font_options: list[FontOption]


class KitOut(CamelModel):
    kit: Kit


# ---- exportação (`sociman.kit/1`) ----

class ExportPerfil(CamelModel):
    id: UUID
    slug: str
    name: str


class ExportKitMeta(CamelModel):
    version: int
    updated_at: datetime | None


class OpenShortsSubtitle(BaseModel):
    """Os campos do `SubtitleRequest` do gerador (sem `job_id` e `clip_index`)."""

    position: Literal["top", "middle", "bottom"]
    font_size: int
    font_name: str
    font_color: str
    border_color: str
    border_width: int
    bg_color: str
    bg_opacity: float
    style: Literal["classic", "karaoke"]
    highlight_color: str
    effect: Literal["none", "glow", "pop", "box"]
    base_opacity: float
    uppercase: bool


class OpenShortsHook(BaseModel):
    """Só referência: `enabled` é sempre false (quem queima o gancho é o SociMan)."""

    enabled: Literal[False]
    style: Literal["classic", "dark", "yellow", "red", "outline", "outline_yellow"]
    size: Literal["S", "M", "L"]
    position: Literal["top", "center", "bottom"]
    duration_seconds: float
    exact: bool
    distance: float


class OpenShorts(BaseModel):
    subtitle: OpenShortsSubtitle
    hook: OpenShortsHook
    approximations: list[str]


class ExportAsset(CamelModel):
    ref: str | None = None  # FonteRef (fontes)
    id: UUID | None = None  # imagem de marca d'água ou de fundo
    name: str | None = None
    url: str
    expires_at: datetime | None  # sempre null na exportação


class ExportAssets(CamelModel):
    fonts: list[ExportAsset]
    watermark_image: ExportAsset | None
    background_images: list[ExportAsset]  # do gancho e do card final (com fundo imagem)


class KitExport(CamelModel):
    schema_id: Literal["sociman.kit/1"] = Field(alias="schema")
    generated_at: datetime
    perfil: ExportPerfil
    kit: ExportKitMeta
    tokens: dict[str, Any]  # cores em hex; fontes como {ref, name, family, style, url}
    openshorts: OpenShorts
    assets: ExportAssets
