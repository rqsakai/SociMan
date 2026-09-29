from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from sociman_api.auth.email import MemoryEmailSender, reset_email, verification_email
from sociman_api.auth.schemas import (
    AuthSession,
    CreateUserIn,
    LoginIn,
    SecurityEventPage,
    UpdateUserIn,
    User,
)

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _orm_user(verified_at=None):
    return SimpleNamespace(
        id=uuid4(), name="Ana", email="ana@x.com", role="dono", is_active=True,
        email_verified_at=verified_at, must_change_password=False,
        created_at=NOW, updated_at=NOW, password_hash="nunca-sai",
    )


def test_email_normalizado():
    assert LoginIn(email="  Ana@Exemplo.COM ", password="x").email == "ana@exemplo.com"


@pytest.mark.parametrize("email", ["", "ana", "ana@", "ana@x", "a b@x.com"])
def test_email_invalido(email):
    with pytest.raises(ValidationError):
        LoginIn(email=email, password="x")


def test_senha_acima_do_teto():
    with pytest.raises(ValidationError):
        LoginIn(email="a@x.com", password="x" * 129)


def test_entrada_aceita_camel_e_snake():
    camel = CreateUserIn.model_validate(
        {"name": " Bia ", "email": "B@x.com", "role": "membro", "provisionalPassword": "p"})
    snake = CreateUserIn(name="Bia", email="b@x.com", role="membro", provisional_password="p")
    assert camel == snake
    assert camel.name == "Bia"
    with pytest.raises(ValidationError):
        CreateUserIn(name="Bia", email="b@x.com", role="admin", provisional_password="p")


def test_update_parcial():
    body = UpdateUserIn.model_validate({"isActive": False})
    assert body.model_dump(exclude_unset=True) == {"is_active": False}


def test_user_de_objeto_orm():
    u = User.model_validate(_orm_user())
    assert u.email_verified is False
    assert User.model_validate(_orm_user(verified_at=NOW)).email_verified is True


def test_saida_em_camel_case():
    out = AuthSession(access_token="t", user=User.model_validate(_orm_user(NOW)))
    data = out.model_dump(mode="json", by_alias=True)
    assert data["accessToken"] == "t"
    assert set(data["user"]) == {
        "id", "name", "email", "role", "isActive", "emailVerified", "mustChangePassword",
        "createdAt", "updatedAt",
    }
    page = SecurityEventPage(items=[], next_cursor=None).model_dump(by_alias=True)
    assert page == {"items": [], "nextCursor": None}


def test_templates_de_email():
    subject, text, html = verification_email("<Ana>", "a+b/c=")
    assert subject == "Confirme seu e-mail no SociMan"
    assert "/verify-email?token=a%2Bb%2Fc%3D" in text
    assert "&lt;Ana&gt;" in html and "<Ana>" not in html
    subject, text, _ = reset_email("Ana", "tok")
    assert subject == "Redefinir sua senha do SociMan"
    assert "/reset-password?token=tok" in text


def test_memory_sender():
    sender = MemoryEmailSender()
    assert sender.send("a@x.com", "s", "t", "h") is True
    assert sender.outbox == [{"to": "a@x.com", "subject": "s", "text": "t", "html": "h"}]
    sender.fail = True
    assert sender.send("a@x.com", "s", "t", "h") is False
    assert len(sender.outbox) == 1
