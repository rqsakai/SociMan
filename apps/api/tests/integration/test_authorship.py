"""US3: autor registrado em toda mutação (T048; FR-016, FR-017, SC-004).

Rotas de mutação da 001: `POST /api/users`, `PATCH /api/users/{id}`,
`POST /api/users/{id}/password`, `POST /api/users/{id}/verification`,
`POST /api/auth/password/change` e `POST /api/auth/verify-email` (o login não altera dados).
"""

import json
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.auth.models import SecurityEvent, User

PW = "senha-forte-123"
PROVISIONAL = "provisoria-forte-456"
NEW_PW = "outra-senha-forte-789"
TARGET = "{target}"
SENSITIVE = ("password", "token", "hash")


def _sensitive_keys(value: Any, path: str = "") -> list[str]:
    if isinstance(value, dict):
        found = [f"{path}.{k}" for k in value if any(s in str(k).lower() for s in SENSITIVE)]
        for k, v in value.items():
            found += _sensitive_keys(v, f"{path}.{k}")
        return found
    if isinstance(value, list):
        return [hit for i, v in enumerate(value) for hit in _sensitive_keys(v, f"{path}[{i}]")]
    return []


@pytest.fixture(autouse=True)
def _details_sem_segredos(db: Session) -> Iterator[None]:
    """Varre TODOS os eventos gravados em cada teste deste módulo: nada de senha, token ou hash."""
    yield
    db.expire_all()
    hashes = [h for h in db.scalars(select(User.password_hash)) if h]
    events = list(db.scalars(select(SecurityEvent)))
    for event in events:
        assert _sensitive_keys(event.details) == [], (event.type, event.details)
        dumped = json.dumps(event.details)
        for secret in (PW, PROVISIONAL, NEW_PW, "$argon2", *hashes):
            assert secret not in dumped, (event.type, event.details)


def _events(db: Session, type: str) -> list[SecurityEvent]:
    db.expire_all()
    return list(db.scalars(select(SecurityEvent).where(SecurityEvent.type == type)
                           .order_by(SecurityEvent.id)))


def _assert_event(db: Session, type: str, actor: User, subject_id) -> SecurityEvent:
    events = _events(db, type)
    assert events, f"nenhum evento {type}"
    event = events[-1]
    assert event.outcome == "ok"
    assert event.actor_kind == "user"
    assert event.actor_user_id == actor.id
    assert event.subject_user_id == subject_id
    assert event.occurred_at is not None
    return event


def _reloaded(db: Session, user_id) -> User:
    db.expire_all()
    return db.get(User, user_id)


def _verify_token(message: dict) -> str:
    match = re.search(r"verify-email\?token=(\S+)", message["text"])
    assert match, message["text"]
    return unquote(match.group(1))


@pytest.fixture
def owner(make_user) -> User:
    return make_user(role="dono", name="Dona")


@pytest.fixture
def owner_headers(client: TestClient, owner: User, login) -> dict[str, str]:
    return login(client, owner.email, PW)


# ---- cada rota de mutação grava autor e evento ----

def test_criar_usuario_grava_created_by_updated_by_e_eventos(
    client: TestClient, db: Session, owner: User, owner_headers, email_sender
) -> None:
    r = client.post("/api/users", headers=owner_headers, json={
        "name": "Novo", "email": "novo@teste.local", "role": "membro",
        "provisionalPassword": PROVISIONAL,
    })
    assert r.status_code == 200, r.text
    created = _reloaded(db, r.json()["user"]["id"])

    assert created.created_by == owner.id
    assert created.updated_by == owner.id
    assert created.created_at is not None and created.updated_at is not None
    _assert_event(db, "user_created", owner, created.id)
    _assert_event(db, "email_verification_sent", owner, created.id)


@pytest.mark.parametrize(("body", "event_type"), [
    ({"name": "Outro nome"}, "user_updated"),
    ({"role": "dono"}, "role_changed"),
    ({"isActive": False}, "user_deactivated"),
    ({"email": "trocado@teste.local"}, "email_changed"),
])
def test_editar_usuario_grava_updated_by_e_evento(
    client: TestClient, db: Session, owner: User, owner_headers, make_user, email_sender,
    body: dict, event_type: str,
) -> None:
    target = make_user()
    assert target.updated_by is None

    r = client.patch(f"/api/users/{target.id}", headers=owner_headers, json=body)
    assert r.status_code == 200, r.text
    assert _reloaded(db, target.id).updated_by == owner.id
    _assert_event(db, event_type, owner, target.id)


def test_senha_provisoria_grava_updated_by_e_evento(
    client: TestClient, db: Session, owner: User, owner_headers, make_user
) -> None:
    target = make_user()
    r = client.post(f"/api/users/{target.id}/password", headers=owner_headers,
                    json={"provisionalPassword": PROVISIONAL})
    assert r.status_code == 200, r.text
    assert _reloaded(db, target.id).updated_by == owner.id
    _assert_event(db, "password_set_by_owner", owner, target.id)


def test_reenvio_de_verificacao_grava_evento_do_dono(
    client: TestClient, db: Session, owner: User, owner_headers, make_user, email_sender
) -> None:
    # Não altera a linha do usuário (só emite um token): a autoria fica no evento.
    target = make_user(verified=False)
    r = client.post(f"/api/users/{target.id}/verification", headers=owner_headers)
    assert r.status_code == 200, r.text
    _assert_event(db, "email_verification_sent", owner, target.id)


def test_troca_da_propria_senha_grava_updated_by_e_evento(
    client: TestClient, db: Session, make_user, login
) -> None:
    member = make_user(must_change=True)
    headers = login(client, member.email, PW)
    r = client.post("/api/auth/password/change", headers=headers,
                    json={"currentPassword": PW, "newPassword": NEW_PW})
    assert r.status_code == 200, r.text
    assert _reloaded(db, member.id).updated_by == member.id
    _assert_event(db, "password_changed", member, member.id)


def test_verificacao_de_email_tem_o_proprio_usuario_como_autor(
    client: TestClient, db: Session, owner: User, owner_headers, make_user, email_sender
) -> None:
    target = make_user(verified=False)
    r = client.post(f"/api/users/{target.id}/verification", headers=owner_headers)
    assert r.status_code == 200, r.text
    token = _verify_token(email_sender.outbox[-1])

    r = client.post("/api/auth/verify-email", json={"token": token})  # rota pública
    assert r.status_code == 200, r.text
    verified = _reloaded(db, target.id)
    assert verified.email_verified_at is not None
    assert verified.updated_by == target.id
    _assert_event(db, "email_verified", target, target.id)


def test_dois_autores_diferentes_ficam_registrados(
    client: TestClient, db: Session, owner: User, owner_headers, make_user, login
) -> None:
    """Cenário do teste independente da US3: cada alteração guarda quem a fez."""
    member = make_user()
    r = client.patch(f"/api/users/{member.id}", headers=owner_headers, json={"name": "Renomeado"})
    assert r.status_code == 200, r.text
    assert _reloaded(db, member.id).updated_by == owner.id

    headers = login(client, member.email, PW)
    r = client.post("/api/auth/password/change", headers=headers,
                    json={"currentPassword": PW, "newPassword": NEW_PW})
    assert r.status_code == 200, r.text
    assert _reloaded(db, member.id).updated_by == member.id

    assert _assert_event(db, "user_updated", owner, member.id).actor_user_id == owner.id
    assert _assert_event(db, "password_changed", member, member.id).actor_user_id == member.id


# ---- sem sessão: 401 e nada é gravado ----

MUTATIONS = [
    ("POST", "/api/users", {"name": "X", "email": "x@teste.local", "role": "membro",
                            "provisionalPassword": PROVISIONAL}),
    ("PATCH", f"/api/users/{TARGET}", {"name": "Outro nome"}),
    ("POST", f"/api/users/{TARGET}/password", {"provisionalPassword": PROVISIONAL}),
    ("POST", f"/api/users/{TARGET}/verification", None),
    ("POST", "/api/auth/password/change", {"currentPassword": PW, "newPassword": NEW_PW}),
]
IDS = [f"{m} {p}" for m, p, _ in MUTATIONS]


def _counts(db: Session) -> tuple[int, int]:
    db.expire_all()
    return (db.scalar(select(func.count()).select_from(User)),
            db.scalar(select(func.count()).select_from(SecurityEvent)))


@pytest.mark.parametrize("auth", [None, "Bearer token-invalido", "Basic abc"],
                         ids=["sem-header", "bearer-invalido", "outro-esquema"])
@pytest.mark.parametrize(("method", "path", "body"), MUTATIONS, ids=IDS)
def test_mutacao_sem_sessao_da_401_e_nao_grava_nada(
    client: TestClient, db: Session, make_user, email_sender,
    method: str, path: str, body: dict | None, auth: str | None,
) -> None:
    target = make_user(verified=False, name="Alvo")
    before = _counts(db)

    headers = {"Authorization": auth} if auth else None
    r = client.request(method, path.replace(TARGET, str(target.id)), json=body, headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"

    assert _counts(db) == before
    unchanged = _reloaded(db, target.id)
    assert unchanged.name == "Alvo"
    assert unchanged.updated_by is None
    assert email_sender.outbox == []


# ---- varredura de details em um ciclo com todos os tipos de evento ----

def test_details_de_todos_os_eventos_sem_senha_token_ou_hash(
    client: TestClient, db: Session, owner: User, owner_headers, make_user, login, email_sender
) -> None:
    """Passa por todas as rotas que gravam eventos; a fixture autouse varre o resultado."""
    client.post("/api/auth/login", json={"email": owner.email, "password": "senha-errada-000"})
    r = client.post("/api/users", headers=owner_headers, json={
        "name": "Ciclo", "email": "ciclo@teste.local", "role": "membro",
        "provisionalPassword": PROVISIONAL,
    })
    assert r.status_code == 200, r.text
    user_id = r.json()["user"]["id"]
    token = _verify_token(email_sender.outbox[-1])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    client.post("/api/auth/verify-email", json={"token": token})  # reuso: recusado

    for body in ({"name": "Ciclo 2"}, {"role": "dono"}, {"role": "membro"},
                 {"isActive": False}, {"isActive": True}, {"email": "ciclo2@teste.local"}):
        r = client.patch(f"/api/users/{user_id}", headers=owner_headers, json=body)
        assert r.status_code == 200, (body, r.text)
    assert client.post(f"/api/users/{user_id}/verification",
                       headers=owner_headers).status_code == 200
    assert client.post(f"/api/users/{user_id}/password", headers=owner_headers,
                       json={"provisionalPassword": PROVISIONAL}).status_code == 200
    token = _verify_token(email_sender.outbox[-1])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200

    headers = login(client, "ciclo2@teste.local", PROVISIONAL)
    client.post("/api/auth/password/change", headers=headers,
                json={"currentPassword": "senha-errada-000", "newPassword": NEW_PW})
    r = client.post("/api/auth/password/change", headers=headers,
                    json={"currentPassword": PROVISIONAL, "newPassword": NEW_PW})
    assert r.status_code == 200, r.text
    client.post("/api/auth/verify-email/resend", json={"email": "ciclo2@teste.local"})
    client.post("/api/auth/logout", headers=headers)

    types = {e.type for e in db.scalars(select(SecurityEvent))}
    assert {"login_failed", "login_succeeded", "user_created", "email_verification_sent",
            "email_verified", "user_updated", "role_changed", "user_deactivated",
            "user_reactivated", "email_changed", "password_set_by_owner", "password_changed",
            "logout"} <= types
