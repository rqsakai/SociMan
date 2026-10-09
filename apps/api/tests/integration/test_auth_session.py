"""US1: login, renovação, logout e `me` (T027; contracts/http-api.md, research.md R2–R5)."""

from http.cookies import SimpleCookie

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.auth import tokens
from sociman_api.auth.models import SecurityEvent, User
from sociman_api.config import get_settings

PW = "senha-forte-123"
COOKIE = "sociman_rt"


def _cookie(r) -> SimpleCookie:
    header = r.headers.get("set-cookie")
    assert header, "resposta sem Set-Cookie"
    jar = SimpleCookie()
    jar.load(header)
    assert COOKIE in jar
    return jar


def _rt(r) -> str:
    return _cookie(r)[COOKIE].value


def _refresh(client: TestClient, rt: str | None):
    # Cookie explícito: o jar do TestClient (http) nunca manda cookie Secure.
    headers = {"Cookie": f"{COOKIE}={rt}"} if rt else {}
    return client.post("/api/auth/refresh", headers=headers)


def _login(client: TestClient, email: str, pw: str = PW):
    return client.post("/api/auth/login", json={"email": email, "password": pw})


def _events(db: Session, type: str) -> list[SecurityEvent]:
    db.expire_all()
    return list(db.scalars(select(SecurityEvent).where(SecurityEvent.type == type)))


def _bearer(access: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}"}


# ---- login ----

def test_login_ok_returns_session_and_refresh_cookie(client, make_user, db):
    user = make_user(role="dono", email="dono@teste.local")
    r = _login(client, "Dono@Teste.local")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accessToken"]
    assert body["user"]["email"] == "dono@teste.local"
    assert body["user"]["role"] == "dono"
    assert body["user"]["isActive"] is True
    assert body["user"]["emailVerified"] is True
    assert body["user"]["mustChangePassword"] is False
    assert "passwordHash" not in body["user"]

    morsel = _cookie(r)[COOKIE]
    assert morsel["path"] == "/api/auth/refresh"
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"].lower() == "strict"
    ttl = get_settings().refresh_ttl
    assert ttl - 5 <= int(morsel["max-age"]) <= ttl

    [event] = _events(db, "login_succeeded")
    assert event.outcome == "ok"
    assert event.actor_kind == "user"
    assert event.actor_user_id == user.id
    assert event.subject_user_id == user.id


def test_wrong_password_and_unknown_email_give_identical_401(client, make_user, db):
    user = make_user(email="alguem@teste.local")
    wrong = _login(client, "alguem@teste.local", "senha-errada-999")
    unknown = _login(client, "ninguem@teste.local", "senha-errada-999")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.content == unknown.content
    assert wrong.json() == {
        "error": {"code": "invalid_credentials", "message": "E-mail ou senha incorretos"}
    }
    assert "set-cookie" not in wrong.headers

    events = _events(db, "login_failed")
    reasons = {e.details["reason"]: e for e in events}
    assert set(reasons) == {"wrong_password", "unknown_email"}
    assert reasons["wrong_password"].subject_user_id == user.id
    assert reasons["unknown_email"].subject_user_id is None
    for e in events:
        assert e.outcome == "denied"
        assert e.actor_kind == "anonymous"
        assert "senha-errada-999" not in str(e.details)


def test_unverified_email_gives_403_only_with_right_password(client, make_user):
    make_user(email="novo@teste.local", verified=False)
    r = _login(client, "novo@teste.local")
    assert r.status_code == 403
    assert r.json()["error"] == {
        "code": "email_not_verified", "message": "Confirme seu e-mail antes de entrar"
    }
    wrong = _login(client, "novo@teste.local", "senha-errada-999")
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"


def test_inactive_user_gets_same_401(client, make_user, db):
    make_user(email="saiu@teste.local", active=False)
    r = _login(client, "saiu@teste.local")
    assert r.status_code == 401
    assert r.json()["error"] == {
        "code": "invalid_credentials", "message": "E-mail ou senha incorretos"
    }
    [event] = _events(db, "login_failed")
    assert event.details == {"reason": "inactive"}


def test_login_rehashes_outdated_hash(client, make_user, db, monkeypatch):
    user = make_user(email="velho@teste.local")
    monkeypatch.setattr("sociman_api.auth.service.needs_rehash", lambda _h: True)
    old_hash = user.password_hash
    assert _login(client, "velho@teste.local").status_code == 200
    db.expire_all()
    new_hash = db.get(User, user.id).password_hash
    assert new_hash != old_hash
    assert new_hash.startswith("$argon2id$")


def test_eleventh_login_for_account_is_rate_limited(client, make_user):
    make_user(email="alvo@teste.local")
    for _ in range(10):
        assert _login(client, "alvo@teste.local", "senha-errada-999").status_code == 401
    r = _login(client, "alvo@teste.local")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) > 0


def test_invalid_body_is_400_validation_error(client):
    r = client.post("/api/auth/login", json={"email": "nao-e-email", "password": PW})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


# ---- renovação ----

def test_refresh_rotates_and_replay_outside_grace_kills_family(client, make_user, db,
                                                                monkeypatch):
    monkeypatch.setattr(get_settings(), "refresh_grace", 0)
    user = make_user(email="gira@teste.local")
    first = _rt(_login(client, "gira@teste.local"))

    r = _refresh(client, first)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == str(user.id)
    second = _rt(r)
    assert second != first
    morsel = _cookie(r)[COOKIE]
    assert morsel["path"] == "/api/auth/refresh"
    assert 0 < int(morsel["max-age"]) <= get_settings().refresh_ttl

    replay = _refresh(client, first)
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_token"
    cleared = _cookie(replay)[COOKIE]
    assert cleared.value == ""
    assert cleared["max-age"] == "0"
    assert cleared["path"] == "/api/auth/refresh"

    # a família inteira caiu: nem o token mais novo renova
    assert _refresh(client, second).status_code == 401

    [event] = _events(db, "refresh_reuse_detected")
    assert event.outcome == "denied"
    assert event.subject_user_id == user.id


def test_refresh_replay_within_grace_is_accepted(client, make_user):
    make_user(email="abas@teste.local")
    first = _rt(_login(client, "abas@teste.local"))
    assert _refresh(client, first).status_code == 200
    assert _refresh(client, first).status_code == 200


@pytest.fixture
def clock(monkeypatch):
    now = {"ms": tokens._now_ms()}
    monkeypatch.setattr(tokens, "_now_ms", lambda: now["ms"])
    return now


def test_concurrent_refresh_within_tolerance_keeps_sessions(client, make_user, db, clock):
    # Duas abas renovam juntas com o mesmo cookie: as duas ganham 200 e o MESMO token novo.
    assert get_settings().refresh_grace == 10
    user = make_user(email="duas-abas@teste.local")
    other = _rt(_login(client, "duas-abas@teste.local"))  # outra sessão (outro aparelho)
    first = _rt(_login(client, "duas-abas@teste.local"))

    a = _refresh(client, first)
    clock["ms"] += 9_000
    b = _refresh(client, first)
    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    assert _rt(b) == _rt(a)
    assert b.json()["accessToken"]

    # nada revogado: o token comum segue girando, e a outra sessão também
    assert _refresh(client, _rt(a)).status_code == 200
    assert _refresh(client, other).status_code == 200
    assert _events(db, "refresh_reuse_detected") == []
    [event] = _events(db, "refresh_concorrente")
    assert event.outcome == "ok"
    assert event.subject_user_id == user.id
    assert event.actor_user_id == user.id


def test_previous_token_after_tolerance_is_reuse(client, make_user, db, clock):
    make_user(email="atrasado@teste.local")
    other = _rt(_login(client, "atrasado@teste.local"))
    first = _rt(_login(client, "atrasado@teste.local"))
    second = _rt(_refresh(client, first))
    clock["ms"] += 11_000

    assert _refresh(client, first).status_code == 401
    assert _refresh(client, second).status_code == 401  # a família caiu
    [event] = _events(db, "refresh_reuse_detected")
    assert event.outcome == "denied"
    assert _events(db, "refresh_concorrente") == []
    # o reuso revoga a família apresentada, não as outras sessões do usuário
    assert _refresh(client, other).status_code == 200


def test_token_two_rotations_back_is_reuse_even_within_tolerance(client, make_user, db, clock):
    make_user(email="velho@teste.local")
    t0 = _rt(_login(client, "velho@teste.local"))
    t1 = _rt(_refresh(client, t0))
    t2 = _rt(_refresh(client, t1))
    clock["ms"] += 1_000

    assert _refresh(client, t0).status_code == 401
    assert _refresh(client, t2).status_code == 401
    assert len(_events(db, "refresh_reuse_detected")) == 1


def test_refresh_without_cookie_is_401_session_missing(client):
    r = _refresh(client, None)
    assert r.status_code == 401
    assert r.json()["error"] == {"code": "invalid_token", "message": "Sessão ausente"}
    assert _cookie(r)[COOKIE]["max-age"] == "0"


@pytest.mark.parametrize("rt", ["lixo", "fam-inexistente.segredo"])
def test_refresh_with_unknown_token_is_401(client, rt):
    r = _refresh(client, rt)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_refresh_for_deactivated_user_revokes_family(client, make_user, db):
    user = make_user(email="desliga@teste.local")
    login = _login(client, "desliga@teste.local")
    rt = _rt(login)
    access = login.json()["accessToken"]
    user.is_active = False
    db.commit()

    r = _refresh(client, rt)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"
    fam = tokens.decode_access(access)["fam"]
    assert not tokens.family_alive(fam)


# ---- logout e me ----

def test_logout_with_expired_bearer_revokes_family(client, make_user, db):
    user = make_user(email="sai@teste.local")
    login = _login(client, "sai@teste.local")
    access = login.json()["accessToken"]
    rt = _rt(login)
    fam = tokens.decode_access(access)["fam"]

    expired_settings = get_settings().model_copy(update={"access_ttl": -120})
    expired = tokens.sign_access(str(user.id), fam, expired_settings)
    assert tokens.decode_access(expired) is None

    r = client.post("/api/auth/logout", headers=_bearer(expired))
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert _cookie(r)[COOKIE]["max-age"] == "0"

    assert client.get("/api/auth/me", headers=_bearer(access)).status_code == 401
    assert _refresh(client, rt).status_code == 401
    [event] = _events(db, "logout")
    assert event.outcome == "ok"
    assert event.actor_user_id == user.id


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer lixo"}])
def test_logout_without_valid_bearer_is_still_ok(client, db, headers):
    r = client.post("/api/auth/logout", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert _events(db, "logout") == []


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_me_returns_user_even_with_pending_password_change(client, make_user, login):
    make_user(email="troca@teste.local", must_change=True)
    headers = login(client, "troca@teste.local", PW)
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["user"]["mustChangePassword"] is True


def test_deactivation_drops_me_on_next_request(client, make_user, db, login):
    user = make_user(email="corta@teste.local")
    headers = login(client, "corta@teste.local", PW)
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    user.is_active = False
    db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_me_exposes_only_contract_fields(client, make_user, login):
    make_user(email="priv@teste.local")
    headers = login(client, "priv@teste.local", PW)
    body = client.get("/api/auth/me", headers=headers).json()
    assert set(body["user"]) == {
        "id", "name", "email", "role", "isActive", "emailVerified", "mustChangePassword",
        "createdAt", "updatedAt",
    }


# ---- config ----

def test_config_exposes_password_policy(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json() == {"passwordMinLength": 12, "passwordMaxLength": 128}
