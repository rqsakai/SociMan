"""Rotas da importação da agência (contracts/http-api.md da spec 013): `operationId` `agencia_*`,
sem "youtube" nem "tiktok". Prévia, confirmar e desfazer são **H** (`RequireHumanOwner`: um não
humano recebe 403 `somente_humano` e deixa `publicacao_recusada`; um membro, `somente_dono`).
Estado, lista e detalhe são para dono e membro. Não existe rota DELETE.
"""

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from sociman_api.agencia import aplicar, desfazer, previa, schemas
from sociman_api.auth.deps import RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope

router = APIRouter(prefix="/api/agencia")

Youtube = Annotated[Callable[[], Any], Depends(aplicar.fabrica_youtube)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/estado", operation_id="agencia_estado", response_model=schemas.AgenciaEstado,
            responses=_errors(401, 403))
def agencia_estado(actor: RequireUser, db: DbSession) -> schemas.AgenciaEstado:
    return previa.estado(db)


@router.post("/previa", operation_id="agencia_previa", status_code=201,
             response_model=schemas.AgenciaPrevia, responses=_errors(401, 403, 409, 413, 503))
def agencia_previa(actor: RequireHumanOwner, db: DbSession, yt: Youtube) -> schemas.AgenciaPrevia:
    """Lê as pastas da agência e concilia com o banco; nada é gravado (30 min, uso único)."""
    return previa.montar(db, actor, yt)


@router.post("/importacoes", operation_id="agencia_confirmar", status_code=202,
             response_model=schemas.AgenciaImportacao, responses=_errors(400, 401, 403, 404, 409, 422))
def agencia_confirmar(body: schemas.AgenciaConfirmar, actor: RequireHumanOwner, db: DbSession,
                      tasks: BackgroundTasks, yt: Youtube) -> schemas.AgenciaImportacao:
    """Registra a importação (`processando`) e grava numa tarefa de fundo; acompanhe pelo
    detalhe até `concluida` ou `falhou`."""
    imp, plano = aplicar.confirmar(db, actor, body)
    tasks.add_task(aplicar.executar, plano, yt)
    return aplicar.importacao_out(db, imp)


@router.get("/importacoes", operation_id="agencia_importacoes_list",
            response_model=schemas.AgenciaImportacoesList, responses=_errors(401, 403))
def agencia_importacoes_list(actor: RequireUser, db: DbSession) -> schemas.AgenciaImportacoesList:
    return aplicar.listar(db)


@router.get("/importacoes/{importacao_id}", operation_id="agencia_importacoes_get",
            response_model=schemas.AgenciaImportacao, responses=_errors(401, 403, 404))
def agencia_importacoes_get(
    importacao_id: UUID, actor: RequireUser, db: DbSession,
    situacao: Annotated[schemas.Situacao | None, Query()] = None,
    tipo: Annotated[schemas.Tipo | None, Query()] = None,
    perfil: Annotated[str | None, Query(max_length=60)] = None,
) -> schemas.AgenciaImportacao:
    return aplicar.obter(db, importacao_id, situacao, tipo, perfil)


@router.post("/importacoes/{importacao_id}/desfazer", operation_id="agencia_desfazer",
             response_model=schemas.AgenciaImportacao, responses=_errors(400, 401, 403, 404, 409))
def agencia_desfazer(importacao_id: UUID, body: schemas.AgenciaDesfazerIn, actor: RequireHumanOwner,
                     db: DbSession) -> schemas.AgenciaImportacao:
    return desfazer.desfazer(db, actor, importacao_id, body.version)
