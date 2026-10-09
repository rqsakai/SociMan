"""Rotas das notificações (contracts/http-api.md da 006, "Notificações"): só as do usuário logado.

O SPA faz polling com `after` (R11); não há SSE (o Bearer não vai no `EventSource`).
"""

from typing import Annotated

from fastapi import APIRouter, Query

from sociman_api.auth.deps import RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.notificacoes import service
from sociman_api.notificacoes.schemas import (
    MarcarLidasIn,
    NaoLidasOut,
    Notificacao,
    NotificacoesList,
)

router = APIRouter(prefix="/api")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/notificacoes", operation_id="notificacoes_list", response_model=NotificacoesList,
            responses=_errors(400, 401, 403))
def list_notificacoes(
    actor: RequireUser,
    db: DbSession,
    after: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=service.LIMIT_MAX)] = service.LIMIT_PADRAO,
    nao_lidas: Annotated[bool, Query(alias="naoLidas")] = False,
) -> NotificacoesList:
    items = service.listar(db, actor.user_id, after=after, limit=limit, so_nao_lidas=nao_lidas)
    return NotificacoesList(
        items=[Notificacao(id=n.id, tipo=n.tipo, titulo=n.titulo, corpo=n.corpo, link=n.link,
                           created_at=n.created_at, lida=n.lida_em is not None) for n in items],
        nao_lidas=service.nao_lidas(db, actor.user_id),
    )


@router.post("/notificacoes/lidas", operation_id="notificacoes_marcar_lidas",
             response_model=NaoLidasOut, responses=_errors(400, 401, 403))
def marcar_lidas(body: MarcarLidasIn, actor: RequireUser, db: DbSession) -> NaoLidasOut:
    restantes = service.marcar_lidas(db, actor.user_id, ids=body.ids, todas=body.todas)
    return NaoLidasOut(nao_lidas=restantes)
