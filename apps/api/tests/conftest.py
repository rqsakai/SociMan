"""Fixtures dos testes (research R9): Postgres, Redis e MinIO reais do compose, banco
`sociman_test` e bucket `TEST_S3_BUCKET` (nunca o bucket de dev).

Rode no container: `docker compose exec api uv run pytest`.
"""

import itertools
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from minio import Minio
from minio.deleteobjects import DeleteObject
from sqlalchemy import text
from sqlalchemy.orm import Session

from sociman_api.auth.models import User, UserRole
from sociman_api.config import get_settings
from sociman_api.db import get_engine, get_sessionmaker
from sociman_api.redis import get_redis

API_DIR = Path(__file__).resolve().parents[1]


def _point_settings_to_test() -> None:
    """Troca DATABASE_URL/REDIS_URL pelos de teste antes de qualquer engine ou cliente existir."""
    missing = [
        k for k in ("TEST_DATABASE_URL", "TEST_REDIS_URL", "TEST_S3_BUCKET")
        if not os.environ.get(k)
    ]
    if missing:
        raise pytest.UsageError(
            f"Faltam {', '.join(missing)}: rode os testes no container "
            "(docker compose exec api uv run pytest)"
        )
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    os.environ["REDIS_URL"] = os.environ["TEST_REDIS_URL"]
    # Já no import, não só na fixture `s3_bucket`: nenhum teste grava no bucket de dev.
    os.environ["S3_BUCKET"] = os.environ["TEST_S3_BUCKET"]
    for cached in (get_settings, get_engine, get_sessionmaker, get_redis):
        cached.cache_clear()


_point_settings_to_test()

# Só depois de apontar para o banco de teste.
from sociman_api.main import app


@pytest.fixture(scope="session", autouse=True)
def _migrated() -> None:
    # Config sem arquivo .ini: o env.py não reconfigura o logging dos testes.
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    command.upgrade(cfg, "head")


# Ordem irrelevante (CASCADE); as da 003 e da 004 só entram se a migration já existir.
_TABLES = ("users", "one_time_tokens", "security_events", "entity_versions", "images", "contas",
           "perfis", "brand_kits", "brand_fonts", "cortes", "assets", "asset_files")
# Spec 006 (a mesma regra: só entram as que já existem).
_TABLES += ("canais_fonte", "canal_perfis", "videos_fonte", "video_metricas", "youtube_cota",
            "padroes_corte", "envios", "postagens", "ia_chamadas", "notificacoes")
# Spec 008.
_TABLES += ("ia_regras",)
# Spec 014.
_TABLES += ("conteudos",)
# Spec 015 (a linha única de `publicacao_config` volta desligada em `_clean_state`).
_TABLES += ("conexoes", "conexao_credenciais", "publicacao_tentativas")
# Spec 016: as 5 tabelas `metricas_*`, na ordem das FKs (o trigger de linha só de inserção não
# dispara no TRUNCATE, research R7).
_TABLES += ("metricas_buscas_post", "metricas_conta_fotos", "metricas_video_fotos",
            "metricas_videos", "metricas_series")
# Spec 017: os guias de comunicação (FKs para `perfis`/`contas`; o CASCADE cobre a ordem).
_TABLES += ("ia_guias",)
# Spec 020: o histórico do Studio (os dias primeiro; o trigger só de inserção não dispara no
# TRUNCATE).
_TABLES += ("metricas_studio_dias", "metricas_studio_importacoes")
# Spec 009: clientes MCP, registro (só inserção: o trigger de linha não dispara no TRUNCATE) e
# anotações. A linha única de `mcp_config` volta desligada em `_clean_state`.
_TABLES += ("mcp_chamadas", "anotacoes", "mcp_clientes")


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    with get_engine().begin() as conn:
        existing = [t for t in _TABLES
                    if conn.execute(text("SELECT to_regclass(:t)"), {"t": t}).scalar()]
        conn.execute(text(f"TRUNCATE {', '.join(existing)} RESTART IDENTITY CASCADE"))
        # Spec 015: o TRUNCATE de `users` (CASCADE) leva o singleton junto; volta desligado.
        if conn.execute(text("SELECT to_regclass('publicacao_config')")).scalar():
            conn.execute(text(
                "INSERT INTO publicacao_config (id, envios_habilitados, version) "
                "VALUES (1, false, 1) ON CONFLICT (id) DO UPDATE SET envios_habilitados = false, "
                "version = 1, created_by = NULL, updated_by = NULL"))
        if conn.execute(text("SELECT to_regclass('mcp_config')")).scalar():  # spec 009
            conn.execute(text(
                "INSERT INTO mcp_config (id, habilitado, version) VALUES (1, false, 1) "
                "ON CONFLICT (id) DO UPDATE SET habilitado = false, version = 1, "
                "created_by = NULL, updated_by = NULL"))
    get_redis().flushdb()
    yield
    app.dependency_overrides.clear()


@dataclass(frozen=True)
class TestBucket:
    """O bucket de teste no MinIO real do compose, com o cliente `minio` direto."""

    __test__ = False  # não é uma classe de teste do pytest

    name: str
    client: Minio

    def keys(self) -> list[str]:
        return [o.object_name for o in self.client.list_objects(self.name, recursive=True)]

    def empty(self) -> None:
        """Apaga os objetos SÓ do bucket de teste (o domínio nunca apaga; isto é só teste)."""
        if self.name != os.environ["TEST_S3_BUCKET"] or self.name == "sociman":
            raise RuntimeError(f"recusando esvaziar o bucket {self.name!r}")
        errors = self.client.remove_objects(
            self.name, (DeleteObject(k) for k in self.keys())
        )
        for error in errors:  # remove_objects é preguiçoso: iterar executa
            raise RuntimeError(f"falha ao apagar {error.name}: {error.message}")


@pytest.fixture(scope="session")
def s3_bucket() -> TestBucket:
    """Garante `settings.s3_bucket == TEST_S3_BUCKET` e o bucket criado. Não esvazia: use
    `s3` (por teste) ou `s3_bucket.empty()`."""
    settings = get_settings()
    name = os.environ["TEST_S3_BUCKET"]
    assert settings.s3_bucket == name, "settings.s3_bucket deveria ser o bucket de teste"
    client = Minio(settings.s3_endpoint, access_key=settings.s3_access_key,
                   secret_key=settings.s3_secret_key, secure=settings.s3_secure)
    if not client.bucket_exists(name):
        client.make_bucket(name)
    return TestBucket(name=name, client=client)


@pytest.fixture
def s3(s3_bucket: TestBucket) -> TestBucket:
    """Bucket de teste vazio no início do teste."""
    s3_bucket.empty()
    return s3_bucket


@pytest.fixture
def db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def email_sender():
    """Troca o SMTP por um `MemoryEmailSender` (import tardio: o módulo é de outra tarefa)."""
    from sociman_api.auth.email import MemoryEmailSender, get_email_sender

    sender = MemoryEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    return sender


@pytest.fixture
def outbox(email_sender) -> list[dict]:
    """Mensagens enviadas: dicts com `to`, `subject`, `text` e `html`."""
    return email_sender.outbox


def _hash_password(password: str) -> str:
    try:
        from sociman_api.auth.passwords import hash_password
    except ImportError:  # passwords.py ainda não existe: mesmos parâmetros de research R1
        from argon2 import PasswordHasher

        hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32,
                                salt_len=16)
        return hasher.hash(password)
    return hash_password(password)


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    seq = itertools.count(1)

    def _make(
        role: str = "membro",
        verified: bool = True,
        must_change: bool = False,
        password: str = "senha-forte-123",
        email: str | None = None,
        name: str | None = None,
        active: bool = True,
    ) -> User:
        n = next(seq)
        now = datetime.now(UTC)
        user = User(
            name=name or f"Usuário {n}",
            email=email or f"usuario{n}@teste.local",
            password_hash=_hash_password(password),
            role=UserRole(role),
            is_active=active,
            email_verified_at=now if verified else None,
            must_change_password=must_change,
            password_changed_at=now,
        )
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def login() -> Callable[[TestClient, str, str], dict[str, str]]:
    def _login(client: TestClient, email: str, pw: str) -> dict[str, str]:
        r = client.post("/api/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['accessToken']}"}

    return _login


# ---- spec 015 ----

@pytest.fixture
def tiktok_fake():
    """TikTok falsa (`tests/fakes/tiktok_fake.py`, R18): nenhum teste chama a TikTok real."""
    from fakes.tiktok_fake import TikTokFake

    return TikTokFake()


@pytest.fixture
def publicacao_habilitada(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    """Override do nível do servidor do interruptor (`PUBLICACAO_HABILITADA`, R11): a stack de
    teste sobe com `false`; `publicacao_habilitada(True)` liga só neste teste."""

    def _set(valor: bool = True) -> None:
        monkeypatch.setattr(get_settings(), "publicacao_habilitada", valor)

    return _set


# ---- spec 009 ----

@pytest.fixture
def mcp_habilitado(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    """Override do nível do servidor do interruptor MCP (`MCP_HABILITADO`, R11): a stack de
    teste sobe com `false`; `mcp_habilitado(True)` liga só neste teste."""

    def _set(valor: bool = True) -> None:
        monkeypatch.setattr(get_settings(), "mcp_habilitado", valor)

    return _set
