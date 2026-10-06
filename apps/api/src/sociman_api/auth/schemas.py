"""Modelos Pydantic do contrato (contracts/http-api.md). JSON em camelCase, Python em snake_case.

A política completa de senha (mínimo, igual à atual etc.) fica no service; aqui só o teto.
"""

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel

from sociman_api.errors import ErrorEnvelope

__all__ = [
    "AppConfig", "AuthSession", "ChangePasswordIn", "CreateUserIn", "EmailSentOut",
    "ErrorEnvelope", "ForgotIn", "LoginIn", "Ok", "Page", "ResendIn", "ResetIn",
    "SecurityEvent", "SecurityEventPage", "SetPasswordIn", "UpdateUserIn", "User", "UserOut",
    "UserWithEmailSent", "UsersList", "VerifyIn",
]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("e-mail inválido")
    return value


Email = Annotated[str, Field(max_length=254), AfterValidator(_normalize_email)]
Password = Annotated[str, Field(min_length=1, max_length=128)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Role = Literal["dono", "membro"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True,
                              from_attributes=True)


# ---- saídas ----

class User(CamelModel):
    id: UUID
    name: str
    email: str
    role: Role
    is_active: bool
    email_verified: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _from_orm(cls, data: Any) -> Any:
        # O ORM guarda email_verified_at (timestamp); o contrato expõe só o booleano.
        if isinstance(data, dict):
            if "email_verified_at" in data and "email_verified" not in data:
                data = {**data, "email_verified": data["email_verified_at"] is not None}
            return data
        if hasattr(data, "email_verified_at"):
            return {
                "id": data.id,
                "name": data.name,
                "email": data.email,
                "role": data.role,
                "is_active": data.is_active,
                "email_verified": data.email_verified_at is not None,
                "must_change_password": data.must_change_password,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


class AuthSession(CamelModel):
    access_token: str
    user: User


class UserOut(CamelModel):
    user: User


class UsersList(CamelModel):
    items: list[User]


class UserWithEmailSent(CamelModel):
    user: User
    email_sent: bool | None


class EmailSentOut(CamelModel):
    email_sent: bool


class Ok(CamelModel):
    ok: Literal[True] = True


class AppConfig(CamelModel):
    password_min_length: int
    password_max_length: int


class McpClienteRef(CamelModel):
    id: UUID
    nome: str


class SecurityEvent(CamelModel):
    id: int
    occurred_at: datetime
    type: str
    outcome: Literal["ok", "denied"]
    actor_kind: str
    actor_user_id: UUID | None
    actor_name: str | None
    actor_mcp_client: "McpClienteRef | None" = None  # spec 009: o agente autor do evento
    subject_user_id: UUID | None
    subject_name: str | None
    ip: str | None
    details: dict[str, Any]


class Page[T](CamelModel):
    items: list[T]
    next_cursor: str | None


class SecurityEventPage(Page[SecurityEvent]):
    pass


# ---- entradas ----

class LoginIn(CamelModel):
    email: Email
    password: Password


class ForgotIn(CamelModel):
    email: Email


class ResendIn(CamelModel):
    email: Email


class VerifyIn(CamelModel):
    token: Annotated[str, Field(min_length=1, max_length=512)]


class ResetIn(CamelModel):
    token: Annotated[str, Field(min_length=1, max_length=512)]
    new_password: Password


class ChangePasswordIn(CamelModel):
    current_password: Password
    new_password: Password


class CreateUserIn(CamelModel):
    name: Name
    email: Email
    role: Role
    provisional_password: Password


class UpdateUserIn(CamelModel):
    name: Name | None = None
    email: Email | None = None
    role: Role | None = None
    is_active: bool | None = None


class SetPasswordIn(CamelModel):
    provisional_password: Password
