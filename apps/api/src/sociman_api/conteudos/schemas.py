"""Modelos Pydantic dos conteúdos (contracts/http-api.md da spec 014, "Tipos" e "Conteúdos").
JSON em camelCase."""

import enum
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.schemas import PerfilRef
from sociman_api.cenas.schemas import CenaResumo
from sociman_api.conteudos.consulta import Situacao
from sociman_api.conteudos.models import ConteudoOrigem as Origem
from sociman_api.perfis.schemas import UserRef, VersionNumber
from sociman_api.postagem.schemas import Destino, DestinoResumo

__all__ = ["Atalho", "Atalhos", "Conteudo", "ConteudoItem", "ConteudoOut", "ConteudosList",
           "EstadoFiltro", "OrdemConteudos", "Origem", "PropostaOpenshorts", "Situacao",
           "UpdateConteudoIn"]


class EstadoFiltro(enum.StrEnum):
    """Filtro `estado` da lista: um estado efetivo de algum destino, ou `sem_conta`."""

    pronto = "pronto"
    aprovacao_pedida = "aprovacao_pedida"
    aprovado = "aprovado"
    agendado = "agendado"
    a_postar = "a_postar"
    atrasado = "atrasado"
    atencao = "atencao"
    postado = "postado"
    rascunho_criado = "rascunho_criado"
    publicado = "publicado"
    falhou = "falhou"
    em_revisao = "em_revisao"
    arquivado = "arquivado"
    sem_conta = "sem_conta"
    # spec 015
    enviando = "enviando"
    pausado = "pausado"
    vencido = "vencido"
    aguardando_vaga = "aguardando_vaga"


class Atalho(enum.StrEnum):
    prontos_sem_agendamento = "prontos_sem_agendamento"
    aprovados_sem_data = "aprovados_sem_data"
    aprovacao_pedida = "aprovacao_pedida"
    agendados_hoje = "agendados_hoje"
    esta_semana = "esta_semana"
    a_postar = "a_postar"
    atrasados = "atrasados"
    falharam = "falharam"
    # spec 015
    vencidos = "vencidos"
    enviando = "enviando"
    rascunhos_criados = "rascunhos_criados"


class OrdemConteudos(enum.StrEnum):
    recentes = "recentes"  # criados mais recentes primeiro (padrão)
    agenda = "agenda"  # pelo próximo agendamento; sem agendamento no fim


TituloConteudo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class ConteudoItem(CamelModel):
    """Uma linha da lista."""

    id: UUID
    perfil: PerfilRef
    origem: Origem
    titulo: str
    situacao: Situacao
    poster_url: str | None  # via /img
    duration_ms: int | None
    created_at: datetime
    archived: bool
    corte_id: UUID | None
    envio_id: UUID | None
    destinos: list[DestinoResumo]  # os ativos
    sem_conta: bool


class PropostaOpenshorts(CamelModel):
    """O que o OpenShorts propôs para o corte (T074): só leitura, cópia de `cortes`."""

    titulo: str | None
    descricao: str | None
    gancho: str | None
    score: int | None  # a nota do OpenShorts


class Conteudo(ConteudoItem):
    """O detalhe: a linha + o arquivo e os destinos completos."""

    width: int | None
    height: int | None
    nao_vertical: bool  # largura ≥ altura (aviso, não bloqueia)
    video_bytes: int | None
    original_filename: str | None
    version: int
    updated_at: datetime
    updated_by: UserRef | None
    destinos: list[Destino]  # type: ignore[assignment]  # todos, inclusive os arquivados
    proposta_openshorts: PropostaOpenshorts | None  # null fora da origem corte do OpenShorts
    cenas: list[CenaResumo] = Field(default_factory=list)  # spec 010: as cenas que compõem o vídeo próprio


class ConteudoOut(CamelModel):
    conteudo: Conteudo


class ConteudosList(CamelModel):
    items: list[ConteudoItem]
    total: int  # do filtro, sem o cursor
    next_cursor: str | None


class Atalhos(CamelModel):
    prontos_sem_agendamento: int
    aprovados_sem_data: int
    aprovacao_pedida: int
    agendados_hoje: int
    esta_semana: int
    a_postar: int
    atrasados: int
    falharam: int
    vencidos: int  # spec 015
    enviando: int
    rascunhos_criados: int


# ---- entradas ----

class UpdateConteudoIn(CamelModel):
    version: VersionNumber
    titulo: TituloConteudo
