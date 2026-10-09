"""Schemas do cadastro padronizado (contracts/http-api.md da spec 025). JSON em camelCase."""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.geracao.schemas import Audio, GeracaoResumo
from sociman_api.perfis.schemas import UserRef, VersionNumber

Slot = Literal["rosto_origem", "rosto_frontal", "rosto_34_esq", "rosto_34_dir", "corpo_base",
               "cena"]
NomePessoa = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                              max_length=120)]
Observacao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


# ---- entradas ----

class ProvaIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    image_id: UUID | None = None
    audio_id: UUID | None = None


class ConsentimentoIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    nome: NomePessoa
    data: date
    observacao: Observacao = ""
    prova: ProvaIn | None = None


class RevogarIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    confirmo: bool = False


# ---- saídas ----

class ProvaOut(CamelModel):
    image_id: UUID | None = None
    link: str | None = None
    audio: Audio | None = None


class ConsentimentoPessoa(CamelModel):
    nome: str | None
    data: str | None
    observacao: str
    registrado_por: UserRef | None
    registrado_em: str | None
    prova: ProvaOut | None
    tem_prova: bool
    revogado_em: str | None
    revogado_por: UserRef | None


class VozPadrao(CamelModel):
    id: UUID
    name: str
    status: str
    arquivada: bool
    revogada: bool


class NotaSlot(CamelModel):
    nota: int
    observacao: str


class Identidade(CamelModel):
    modelo: str | None = None
    data: str | None = None
    geracao_id: UUID | None = None
    notas: dict[str, NotaSlot] = Field(default_factory=dict)


class SlotKit(CamelModel):
    slot: Slot
    file_id: UUID | None
    aberto: bool
    motivo: str | None
    nota: int | None
    observacao: str | None
    refazer: bool


class PassoKit(CamelModel):
    passo: str
    aberto: bool
    motivo: str | None
    geracao_aberta: GeracaoResumo | None


class DescricaoNaoAplicada(CamelModel):
    proibidas: list[str]


class KitPadrao(CamelModel):
    slots: list[SlotKit]
    passos: list[PassoKit]
    checagem_pendente: bool
    descricao_nao_aplicada: DescricaoNaoAplicada | None


class AvisoDerivados(CamelModel):
    codigo: Literal["derivados_desatualizados"] = "derivados_desatualizados"
    itens: list[dict[str, Any]]


class PreviaRevogacao(CamelModel):
    imagens: int
    audios: int
    candidatos: int
    geracoes: int
    bytes: int
    cenas_afetadas: list[dict[str, Any]]
    avatares_afetados: list[dict[str, Any]] = Field(default_factory=list)


class RevogacaoOut(CamelModel):
    apagados: PreviaRevogacao
    revogado_em: datetime
