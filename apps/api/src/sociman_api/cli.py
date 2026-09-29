"""CLI `sociman` (research.md R10, FR-011): instalação e emergência, dentro do container `api`.

- `create-owner`: cria o primeiro dono, já verificado e sem troca obrigatória de senha;
- `set-password`: redefine a senha de alguém e encerra as sessões dele;
- `reset-db`: zera banco e Redis para o e2e (nunca em produção);
- `worker`: processa a fila de cortes (spec 004, serviço `worker` do compose);
- `agendador`: tarefas periódicas da spec 006 (serviço `agendador` do compose).

Cada comando faz o próprio commit e grava o evento com o autor `system:cli`.
"""

import sys
from datetime import UTC, datetime
from typing import Annotated, NoReturn

import typer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from sociman_api.auth.deps import CLI
from sociman_api.auth.events import record_event
from sociman_api.auth.models import User, UserRole
from sociman_api.auth.passwords import hash_password, validate_password_policy
from sociman_api.auth.tokens import revoke_all_for_user
from sociman_api.config import get_settings
from sociman_api.db import get_engine, get_sessionmaker
from sociman_api.errors import ApiError
from sociman_api.redis import get_redis

app = typer.Typer(help="Administração do SociMan (instalação e emergência).", no_args_is_help=True)

PasswordStdin = Annotated[
    bool,
    typer.Option("--password-stdin", help="Lê a senha da primeira linha do stdin (sem prompt)."),
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Erro: {message}", err=True)
    raise typer.Exit(1)


def _normalize_email(email: str) -> str:
    email = email.strip().lower()
    if "@" not in email:
        _fail("e-mail inválido")
    return email


def _read_password(from_stdin: bool) -> str:
    """Senha validada pela política: prompt oculto (duas vezes) ou uma linha do stdin."""
    if from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = typer.prompt("Senha", hide_input=True, confirmation_prompt=True)
    try:
        validate_password_policy(password)
    except ApiError as e:
        _fail(e.message)
    return password


def _find_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


@app.command("create-owner")
def create_owner(
    email: Annotated[str, typer.Option(help="E-mail do dono.")],
    name: Annotated[str, typer.Option(help="Nome do dono.")],
    force: Annotated[bool, typer.Option(help="Cria mesmo que já exista um dono ativo.")] = False,
    password_stdin: PasswordStdin = False,
) -> None:
    """Cria um dono verificado, sem troca obrigatória de senha."""
    email = _normalize_email(email)
    name = name.strip()
    if not name:
        _fail("o nome não pode ser vazio")

    with get_sessionmaker()() as db:
        has_owner = db.scalar(
            select(User.id).where(User.role == UserRole.dono, User.is_active.is_(True)).limit(1)
        )
        if has_owner is not None and not force:
            _fail("já existe um dono ativo (use --force para criar outro)")
        if _find_by_email(db, email) is not None:
            _fail(f"já existe um usuário com o e-mail {email}")

        password = _read_password(password_stdin)
        now = datetime.now(UTC)
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.dono,
            is_active=True,
            email_verified_at=now,
            must_change_password=False,
            password_changed_at=now,
            created_by=None,
        )
        db.add(user)
        db.flush()
        record_event(db, "user_created", "ok", CLI, subject_user_id=user.id,
                     details={"role": UserRole.dono.value, "via": "cli"})
        db.commit()
        typer.echo(f"Dono criado: {user.email} (id {user.id})")


@app.command("set-password")
def set_password(
    email: Annotated[str, typer.Option(help="E-mail do usuário.")],
    password_stdin: PasswordStdin = False,
) -> None:
    """Redefine a senha (emergência) e encerra todas as sessões do usuário."""
    email = _normalize_email(email)
    with get_sessionmaker()() as db:
        user = _find_by_email(db, email)
        if user is None:
            _fail(f"nenhum usuário com o e-mail {email}")

        password = _read_password(password_stdin)
        user.password_hash = hash_password(password)
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        record_event(db, "password_set_by_owner", "ok", CLI, subject_user_id=user.id,
                     details={"via": "cli"})
        db.commit()
        revoke_all_for_user(str(user.id))
        typer.echo(f"Senha redefinida para {user.email}; sessões encerradas.")


@app.command("reset-db")
def reset_db(
    yes: Annotated[bool, typer.Option("--yes", help="Confirma que quer apagar tudo.")] = False,
) -> None:
    """Apaga usuários, tokens e eventos e limpa o Redis (só fora de produção; usado pelo e2e)."""
    if get_settings().env == "production":
        _fail("reset-db é proibido com ENV=production")
    if not yes:
        _fail("isso apaga todos os dados; confirme com --yes")
    with get_engine().begin() as conn:
        conn.execute(
            text("TRUNCATE users, one_time_tokens, security_events RESTART IDENTITY CASCADE")
        )
    get_redis().flushdb()
    typer.echo("Banco e Redis zerados.")


@app.command("worker")
def worker() -> None:
    """Processa a fila de cortes, um por vez, até receber SIGTERM ou SIGINT."""
    from sociman_api.cortes.worker import main

    main()


@app.command("agendador")
def agendador() -> None:
    """Roda as trilhas periódicas da spec 006 (sync, openshorts, importacao, lembretes)."""
    from sociman_api.agendador import main

    main()


if __name__ == "__main__":
    app()
