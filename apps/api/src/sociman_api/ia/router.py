"""Rotas do assistente de IA (contracts/http-api.md da spec 008), sob `/api/ia`.

Gerar e descartar: dono e membro (`RequireUser`). Editar regras, registro e resumo: só o dono
(`RequireOwner`). Nada aqui publica nem salva entidade (princípio I e VII): gerar só devolve a
proposta; quem salva é o save de cada tela, no clique humano. Não existe rota DELETE.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.ia import schemas, service, service_regras
from sociman_api.ia.cliente import IaClient, get_ia_client
from sociman_api.ia.models import IaDesfecho
from sociman_api.perfis.schemas import RevertIn, VersionsList

router = APIRouter(prefix="/api/ia")

Cliente = Annotated[IaClient | None, Depends(get_ia_client)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- tipos de campo e regras ----

@router.get("/tipos", operation_id="ia_tipos_list", response_model=schemas.TiposList,
            responses=_errors(401, 403))
def tipos_list(actor: RequireUser, db: DbSession) -> schemas.TiposList:
    return schemas.TiposList(items=service_regras.listar(db))


@router.get("/tipos/{tipo}", operation_id="ia_tipos_get", response_model=schemas.TipoOut,
            responses=_errors(401, 403, 404))
def tipos_get(tipo: str, actor: RequireUser, db: DbSession) -> schemas.TipoOut:
    return schemas.TipoOut(tipo=service_regras.obter(db, tipo))


@router.put("/tipos/{tipo}/regras", operation_id="ia_regras_update",
            response_model=schemas.TipoOut, responses=_errors(400, 401, 403, 404, 409))
def regras_update(tipo: str, body: schemas.RegrasIn, actor: RequireOwner,
                  db: DbSession) -> schemas.TipoOut:
    return schemas.TipoOut(tipo=service_regras.put_regras(db, actor, tipo, body))


@router.post("/tipos/{tipo}/padrao", operation_id="ia_regras_padrao",
             response_model=schemas.TipoOut, responses=_errors(400, 401, 403, 404, 409))
def regras_padrao(tipo: str, body: schemas.PadraoIn, actor: RequireOwner,
                  db: DbSession) -> schemas.TipoOut:
    return schemas.TipoOut(tipo=service_regras.voltar_ao_padrao(db, actor, tipo, body.version))


@router.get("/tipos/{tipo}/versions", operation_id="ia_regras_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def regras_versions(tipo: str, actor: RequireUser, db: DbSession) -> VersionsList:
    return service_regras.versoes(db, tipo)


@router.post("/tipos/{tipo}/revert", operation_id="ia_regras_revert",
             response_model=schemas.TipoOut, responses=_errors(400, 401, 403, 404, 409))
def regras_revert(tipo: str, body: RevertIn, actor: RequireOwner,
                  db: DbSession) -> schemas.TipoOut:
    return schemas.TipoOut(tipo=service_regras.revert(db, actor, tipo, body.version,
                                                      body.to_version))


# ---- gerar e descartar ----

@router.post("/gerar", operation_id="ia_gerar", response_model=schemas.ChamadaOut,
             responses=_errors(400, 401, 403, 404, 409, 502, 503, 504))
def gerar(body: schemas.GerarIn, actor: RequireUser, db: DbSession,
          client: Cliente) -> schemas.ChamadaOut:
    row = service.gerar(db, actor, body, client)
    return schemas.ChamadaOut(chamada=service.chamada_out(db, row))


@router.post("/chamadas/{chamada_id}/descartar", operation_id="ia_chamadas_descartar",
             status_code=204, response_class=Response, responses=_errors(401, 403, 404))
def descartar(chamada_id: UUID, actor: RequireUser, db: DbSession) -> Response:
    service.descartar(db, actor, chamada_id)
    return Response(status_code=204)


# ---- registro e resumo (dono) ----

@router.get("/chamadas", operation_id="ia_chamadas_list", response_model=schemas.ChamadasList,
            responses=_errors(400, 401, 403))
def chamadas_list(
    actor: RequireOwner, db: DbSession,
    perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
    tipo_campo: Annotated[str | None, Query(alias="tipoCampo")] = None,
    desfecho: IaDesfecho | None = None,
    de: date | None = None,
    ate: date | None = None,
    sessao_id: Annotated[UUID | None, Query(alias="sessaoId")] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=service.LIMIT_MAX)] = service.LIMIT_PADRAO,
) -> schemas.ChamadasList:
    return service.listar_chamadas(db, perfil_id=perfil_id, tipo_campo=tipo_campo,
                                   desfecho=desfecho, de=de, ate=ate, sessao_id=sessao_id,
                                   cursor=cursor, limit=limit)


@router.get("/chamadas/{chamada_id}", operation_id="ia_chamadas_get",
            response_model=schemas.ChamadaOut, responses=_errors(401, 403, 404))
def chamadas_get(chamada_id: UUID, actor: RequireOwner, db: DbSession) -> schemas.ChamadaOut:
    return schemas.ChamadaOut(chamada=service.get_chamada(db, chamada_id))


@router.get("/resumo", operation_id="ia_resumo", response_model=schemas.IaResumo,
            responses=_errors(400, 401, 403))
def resumo(actor: RequireOwner, db: DbSession,
           mes: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None
           ) -> schemas.IaResumo:
    return service.resumo(db, mes)
