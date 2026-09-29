"""Modelos Pydantic de sugestões, postagens e calendário (contracts/http-api.md da 006,
"Postagens"). JSON em camelCase.

Aqui ficam formato e limites (data-model.md). A normalização das hashtags, a ligação conta ×
perfil do corte, o `corte_not_ready` e o `planned_in_past` ficam no service.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.schemas import PerfilRef  # o mesmo nome no OpenAPI (trilha A)
from sociman_api.cortes.models import CorteStatus
from sociman_api.ia.aplicacao import IaAplicacoes
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import UserRef, VersionNumber
from sociman_api.postagem.models import EstadoPostagem

Titulo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Descricao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
# Cada hashtag chega crua (com ou sem #); o service normaliza e confere `^#[\p{L}0-9_]{1,50}$`.
HashtagIn = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Hashtags = Annotated[list[HashtagIn], Field(max_length=8)]
PostedUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500, pattern=r"^https?://\S+$")
]


# ---- saídas ----

class ContaRef(CamelModel):
    id: UUID
    platform: Platform
    platform_name: str
    handle: str


class Sugestao(CamelModel):
    id: UUID
    plataforma: Platform
    titulo: str
    descricao: str
    hashtags: list[str]
    ajustes: list[str]  # o que foi cortado ou completado na validação
    model: str
    created_at: datetime


class SugestaoOut(CamelModel):
    sugestao: Sugestao


class SugestoesList(CamelModel):
    items: list[Sugestao]  # mais recentes primeiro (só as que deram resultado)


class Postagem(CamelModel):
    id: UUID
    corte_id: UUID
    conta: ContaRef
    titulo: str
    descricao: str
    hashtags: list[str]
    estado: EstadoPostagem
    planned_at: datetime | None  # ISO com o offset de APP_TZ
    posted_at: datetime | None
    posted_url: str | None
    lembrado: bool  # "Hora de postar" já avisada para este horário
    archived: bool
    version: int
    created_at: datetime
    updated_at: datetime
    updated_by: UserRef | None


class PostagemResumo(CamelModel):
    """O que o `Corte` mostra das postagens ativas dele (T057/T067)."""

    id: UUID
    conta_id: UUID
    plataforma: Platform
    handle: str
    estado: EstadoPostagem
    planned_at: datetime | None


class PostagemOut(CamelModel):
    postagem: Postagem


class PostagensList(CamelModel):
    items: list[Postagem]


class CorteCalendario(CamelModel):
    id: UUID
    poster_url: str | None
    perfil_id: UUID
    duration_ms: int
    status: CorteStatus


class PerfilCalendario(PerfilRef):
    cor: str | None = None  # 1ª cor da paleta do kit (#RRGGBB); null sem kit salvo (R14)


class CalendarioItem(Postagem):
    corte: CorteCalendario
    perfil: PerfilCalendario


class SemData(CamelModel):
    corte_id: UUID
    perfil_id: UUID
    poster_url: str | None
    titulo: str
    perfil_cor: str | None = None  # a mesma cor do PerfilCalendario


class CalendarioOut(CamelModel):
    items: list[CalendarioItem]  # por planned_at
    sem_data: list[SemData]  # cortes prontos sem postagem agendada


# ---- entradas ----

class SugestaoIn(CamelModel):
    conta_id: UUID  # a plataforma vem da conta
    # "Outra versão": manda ao Claude as sugestões anteriores deste corte na plataforma.
    outra_versao: bool = False


class CreatePostagemIn(CamelModel):
    conta_id: UUID
    titulo: Titulo = ""
    descricao: Descricao = ""
    hashtags: Hashtags = Field(default_factory=list)
    planned_at: datetime | None = None  # com data → `agendado` (corte pronto)
    # Spec 008: `ia` substitui o `sugestaoId` (o servidor o grava a partir do item da IA).
    sugestao_id: UUID | None = Field(default=None, json_schema_extra={"deprecated": True})
    ia: IaAplicacoes | None = None


class UpdatePostagemIn(CamelModel):
    """`plannedAt` ausente não muda; `null` volta a `rascunho`; com data, `agendado`."""

    version: VersionNumber
    conta_id: UUID | None = None
    titulo: Titulo | None = None
    descricao: Descricao | None = None
    hashtags: Hashtags | None = None
    planned_at: datetime | None = None
    sugestao_id: UUID | None = Field(default=None, json_schema_extra={"deprecated": True})
    ia: IaAplicacoes | None = None


class PostadoIn(CamelModel):
    version: VersionNumber
    posted_url: PostedUrl | None = None
