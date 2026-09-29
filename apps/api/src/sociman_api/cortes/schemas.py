"""Modelos Pydantic dos cortes (contracts/http-api.md "Cortes" e `Armazenamento`). JSON em
camelCase.

Spec 006: o corte ganha a origem (upload ou OpenShorts), o envio, o trecho, os textos do
OpenShorts, a legenda aplicada, o canal e o direito no envio; `kitVersion` é null em `revisao`
(a marca ainda não foi aplicada)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from sociman_api.auth.schemas import CamelModel
from sociman_api.cortes.models import CorteOrigem, CorteStatus
from sociman_api.envios.models import DireitoEnvio
from sociman_api.perfis.schemas import UserRef, VersionNumber
from sociman_api.postagem.schemas import PostagemResumo  # o mesmo nome no OpenAPI (Trilha C)


class CorteCanal(CamelModel):
    id: UUID
    title: str




class Corte(CamelModel):
    id: UUID
    perfil_id: UUID
    hook_text: str
    kit_version: int | None  # null em `revisao`
    status: CorteStatus
    progress: int
    queue_position: int | None  # 1 = o próximo; só com status na_fila
    attempts: int
    error_message: str | None
    original_filename: str
    bytes: int
    duration_ms: int
    width: int
    height: int
    has_audio: bool
    result_bytes: int | None
    processing_ms: int | None
    poster_url: str | None
    version: int
    created_at: datetime
    created_by: UserRef | None
    finished_at: datetime | None
    # ---- spec 006 ----
    origem: CorteOrigem
    envio_id: UUID | None
    clip_index: int | None
    source_start_ms: int | None
    source_end_ms: int | None
    openshorts_title: str | None
    openshorts_description: str | None
    openshorts_score: int | None
    legenda: Literal["kit", "gerador", "nenhuma", "sem_fala"] | None
    canal: CorteCanal | None
    direito_no_envio: DireitoEnvio | None
    archived: bool
    postagens: list[PostagemResumo]


class CorteOut(CamelModel):
    corte: Corte


class CortesList(CamelModel):
    items: list[Corte]


class Armazenamento(CamelModel):
    """O HD de dados (R5): a aba Cortes mostra uso e espaço livre e desabilita o envio."""

    available: bool
    reason: Literal["ok", "sem_sentinela", "pouco_espaco"]
    free_bytes: int | None
    total_bytes: int | None
    min_free_bytes: int
    cortes_bytes: int


# ---- entradas (spec 006) ----

class HookIn(CamelModel):
    version: VersionNumber
    hook_text: str = Field(max_length=4096)


class AplicarMarcaItem(CamelModel):
    corte_id: UUID
    version: VersionNumber


class AplicarMarcaIn(CamelModel):
    items: list[AplicarMarcaItem] = Field(min_length=1, max_length=30)
