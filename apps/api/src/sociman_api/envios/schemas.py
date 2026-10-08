"""Modelos Pydantic dos padrões de corte e dos envios (contracts/http-api.md da 006).

JSON em camelCase. As entradas dos padrões e da `config` do envio aceitam os tipos básicos e a
validação das faixas é feita no serviço, para responder `invalid_padroes` / `invalid_config`
com o `field` (e não o `validation_error` genérico).
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.schemas import CanalRef, VideoFonteRef  # os mesmos nomes no OpenAPI
from sociman_api.cortes.schemas import Corte
from sociman_api.envios.models import DireitoEnvio, EnvioOrigem, EnvioStatus
from sociman_api.envios.progresso import EnvioEtapa
from sociman_api.perfis.schemas import UserRef, VersionNumber

Layout = Literal["auto", "none", "split", "screencast", "speaker_cut"]
Formato = Literal["vertical", "square"]
Legenda = Literal["kit", "gerador", "nenhuma"]


# ---- padrões de corte ----

class PadroesCorte(CamelModel):
    perfil_id: UUID
    version: int  # 0 = padrão, nunca salvo
    clip_min_s: int
    clip_max_s: int
    quantidade: int | None
    layout: Layout
    formato: Formato
    legenda: Legenda
    marca_automatica: bool
    conta_padrao_id: UUID | None
    updated_at: datetime | None
    updated_by: UserRef | None


class PadroesCorteOut(CamelModel):
    padroes: PadroesCorte


class PadroesCorteIn(CamelModel):
    version: Annotated[int, Field(ge=0)]  # 0 = primeiro salvamento (cria a v1)
    clip_min_s: int
    clip_max_s: int
    quantidade: int | None = None
    layout: str
    formato: str
    legenda: str
    marca_automatica: bool
    conta_padrao_id: UUID | None = None


# ---- envios ----

class EnvioConfig(CamelModel):
    """Os padrões resolvidos no envio. O `subtitle` do kit fica só no servidor."""

    clip_min_s: int
    clip_max_s: int
    quantidade: int | None
    layout: Layout
    formato: Formato
    legenda: Legenda
    marca_automatica: bool
    kit_version: int | None


class EnvioConfigIn(CamelModel):
    """Sobrescreve os padrões do perfil no envio (tudo opcional)."""

    clip_min_s: int | None = None
    clip_max_s: int | None = None
    quantidade: int | None = None
    layout: str | None = None
    formato: str | None = None
    legenda: str | None = None
    marca_automatica: bool | None = None


class CortesResumo(CamelModel):
    """Clipes da geração por situação (spec 024, FR-018). A soma é o total, inclusive arquivados."""

    aceitos: int  # não arquivados com a marca aplicada ou em aplicação (na_fila, processando, pronto)
    pendentes: int  # não arquivados em revisão
    falhou: int  # não arquivados com falha
    arquivados: int


class Envio(CamelModel):
    id: UUID
    perfil_id: UUID
    origem: EnvioOrigem
    video: VideoFonteRef | None
    canal: CanalRef | None
    source_url: str | None
    source_title: str
    status: EnvioStatus
    config: EnvioConfig | None
    direito_no_envio: DireitoEnvio | None
    precisa_aviso: bool  # canal sem_acordo ou avulso: a UI mostra o aviso de direito
    progress: int  # % geral estimado, ponderado por etapa (envios/progresso.py)
    queue_position: int | None
    clips_total: int | None
    clips_importados: int
    # Progresso real (FR-010a): null em selecionado, confirmar_qualidade e descartado.
    etapa: EnvioEtapa | None
    etapa_pct: int | None
    clipe_atual: int | None
    clipes_previstos: int | None
    # Detalhe da etapa em pt-BR ("Transcrevendo o vídeo 25%", "Cortando clipe 3 de 9 (cenas 40%)");
    # o SPA junta com o % geral: "Processando 10% · Transcrevendo o vídeo 25%".
    etapa_mensagem: str | None
    error_message: str | None
    sent_at: datetime | None
    finished_at: datetime | None
    archived: bool
    version: int
    created_at: datetime
    created_by: UserRef | None
    cortes_resumo: CortesResumo | None = None  # null: a geração não tem nenhum corte


class EnvioOut(CamelModel):
    envio: Envio


class EnvioDetalhe(CamelModel):
    envio: Envio
    cortes: list[Corte]  # os clipes importados, para a revisão (inclui os arquivados)


class EnviosList(CamelModel):
    items: list[Envio]


class SelecionarIn(CamelModel):
    """`videoFonteId` (vídeo de canal) ou `url` (+ `titulo`) para o avulso por link."""

    video_fonte_id: UUID | None = None
    url: str | None = None
    titulo: str | None = None
    confirmar_duplicado: bool = False


class EnviarItem(CamelModel):
    envio_id: UUID
    version: VersionNumber


class EnviarIn(CamelModel):
    items: Annotated[list[EnviarItem], Field(min_length=1, max_length=20)]
    config: EnvioConfigIn | None = None
    confirmar_aviso: bool = False
    confirmar_duplicado: bool = False


class ConfirmarQualidadeIn(CamelModel):
    version: VersionNumber
    enviar: bool
