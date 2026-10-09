"""Schemas das gerações e dos áudios (contracts/http-api.md da spec 021), em camelCase."""

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from sociman_api.auth.schemas import CamelModel
from sociman_api.geracao.models import GeracaoAlvo, GeracaoMotor, GeracaoStatus
from sociman_api.perfis.schemas import ImageRef, UserRef

EXTRAS_MAX_BYTES = 2048


# ---- entradas ----

class GeracaoIn(CamelModel):
    alvo_tipo: GeracaoAlvo
    alvo_id: uuid.UUID
    passo: str = Field(min_length=1, max_length=40)
    instrucao: str = Field(default="", max_length=2000)
    referencias: list[uuid.UUID] = Field(default_factory=list, max_length=4)
    n_opcoes: int | None = Field(default=None, ge=1, le=4)
    rotulo: str | None = Field(default=None, min_length=1, max_length=60)
    texto: str | None = Field(default=None, min_length=1, max_length=500)
    extras: dict[str, Any] | None = None

    @field_validator("extras")
    @classmethod
    def _extras_pequeno(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and len(json.dumps(value, ensure_ascii=False).encode()) \
                > EXTRAS_MAX_BYTES:
            raise ValueError("até 2 KB")
        return value

    @field_validator("referencias")
    @classmethod
    def _sem_repetir(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("referência repetida")
        return value


class VersaoIn(CamelModel):
    version: int


class EscolherIn(CamelModel):
    candidato_id: uuid.UUID
    version: int
    alvo_version: int


# ---- saídas ----

class Link(CamelModel):
    url: str
    expires_at: datetime | None


class Erro(CamelModel):
    code: str
    message: str


class ImagemCandidato(CamelModel):
    image_id: uuid.UUID
    width: int
    height: int
    url: str  # /img da prévia grande (para comparar lado a lado)
    link: Link  # o original, com validade (a limpeza pode apagar)


class Audio(CamelModel):
    id: uuid.UUID
    perfil_id: uuid.UUID
    formato: str
    sample_rate: int
    duracao_ms: int
    sha256: str
    bytes: int
    link: Link  # sempre com validade e Range
    created_at: datetime
    created_by: UserRef | None


class CandidatoGeracao(CamelModel):
    id: uuid.UUID
    numero: int
    seed: int | None
    imagem: ImagemCandidato | None
    imagem_par: ImagemCandidato | None  # só avatar.rostos_34: o lado direito
    audio: Audio | None
    metricas: dict[str, Any]
    teste_audio: Audio | None  # voz: o áudio de teste


class GeracaoResumo(CamelModel):
    id: uuid.UUID
    perfil_id: uuid.UUID
    alvo_tipo: GeracaoAlvo
    alvo_id: uuid.UUID
    passo: str
    motor: GeracaoMotor
    instrucao: str
    referencias: list[ImageRef]
    rotulo: str | None
    texto: str | None
    extras: dict[str, Any] | None
    n_opcoes: int
    status: GeracaoStatus
    progress: int
    etapa_mensagem: str | None
    attempts: int
    next_attempt_at: datetime | None
    erro: Erro | None
    escolhido_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    limpa_em: datetime | None
    sem_escolha: bool
    de_geracao_id: uuid.UUID | None
    version: int
    created_at: datetime
    created_by: UserRef | None
    updated_at: datetime
    n_candidatos: int
    miniatura_escolhido: str | None  # /img do escolhido (lista)


class GeracaoDetalhe(GeracaoResumo):
    candidatos: list[CandidatoGeracao]


class AlvoGeracao(CamelModel):
    tipo: GeracaoAlvo
    id: uuid.UUID
    version: int


class GeracaoEscolhida(GeracaoDetalhe):
    alvo: AlvoGeracao  # o alvo depois da escolha (a tela recarrega o detalhe dele)


class GeracoesPagina(CamelModel):
    itens: list[GeracaoResumo]
    proximo: str | None
