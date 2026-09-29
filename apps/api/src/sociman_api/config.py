"""Configuração por variáveis de ambiente (nunca segredos no código)."""

import logging
import secrets
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    refresh_grace: int = 60
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
