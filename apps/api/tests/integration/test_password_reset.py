"""US4: recuperação de senha (T053; contracts/http-api.md, FR-006/019, SC-005/006)."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sociman_api.auth.models import OneTimeToken, SecurityEvent, TokenPurpose
from sociman_api.auth.rate_limit import LIMITS

PW = "senha-forte-123"
NEW_PW = "outra-senha-forte-456"
COOKIE = "sociman_rt"


def _events(db: Session, type: str) -> list[SecurityEvent]:
    db.expire_all()
    return list(db.scalars(select(SecurityEvent).where(SecurityEvent.type == type)))


def _token_from(message: dict) -> str:
    match = re.search(r"reset-password\?token=(\S+)", message["text"])
    assert match, message["text"]
    return unquote(match.group(1))


def _forgot(client: TestClient, email: str):
    return client.post("/api/auth/password/forgot", json={"email": email})


def _reset(client: TestClient, token: str, new: str = NEW_PW):
    return client.post("/api/auth/password/reset", json={"token": token, "newPassword": new})


def _request_link(client: TestClient, outbox: list[dict], email: str) -> str:
    r = _forgot(client, email)
    assert r.status_code == 200, r.text
    return _token_from(outbox[-1])


def _login(client: TestClient, email: str, pw: str):
    return client.post("/api/auth/login", json={"email": email, "password": pw})


def _session(client: TestClient, email: str, pw: str = PW) -> tuple[dict[str, str], str]:
    r = _login(client, email, pw)
    assert r.status_code == 200, r.text
    rt = r.headers["set-cookie"].split(f"{COOKIE}=", 1)[1].split(";", 1)[0]
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}, rt


def _refresh(client: TestClient, rt: str):
    # Cookie explícito: o jar do TestClient (http) nunca manda cookie Secure.
    return client.post("/api/auth/refresh", headers={"Cookie": f"{COOKIE}={rt}"})


# ---- pedido (forgot) ----

def test_forgot_is_identical_for_existing_unknown_and_inactive(client, make_user, outbox, db):
    active = make_user(email="ativo@teste.local")
    make_user(active=False, email="inativo@teste.local")

    responses = [_forgot(client, e) for e in ("ativo@teste.local", "ninguem@teste.local",
                                              "inativo@teste.local")]
    assert {r.status_code for r in responses} == {200}
    assert len({r.text for r in responses}) == 1
    assert responses[0].json() == {"ok": True}

    # Só a conta ativa recebe o link e gera o evento.
    assert [m["to"] for m in outbox] == ["ativo@teste.local"]
    [event] = _events(db, "password_reset_requested")
    assert event.subject_user_id == active.id
    assert event.actor_kind == "anonymous"
    # envio adiado (BackgroundTask) para o tempo de resposta não revelar a conta
    assert event.details == {"deferred": True}


def test_forgot_is_rate_limited_per_account(client, make_user, outbox):
    make_user(email="ativo@teste.local")
    limit = LIMITS["forgot"].per_account
    for _ in range(limit):
        assert _forgot(client, "ativo@teste.local").status_code == 200
    r = _forgot(client, "Ativo@Teste.local")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert "retry-after" in r.headers
    assert len(outbox) == limit


# ---- redefinição (reset) ----

def test_reset_changes_password_and_ends_all_sessions(client, make_user, outbox, db):
    user = make_user(must_change=True, email="ativo@teste.local")
    headers_a, rt_a = _session(client, user.email)
    headers_b, rt_b = _session(client, user.email)
    token = _request_link(client, outbox, user.email)

    r = _reset(client, token)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    # Todas as sessões caem: access token antigo e renovação.
    for headers, rt in ((headers_a, rt_a), (headers_b, rt_b)):
        assert client.get("/api/auth/me", headers=headers).status_code == 401
        assert _refresh(client, rt).status_code == 401

    db.refresh(user)
    assert user.must_change_password is False
    assert user.updated_by == user.id
    [event] = _events(db, "password_reset_completed")
    assert event.outcome == "ok"
    assert event.subject_user_id == user.id
    assert event.actor_kind == "user"
    assert event.actor_user_id == user.id

    # A senha antiga falha e a nova entra.
    old = _login(client, user.email, PW)
    assert old.status_code == 401
    assert old.json()["error"]["code"] == "invalid_credentials"
    assert _login(client, user.email, NEW_PW).status_code == 200


def test_reset_token_is_single_use(client, make_user, outbox):
    user = make_user()
    token = _request_link(client, outbox, user.email)
    assert _reset(client, token).status_code == 200

    again = _reset(client, token, "mais-uma-senha-forte-789")
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_token"
    assert again.json()["error"]["message"] == "Link inválido ou expirado — peça um novo"
    assert _login(client, user.email, NEW_PW).status_code == 200


def test_unknown_token_is_invalid(client):
    r = _reset(client, "nao-existe")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_token"


def test_expired_token_is_invalid(client, make_user, outbox, db):
    user = make_user()
    token = _request_link(client, outbox, user.email)
    # +15 min: o prazo do link passou.
    db.execute(update(OneTimeToken).values(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        created_at=datetime.now(UTC) - timedelta(minutes=15, seconds=1),
    ))
    db.commit()

    r = _reset(client, token)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_token"
    assert _login(client, user.email, PW).status_code == 200


def test_new_request_invalidates_previous_link(client, make_user, outbox):
    user = make_user()
    first = _request_link(client, outbox, user.email)
    second = _request_link(client, outbox, user.email)

    assert _reset(client, first).status_code == 400
    assert _reset(client, second).status_code == 200


def test_weak_password_does_not_consume_token(client, make_user, outbox, db):
    user = make_user()
    token = _request_link(client, outbox, user.email)

    for weak in ("curta", "123456789012"):  # curta demais; comum
        r = _reset(client, token, weak)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "validation_error"

    db.expire_all()
    [row] = db.scalars(select(OneTimeToken).where(
        OneTimeToken.purpose == TokenPurpose.reset_password, OneTimeToken.used_at.is_(None)))
    assert row.user_id == user.id
    assert _events(db, "password_reset_completed") == []
    assert _reset(client, token).status_code == 200


def test_reset_is_rate_limited_per_ip(client):
    for _ in range(LIMITS["reset"].per_ip):
        assert _reset(client, "nao-existe").status_code == 400
    r = _reset(client, "nao-existe")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
