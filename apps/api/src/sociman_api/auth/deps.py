"""Dependências de autenticação: quem é o ator da requisição (FR-016) e o que ele pode fazer.

- `current_user`: Bearer válido + família viva no Redis + usuário ativo no banco (FR-014 na hora).
- `require_user`: idem, mas bloqueia quem ainda precisa trocar a senha provisória (FR-012a).
- `require_owner`: idem, e só para o papel `dono` (FR-010).
- `require_human_owner` (spec 015, research R15): dono **e** `actor.kind == "user"`. Qualquer
  outro ator (cliente MCP da 009, `system:*`, token de agente) recebe 403 `somente_humano` e
  deixa um evento de segurança `publicacao_recusada` (princípio I).
- `require_human` (spec 009): qualquer humano (`actor.kind == "user"`), com a mesma recusa.
- Bearer `smcp_…` (spec 009): o ator `mcp_client` vem do portão (`mcp/portao.py`, R5).
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from sociman_api.auth import tokens
from sociman_api.auth.events import record_event
from sociman_api.auth.models import User, UserRole
from sociman_api.db import DbSession, get_sessionmaker
from sociman_api.errors import ApiError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Actor:
    """Autor de uma ação. O `mcp_client` (spec 009) nunca tem `user`: lê como um membro."""

    kind: str  # user | anonymous | system:cli | system:publicacao | mcp_client (009)
    user_id: uuid.UUID | None = None
    user: User | None = None
    fam: str | None = None
    mcp_client_id: uuid.UUID | None = None  # spec 009: o cliente MCP (kind == "mcp_client")
    mcp_escopo: str | None = None  # leitura | propostas


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
    if token.startswith("smcp_"):  # spec 009: token de cliente MCP, decidido pelo portão (R5)
        from sociman_api.mcp import portao  # import tardio (o portão usa este módulo)

        return portao.ator(request)
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


SOMENTE_HUMANO = "Só um dono, pela interface, pode fazer isto"
SOMENTE_DONO = "Só donos podem fazer isto"
EVENTO_RECUSA = "publicacao_recusada"


def registrar_recusa(actor: Actor, rota: str, request: Request | None = None,
                     conta_id: uuid.UUID | str | None = None,
                     destino_id: uuid.UUID | str | None = None) -> None:
    """Grava `publicacao_recusada` numa sessão própria, já commitada.

    Sessão própria porque a requisição recusada faz rollback (armadilha 8) e porque os services
    chamam isto no meio de uma transação que não deve ser commitada junto.
    """
    details: dict[str, str] = {"rota": rota, "actorKind": actor.kind}
    if conta_id is not None:
        details["contaId"] = str(conta_id)
    if destino_id is not None:
        details["destinoId"] = str(destino_id)
    session = get_sessionmaker()()
    try:
        record_event(session, EVENTO_RECUSA, "denied", actor, request=request, details=details)
        session.commit()
    except Exception:  # o 403 sai de qualquer jeito; a falha do registro fica no log
        session.rollback()
        log.exception("falha ao registrar %s", EVENTO_RECUSA)
    finally:
        session.close()


def _rota(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


def require_human_owner(request: Request,
                        actor: Annotated[Actor, Depends(require_user)]) -> Actor:
    """Rotas **H** da 015: só um dono humano (sessão de usuário)."""
    if actor.kind != "user":
        params = request.path_params
        registrar_recusa(actor, _rota(request), request, params.get("conta_id"),
                         params.get("destino_id"))
        raise ApiError(403, "somente_humano", SOMENTE_HUMANO)
    if actor.user is None or actor.user.role != UserRole.dono:
        raise ApiError(403, "somente_dono", SOMENTE_DONO)
    return actor


def require_human(request: Request, actor: Annotated[Actor, Depends(require_user)]) -> Actor:
    """Rotas **Hu** da 009: qualquer usuário humano (dono ou membro). Outro ator → 403
    `somente_humano` + evento `publicacao_recusada`."""
    if actor.kind != "user":
        registrar_recusa(actor, _rota(request), request)
        raise ApiError(403, "somente_humano", SOMENTE_HUMANO)
    return actor


CurrentUser = Annotated[Actor, Depends(current_user)]
RequireUser = Annotated[Actor, Depends(require_user)]
RequireOwner = Annotated[Actor, Depends(require_owner)]
OptionalActor = Annotated[Actor, Depends(get_actor)]
RequireHumanOwner = Annotated[Actor, Depends(require_human_owner)]
RequireHuman = Annotated[Actor, Depends(require_human)]
