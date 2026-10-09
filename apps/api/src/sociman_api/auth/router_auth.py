"""Rotas de sessão: login, renovação, logout, `me`, verificação de e-mail, troca e recuperação de
senha e a config pública (contracts/http-api.md)."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from sociman_api.auth import service, tokens
from sociman_api.auth.deps import CurrentUser, bearer_token
from sociman_api.auth.email import EmailSender, get_email_sender
from sociman_api.auth.schemas import (
    AppConfig,
    AuthSession,
    ChangePasswordIn,
    ForgotIn,
    LoginIn,
    Ok,
    ResendIn,
    ResetIn,
    User,
    UserOut,
    VerifyIn,
)
from sociman_api.config import get_settings
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope, error_response

router = APIRouter(prefix="/api")

REFRESH_COOKIE = "sociman_rt"
REFRESH_PATH = "/api/auth/refresh"

Db = DbSession
Sender = Annotated[EmailSender, Depends(get_email_sender)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- cookie de renovação (research.md R5) ----

def set_refresh_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(REFRESH_COOKIE, token, max_age=max_age, path=REFRESH_PATH,
                        secure=True, httponly=True, samesite="strict")


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, secure=True, httponly=True,
                           samesite="strict")


# ---- rotas ----

@router.get("/config", operation_id="app_config", response_model=AppConfig)
def app_config() -> AppConfig:
    settings = get_settings()
    return AppConfig(password_min_length=settings.password_min_length,
                     password_max_length=settings.password_max_length)


@router.post("/auth/login", operation_id="auth_login", response_model=AuthSession,
             responses=_errors(400, 401, 403, 429))
def login(body: LoginIn, request: Request, response: Response, db: Db) -> AuthSession:
    user, access, refresh_token, fam = service.login(db, body.email, body.password, request)
    set_refresh_cookie(response, refresh_token, tokens.remaining_ttl(fam))
    return AuthSession(access_token=access, user=User.model_validate(user))


@router.post("/auth/refresh", operation_id="auth_refresh", response_model=AuthSession,
             responses=_errors(401))
def refresh(request: Request, response: Response, db: Db):
    # Cookie lido à mão: como parâmetro, entraria no OpenAPI e no client gerado.
    presented = request.cookies.get(REFRESH_COOKIE)
    try:
        if not presented:
            raise ApiError(401, "invalid_token", "Sessão ausente")
        user, access, refresh_token, remaining = service.refresh(db, presented, request)
    except ApiError as exc:
        # O handler global criaria outra resposta sem o Set-Cookie que apaga o cookie.
        failed = error_response(exc.status, exc.code, exc.message, exc.headers)
        clear_refresh_cookie(failed)
        return failed
    set_refresh_cookie(response, refresh_token, remaining)
    return AuthSession(access_token=access, user=User.model_validate(user))


@router.post("/auth/logout", operation_id="auth_logout", response_model=Ok)
def logout(request: Request, response: Response, db: Db) -> Ok:
    service.logout(db, bearer_token(request), request)
    clear_refresh_cookie(response)
    return Ok()


@router.get("/auth/me", operation_id="auth_me", response_model=UserOut, responses=_errors(401))
def me(actor: CurrentUser) -> UserOut:
    return UserOut(user=User.model_validate(actor.user))


@router.post("/auth/verify-email", operation_id="auth_verify_email", response_model=Ok,
             responses=_errors(400, 429))
def verify_email(body: VerifyIn, request: Request, db: Db) -> Ok:
    service.verify_email(db, body.token, request)
    return Ok()


@router.post("/auth/verify-email/resend", operation_id="auth_resend_verification",
             response_model=Ok, responses=_errors(400, 429))
def resend_verification(body: ResendIn, request: Request, db: Db, sender: Sender,
                        background: BackgroundTasks) -> Ok:
    mail = service.resend_verification(db, body.email, request)
    if mail is not None:  # envio depois da resposta: o tempo não revela se a conta existe
        background.add_task(sender.send, mail.to, mail.subject, mail.text, mail.html)
    return Ok()


@router.post("/auth/password/change", operation_id="auth_change_password",
             response_model=AuthSession, responses=_errors(400, 401, 429))
def change_password(body: ChangePasswordIn, request: Request, actor: CurrentUser,
                    db: Db) -> AuthSession:
    # Isenta da troca obrigatória (CurrentUser, não RequireUser): é a própria troca (FR-012a).
    user, access = service.change_password(db, actor, body.current_password, body.new_password,
                                           request)
    return AuthSession(access_token=access, user=User.model_validate(user))


@router.post("/auth/password/forgot", operation_id="auth_forgot_password", response_model=Ok,
             responses=_errors(400, 429))
def forgot_password(body: ForgotIn, request: Request, db: Db, sender: Sender,
                    background: BackgroundTasks) -> Ok:
    mail = service.request_password_reset(db, body.email, request)
    if mail is not None:  # envio depois da resposta: o tempo não revela se a conta existe
        background.add_task(sender.send, mail.to, mail.subject, mail.text, mail.html)
    return Ok()


@router.post("/auth/password/reset", operation_id="auth_reset_password", response_model=Ok,
             responses=_errors(400, 429))
def reset_password(body: ResetIn, request: Request, db: Db) -> Ok:
    service.reset_password(db, body.token, body.new_password, request)
    return Ok()
