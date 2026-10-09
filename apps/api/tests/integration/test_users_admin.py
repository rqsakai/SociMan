"""Gestão de usuários pelo dono (T036, contracts/http-api.md "Só dono")."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.auth.models import SecurityEvent, User
from sociman_api.auth.passwords import verify_password

PW = "senha-forte-123"
PROVISIONAL = "provisoria-forte-456"


@pytest.fixture
def owner_headers(make_user, login, client: TestClient) -> tuple[User, dict[str, str]]:
    owner = make_user(role="dono", email="dono@teste.local")
    return owner, login(client, owner.email, PW)


def _events(db: Session, type_: str) -> list[SecurityEvent]:
    db.expire_all()
    return list(db.scalars(select(SecurityEvent).where(SecurityEvent.type == type_)))


def _reload(db: Session, user_id) -> User:
    db.expire_all()
    return db.get(User, user_id)


def _create(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    body = {"name": "Membro Novo", "email": "Novo@Teste.Local ", "role": "membro",
            "provisionalPassword": PROVISIONAL, **overrides}
    r = client.post("/api/users", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---- criar ----

def test_criar_usuario_exige_troca_e_verificacao_e_envia_email(
    client: TestClient, db: Session, owner_headers, outbox: list[dict]
) -> None:
    owner, headers = owner_headers
    body = _create(client, headers)

    user = body["user"]
    assert body["emailSent"] is True
    assert user["email"] == "novo@teste.local"
    assert user["role"] == "membro"
    assert user["mustChangePassword"] is True
    assert user["emailVerified"] is False
    assert user["isActive"] is True

    assert [m["to"] for m in outbox] == ["novo@teste.local"]
    assert "verify-email?token=" in outbox[0]["text"]

    row = _reload(db, user["id"])
    assert row.created_by == owner.id and row.updated_by == owner.id
    assert verify_password(PROVISIONAL, row.password_hash)

    [created] = _events(db, "user_created")
    assert created.actor_user_id == owner.id
    assert "password" not in str(created.details).lower()
    assert _events(db, "email_verification_sent")


def test_criar_com_email_duplicado_da_409(
    client: TestClient, make_user, owner_headers, outbox
) -> None:
    _, headers = owner_headers
    make_user(email="existe@teste.local", active=False)
    r = client.post("/api/users", headers=headers, json={
        "name": "X", "email": " EXISTE@teste.local", "role": "membro",
        "provisionalPassword": PROVISIONAL,
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_in_use"
    assert outbox == []


def test_criar_com_senha_fraca_da_400(client: TestClient, owner_headers, outbox) -> None:
    _, headers = owner_headers
    r = client.post("/api/users", headers=headers, json={
        "name": "X", "email": "x@teste.local", "role": "membro",
        "provisionalPassword": "12345678",
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


def test_falha_de_smtp_cria_mesmo_assim(
    client: TestClient, db: Session, owner_headers, email_sender
) -> None:
    _, headers = owner_headers
    email_sender.fail = True
    body = _create(client, headers)
    assert body["emailSent"] is False
    assert _reload(db, body["user"]["id"]) is not None


def test_listar_inclui_inativos(client: TestClient, make_user, owner_headers) -> None:
    _, headers = owner_headers
    inactive = make_user(active=False)
    r = client.get("/api/users", headers=headers)
    assert r.status_code == 200
    items = {u["id"]: u for u in r.json()["items"]}
    assert items[str(inactive.id)]["isActive"] is False
    assert len(items) == 2


# ---- editar ----

def test_trocar_email_zera_verificacao_reenvia_e_revoga_sessoes(
    client: TestClient, db: Session, make_user, login, owner_headers, outbox
) -> None:
    owner, headers = owner_headers
    member = make_user(email="antes@teste.local")
    member_headers = login(client, member.email, PW)

    r = client.patch(f"/api/users/{member.id}", headers=headers,
                     json={"email": "Depois@Teste.Local"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["emailSent"] is True
    assert body["user"]["email"] == "depois@teste.local"
    assert body["user"]["emailVerified"] is False
    assert [m["to"] for m in outbox] == ["depois@teste.local"]

    assert client.get("/api/auth/me", headers=member_headers).status_code == 401
    assert _reload(db, member.id).updated_by == owner.id
    [changed] = _events(db, "email_changed")
    assert changed.details == {"before": {"email": "antes@teste.local"},
                               "after": {"email": "depois@teste.local"}}


def test_trocar_email_para_um_existente_da_409(
    client: TestClient, db: Session, make_user, owner_headers
) -> None:
    _, headers = owner_headers
    member = make_user(name="Antes")
    other = make_user()
    r = client.patch(f"/api/users/{member.id}", headers=headers,
                     json={"name": "Depois", "email": other.email.upper()})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_in_use"
    assert _reload(db, member.id).name == "Antes"  # nada fica pela metade


def test_patch_so_do_nome_nao_envia_email(
    client: TestClient, db: Session, make_user, owner_headers, outbox
) -> None:
    _, headers = owner_headers
    member = make_user(name="Antes")
    r = client.patch(f"/api/users/{member.id}", headers=headers, json={"name": " Depois "})
    assert r.status_code == 200
    assert r.json()["emailSent"] is None
    assert r.json()["user"]["name"] == "Depois"
    assert outbox == []
    [event] = _events(db, "user_updated")
    assert event.details == {"before": {"name": "Antes"}, "after": {"name": "Depois"}}


def test_mudar_papel_grava_role_changed(
    client: TestClient, db: Session, make_user, owner_headers
) -> None:
    _, headers = owner_headers
    member = make_user()
    r = client.patch(f"/api/users/{member.id}", headers=headers, json={"role": "dono"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "dono"
    [event] = _events(db, "role_changed")
    assert event.details == {"before": {"role": "membro"}, "after": {"role": "dono"}}


def test_desativar_revoga_sessoes_e_reativar_nao_as_devolve(
    client: TestClient, db: Session, make_user, login, owner_headers
) -> None:
    _, headers = owner_headers
    member = make_user()
    member_headers = login(client, member.email, PW)

    r = client.patch(f"/api/users/{member.id}", headers=headers, json={"isActive": False})
    assert r.status_code == 200
    assert r.json()["user"]["isActive"] is False
    assert client.get("/api/auth/me", headers=member_headers).status_code == 401

    r = client.patch(f"/api/users/{member.id}", headers=headers, json={"isActive": True})
    assert r.status_code == 200
    # Reativado, mas o token antigo continua morto: a família foi revogada no Redis.
    assert client.get("/api/auth/me", headers=member_headers).status_code == 401
    assert _events(db, "user_deactivated") and _events(db, "user_reactivated")


@pytest.mark.parametrize("change", [{"role": "membro"}, {"isActive": False}])
def test_ultimo_dono_ativo_nao_pode_sair(
    client: TestClient, db: Session, make_user, owner_headers, change: dict
) -> None:
    owner, headers = owner_headers
    make_user(role="dono", active=False)  # dono inativo não conta
    r = client.patch(f"/api/users/{owner.id}", headers=headers, json=change)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "last_owner"
    row = _reload(db, owner.id)
    assert row.role.value == "dono" and row.is_active

    denied = db.scalars(select(SecurityEvent).where(SecurityEvent.outcome == "denied")).all()
    assert [e.details for e in denied] == [{"reason": "last_owner"}]


def test_com_outro_dono_ativo_pode_rebaixar(
    client: TestClient, make_user, owner_headers
) -> None:
    owner, headers = owner_headers
    make_user(role="dono")
    r = client.patch(f"/api/users/{owner.id}", headers=headers, json={"role": "membro"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "membro"


def test_patch_de_usuario_inexistente_da_404(client: TestClient, owner_headers) -> None:
    _, headers = owner_headers
    r = client.patch("/api/users/00000000-0000-4000-8000-000000000000", headers=headers,
                     json={"name": "X"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


# ---- senha provisória ----

def test_senha_provisoria_revoga_sessoes_e_liga_troca(
    client: TestClient, db: Session, make_user, login, owner_headers
) -> None:
    owner, headers = owner_headers
    member = make_user()
    member_headers = login(client, member.email, PW)

    r = client.post(f"/api/users/{member.id}/password", headers=headers,
                    json={"provisionalPassword": PROVISIONAL})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["mustChangePassword"] is True
    assert client.get("/api/auth/me", headers=member_headers).status_code == 401

    row = _reload(db, member.id)
    assert verify_password(PROVISIONAL, row.password_hash)
    assert row.updated_by == owner.id
    [event] = _events(db, "password_set_by_owner")
    assert event.actor_user_id == owner.id
    assert event.details == {}


def test_senha_provisoria_fraca_da_400(client: TestClient, make_user, owner_headers) -> None:
    _, headers = owner_headers
    member = make_user()
    r = client.post(f"/api/users/{member.id}/password", headers=headers,
                    json={"provisionalPassword": "password"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


# ---- reenviar verificação ----

def test_reenviar_verificacao(
    client: TestClient, make_user, owner_headers, outbox
) -> None:
    _, headers = owner_headers
    pending = make_user(verified=False)
    r = client.post(f"/api/users/{pending.id}/verification", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"emailSent": True}
    assert [m["to"] for m in outbox] == [pending.email]


def test_reenviar_para_ja_verificado_da_409(
    client: TestClient, make_user, owner_headers, outbox
) -> None:
    _, headers = owner_headers
    verified = make_user()
    r = client.post(f"/api/users/{verified.id}/verification", headers=headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
    assert outbox == []


def test_fluxo_do_membro_criado_ate_o_login(
    client: TestClient, owner_headers, outbox
) -> None:
    """Criado pelo dono, o membro não entra antes de verificar (403 email_not_verified)."""
    _, headers = owner_headers
    _create(client, headers)
    r = client.post("/api/auth/login",
                    json={"email": "novo@teste.local", "password": PROVISIONAL})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "email_not_verified"
