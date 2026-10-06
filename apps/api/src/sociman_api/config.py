"""Configuração por variáveis de ambiente (nunca segredos no código)."""

import logging
import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "sociman"
    env: str = "development"
    database_url: str = "postgresql+psycopg://sociman:sociman@localhost:5432/sociman"
    redis_url: str = "redis://localhost:6379/0"

    # Auth (research.md R2/R3). Em produção JWT_SECRET é obrigatório (>= 32 chars).
    jwt_secret: str | None = None
    access_ttl: int = 15 * 60
    refresh_ttl: int = 7 * 24 * 60 * 60
    # Carência do token anterior (renovação concorrente entre abas). Curta: fora dela é reuso.
    refresh_grace: int = 10
    verify_ttl: int = 24 * 60 * 60
    reset_ttl: int = 15 * 60
    password_min_length: int = 12
    password_max_length: int = 128

    # E-mail (R6). Em dev/teste o SMTP é o Mailpit.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "SociMan <nao-responda@sociman.local>"
    smtp_timeout: int = 5
    app_url: str = "http://localhost:8180"

    # Imagens (spec 003): MinIO (bucket privado) + imgproxy (derivados em /img).
    s3_endpoint: str = "minio:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "sociman"
    s3_secure: bool = False
    imgproxy_key: str | None = None  # hex; sem key/salt as URLs são "unsafe" (só dev)
    imgproxy_salt: str | None = None
    img_public_path: str = "/img"

    # HD de dados (spec 004, R5): MinIO, work/ e o sentinela `.sociman-volume`. Buckets por tipo.
    data_dir: str = Field("/media/sakai/BACKUP/tiktok/sociman",
                          validation_alias=AliasChoices("SOCIMAN_DATA_DIR", "data_dir"))
    data_min_free_gb: float = 20
    s3_fonts_bucket: str = "sociman-fonts"
    s3_videos_bucket: str = "sociman-videos"
    worker_poll_s: float = 30  # espera do worker com a fila vazia ou sem o HD
    midia_link_ttl_s: int = Field(3600, gt=0)  # links de mídia da interface (R6)

    # Canais-fonte, OpenShorts e textos (spec 006, R15). As chaves ficam só no `.env` da raiz
    # (compose → api e agendador) e são SecretStr: nunca aparecem em repr nem em log.
    youtube_api_key: SecretStr = SecretStr("")  # vazio = não configurada
    youtube_api_url: str = "https://www.googleapis.com/youtube/v3"  # o e2e aponta para o fake
    openshorts_url: str = "http://host.docker.internal:8000"
    anthropic_api_key: SecretStr = SecretStr("")
    textos_model: str = "claude-sonnet-5-5"
    anthropic_base_url: str = ""  # spec 008: vazio = padrão do SDK; só o e2e aponta para o fake
    app_tz: str = "America/Sao_Paulo"  # exibição e agendamento; tudo guardado em timestamptz
    yt_quota_daily: int = Field(10000, gt=0)
    sync_novos_h: float = Field(1, gt=0)  # intervalo da sync incremental de cada canal
    # Intervalos das trilhas do `sociman agendador` (R1), em segundos.
    agendador_sync_s: float = Field(60, gt=0)
    agendador_openshorts_s: float = Field(10, gt=0)
    agendador_importacao_s: float = Field(5, gt=0)
    agendador_lembretes_s: float = Field(30, gt=0)

    # Publicação no TikTok (spec 015, contracts "Variáveis de ambiente"). Segredos em SecretStr;
    # vazio = não configurado. Nenhuma URL da TikTok aqui (guarda R16.1): `tiktok_api_url` e
    # `tiktok_upload_hosts` vazios usam as constantes de `publicacao/tiktok/cliente.py`.
    tiktok_client_key: SecretStr = SecretStr("")
    tiktok_client_secret: SecretStr = SecretStr("")
    sociman_tokens_key: SecretStr = SecretStr("")
    sociman_tokens_key_anterior: SecretStr = SecretStr("")
    publicacao_habilitada: bool = False  # nível do servidor do interruptor (R11)
    tiktok_app_situacao: Literal["sandbox", "auditado"] = "sandbox"
    tiktok_redirect_web: str = ""
    tiktok_redirect_desktop: str = ""
    # Spec 016 (R1): + `user.info.stats,video.list` no fim (métricas; opcionais na conexão).
    tiktok_scopes: str = (
        "user.info.basic,user.info.profile,video.upload,video.publish,user.info.stats,video.list")
    tiktok_api_url: str = ""  # só o e2e aponta para o fake
    tiktok_upload_hosts: str = ""  # hosts extras para o PUT das partes, separados por vírgula
    agendador_publicacao_s: float = Field(15, gt=0)

    # Métricas das redes (spec 016, R3): a trilha `metricas` só lê. `false` pausa a coleta sem
    # desconectar (desconectar anonimiza, Q4 = A).
    metricas_coleta_habilitada: bool = True
    agendador_metricas_s: int = Field(60, gt=0)

    # Servidor MCP (spec 009, R10/R11): nível do servidor do interruptor (o outro é a tela) e as
    # origens de navegador aceitas no `/mcp` (vazio = nenhuma; agentes não mandam `Origin`).
    mcp_habilitado: bool = False
    mcp_origens_permitidas: Annotated[list[str], NoDecode] = []

    # Importação da agência (spec 013, R1): as pastas da agência, montadas só leitura no
    # container da API (`AGENCIA_SHARED_HOST`/`AGENCIA_CLIPES_HOST` no compose).
    agencia_shared_dir: str = "/agencia/shared"
    agencia_clipes_dir: str = "/agencia/clipes"

    @field_validator("mcp_origens_permitidas", mode="before")
    @classmethod
    def _origens(cls, value: object) -> object:
        if isinstance(value, str):  # `.env`: separadas por vírgula
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @model_validator(mode="after")
    def _jwt_secret(self) -> "Settings":
        if self.jwt_secret and len(self.jwt_secret) >= 32:
            return self
        if self.env == "production":
            raise ValueError("JWT_SECRET ausente ou com menos de 32 caracteres (obrigatório em produção)")
        self.jwt_secret = secrets.token_urlsafe(48)
        log.warning("JWT_SECRET não definido: usando segredo efêmero (sessões caem a cada restart)")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
