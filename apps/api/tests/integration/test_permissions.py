"""Permissões (T037, SC-003): rotas só-dono e a troca obrigatória da senha provisória."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.auth.models import User

PW = "senha-forte-123"
TARGET = "{target}"

# (método, rota, corpo). `{target}` vira o id de um usuário existente.
OWNER_ONLY = [
    ("GET", "/api/users", None),
    ("POST", "/api/users", {"name": "X", "email": "x@teste.local", "role": "membro",
                            "provisionalPassword": "provisoria-forte-456"}),
    ("PATCH", f"/api/users/{TARGET}", {"name": "Outro nome"}),
    ("POST", f"/api/users/{TARGET}/password", {"provisionalPassword": "provisoria-forte-456"}),
    ("POST", f"/api/users/{TARGET}/verification", None),
    ("GET", "/api/security-events", None),
]
IDS = [f"{m} {p}" for m, p, _ in OWNER_ONLY]


def _call(client: TestClient, method: str, path: str, body: dict | None,
          headers: dict[str, str] | None = None, target: str = ""):
    return client.request(method, path.replace(TARGET, target), json=body, headers=headers)


@pytest.mark.parametrize(("method", "path", "body"), OWNER_ONLY, ids=IDS)
def test_membro_recebe_403_forbidden(
    client: TestClient, db: Session, make_user, login, email_sender,
    method: str, path: str, body: dict | None,
) -> None:
    target = make_user(verified=False, name="Alvo")
    member = make_user()
    headers = login(client, member.email, PW)

    r = _call(client, method, path, body, headers, str(target.id))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"

    # Nada foi alterado.
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(User)) == 2
    assert db.get(User, target.id).name == "Alvo"
    assert email_sender.outbox == []


@pytest.mark.parametrize(("method", "path", "body"), OWNER_ONLY, ids=IDS)
def test_sem_sessao_recebe_401(
    client: TestClient, make_user, method: str, path: str, body: dict | None
) -> None:
    target = make_user()
    r = _call(client, method, path, body, target=str(target.id))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path", "body"), OWNER_ONLY, ids=IDS)
def test_dono_com_troca_pendente_recebe_password_change_required(
    client: TestClient, make_user, login, email_sender,
    method: str, path: str, body: dict | None,
) -> None:
    target = make_user(verified=False)
    owner = make_user(role="dono", must_change=True)
    headers = login(client, owner.email, PW)

    r = _call(client, method, path, body, headers, str(target.id))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "password_change_required"


def test_troca_pendente_ainda_acessa_me_e_logout(
    client: TestClient, make_user, login
) -> None:
    member = make_user(must_change=True)
    headers = login(client, member.email, PW)

    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["user"]["mustChangePassword"] is True
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
