"""Rotas do histórico do Studio (contracts/http-api.md da spec 020): `operationId` `studio_*`, sem
"tiktok" nas rotas. Prévia, confirmar e desfazer são **H** (`RequireHumanOwner`: um não humano
recebe 403 `somente_humano` e deixa `publicacao_recusada`; um membro, `somente_dono`). A lista e
a cobertura são para dono e membro. Não existe rota DELETE.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Response, UploadFile

from sociman_api.auth.deps import RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.metricas.studio import previa, schemas, service

router = APIRouter(prefix="/api")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


Arquivos = Annotated[list[UploadFile], File(
    description="De 1 a 3 arquivos (.zip, .csv ou .xlsx) do TikTok Studio: os ZIPs da Visão "
                "geral, de Seguidores e/ou de Espectadores, até 5 MB no total")]


@router.post("/contas/{conta_id}/studio/previa", operation_id="studio_previa",
             status_code=201, response_model=schemas.PreviaStudio,
             responses=_errors(400, 401, 403, 404, 409, 413))
def studio_previa(conta_id: UUID, actor: RequireHumanOwner, db: DbSession,
                  arquivos: Arquivos = []) -> schemas.PreviaStudio:  # noqa: B006
    """Lê os arquivos em memória e devolve a pré-visualização (nada é gravado). Sem arquivo, o
    padrão `[]` leva ao 400 `studio_arquivos` (e não ao erro genérico de validação)."""
    conta = previa.conta_or_404(db, conta_id)
    return previa.montar(db, actor, conta, arquivos)


@router.post("/contas/{conta_id}/studio/importacoes", operation_id="studio_confirmar",
             status_code=201, response_model=schemas.Importacao,
             responses={200: {"model": schemas.Importacao,
                              "description": "Já importado: nada gravado (gravados = 0)"},
                        **_errors(400, 401, 403, 404, 409, 410)})
def studio_confirmar(conta_id: UUID, body: schemas.ConfirmarIn, actor: RequireHumanOwner,
                     db: DbSession, response: Response) -> schemas.Importacao:
    conta = previa.conta_or_404(db, conta_id)
    imp, criada = service.confirmar(db, actor, conta, body)
    if not criada:
        response.status_code = 200
    return imp


@router.get("/contas/{conta_id}/studio/importacoes", operation_id="studio_importacoes",
            response_model=schemas.ImportacoesList, responses=_errors(401, 403, 404))
def studio_importacoes(conta_id: UUID, actor: RequireUser,
                       db: DbSession) -> schemas.ImportacoesList:
    return service.listar(db, previa.conta_or_404(db, conta_id))


@router.get("/contas/{conta_id}/studio/cobertura", operation_id="studio_cobertura",
            response_model=schemas.Cobertura, responses=_errors(401, 403, 404))
def studio_cobertura(conta_id: UUID, actor: RequireUser, db: DbSession) -> schemas.Cobertura:
    return service.cobertura(db, previa.conta_or_404(db, conta_id))


@router.post("/studio/importacoes/{importacao_id}/desfazer", operation_id="studio_desfazer",
             response_model=schemas.Importacao, responses=_errors(400, 401, 403, 404, 409))
def studio_desfazer(importacao_id: UUID, body: schemas.DesfazerIn, actor: RequireHumanOwner,
                    db: DbSession) -> schemas.Importacao:
    return service.desfazer(db, actor, importacao_id, body.version)
