"""Modelos Pydantic dos cortes (contracts/http-api.md "Cortes" e `Armazenamento`). JSON em
camelCase."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sociman_api.auth.schemas import CamelModel
from sociman_api.cortes.models import CorteStatus
from sociman_api.perfis.schemas import UserRef


class Corte(CamelModel):
    id: UUID
    perfil_id: UUID
    hook_text: str
    kit_version: int
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
