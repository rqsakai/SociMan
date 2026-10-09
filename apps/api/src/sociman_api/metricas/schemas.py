"""Modelos Pydantic das métricas (contracts/http-api.md da 016, "Tipos"). JSON em camelCase.

Nenhum campo tem `tiktok` nem `share` no nome: o link do post se chama `url`, e a rede aparece só
no valor (`rede: "tiktok"`). Um vídeo anônimo sai sem `conta`, `url` nem `legenda`.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.schemas import PerfilRef
from sociman_api.metricas.estado import (  # noqa: F401 — reexportados
    ErroColeta,
    EstadoColeta,
    PermissaoColeta,
)
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import UserRef, VersionNumber
from sociman_api.postagem.schemas import ContaRef, Destino

Origem = Literal["corte", "video_proprio", "fora", "anonima"]
VinculoMetodoOut = Literal["envio", "casamento", "link", "escolha"]
VinculoEstado = Literal["vinculado", "buscando", "a_confirmar", "sem_vinculo", "indisponivel"]
Ancora = Literal["entrega", "postado"]
LegendaClasse = Literal["compativel", "neutra", "incompativel"]
MarcoMotivo = Literal["ainda_nao", "sem_dado"]
BuscaFim = Literal["vinculado", "prazo", "falhou", "desfeito", "anonimizada", "cancelada"]


# ---- fotos e marcos ----

class Contadores(CamelModel):
    views: int | None
    likes: int | None
    comments: int | None
    shares: int | None


class FotoVideo(Contadores):
    coletado_em: datetime
    idade_s: int
    alvo_idade_min: int


class FotoConta(CamelModel):
    coletado_em: datetime
    janela_em: datetime
    seguidores: int | None
    seguindo: int | None
    curtidas: int | None
    videos: int | None
    # Derivada: soma das últimas views de cada vídeo da série até `coletado_em` (a rede não dá).
    views: int | None


class MarcoValor(CamelModel):
    valor: float | None
    estimado: bool
    motivo: MarcoMotivo | None


class MarcoMetricas(CamelModel):
    views: MarcoValor
    likes: MarcoValor
    comments: MarcoValor
    shares: MarcoValor


class Marcos(CamelModel):
    h1: MarcoMetricas
    h24: MarcoMetricas
    d7: MarcoMetricas
    d30: MarcoMetricas


# ---- vídeos ----

class VideoResumo(CamelModel):
    id: UUID  # o `video_ref` do dataset (uuid do SociMan)
    rede: Platform
    conta_id: UUID | None  # null se anônimo
    conta: ContaRef | None
    serie_rotulo: str | None  # "Conta anônima N"
    perfil: PerfilRef | None
    origem: Origem
    publicado_em: datetime
    duracao_s: int
    legenda: str | None
    url: str | None  # link do post (null se anônimo)
    disponivel: bool
    indisponivel_desde: datetime | None
    conteudo_id: UUID | None
    destino_id: UUID | None
    vinculo_metodo: VinculoMetodoOut | None
    miniatura_url: str | None  # a do conteúdo no SociMan (/img), nunca a CDN da rede
    ultima: FotoVideo | None
    # Alias explícito: o gerador faria `views24H` (o contrato diz `views24h`).
    views24h: MarcoValor = Field(alias="views24h")
    views7d: MarcoValor = Field(alias="views7d")
    engajamento: float | None  # (likes + comments + shares) / views da última foto
    velocidade: float | None  # views/h nas últimas 24 h de idade


class VideoDetalhe(VideoResumo):
    fotos: list[FotoVideo]
    marcos: Marcos
    coleta_parada_em: datetime | None  # > 365 d


class VideosList(CamelModel):
    items: list[VideoResumo]
    next_cursor: str | None
    total: int


class Publicacao(CamelModel):
    video_id: UUID
    publicado_em: datetime
    conteudo_id: UUID | None


class ContaMetricasOut(CamelModel):
    coleta: EstadoColeta
    fotos: list[FotoConta]
    publicacoes: list[Publicacao]
    views_total: int | None  # soma da última foto de cada vídeo da série (agora)


# ---- vínculo do destino ----

class Candidato(CamelModel):
    video: VideoResumo
    duracao_diferenca_s: float
    legenda: LegendaClasse
    minutos_da_ancora: int | None  # publicadoEm − âncora (ou − planned_at, sem âncora)


class Busca(CamelModel):
    entregue_em: datetime
    consultas: int
    ate: datetime  # entregue_em + 14 d
    fim: BuscaFim | None


class Vinculo(CamelModel):
    estado: VinculoEstado
    video: VideoResumo | None
    metodo: VinculoMetodoOut | None
    vinculado_por: UserRef | None  # null = automático
    vinculado_em: datetime | None
    busca: Busca | None
    ancora: Ancora | None  # null = lembrete antes do clique (ou sem âncora)
    ancora_em: datetime | None
    candidatos: list[Candidato]
    bloqueado: bool  # houve `vinculo_desfeito` (R10)
    automatico: bool  # false depois de desfeito
    pode_vincular: bool
    motivo: str | None


class VinculoIn(CamelModel):
    """Exatamente um de `videoId` (escolher) ou `link` (colar)."""

    version: VersionNumber
    video_id: UUID | None = None
    link: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _um_so(self) -> "VinculoIn":
        if (self.video_id is None) == (self.link is None or not self.link.strip()):
            raise ValueError("Informe o post escolhido ou o link, um dos dois")
        return self


class VinculoOut(CamelModel):
    destino: Destino
    vinculo: Vinculo


class DestinoMetricasOut(CamelModel):
    vinculo: Vinculo
    video: VideoDetalhe | None
