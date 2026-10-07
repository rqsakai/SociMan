"""Modelos Pydantic dos canais-fonte e da descoberta (contracts/http-api.md da 006). camelCase.

`PerfilRef`, `CanalRef` e `VideoFonteRef` são compartilhados com envios e postagens: as outras
trilhas importam daqui, para o OpenAPI não ganhar dois esquemas com o mesmo nome.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.models import CanalDireito, CanalSync, VideoLive
from sociman_api.perfis.schemas import UserRef, VersionNumber

__all__ = [
    "CanaisList",
    "CanalCandidato",
    "CanalFonte",
    "CanalOut",
    "CanalRef",
    "CreateCanalIn",
    "DireitoIn",
    "Existente",
    "Metrica",
    "PerfilRef",
    "ResolverIn",
    "ResolverOut",
    "ScoreDetail",
    "SyncInfo",
    "UpdateCanalIn",
    "VideoDetalheOut",
    "VideoFonte",
    "VideoFonteRef",
    "VideosList",
]

ChannelId = Annotated[str, StringConstraints(strip_whitespace=True,
                                              pattern=r"^UC[0-9A-Za-z_-]{22}$")]
EvidenciaUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500, pattern=r"^https?://\S+$")
]
EvidenciaNota = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Ordem = Literal["score", "views", "vph", "data"]


# ---- referências compartilhadas ----

class PerfilRef(CamelModel):
    id: UUID
    name: str
    slug: str


class CanalRef(CamelModel):
    id: UUID
    title: str
    direito: CanalDireito


class VideoFonteRef(CamelModel):
    id: UUID
    youtube_video_id: str
    title: str
    url: str
    thumbnail_url: str | None
    duration_s: int | None
    disponivel: bool


# ---- canais ----

class SyncInfo(CamelModel):
    status: CanalSync
    lidos: int | None
    total: int | None
    erro: str | None
    last_synced_at: datetime | None
    next_sync_at: datetime


class CanalFonte(CamelModel):
    id: UUID
    youtube_channel_id: str
    handle: str | None
    title: str
    avatar_url: str | None  # via /img (imgproxy)
    subscribers: int | None
    video_count: int | None
    direito: CanalDireito
    direito_evidencia_url: str | None
    direito_evidencia_nota: str
    perfis: list[PerfilRef]
    sync: SyncInfo
    videos_conhecidos: int
    archived: bool
    version: int
    created_at: datetime
    created_by: UserRef | None


class CanalOut(CamelModel):
    canal: CanalFonte


class CanaisList(CamelModel):
    items: list[CanalFonte]


class CanalCandidato(CamelModel):
    youtube_channel_id: str
    title: str
    handle: str | None
    avatar_url: str | None
    subscribers: int | None
    video_count: int | None


class Existente(CamelModel):
    id: UUID


class ResolverOut(CamelModel):
    candidato: CanalCandidato
    custo: int  # unidades da cota gastas na consulta
    existente: Existente | None


class ResolverIn(CamelModel):
    entrada: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                              max_length=500)]


class CreateCanalIn(CamelModel):
    youtube_channel_id: ChannelId
    perfil_ids: list[UUID] = Field(default_factory=list, max_length=50)


class UpdateCanalIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    perfil_ids: list[UUID] | None = Field(default=None, max_length=50)


class DireitoIn(CamelModel):
    """PUT: substitui direito e evidência (campo omitido = sem evidência)."""

    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    direito: CanalDireito
    evidencia_url: EvidenciaUrl | None = None
    evidencia_nota: EvidenciaNota = ""


# ---- vídeos ----

class ScoreDetail(CamelModel):
    v: float = 0
    e: float = 0
    r: float = 0
    d: float = 0
    componente: str = ""
    valores: dict[str, Any] = Field(default_factory=dict)


class JaCortado(CamelModel):
    perfil_id: UUID
    envio_id: UUID
    status: str


class Selecionado(CamelModel):
    perfil_id: UUID
    envio_id: UUID


class AprendizadoAfinidade(CamelModel):
    """Spec 023 (R9): a afinidade do vídeo-fonte com o perfil escolhido (só com `perfilId`)."""

    pontos: float  # −20..20, já somados ao `score`
    tema_id: UUID | None
    tema_nome: str | None
    cortado: bool
    motivo: str | None  # null se a afinidade não for o componente principal


class VideoFonte(CamelModel):
    id: UUID
    canal: CanalRef
    youtube_video_id: str
    url: str
    title: str
    thumbnail_url: str | None  # via /img
    published_at: datetime
    duration_s: int | None
    live: VideoLive
    disponivel: bool
    views: int | None
    likes: int | None
    comments: int | None
    vph_recente: float | None
    score: float
    score_reason: str
    score_detail: ScoreDetail
    recomendavel: bool
    ja_cortado: list[JaCortado]
    selecionado: list[Selecionado]
    afinidade: AprendizadoAfinidade | None = None  # spec 023


class VideosList(CamelModel):
    items: list[VideoFonte]
    next_cursor: str | None
    total: int
    ocultos_por_tema: int = 0  # spec 023: escondidos por tema cortado (sem `mostrarCortados`)


class Metrica(CamelModel):
    observed_at: datetime
    views: int | None
    likes: int | None
    comments: int | None


class VideoDetalheOut(CamelModel):
    video: VideoFonte
    metricas: list[Metrica]  # últimas 50, mais recentes primeiro
