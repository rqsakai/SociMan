"""Dependências de autenticação: quem é o ator da requisição (FR-016) e o que ele pode fazer.

- `current_user`: Bearer válido + família viva no Redis + usuário ativo no banco (FR-014 na hora).
- `require_user`: idem, mas bloqueia quem ainda precisa trocar a senha provisória (FR-012a).
- `require_owner`: idem, e só para o papel `dono` (FR-010).
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from sociman_api.auth import tokens
from sociman_api.auth.models import User, UserRole
from sociman_api.db import DbSession
from sociman_api.errors import ApiError


@dataclass(frozen=True)
class Actor:
    """Autor de uma ação. `mcp_client` fica reservado para a spec 009."""

    kind: str  # user | anonymous | system:cli
    user_id: uuid.UUID | None = None
    user: User | None = None
    fam: str | None = None


ANONYMOUS = Actor(kind="anonymous")
CLI = Actor(kind="system:cli")


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _unauthorized() -> ApiError:
    return ApiError(401, "unauthorized", "Não autenticado")


def _actor_from_request(request: Request, db: Session) -> Actor | None:
    token = bearer_token(request)
    if not token:
        return None
    claims = tokens.decode_access(token)
    if not claims:
        return None
    fam = claims.get("fam")
    if not fam or not tokens.family_alive(fam):
        return None
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return Actor(kind="user", user_id=user.id, user=user, fam=fam)


def get_actor(request: Request, db: DbSession) -> Actor:
    """Ator opcional (rotas públicas): usuário se houver sessão válida, senão anônimo."""
    return _actor_from_request(request, db) or ANONYMOUS


def current_user(request: Request, db: DbSession) -> Actor:
    actor = _actor_from_request(request, db)
    if actor is None:
        raise _unauthorized()
    return actor


def require_user(actor: Annotated[Actor, Depends(current_user)]) -> Actor:
    """Rotas comuns: exige sessão e senha provisória já trocada."""
    if actor.user is not None and actor.user.must_change_password:
        raise ApiError(403, "password_change_required",
                       "Troque a senha provisória para continuar")
    return actor


def require_owner(actor: Annotated[Actor, Depends(require_user)]) -> Actor:
    if actor.user is None or actor.user.role != UserRole.dono:
        raise ApiError(403, "forbidden", "Sem permissão")
    return actor


CurrentUser = Annotated[Actor, Depends(current_user)]
RequireUser = Annotated[Actor, Depends(require_user)]
RequireOwner = Annotated[Actor, Depends(require_owner)]
OptionalActor = Annotated[Actor, Depends(get_actor)]
