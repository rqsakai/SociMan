"""CLI `sociman` (research.md R10, FR-011): instalação e emergência, dentro do container `api`.

- `create-owner`: cria o primeiro dono, já verificado e sem troca obrigatória de senha;
- `set-password`: redefine a senha de alguém e encerra as sessões dele;
- `reset-db`: zera banco e Redis para o e2e (nunca em produção);
- `worker`: processa a fila de cortes (spec 004, serviço `worker` do compose);
- `agendador`: tarefas periódicas da spec 006 (serviço `agendador` do compose);
- `tokens recifrar`: regrava as credenciais da publicação com a chave atual (spec 015, R4);
- `gerador`: a fila da geração local (spec 021, serviço `gerador` do compose);
- `geracoes limpar [--dry-run]`: a limpeza de 90 dias das opções não escolhidas (spec 021, R12).

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
    # O CASCADE trava quase todas as tabelas; o agendador (trilhas de publicação e métricas) pode
    # estar lendo algumas delas e o Postgres acusa deadlock. A transação perdedora já foi desfeita,
    # então repetir é seguro.
    import time

    from sqlalchemy.exc import OperationalError

    for tentativa in range(1, 6):
        try:
            with get_engine().begin() as conn:
                conn.execute(
                    text("TRUNCATE users, one_time_tokens, security_events RESTART IDENTITY CASCADE")
                )
            break
        except OperationalError as exc:
            if "deadlock detected" not in str(exc) or tentativa == 5:
                raise
            time.sleep(0.5 * tentativa)
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


@app.command("gerador")
def gerador() -> None:
    """Roda a fila da geração local (spec 021): a linha GPU e a linha Claude."""
    from sociman_api.geracao.gerador import main

    main()


geracoes_app = typer.Typer(help="Geração local (spec 021).", no_args_is_help=True)
app.add_typer(geracoes_app, name="geracoes")


@geracoes_app.command("limpar")
def geracoes_limpar(
    dry_run: Annotated[bool, typer.Option("--dry-run",
                                          help="Só lista o que seria apagado; não apaga.")] = False,
) -> None:
    """Apaga as opções não escolhidas das gerações terminadas há mais de 90 dias (exceção 1 da
    constitution 4.3.0). Imprime só contagens."""
    from sociman_api.agendador import _registrar_modelos
    from sociman_api.geracao import limpeza

    _registrar_modelos()
    with get_sessionmaker()() as db:
        r = limpeza.limpar(db, CLI, dry_run=dry_run)
    acao = "seriam apagadas" if dry_run else "apagadas"
    typer.echo(f"Gerações: {r.geracoes}; opções {acao}: {r.candidatos} ({r.imagens} imagens, "
               f"{r.audios} áudios, {r.bytes} bytes); mantidas por estarem em uso: {r.mantidos}.")


tokens_app = typer.Typer(help="Credenciais da publicação (spec 015).", no_args_is_help=True)
app.add_typer(tokens_app, name="tokens")


@tokens_app.command("recifrar")
def tokens_recifrar() -> None:
    """Regrava com SOCIMAN_TOKENS_KEY todas as credenciais (e links de envio em andamento)
    cifradas com a chave anterior. Imprime só contagens, nunca valores."""
    from sociman_api.agendador import _registrar_modelos
    from sociman_api.publicacao import cifra
    from sociman_api.publicacao.models import ConexaoCredencial, Tentativa

    _registrar_modelos()
    try:
        atual = cifra.key_id_atual()
    except cifra.CifraErro as e:
        _fail(str(e))
    regravadas = iguais = links = 0
    with get_sessionmaker()() as db:
        try:
            for cred in db.scalars(select(ConexaoCredencial).with_for_update()):
                if cred.key_id == atual:
                    iguais += 1
                    continue
                for campo in ("access", "refresh"):
                    coluna = f"{campo}_cifrado"
                    aad = cifra.aad(cred.conexao_id, campo)
                    texto = cifra.decifrar(getattr(cred, coluna), aad, cred.key_id)
                    setattr(cred, coluna, cifra.cifrar(texto, aad)[0])
                cred.key_id = atual
                regravadas += 1
            for t in db.scalars(select(Tentativa).where(Tentativa.upload_url_cifrado.is_not(None))
                                .with_for_update()):
                aad = cifra.aad(t.id, "upload")
                t.upload_url_cifrado = cifra.cifrar(cifra.decifrar(t.upload_url_cifrado, aad),
                                                    aad)[0]
                links += 1
        except cifra.CifraErro as e:
            db.rollback()
            _fail(f"nada foi regravado: {e}")
        db.commit()
    typer.echo(f"Credenciais regravadas: {regravadas}; já na chave atual: {iguais}; "
               f"links de envio regravados: {links}.")


if __name__ == "__main__":
    app()
