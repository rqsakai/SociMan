"""Schemas dos roteiros, dos padrões de portões e das pronúncias (contracts/http-api.md da 011).
JSON em camelCase. Aqui ficam formato e limites; as regras (frases contíguas, produto aprovado,
voz válida, limite de cenas) ficam no service (400 `invalid_roteiro` com `field`, 409…)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.cenas.models import CenaMotor, CenaStatus, QuadroPapel, TomadaOrigem
from sociman_api.cenas.schemas import KeyframeRef
from sociman_api.perfis.schemas import VersionNumber
from sociman_api.roteiros.models import (
    ConversaEstado,
    ConversaTipo,
    PosicaoReuso,
    RoteiroEtapa,
    RoteiroFormato,
    RoteiroModo,
    RoteiroStatus,
    RoteiroTipoVideo,
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
# T059 (2026-10-15): `leve` (padrão, lanczos em segundos) ou `hd` (SeedVR2 na GPU, opcional).
AcabamentoModo = Literal["leve", "hd"]


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
    # Spec 031: só no vídeo guiado (1 a 3; ausente = o da posição atual ou o da cena).
    trechos: Annotated[int, Field(ge=1, le=3)] | None = None


class RoteiroIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    nome: Nome
    brief: Brief = ""
    avatar_id: UUID | None = None
    voz_id: UUID | None = None
    produtos: Annotated[list[ProdutoRoteiroIn], Field(min_length=1, max_length=6)]


class RoteiroGuiadoIn(CamelModel):
    """Spec 031: o "Novo vídeo" guiado (os 6 blocos). Sem `vozId`, vale a voz padrão do avatar;
    sem `varianteId`, a primeira variante ativa com recorte; sem `nome`, "<produto> – dd/mm"."""

    model_config = ConfigDict(extra="forbid")

    perfil_id: UUID
    tipo_video: RoteiroTipoVideo = RoteiroTipoVideo.avatar_pov
    avatar_id: UUID
    voz_id: UUID | None = None
    cenario_id: UUID
    produto_id: UUID
    variante_id: UUID | None = None
    duracao_s: Annotated[int, Field(ge=1, le=600)]
    nome: Nome | None = None
    acabamento_modo: AcabamentoModo | None = None  # ausente = leve (T059)


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
    # Spec 031 (FR-033): a duração do vídeo guiado, dentro da grade guardada (refaz o plano).
    duracao_s: Annotated[int, Field(ge=1, le=600)] | None = None


class RoteiroVersionIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber


class AprovarIn(RoteiroVersionIn):
    portao: Portao
    # Só com `portao = "final"`: o acabamento escolhido na hora de aprovar a prévia (T059).
    acabamento_modo: AcabamentoModo | None = None


class ControleIn(RoteiroVersionIn):
    modo: RoteiroModo
    portoes: Portoes
    acabamento_modo: AcabamentoModo | None = None  # ausente = não muda


class RegerarKeyframeIn(RoteiroVersionIn):
    instrucao: Instrucao | None = None
    referencias: Annotated[list[UUID], Field(max_length=6)] | None = None
    # Spec 031 (avançado): o quadro do guiado a refazer (padrão 0; os seguintes também) e quantas
    # opções pedir (o wizard pede sempre 1; com 2 ou mais, a cadeia espera a escolha humana).
    quadro: Annotated[int, Field(ge=0, le=3)] | None = None
    n_opcoes: Annotated[int, Field(ge=1, le=4)] | None = None


class RegerarClipeIn(RoteiroVersionIn):
    motor: CenaMotor | None = None
    # Spec 031 (avançado): o trecho do guiado a refazer (padrão 0) e quantas versões pedir (cada
    # uma é uma geração e uma tomada; com 2, quem escolhe é o `PUT …/tomada` com o `trecho`).
    trecho: Annotated[int, Field(ge=0, le=2)] | None = None
    n_opcoes: Annotated[int, Field(ge=1, le=2)] | None = None


class EscolherTomadaIn(RoteiroVersionIn):
    tomada_id: UUID
    trecho: Annotated[int, Field(ge=0, le=2)] | None = None  # 031: o trecho do guiado


class DefinirCenaIn(RoteiroVersionIn):
    """Spec 031 (FR-019/021, R7): a decisão do modal de cenas para uma posição. `total` e `plano`
    pedem a `cenaId` (da biblioteca); `nova` pede à IA a cena daquela posição. Depois do texto,
    só no modo avançado (`avancado: true`)."""

    reuso: Literal["total", "plano", "nova"]
    cena_id: UUID | None = None
    avancado: bool = False


IdCurto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class ResponderIn(RoteiroVersionIn):
    """Spec 031: a resposta a uma pergunta do chat (só cliques, ou com o texto curto)."""

    pergunta_id: IdCurto
    opcoes: Annotated[list[IdCurto], Field(max_length=6)] = Field(default_factory=list)
    texto: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class AlvoRecusa(CamelModel):
    """Spec 031 (R6): o item recusado no wizard. `ordem` é a posição (0-based); `quadro` e
    `trecho` dizem de onde refazer."""

    model_config = ConfigDict(extra="forbid")

    tipo: Literal["narracao", "quadros", "trecho", "posicao", "final"]
    ordem: Annotated[int, Field(ge=0, le=19)] | None = None
    quadro: Annotated[int, Field(ge=0, le=3)] | None = None
    trecho: Annotated[int, Field(ge=0, le=2)] | None = None


OpcaoRecusa = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                               max_length=80, pattern=r"^[^\r\n]*$")]


class RecusarIn(RoteiroVersionIn):
    """Spec 031: o "Não aprovo": as opções de troca clicadas e/ou o texto curto."""

    alvo: AlvoRecusa
    opcoes: Annotated[list[OpcaoRecusa], Field(max_length=6)] = Field(default_factory=list)
    texto: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class AprovarPosicaoIn(RoteiroVersionIn):
    """Spec 031 (R9): aprovar a sequência de quadros (ou os trechos) de uma posição."""

    etapa: Literal["keyframes", "clipe"]


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


class QuadroResumo(CamelModel):
    """Spec 031: um quadro da sequência da cena (o texto da instrução fica fora do wizard por
    regra da tela, FR-015)."""

    ordem: int
    papel: QuadroPapel
    image_id: UUID | None
    image_url: str | None
    provisorio: bool
    geracao_id: UUID | None
    instrucao: str


class TomadaTrecho(CamelModel):
    trecho: int
    tomada: TomadaRoteiro | None


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
    # ---- spec 031 (nulos/vazios nos roteiros da 011) ----
    trechos: int | None = None
    reuso: PosicaoReuso | None = None
    motivo: str | None = None
    orcamento_chars: int | None = None
    aprovado_keyframes_em: datetime | None = None
    aprovado_clipe_em: datetime | None = None
    quadros: list[QuadroResumo] = Field(default_factory=list)
    tomadas_trechos: list[TomadaTrecho] = Field(default_factory=list)


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
    acabamento_modo: AcabamentoModo
    conteudo_id: UUID | None
    geracoes_abertas: list[GeracaoAberta]  # as do roteiro (plano, narração, prévia, HD)
    max_cenas: int
    arquivado: bool
    version: int
    created_at: datetime
    updated_at: datetime
    # ---- spec 031: o vídeo guiado (nulos nos roteiros da 011) ----
    tipo_video: RoteiroTipoVideo | None = None
    cenario_id: UUID | None = None
    duracao_alvo_s: int | None = None
    trecho_base_s: int | None = None
    conversa_estado: ConversaEstado | None = None


class GradeOut(CamelModel):
    """Spec 031 (R1): a grade de duração que vale para um vídeo novo."""

    trecho_base_s: int
    opcoes: list[int]
    max_trechos_por_cena: int


class OpcaoConversa(CamelModel):
    id: str
    rotulo: str


class PerguntaConversa(CamelModel):
    id: str
    texto: str
    multipla: bool
    rodada: int
    opcoes: list[OpcaoConversa]
    exemplos: list[str]


class AutorConversa(CamelModel):
    tipo: str  # "user" | "system:roteiro"
    id: UUID | None
    nome: str | None


class MensagemConversa(CamelModel):
    id: UUID
    seq: int
    tipo: ConversaTipo
    pergunta_id: str | None
    conteudo: dict[str, Any]
    alvo: dict[str, Any] | None
    autor: AutorConversa
    created_at: datetime


class ConversaOut(CamelModel):
    """Spec 031: o chat do roteiro guiado. `perguntaAtual` = a primeira sem resposta da rodada;
    `erro` = a IA não respondeu (o "tentar de novo" é o refazer-perguntas)."""

    estado: ConversaEstado | None
    rodada: int
    mensagens: list[MensagemConversa]
    pergunta_atual: PerguntaConversa | None
    respondidas: int
    total: int
    geracao_aberta: GeracaoAberta | None
    erro: ErroRoteiro | None
    version: int  # do roteiro: o `version` da próxima resposta


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
