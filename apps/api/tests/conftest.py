"""Fixtures dos testes (research R9): Postgres e Redis reais do compose, banco `sociman_test`.

Rode no container: `docker compose exec api uv run pytest`.
"""

import itertools
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from sociman_api.auth.models import User, UserRole
from sociman_api.config import get_settings
from sociman_api.db import get_engine, get_sessionmaker
from sociman_api.redis import get_redis

API_DIR = Path(__file__).resolve().parents[1]


def _point_settings_to_test() -> None:
    """Troca DATABASE_URL/REDIS_URL pelos de teste antes de qualquer engine ou cliente existir."""
    missing = [k for k in ("TEST_DATABASE_URL", "TEST_REDIS_URL") if not os.environ.get(k)]
    if missing:
        raise pytest.UsageError(
            f"Faltam {', '.join(missing)}: rode os testes no container "
            "(docker compose exec api uv run pytest)"
        )
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    os.environ["REDIS_URL"] = os.environ["TEST_REDIS_URL"]
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


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    with get_engine().begin() as conn:
        conn.execute(
            text("TRUNCATE users, one_time_tokens, security_events RESTART IDENTITY CASCADE")
        )
    get_redis().flushdb()
    yield
    app.dependency_overrides.clear()


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
