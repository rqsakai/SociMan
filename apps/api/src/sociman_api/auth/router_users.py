"""Rotas só-dono de gestão de usuários (T042, contracts/http-api.md "Só dono")."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from sociman_api.auth import users_service
from sociman_api.auth.deps import RequireOwner
from sociman_api.auth.email import EmailSender, get_email_sender
from sociman_api.auth.schemas import (
    CreateUserIn,
    EmailSentOut,
    SetPasswordIn,
    UpdateUserIn,
    User,
    UserOut,
    UsersList,
    UserWithEmailSent,
)
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope

router = APIRouter(prefix="/api/users")

Db = DbSession
Sender = Annotated[EmailSender, Depends(get_email_sender)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("", operation_id="users_list", response_model=UsersList,
            responses=_errors(401, 403))
def list_users(actor: RequireOwner, db: Db) -> UsersList:
    return UsersList(items=[User.model_validate(u) for u in users_service.list_users(db)])


@router.post("", operation_id="users_create", response_model=UserWithEmailSent,
             responses=_errors(400, 401, 403, 409))
def create_user(body: CreateUserIn, actor: RequireOwner, request: Request, db: Db,
                sender: Sender) -> UserWithEmailSent:
    user, email_sent = users_service.create_user(db, actor, body, request, sender)
    return UserWithEmailSent(user=User.model_validate(user), email_sent=email_sent)


@router.patch("/{user_id}", operation_id="users_update", response_model=UserWithEmailSent,
              responses=_errors(400, 401, 403, 404, 409))
def update_user(user_id: UUID, body: UpdateUserIn, actor: RequireOwner, request: Request,
                db: Db, sender: Sender) -> UserWithEmailSent:
    user, email_sent = users_service.update_user(db, actor, user_id, body, request, sender)
    return UserWithEmailSent(user=User.model_validate(user), email_sent=email_sent)


@router.post("/{user_id}/password", operation_id="users_set_password", response_model=UserOut,
             responses=_errors(400, 401, 403, 404))
def set_password(user_id: UUID, body: SetPasswordIn, actor: RequireOwner, request: Request,
                 db: Db) -> UserOut:
    user = users_service.set_provisional_password(db, actor, user_id,
                                                  body.provisional_password, request)
    return UserOut(user=User.model_validate(user))


@router.post("/{user_id}/verification", operation_id="users_resend_verification",
             response_model=EmailSentOut, responses=_errors(401, 403, 404, 409))
def resend_verification(user_id: UUID, actor: RequireOwner, request: Request, db: Db,
                        sender: Sender) -> EmailSentOut:
    sent = users_service.resend_user_verification(db, actor, user_id, request, sender)
    return EmailSentOut(email_sent=sent)
