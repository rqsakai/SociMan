"""Schemas das cenas (contracts/http-api.md da spec 010). JSON em camelCase.

Aqui ficam formato e limites (data-model.md). A posse dos assets no perfil, o papel do arquivo
do avatar e as regras de status ficam no service (422 `cena_invalida`, 409 `cena_usada`…).
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, ConfigDict, Field, StringConstraints

from sociman_api.assets.schemas import normalize_tags
from sociman_api.auth.schemas import CamelModel
from sociman_api.cenas.models import (
    CenaModo,
    CenaMovimento,
    CenaPlano,
    CenaStatus,
    TomadaOrigem,
)
from sociman_api.ia.aplicacao import IaAplicacoes
from sociman_api.perfis.schemas import Autor, VersionNumber

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120,
                                        pattern=r"^[^\r\n]*$")]
Acao = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Fala = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300,
                                        pattern=r"^[^\r\n]*$")]
Texto300 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Texto500 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
ProdutoNome = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Notas = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Tags = Annotated[list[str], AfterValidator(normalize_tags)]
Duracao = Literal[4, 6, 8]
Nota = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class _CamposCena(CamelModel):
    """Os campos editáveis (todos opcionais aqui; `CenaIn` exige nome e ação)."""

    model_config = ConfigDict(extra="forbid")

    avatar_id: UUID | None = None
    avatar_arquivo_id: UUID | None = None
    cenario_id: UUID | None = None
    cenario_arquivo_id: UUID | None = None
    plano: CenaPlano | None = None
    movimento: CenaMovimento | None = None
    camera: Texto500 | None = None
    fala: Fala | None = None
    texto_tela: Texto300 | None = None
    estilo: Texto500 | None = None
    audio: Texto300 | None = None
    quadro_inicial: Texto500 | None = None
    quadro_final: Texto500 | None = None
    produto_nome: ProdutoNome | None = None
    produto_imagem_id: UUID | None = None
    # Spec 012 (R13): o produto do catálogo; com ele, `produtoNome`/`produtoImagemId` ficam nulos.
    produto_id: UUID | None = None
    produto_variante_id: UUID | None = None
    negative: Texto500 | None = None


class CenaIn(_CamposCena):
    nome: Nome
    acao: Acao
    duracao_s: Duracao = 8
    modo: CenaModo = CenaModo.ingredientes
    tags: Tags = Field(default_factory=list)
    notas: Notas = ""
    proposta_id: UUID | None = None  # proposta de cena aplicada (009)
    ia: IaAplicacoes | None = None  # campos aplicados da IA (008)


class CenaPatch(_CamposCena):
    """Qualquer subconjunto dos campos. Nulo limpa os opcionais; em nome, ação, duração, modo,
    tags e notas, é ignorado."""

    version: VersionNumber
    nome: Nome | None = None
    acao: Acao | None = None
    duracao_s: Duracao | None = None
    modo: CenaModo | None = None
    tags: Tags | None = None
    notas: Notas | None = None
    proposta_id: UUID | None = None
    ia: IaAplicacoes | None = None


class CamposCena(_CamposCena):
    """Os campos de uma proposta de cena (009): subconjunto não vazio de `CenaIn` sem tags nem
    notas."""

    nome: Nome | None = None
    acao: Acao | None = None
    duracao_s: Duracao | None = None
    modo: CenaModo | None = None


class VersionIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber


class NotaIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    nota: Nota


class PadroesIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: Annotated[int, Field(ge=0)]  # 0 = ainda sem linha (padrão do código)
    estilo: Texto500
    negative: Texto500


class UsosIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber  # do conteúdo
    cena_ids: Annotated[list[UUID], Field(max_length=100)]


# ---- saídas ----

class AssetRef(CamelModel):
    id: UUID
    nome: str
    arquivada: bool


class ParteOut(CamelModel):
    parte: str
    texto: str


class PromptOut(CamelModel):
    texto: str
    negative: str
    partes: list[ParteOut]  # vazio no congelado (só o texto foi guardado)
    congelado: bool
    avatar_version: int | None
    cenario_version: int | None


class Ingrediente(CamelModel):
    papel: Literal["avatar", "produto", "cenario"]
    asset_id: UUID | None = None  # nulo no produto do catálogo (spec 012)
    arquivo_id: UUID | None = None
    produto_id: UUID | None = None  # spec 012: o recorte da variante
    produto_variante_id: UUID | None = None
    nome: str
    largura: int
    altura: int
    download_url: str
    thumb_url: str


class Aviso(CamelModel):
    codigo: str
    mensagem: str
    campo: str | None
    detalhe: dict[str, Any] | None


class Tomada(CamelModel):
    id: UUID
    cena_id: UUID
    origem: TomadaOrigem
    duracao_ms: int
    largura: int
    altura: int
    nao_vertical: bool
    bytes: int
    content_type: str
    thumb_url: str
    video_url: str | None  # com validade; nulo para o MCP
    prompt_usado: str
    negative_usado: str
    nota: str
    escolhida: bool
    arquivada: bool
    version: int
    created_at: datetime
    autor: Autor


class UsoOut(CamelModel):
    conteudo_id: UUID
    titulo: str
    link: str


class CenaResumo(CamelModel):
    id: UUID
    perfil_id: UUID
    nome: str
    status: CenaStatus
    duracao_s: int
    modo: CenaModo
    avatar: AssetRef | None
    cenario: AssetRef | None
    produto_nome: str | None
    produto_id: UUID | None = None  # spec 012
    thumb_url: str | None
    tags: list[str]
    arquivada: bool
    tomadas: int
    usos: int
    updated_at: datetime


class VarianteRef(CamelModel):
    id: UUID
    cor_pt: str | None
    cor_en: str | None
    thumb_url: str | None


class ProdutoRef(CamelModel):
    """Spec 012: o produto do catálogo ligado à cena."""

    id: UUID
    nome_comercial: str | None
    nome: str
    status: str
    estado: str
    variante: VarianteRef | None


class Cena(CamelModel):
    id: UUID
    perfil_id: UUID
    nome: str
    avatar_id: UUID | None
    avatar_arquivo_id: UUID | None
    cenario_id: UUID | None
    cenario_arquivo_id: UUID | None
    plano: CenaPlano | None
    movimento: CenaMovimento | None
    camera: str | None
    acao: str
    fala: str | None
    texto_tela: str | None
    estilo: str | None
    audio: str | None
    duracao_s: int
    modo: CenaModo
    quadro_inicial: str | None
    quadro_final: str | None
    produto_nome: str | None
    produto_imagem_id: UUID | None
    produto_id: UUID | None
    produto_variante_id: UUID | None
    negative: str | None
    tags: list[str]
    notas: str
    status: CenaStatus
    version: int
    arquivada: bool
    avatar: AssetRef | None
    cenario: AssetRef | None
    produto_imagem: AssetRef | None
    produto: ProdutoRef | None = None  # spec 012
    prompt: PromptOut
    ingredientes: list[Ingrediente]
    avisos: list[Aviso]
    tomada_escolhida: Tomada | None
    tomadas: int
    usos: list[UsoOut]
    thumb_url: str | None
    duplicada_de: UUID | None
    created_at: datetime
    updated_at: datetime
    autor: Autor  # quem criou


class CenasList(CamelModel):
    items: list[CenaResumo]
    next_cursor: str | None


class TomadasList(CamelModel):
    items: list[Tomada]


class CenasResumoList(CamelModel):
    items: list[CenaResumo]


class UsosOut(CamelModel):
    items: list[CenaResumo]
    version: int  # do conteúdo


class CenaPadroesTexto(CamelModel):
    estilo: str
    negative: str


class CenaPadroes(CamelModel):
    perfil_id: UUID
    estilo: str
    negative: str
    version: int  # 0 = padrão do código
    padrao_codigo: CenaPadroesTexto
