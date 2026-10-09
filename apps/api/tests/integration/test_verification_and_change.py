"""US2: verificação de e-mail e troca de senha (T038; contracts/http-api.md, FR-012a/015/020/021)."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sociman_api.auth.models import OneTimeToken, SecurityEvent, User
from sociman_api.auth.rate_limit import LIMITS

PW = "senha-forte-123"
NEW_PW = "outra-senha-forte-456"
COOKIE = "sociman_rt"


def _events(db: Session, type: str) -> list[SecurityEvent]:
    db.expire_all()
    return list(db.scalars(select(SecurityEvent).where(SecurityEvent.type == type)))


def _token_from(message: dict) -> str:
    match = re.search(r"verify-email\?token=(\S+)", message["text"])
    assert match, message["text"]
    return unquote(match.group(1))


def _resend(client: TestClient, email: str):
    return client.post("/api/auth/verify-email/resend", json={"email": email})


def _verify(client: TestClient, token: str):
    return client.post("/api/auth/verify-email", json={"token": token})


def _request_link(client: TestClient, outbox: list[dict], email: str) -> str:
    r = _resend(client, email)
    assert r.status_code == 200, r.text
    return _token_from(outbox[-1])


def _session(client: TestClient, email: str, pw: str = PW) -> tuple[dict[str, str], str]:
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    rt = r.headers["set-cookie"].split(f"{COOKIE}=", 1)[1].split(";", 1)[0]
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}, rt


def _refresh(client: TestClient, rt: str):
    # Cookie explícito: o jar do TestClient (http) nunca manda cookie Secure.
    return client.post("/api/auth/refresh", headers={"Cookie": f"{COOKIE}={rt}"})


def _change(client: TestClient, headers: dict[str, str], current: str, new: str):
    return client.post("/api/auth/password/change", headers=headers,
                       json={"currentPassword": current, "newPassword": new})


# ---- verificação de e-mail ----

def test_verify_email_marks_verified_and_token_is_single_use(client, make_user, outbox, db):
    user = make_user(verified=False, email="novo@teste.local")
    token = _request_link(client, outbox, "novo@teste.local")
    assert outbox[-1]["to"] == "novo@teste.local"

    r = _verify(client, token)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert COOKIE not in r.headers.get("set-cookie", "")  # não abre sessão
    db.refresh(user)
    assert user.email_verified_at is not None
    [event] = _events(db, "email_verified")
    assert event.outcome == "ok"
    assert event.subject_user_id == user.id

    again = _verify(client, token)
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_token"

    # Depois de verificar, o login passa.
    assert client.post("/api/auth/login",
                       json={"email": "novo@teste.local", "password": PW}).status_code == 200


def test_unknown_token_is_invalid(client):
    r = _verify(client, "nao-existe")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_token"


def test_expired_token_is_invalid(client, make_user, outbox, db):
    user = make_user(verified=False)
    token = _request_link(client, outbox, user.email)
    db.execute(update(OneTimeToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()

    r = _verify(client, token)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_token"
    db.refresh(user)
    assert user.email_verified_at is None


def test_token_for_old_email_is_invalid_after_email_change(client, make_user, outbox, db):
    user = make_user(verified=False, email="antigo@teste.local")
    token = _request_link(client, outbox, "antigo@teste.local")
    user.email = "novo@teste.local"
    db.commit()

    r = _verify(client, token)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_token"
    db.refresh(user)
    assert user.email_verified_at is None


def test_new_link_invalidates_previous_one(client, make_user, outbox):
    user = make_user(verified=False)
    first = _request_link(client, outbox, user.email)
    second = _request_link(client, outbox, user.email)

    assert _verify(client, first).status_code == 400
    assert _verify(client, second).status_code == 200


# ---- reenvio ----

def test_resend_is_identical_for_existing_and_unknown_email(client, make_user, outbox, db):
    unverified = make_user(verified=False, email="pendente@teste.local")
    make_user(verified=True, email="verificado@teste.local")
    make_user(verified=False, active=False, email="inativo@teste.local")

    responses = [_resend(client, e) for e in ("pendente@teste.local", "ninguem@teste.local",
                                              "verificado@teste.local", "inativo@teste.local")]
    assert {r.status_code for r in responses} == {200}
    assert len({r.text for r in responses}) == 1

    # Só a conta ativa e não verificada recebe o link e gera o evento.
    assert [m["to"] for m in outbox] == ["pendente@teste.local"]
    [event] = _events(db, "email_verification_sent")
    assert event.subject_user_id == unverified.id
    assert event.actor_kind == "anonymous"
    # envio adiado (BackgroundTask) para o tempo de resposta não revelar a conta
    assert event.details == {"emailSent": None, "deferred": True}


def test_resend_is_rate_limited_per_account(client, make_user, outbox):
    make_user(verified=False, email="pendente@teste.local")
    limit = LIMITS["resend"].per_account
    for _ in range(limit):
        assert _resend(client, "pendente@teste.local").status_code == 200
    r = _resend(client, "Pendente@Teste.local")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert "retry-after" in r.headers
    assert len(outbox) == limit

    # O mesmo limite vale para e-mail inexistente (não revela nada).
    for _ in range(limit):
        assert _resend(client, "ninguem@teste.local").status_code == 200
    assert _resend(client, "ninguem@teste.local").status_code == 429


def test_resend_with_smtp_failure_still_answers_ok(client, make_user, email_sender, db):
    make_user(verified=False, email="pendente@teste.local")
    email_sender.fail = True
    r = _resend(client, "pendente@teste.local")
    assert r.status_code == 200
    [event] = _events(db, "email_verification_sent")
    assert event.details == {"emailSent": None, "deferred": True}


# ---- troca de senha ----

def test_change_password_with_wrong_current_gives_400(client, make_user, db):
    user = make_user()
    headers, _ = _session(client, user.email)
    r = _change(client, headers, "senha-errada-000", NEW_PW)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_credentials"
    assert r.json()["error"]["message"] == "Senha atual incorreta"

    [event] = _events(db, "password_changed")
    assert event.outcome == "denied"
    assert event.actor_kind == "user"
    assert event.actor_user_id == user.id
    assert event.details == {"reason": "wrong_current_password"}
    # A senha continua a mesma.
    assert _session(client, user.email)[0]


def test_change_to_same_password_gives_400(client, make_user):
    user = make_user()
    headers, _ = _session(client, user.email)
    r = _change(client, headers, PW, PW)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


def test_change_to_weak_password_gives_400(client, make_user):
    user = make_user()
    headers, _ = _session(client, user.email)
    r = _change(client, headers, PW, "curta")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


def test_change_keeps_current_session_and_revokes_others(client, make_user, db):
    user = make_user(must_change=True)
    current, current_rt = _session(client, user.email)
    other, other_rt = _session(client, user.email)

    r = _change(client, current, PW, NEW_PW)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["mustChangePassword"] is False
    new_headers = {"Authorization": f"Bearer {body['accessToken']}"}

    # Sessão atual: o access novo, o antigo e o refresh continuam valendo.
    assert client.get("/api/auth/me", headers=new_headers).status_code == 200
    assert client.get("/api/auth/me", headers=current).status_code == 200
    assert _refresh(client, current_rt).status_code == 200
    # Outra sessão: encerrada.
    assert client.get("/api/auth/me", headers=other).status_code == 401
    assert _refresh(client, other_rt).status_code == 401

    db.refresh(user)
    assert user.must_change_password is False
    assert user.updated_by == user.id
    [event] = _events(db, "password_changed")
    assert event.outcome == "ok"
    assert event.actor_user_id == user.id

    # Só a senha nova entra.
    assert client.post("/api/auth/login",
                       json={"email": user.email, "password": PW}).status_code == 401
    assert _session(client, user.email, NEW_PW)[0]


def test_change_password_requires_session(client):
    r = _change(client, {}, PW, NEW_PW)
    assert r.status_code == 401


def test_change_password_is_rate_limited_per_account(client, make_user):
    user = make_user()
    headers, _ = _session(client, user.email)
    for _ in range(LIMITS["change"].per_account):
        assert _change(client, headers, "senha-errada-000", NEW_PW).status_code == 400
    r = _change(client, headers, PW, NEW_PW)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


# ---- troca obrigatória (FR-012a) ----

def test_must_change_password_still_allows_me_and_change(client, make_user, db):
    user = make_user(must_change=True)
    headers, _ = _session(client, user.email)

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["mustChangePassword"] is True

    r = _change(client, headers, PW, NEW_PW)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, user.id).must_change_password is False
