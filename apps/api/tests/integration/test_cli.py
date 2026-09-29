"""CLI `sociman` (T028, research R10): create-owner, set-password e reset-db."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from sociman_api import cli
from sociman_api.auth import tokens
from sociman_api.auth.models import SecurityEvent, User, UserRole
from sociman_api.auth.passwords import verify_password
from sociman_api.config import get_settings

runner = CliRunner()
PW = "senha-do-dono-123"
NEW_PW = "outra-senha-forte-456"


def _prompt(pw: str) -> str:
    return f"{pw}\n{pw}\n"


def _create_owner(email: str = "Dono@Teste.Local ", *extra: str, pw: str = PW):
    return runner.invoke(
        cli.app, ["create-owner", "--email", email, "--name", "Dono", *extra], input=_prompt(pw)
    )


def _events(db: Session, type_: str) -> list[SecurityEvent]:
    return list(db.scalars(select(SecurityEvent).where(SecurityEvent.type == type_)))


def test_create_owner_cria_dono_verificado_com_evento(db: Session) -> None:
    r = _create_owner()
    assert r.exit_code == 0, r.output

    user = db.scalar(select(User).where(User.email == "dono@teste.local"))
    assert user is not None
    assert user.role == UserRole.dono
    assert user.is_active
    assert user.email_verified_at is not None
    assert user.must_change_password is False
    assert user.created_by is None
    assert verify_password(PW, user.password_hash)

    [event] = _events(db, "user_created")
    assert event.actor_kind == "system:cli"
    assert event.actor_user_id is None
    assert event.subject_user_id == user.id
    assert event.outcome == "ok"


def test_create_owner_aceita_senha_por_stdin(db: Session) -> None:
    r = runner.invoke(
        cli.app,
        ["create-owner", "--email", "e2e@teste.local", "--name", "E2E", "--password-stdin"],
        input=f"{PW}\n",
    )
    assert r.exit_code == 0, r.output
    user = db.scalar(select(User).where(User.email == "e2e@teste.local"))
    assert user is not None and verify_password(PW, user.password_hash)


def test_create_owner_segunda_vez_recusada_sem_force(db: Session) -> None:
    assert _create_owner().exit_code == 0

    r = _create_owner("outro@teste.local")
    assert r.exit_code == 1
    assert "dono ativo" in r.output
    assert db.scalar(select(func.count()).select_from(User)) == 1

    r = _create_owner("outro@teste.local", "--force")
    assert r.exit_code == 0, r.output
    assert db.scalar(select(func.count()).select_from(User)) == 2


def test_create_owner_recusa_email_existente(db: Session, make_user) -> None:
    make_user(email="membro@teste.local")
    r = _create_owner("MEMBRO@teste.local")
    assert r.exit_code == 1
    assert "já existe um usuário" in r.output


def test_create_owner_recusa_senha_fraca(db: Session) -> None:
    r = _create_owner(pw="curta")
    assert r.exit_code == 1
    assert "pelo menos 12" in r.output
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_set_password_troca_senha_e_revoga_sessoes(db: Session, make_user) -> None:
    user = make_user(email="alguem@teste.local", must_change=True)
    _, _, fam1 = tokens.create_family(str(user.id))
    _, _, fam2 = tokens.create_family(str(user.id))

    r = runner.invoke(cli.app, ["set-password", "--email", "Alguem@teste.local"],
                      input=_prompt(NEW_PW))
    assert r.exit_code == 0, r.output

    db.refresh(user)
    assert verify_password(NEW_PW, user.password_hash)
    assert user.must_change_password is False
    assert not tokens.family_alive(fam1)
    assert not tokens.family_alive(fam2)

    [event] = _events(db, "password_set_by_owner")
    assert event.actor_kind == "system:cli"
    assert event.subject_user_id == user.id
    assert event.details == {"via": "cli"}


def test_set_password_email_inexistente(db: Session) -> None:
    r = runner.invoke(cli.app, ["set-password", "--email", "ninguem@teste.local"],
                      input=_prompt(NEW_PW))
    assert r.exit_code == 1
    assert "nenhum usuário" in r.output


def test_reset_db_zera_banco_e_redis(db: Session, make_user) -> None:
    user = make_user()
    _, _, fam = tokens.create_family(str(user.id))

    r = runner.invoke(cli.app, ["reset-db", "--yes"])
    assert r.exit_code == 0, r.output
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert not tokens.family_alive(fam)


def test_reset_db_exige_yes(db: Session, make_user) -> None:
    make_user()
    r = runner.invoke(cli.app, ["reset-db"])
    assert r.exit_code == 1
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_reset_db_recusa_em_producao(
    db: Session, make_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user()
    prod = get_settings().model_copy(update={"env": "production"})
    monkeypatch.setattr(cli, "get_settings", lambda: prod)

    r = runner.invoke(cli.app, ["reset-db", "--yes"])
    assert r.exit_code == 1
    assert "production" in r.output
    assert db.scalar(select(func.count()).select_from(User)) == 1
