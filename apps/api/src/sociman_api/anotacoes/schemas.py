"""Modelos Pydantic das anotações e propostas (contracts/http-api.md da 009). JSON em camelCase.

Os `campos` de uma proposta de texto têm os mesmos limites dos textos do destino.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints

from sociman_api.anotacoes.models import AnotacaoAlvo, AnotacaoSituacao, AnotacaoTipo
from sociman_api.auth.schemas import CamelModel
from sociman_api.cenas.schemas import CamposCena
from sociman_api.perfis.schemas import Autor, UserRef
from sociman_api.postagem.schemas import Descricao, Hashtags, Titulo

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Motivo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
VersionNumber = Annotated[int, Field(ge=1)]


class CamposProposta(CamelModel):
    """Proposta de texto para um destino: pelo menos um campo (400 `campos_vazios`)."""

    model_config = ConfigDict(extra="forbid")

    titulo: Titulo | None = None
    descricao: Descricao | None = None
    hashtags: Hashtags | None = None


# Spec 010: a proposta de cena (`proposta_cena`) traz os campos da cena; o `tipo` decide qual.
Campos = CamposProposta | CamposCena


class AlvoRef(CamelModel):
    tipo: AnotacaoAlvo
    id: UUID
    titulo: str
    link: str  # rota do SPA do item
    arquivado: bool  # calculado na leitura (o item pode ter sido arquivado depois)


class Anotacao(CamelModel):
    id: UUID
    alvo: AlvoRef
    perfil_id: UUID | None
    tipo: AnotacaoTipo
    texto: str
    campos: Campos | None
    situacao: AnotacaoSituacao
    autor: Autor
    resolvida_por: UserRef | None
    resolvida_em: datetime | None
    motivo_descarte: str | None
    created_at: datetime
    version: int


class AnotacaoOut(CamelModel):
    anotacao: Anotacao


class AnotacoesPage(CamelModel):
    anotacoes: list[Anotacao]
    next_cursor: str | None


class AnotacoesResumo(CamelModel):
    abertas: int  # contador do menu "Propostas"


class CreateAnotacaoIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    alvo_tipo: AnotacaoAlvo
    alvo_id: UUID
    tipo: AnotacaoTipo = AnotacaoTipo.observacao
    texto: Texto
    campos: Campos | None = None


class UpdateAnotacaoIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    texto: Texto | None = None
    campos: Campos | None = None


class AnotacaoVersionIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber


class DescartarIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    motivo: Motivo | None = None


SituacaoFiltro = Literal["aberta", "aplicada", "descartada", "arquivada"]
