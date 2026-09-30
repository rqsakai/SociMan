"""Modelos Pydantic de perfis e contas (contracts/http-api.md da 003). JSON em camelCase.

Aqui ficam só formato e limites (data-model.md). Normalização de @ e link, unicidade e
permissões ficam no service.
"""

from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from sociman_api.auth.schemas import CamelModel
from sociman_api.ia.aplicacao import IaAplicacoes
from sociman_api.perfis.models import ContaStatus, PerfilStatus, Platform

__all__ = [
    "Conta", "ContaOut", "CreateContaIn", "CreatePerfilIn", "ImageRef", "ImageUrls", "Perfil",
    "PerfilDetail", "PerfilOut", "PerfisList", "RevertIn", "SlugSuggestion", "UpdateContaIn",
    "UpdatePerfilIn", "UserRef", "Version", "VersionIn", "VersionsList",
]

PerfilName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Slug = Annotated[
    str, StringConstraints(min_length=2, max_length=60, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
]
Niche = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Bio = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
# BCP 47 simples: idioma e, opcionalmente, região (`pt-BR`, `en`, `es`).
Language = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
PlatformName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
# @ cru (com @, espaços e maiúsculas): o service normaliza para ^[a-z0-9._-]{1,60}$.
RawHandle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
HttpUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500, pattern=r"^https?://\S+$")
]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
IntervaloMin = Annotated[int, Field(ge=0, le=1440)]  # minutos (spec 014, Q3 = C)
VersionNumber = Annotated[int, Field(ge=1)]
Action = Literal["created", "updated", "archived", "restored", "reverted"]


# ---- saídas ----

class UserRef(CamelModel):
    id: UUID
    name: str


class ImageUrls(CamelModel):
    thumb: str
    medium: str


class ImageRef(CamelModel):
    id: UUID
    width: int
    height: int
    urls: ImageUrls


class Perfil(CamelModel):
    id: UUID
    slug: str
    name: str
    niche: str
    bio: str
    language: str
    status: PerfilStatus
    logo: ImageRef | None
    banner: ImageRef | None
    platforms: list[Platform]  # plataformas das contas ativas
    archived: bool
    archived_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: UserRef | None
    updated_by: UserRef | None


class Conta(CamelModel):
    id: UUID
    perfil_id: UUID
    platform: Platform
    platform_name: str
    handle: str
    url: str
    status: ContaStatus
    notes: str
    intervalo_min_minutos: int  # spec 014: intervalo mínimo entre posts (só dono muda)
    archived: bool
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: UserRef | None
    updated_by: UserRef | None


class Version(CamelModel):
    version: int
    action: Action
    actor: UserRef | None
    actor_kind: str
    occurred_at: datetime
    changed_fields: list[str]
    before: dict[str, Any] | None
    after: dict[str, Any]
    details: dict[str, Any]


class PerfisList(CamelModel):
    items: list[Perfil]


class PerfilOut(CamelModel):
    perfil: Perfil


class PerfilDetail(CamelModel):
    perfil: Perfil
    contas: list[Conta]  # inclui as arquivadas, com a flag


class ContaOut(CamelModel):
    conta: Conta


class VersionsList(CamelModel):
    items: list[Version]  # da mais recente para a mais antiga


class SlugSuggestion(CamelModel):
    slug: str


# ---- entradas ----

class CreatePerfilIn(CamelModel):
    name: PerfilName
    slug: Slug
    niche: Niche = ""
    bio: Bio = ""
    language: Language = "pt-BR"
    status: PerfilStatus = PerfilStatus.em_preparacao


class UpdatePerfilIn(CamelModel):
    # extra="forbid": o slug é imutável (FR-002a); mandá-lo no PATCH dá 400, não é ignorado.
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    name: PerfilName | None = None
    niche: Niche | None = None
    bio: Bio | None = None
    language: Language | None = None
    status: PerfilStatus | None = None
    # Spec 008: campos aplicados de uma chamada da IA (marca "com ajuda da IA" na versão).
    ia: IaAplicacoes | None = None


class VersionIn(CamelModel):
    version: VersionNumber


class RevertIn(CamelModel):
    version: VersionNumber
    to_version: VersionNumber


class CreateContaIn(CamelModel):
    platform: Platform
    platform_name: PlatformName = ""
    handle: RawHandle | None = None
    url: HttpUrl | None = None
    status: ContaStatus = ContaStatus.planejada
    notes: Notes = ""

    @model_validator(mode="after")
    def _handle_or_url(self) -> Self:
        if self.handle is None and self.url is None:
            raise ValueError("informe o @ ou o link")
        if self.platform == Platform.outra:
            if not self.platform_name:
                raise ValueError("informe o nome da plataforma")
            if self.url is None:
                raise ValueError("informe o link da conta")
        elif self.platform_name:
            raise ValueError("o nome da plataforma só vale para \"outra\"")
        return self


class UpdateContaIn(CamelModel):
    # A plataforma não muda depois de criada; campo desconhecido dá 400.
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    handle: RawHandle | None = None
    url: HttpUrl | None = None
    status: ContaStatus | None = None
    notes: Notes | None = None
    platform_name: PlatformName | None = None
    # Spec 014: só dono muda (403 `forbidden` para membro, no service).
    intervalo_min_minutos: IntervaloMin | None = None
