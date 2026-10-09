"""Schemas das vozes (contracts/http-api.md da spec 025). JSON em camelCase."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints

from sociman_api.assets.schemas_padrao import ConsentimentoPessoa, PreviaRevogacao
from sociman_api.auth.schemas import CamelModel
from sociman_api.geracao.schemas import Audio, GeracaoResumo
from sociman_api.perfis.schemas import UserRef, VersionNumber
from sociman_api.vozes.models import VozOrigem, VozStatus

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Tom = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Descricao = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                             max_length=1000)]
Sincronizacao = Literal["ok", "pendente", "removendo", "nao_se_aplica"]


class VozIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    name: Nome
    origem: VozOrigem
    tom: Tom
    descricao: Descricao | None = None


class VozInAgencia(VozIn):
    """Spec 029: o cadastro da biblioteca da agência, com o perfil base opcional."""

    perfil_id: UUID | None = None


class VozPatch(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    name: Nome | None = None
    tom: Tom | None = None
    descricao: Descricao | None = None
    gravacao_audio_id: UUID | None = None
    perfil_id: UUID | None = None  # spec 029: o perfil base (null = sem perfil)


class Analise(CamelModel):
    codec: str | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    piso_ruido_dbfs: float | None = None
    snr_db: float | None = None
    clipping_pct: float | None = None
    duracao_s: float | None = None
    avisos: list[str] = Field(default_factory=list)


class UsadaPor(CamelModel):
    id: UUID
    name: str


class VozResumo(CamelModel):
    id: UUID
    perfil_id: UUID | None  # spec 029: o perfil base (null = sem perfil)
    perfil_nome: str | None = None
    name: str
    origem: VozOrigem
    tom: str
    descricao: str | None
    tts_id: str
    status: VozStatus
    trocando_referencia: bool
    sincronizada_em: datetime | None
    sincronizacao: Sincronizacao
    n_usada_por: int
    revogada: bool
    archived: bool
    version: int
    created_at: datetime
    updated_at: datetime


class Voz(VozResumo):
    gravacao: Audio | None
    referencia: Audio | None
    ref_texto: str | None
    analise: Analise | None
    consentimento: ConsentimentoPessoa | None
    usada_por: list[UsadaPor]
    geracao_aberta: GeracaoResumo | None
    ultimo_teste: GeracaoResumo | None
    created_by: UserRef | None


class VozesLista(CamelModel):
    itens: list[VozResumo]
    proximo: str | None


class RevogacaoVozOut(CamelModel):
    voz: Voz
    apagados: PreviaRevogacao
    avatares_afetados: list[dict[str, Any]]
