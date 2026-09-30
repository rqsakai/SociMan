"""Modelos Pydantic do assistente (contracts/http-api.md da spec 008). JSON em camelCase.

Formato e limites dos corpos ficam aqui; o cruzamento tipo × alvo × perfil, o limite do
`valorAtual` (1,5 × o do campo) e a seleção por formato ficam no service. O `IaAplicacao` dos
saves fica em `ia/aplicacao.py`.
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.schemas import PerfilRef
from sociman_api.ia.models import REGRAS_MAX, IaDesfecho
from sociman_api.ia.tipos import Entidade, Formato, Idioma, TipoCampoId
from sociman_api.perfis.schemas import UserRef

INSTRUCAO_MAX = 1000
ANTERIORES_MAX = 5
ACEITOS_MAX = 20
REJEITADOS_MAX = 100
LISTA_MAX = 40  # itens no valor atual (o limite do tipo é conferido no service)
ITEM_MAX = 400

# Spec 014: "conteudo" (+ conta) antes de o destino existir; "corte" continua (mesmo id).
AlvoTipo = Literal["asset", "perfil", "kit", "postagem", "corte", "conteudo"]
Item = Annotated[str, StringConstraints(max_length=ITEM_MAX)]


# ---- tipos e regras ----

class Limites(CamelModel):
    max_chars: int | None
    min_chars: int | None
    uma_linha: bool
    max_itens: int | None
    min_itens: int | None
    max_chars_item: int | None
    max_sugestoes: int | None


class Regras(CamelModel):
    texto: str  # em vigor (personalizado ou padrão)
    padrao: str
    personalizada: bool
    padrao_atualizado: bool  # o padrão mudou depois da última edição
    version: int  # 0 = nunca editada
    updated_at: datetime | None
    updated_by: UserRef | None


class TipoCampo(CamelModel):
    id: TipoCampoId
    rotulo: str
    onde: str
    entidade: Entidade
    idioma: Idioma
    formato: Formato
    limites: Limites
    regras: Regras


class TiposList(CamelModel):
    items: list[TipoCampo]  # na ordem do registro


class TipoOut(CamelModel):
    tipo: TipoCampo


class RegrasIn(CamelModel):
    version: Annotated[int, Field(ge=0)]  # 0 = nunca editada (cria a linha)
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                            max_length=REGRAS_MAX)]


class PadraoIn(CamelModel):
    version: Annotated[int, Field(ge=0)]


# ---- gerar ----

class Alvo(CamelModel):
    entity_type: AlvoTipo
    entity_id: UUID | None = None  # null no kit nunca salvo
    conta_id: UUID | None = None  # conteúdo (ou corte) + conta quando o destino não existe


class Valor(CamelModel):
    """Um formato por tipo: `texto`, `itens` ou os três da postagem."""

    texto: Annotated[str, StringConstraints(max_length=4000)] | None = None
    itens: Annotated[list[Item], Field(max_length=LISTA_MAX)] | None = None
    titulo: Annotated[str, StringConstraints(max_length=400)] | None = None
    descricao: Annotated[str, StringConstraints(max_length=4000)] | None = None
    hashtags: Annotated[list[Item], Field(max_length=LISTA_MAX)] | None = None


class Selecao(CamelModel):
    """Só nas `sugestoes`: marcados e ainda não aplicados, e os mostrados e não marcados."""

    aceitos: Annotated[list[Item], Field(max_length=ACEITOS_MAX)] = Field(default_factory=list)
    rejeitados: Annotated[list[Item], Field(max_length=REJEITADOS_MAX)] = Field(
        default_factory=list)


class GerarIn(CamelModel):
    tipo_campo: TipoCampoId
    perfil_id: UUID
    alvo: Alvo
    valor_atual: Valor = Field(default_factory=Valor)
    instrucao: Annotated[str, StringConstraints(max_length=INSTRUCAO_MAX)] = ""
    sessao_id: UUID
    anteriores: Annotated[list[UUID], Field(max_length=ANTERIORES_MAX)] = Field(
        default_factory=list)
    selecao: Selecao | None = None


class IaChamada(CamelModel):
    id: UUID
    tipo_campo: str  # as linhas antigas guardam o id que valia na época
    perfil: PerfilRef
    alvo: Alvo
    sessao_id: UUID | None
    instrucao: str
    aceitos: list[str]
    rejeitados: list[str]
    itens_aplicados: list[str] | None
    entrada: Valor | None
    proposta: Valor | None
    explicacao: str
    avisos: list[str]
    excede: bool
    contexto_faltante: list[str]
    desfecho: IaDesfecho
    desfecho_em: datetime | None
    desfecho_por: UserRef | None
    aplicada_versao: int | None
    model: str
    model_servido: str | None
    regras_version: int
    erro_code: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    custo_usd: float | None  # ≈ US$ (R7)
    duration_ms: int
    created_at: datetime
    created_by: UserRef | None


class ChamadaOut(CamelModel):
    chamada: IaChamada


# ---- registro e resumo (dono) ----

class ChamadasList(CamelModel):
    items: list[IaChamada]  # mais recentes primeiro
    next_cursor: str | None


class ResumoTipo(CamelModel):
    tipo_campo: str
    chamadas: int
    custo_usd: float


class ResumoPerfil(CamelModel):
    perfil: PerfilRef
    chamadas: int
    custo_usd: float


class IaResumo(CamelModel):
    mes: str  # YYYY-MM em APP_TZ
    de: date
    ate: date
    chamadas: int
    erros: int
    aplicadas: int
    editadas: int
    descartadas: int
    custo_usd: float
    por_tipo: list[ResumoTipo]
    por_perfil: list[ResumoPerfil]
    precos_versao: str
