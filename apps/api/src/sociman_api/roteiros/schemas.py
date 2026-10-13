"""Schemas dos roteiros, dos padrões de portões e das pronúncias (contracts/http-api.md da 011).
JSON em camelCase. Aqui ficam formato e limites; as regras (frases contíguas, produto aprovado,
voz válida, limite de cenas) ficam no service (400 `invalid_roteiro` com `field`, 409…)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.cenas.models import CenaMotor, CenaStatus, TomadaOrigem
from sociman_api.cenas.schemas import KeyframeRef
from sociman_api.perfis.schemas import VersionNumber
from sociman_api.roteiros.models import (
    RoteiroEtapa,
    RoteiroFormato,
    RoteiroModo,
    RoteiroStatus,
)

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120,
                                        pattern=r"^[^\r\n]*$")]
Brief = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Frase = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300,
                                         pattern=r"^[^\r\n]*$")]
Velocidade = Annotated[Decimal, Field(ge=Decimal("0.90"), le=Decimal("1.20"), max_digits=3,
                                      decimal_places=2)]
Palavra = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60,
                                           pattern=r"^[^\r\n]*$")]
Instrucao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Portao = Literal["texto", "narracao", "keyframes", "clipes", "final"]


class Portoes(CamelModel):
    model_config = ConfigDict(extra="forbid")

    texto: bool = True
    narracao: bool = True
    keyframes: bool = True
    clipes: bool = True
    final: bool = True


class ProdutoRoteiroIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    produto_id: UUID
    variante_id: UUID | None = None


class PosicaoIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    cena_id: UUID
    frases: Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=1, max_length=60)]
    tomada_id: UUID | None = None


class RoteiroIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    nome: Nome
    brief: Brief = ""
    avatar_id: UUID | None = None
    voz_id: UUID | None = None
    produtos: Annotated[list[ProdutoRoteiroIn], Field(min_length=1, max_length=6)]


class RoteiroPatch(CamelModel):
    """Qualquer subconjunto. `avatarId`/`vozId` nulos tiram o avatar ou a voz."""

    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    nome: Nome | None = None
    brief: Brief | None = None
    avatar_id: UUID | None = None
    voz_id: UUID | None = None
    velocidade: Velocidade | None = None
    frases: Annotated[list[Frase], Field(max_length=60)] | None = None
    produtos: Annotated[list[ProdutoRoteiroIn], Field(min_length=1, max_length=6)] | None = None
    posicoes: Annotated[list[PosicaoIn], Field(max_length=20)] | None = None


class RoteiroVersionIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber


class AprovarIn(RoteiroVersionIn):
    portao: Portao


class ControleIn(RoteiroVersionIn):
    modo: RoteiroModo
    portoes: Portoes


class RegerarKeyframeIn(RoteiroVersionIn):
    instrucao: Instrucao | None = None
    referencias: Annotated[list[UUID], Field(max_length=6)] | None = None


class RegerarClipeIn(RoteiroVersionIn):
    motor: CenaMotor | None = None


class EscolherTomadaIn(RoteiroVersionIn):
    tomada_id: UUID


class RoteiroPadroesIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: Annotated[int, Field(ge=0)]  # 0 = ainda sem linha (padrão do código)
    modo: RoteiroModo
    portoes: Portoes


class PronunciaIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    escrita: Palavra
    falada: Palavra


class PronunciaPatch(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    escrita: Palavra | None = None
    falada: Palavra | None = None


# ---- saídas ----

class ErroRoteiro(CamelModel):
    code: str
    message: str


class AvisoRoteiro(CamelModel):
    code: str
    message: str
    ordem: int | None = None


class AvatarRef(CamelModel):
    id: UUID
    nome: str
    kit_status: str | None
    revogado: bool


class VozRef(CamelModel):
    id: UUID
    nome: str
    origem: str
    revogada: bool


class ProdutoRoteiro(CamelModel):
    produto_id: UUID
    nome_comercial: str | None
    nome: str
    variante_id: UUID | None
    cor: str | None
    aprovado: bool


class CenaRoteiro(CamelModel):
    id: UUID
    nome: str
    status: CenaStatus
    motor: CenaMotor
    largura: int
    altura: int
    arquivada: bool
    perfil_id: UUID | None
    keyframe_image_id: UUID | None
    keyframe_url: str | None
    keyframe_geracao_id: UUID | None
    keyframe_instrucao: str | None
    keyframe_refs: list[KeyframeRef]  # como o da `Cena` (a apagada vem `removida`)
    version: int  # da cena: o `alvoVersion` da escolha do keyframe (021)


class TomadaRoteiro(CamelModel):
    id: UUID
    origem: TomadaOrigem
    motor: CenaMotor | None
    duracao_ms: int
    video_url: str | None
    miniatura_url: str | None
    keyframe_antigo: bool
    limpa: bool


class GeracaoAberta(CamelModel):
    id: UUID
    passo: str
    status: str
    progress: int
    etapa_mensagem: str | None


class PosicaoOut(CamelModel):
    ordem: int
    cena: CenaRoteiro
    frases: list[int]
    inicio_s: float | None
    duracao_s: float | None
    tomada: TomadaRoteiro | None
    aviso: str | None
    reaproveitada: bool
    geracoes_abertas: list[GeracaoAberta]


class TempoFrase(CamelModel):
    frase: int
    inicio_s: float
    fim_s: float


class NarracaoOut(CamelModel):
    id: UUID
    audio_url: str | None
    tempos: list[TempoFrase]
    total_s: float
    similaridade: float
    velocidade: float
    voz_id: UUID
    desatualizada: bool
    limpa: bool
    created_at: datetime


class PreviaOut(CamelModel):
    geracao_id: UUID
    video_url: str | None
    duracao_ms: int | None
    atual: bool


class RoteiroDetalhe(CamelModel):
    id: UUID
    perfil_id: UUID
    perfil_nome: str | None
    nome: str
    brief: str
    avatar: AvatarRef | None
    voz: VozRef | None
    formato: RoteiroFormato
    frases: list[str]
    velocidade: float
    modo: RoteiroModo
    portoes: Portoes
    status: RoteiroStatus
    etapa_falhou: RoteiroEtapa | None
    erro: ErroRoteiro | None
    avisos: list[AvisoRoteiro]
    produtos: list[ProdutoRoteiro]
    posicoes: list[PosicaoOut]
    narracao: NarracaoOut | None
    narracoes_anteriores: int
    previa: PreviaOut | None
    acabamento: PreviaOut | None
    conteudo_id: UUID | None
    geracoes_abertas: list[GeracaoAberta]  # as do roteiro (plano, narração, prévia, HD)
    max_cenas: int
    arquivado: bool
    version: int
    created_at: datetime
    updated_at: datetime


class RoteiroResumo(CamelModel):
    id: UUID
    perfil_id: UUID
    perfil_nome: str | None
    nome: str
    status: RoteiroStatus
    etapa_falhou: RoteiroEtapa | None
    produtos: list[str]
    cenas: int
    miniatura_url: str | None
    arquivado: bool
    conteudo_id: UUID | None
    updated_at: datetime


class RoteirosPagina(CamelModel):
    itens: list[RoteiroResumo]
    proximo: str | None


class RoteiroPadroes(CamelModel):
    perfil_id: UUID
    modo: RoteiroModo
    portoes: Portoes
    version: int  # 0 = padrão do código


class Pronuncia(CamelModel):
    id: UUID
    perfil_id: UUID
    escrita: str
    falada: str
    archived: bool
    version: int
    updated_at: datetime


class PronunciasList(CamelModel):
    items: list[Pronuncia]


def portoes_de(valor: dict[str, Any] | None) -> Portoes:
    return Portoes(**{k: bool(v) for k, v in (valor or {}).items() if k in Portoes.model_fields})
