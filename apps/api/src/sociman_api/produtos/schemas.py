"""Schemas dos produtos (contracts/api.md da spec 012). JSON em camelCase.

Aqui ficam formato e limites de tamanho; os limites da ficha (palavras do material, itens das
listas) ficam em `ficha.problemas_campos`, que o service chama para responder 400
`invalid_produto` com o `field` em camelCase. Os campos em inglês não têm `strip` (vão literais
para os prompts, R2).
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.errors import ApiError
from sociman_api.geracao.models import GeracaoStatus
from sociman_api.perfis.schemas import UserRef, VersionNumber
from sociman_api.produtos.models import ProdutoFichaPor, ProdutoStatus

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Obs = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
UrlLoja = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500,
                                           pattern=r"^https://\S+$")]
Cor = Annotated[str, StringConstraints(max_length=40)]
Estado = Literal["rascunho", "gerando", "revisao", "aprovado", "arquivado"]
ArquivadosFiltro = Literal["false", "true", "so"]
Motivo = Literal["ficha_incompleta", "sem_variante", "sem_recorte", "sem_flat", "sem_cor",
                 "geracao_em_andamento"]
AvisoVariante = Literal["flat_desatualizado", "sem_cor"]

_CAMEL = {"nome_comercial": "nomeComercial", "material_en": "materialEn",
          "material_pt": "materialPt", "formato_corte": "formatoCorte",
          "detalhes_visiveis": "detalhesVisiveis", "tamanho_relativo": "tamanhoRelativo",
          "descricao_prompt": "descricaoPrompt", "descricao_venda": "descricaoVenda",
          "precisa_flat": "precisaFlat", "cor_en": "corEn", "cor_pt": "corPt",
          "url_loja": "urlLoja"}


def camel(campo: str) -> str:
    """`detalhes_visiveis[2]` → `detalhesVisiveis[2]`."""
    base, _, resto = campo.partition("[")
    return _CAMEL.get(base, base) + (f"[{resto}" if resto else "")


def invalid(field: str, message: str) -> ApiError:
    field = camel(field)
    return ApiError(400, "invalid_produto", f"{field}: {message}", details={"field": field})


# ---- entradas ----

class ProdutoPatch(CamelModel):
    version: VersionNumber
    name: Nome | None = None
    obs: Obs | None = None
    url_loja: UrlLoja | None = None


class FichaIn(CamelModel):
    """A ficha inteira (R9). Os limites finos ficam em `ficha.problemas_campos`."""

    nome_comercial: str = Field(max_length=120)
    categoria: str = Field(max_length=120)
    material_en: str = Field(max_length=60)
    material_pt: str = Field(max_length=60)
    formato_corte: str = Field(max_length=300)
    detalhes_visiveis: list[Annotated[str, StringConstraints(max_length=200)]] = Field(
        max_length=12)
    tamanho_relativo: str = Field(max_length=300)
    descricao_prompt: str = Field(max_length=500)
    cuidados: list[Annotated[str, StringConstraints(max_length=200)]] = Field(max_length=12)
    descricao_venda: str = Field(max_length=600)
    precisa_flat: bool


class CorIn(CamelModel):
    variante_id: uuid.UUID
    cor_en: Cor
    cor_pt: Cor


class SalvarFichaIn(CamelModel):
    version: VersionNumber
    ficha: FichaIn
    cores: list[CorIn] = Field(default_factory=list, max_length=12)


class VarianteEditarIn(CamelModel):
    version: VersionNumber
    cor_en: Cor | None = None
    cor_pt: Cor | None = None


class OrdemIn(CamelModel):
    version: VersionNumber
    ids: list[uuid.UUID] = Field(min_length=1, max_length=6)


class ArquivarIn(CamelModel):
    version: VersionNumber
    cancelar_geracoes: bool = False


# ---- saídas ----

class ImagemRef(CamelModel):
    image_id: uuid.UUID
    largura: int
    altura: int
    thumb_url: str
    url: str
    download_url: str


class Ficha(CamelModel):
    nome_comercial: str | None
    categoria: str | None
    material_en: str | None
    material_pt: str | None
    formato_corte: str | None
    detalhes_visiveis: list[str]
    tamanho_relativo: str | None
    descricao_prompt: str | None
    cuidados: list[str]
    descricao_venda: str | None
    precisa_flat: bool | None


class Variante(CamelModel):
    id: uuid.UUID
    position: int
    cor_en: str | None
    cor_pt: str | None
    original: ImagemRef
    recorte: ImagemRef | None
    flat: ImagemRef | None
    flat_geracao_id: uuid.UUID | None
    avisos: list[AvisoVariante]
    archived_at: datetime | None


class ErroPasso(CamelModel):
    code: str
    message: str


class PassoProduto(CamelModel):
    """Uma geração `produto.*` (a 021 mostra o resto pelo `GET /api/geracoes/{id}`)."""

    id: uuid.UUID
    passo: str
    variante_id: uuid.UUID | None
    status: GeracaoStatus
    progress: int
    etapa_mensagem: str | None
    erro: ErroPasso | None
    n_opcoes: int
    version: int
    created_at: datetime


class Pendencia(CamelModel):
    variante_id: uuid.UUID | None
    motivo: Motivo


class UsoProduto(CamelModel):
    origem: Literal["cena"]
    rotulo: str
    href: str
    bloqueia: bool = False


class ProdutoResumo(CamelModel):
    id: uuid.UUID
    name: str
    nome_comercial: str | None
    categoria: str | None
    status: ProdutoStatus
    estado: Estado
    variantes_ativas: int
    thumb_url: str | None
    updated_at: datetime
    version: int


class ProdutosLista(CamelModel):
    itens: list[ProdutoResumo]
    proximo_cursor: str | None


class Produto(CamelModel):
    id: uuid.UUID
    perfil_id: uuid.UUID
    name: str
    obs: str
    url_loja: str | None
    status: ProdutoStatus
    estado: Estado
    ficha_por: ProdutoFichaPor | None
    ficha: Ficha | None
    variantes: list[Variante]
    passos: list[PassoProduto]
    pendencias: list[Pendencia]
    usos: list[UsoProduto]
    version: int
    archived_at: datetime | None
    created_at: datetime
    created_by: UserRef | None
    updated_at: datetime
    updated_by: UserRef | None
