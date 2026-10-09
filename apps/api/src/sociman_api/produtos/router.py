"""Rotas de um produto (contracts/api.md da 012, "Produto" e "Variantes"). Ler: `RequireUser`
(dono, membro e o MCP pelo mapa). Escrever: só humano, dono ou membro (`RequireHuman`; outro
ator → 403 `somente_humano`). Reverter: só o dono humano (`RequireHumanOwner`). Escolher,
cancelar, tentar de novo e gerar outras são as rotas da 021 (`/api/geracoes/{id}/…`). Não existe
rota DELETE."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile

from sociman_api.auth.deps import RequireHuman, RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.geracao import schemas as geracao_schemas
from sociman_api.geracao import service as geracao_service
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList
from sociman_api.produtos import schemas
from sociman_api.produtos import service as svc

router = APIRouter(prefix="/api/produtos")

Db = DbSession


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/{produto_id}", operation_id="produtos_ver", response_model=schemas.Produto,
            responses=_errors(401, 403, 404))
def ver(produto_id: UUID, actor: RequireUser, db: Db) -> schemas.Produto:
    return svc.ver(db, produto_id)


@router.patch("/{produto_id}", operation_id="produtos_editar", response_model=schemas.Produto,
              responses=_errors(400, 401, 403, 404, 409))
def editar(produto_id: UUID, body: schemas.ProdutoPatch, actor: RequireHuman,
           db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.editar(db, actor, produto_id, body))


@router.put("/{produto_id}/ficha", operation_id="produtos_salvar_ficha",
            response_model=schemas.Produto, responses=_errors(400, 401, 403, 404, 409))
def salvar_ficha(produto_id: UUID, body: schemas.SalvarFichaIn, actor: RequireHuman,
                 db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.salvar_ficha(db, actor, produto_id, body))


@router.post("/{produto_id}/ficha/pedir", operation_id="produtos_pedir_ficha",
             status_code=201, response_model=geracao_schemas.GeracaoResumo,
             responses=_errors(401, 403, 404, 409))
def pedir_ficha(produto_id: UUID, body: VersionIn, actor: RequireHuman,
                db: Db) -> geracao_schemas.GeracaoResumo:
    return geracao_service.resumo_out(db, svc.pedir_ficha(db, actor, produto_id, body.version))


@router.post("/{produto_id}/aprovar", operation_id="produtos_aprovar",
             response_model=schemas.Produto, responses=_errors(401, 403, 404, 409))
def aprovar(produto_id: UUID, body: VersionIn, actor: RequireHuman,
            db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.aprovar(db, actor, produto_id, body.version))


@router.post("/{produto_id}/arquivar", operation_id="produtos_arquivar",
             response_model=schemas.Produto, responses=_errors(401, 403, 404, 409))
def arquivar(produto_id: UUID, body: schemas.ArquivarIn, actor: RequireHuman,
             db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.arquivar(db, actor, produto_id, body))


@router.post("/{produto_id}/restaurar", operation_id="produtos_restaurar",
             response_model=schemas.Produto, responses=_errors(401, 403, 404, 409))
def restaurar(produto_id: UUID, body: VersionIn, actor: RequireHuman,
              db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.restaurar(db, actor, produto_id, body.version))


@router.get("/{produto_id}/versoes", operation_id="produtos_versoes",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def versoes(produto_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return svc.versoes(db, produto_id)


@router.post("/{produto_id}/revert", operation_id="produtos_reverter",
             response_model=schemas.Produto, responses=_errors(400, 401, 403, 404, 409))
def reverter(produto_id: UUID, body: RevertIn, actor: RequireHumanOwner,
             db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.reverter(db, actor, produto_id, body.version,
                                            body.to_version))


# ---- variantes ----

@router.post("/{produto_id}/variantes", operation_id="produtos_variante_criar",
             status_code=201, response_model=schemas.Produto,
             responses=_errors(400, 401, 403, 404, 409, 503, 507))
def variante_criar(
    produto_id: UUID, actor: RequireHuman, db: Db,
    version: Annotated[int, Form(ge=1)],
    foto: Annotated[UploadFile, File(description="PNG, JPG ou WebP, ≥ 512×512, até 20 MB")],
) -> schemas.Produto:
    return svc.produto_out(db, svc.variante_criar(db, actor, produto_id, version, foto.file))


@router.put("/{produto_id}/variantes/ordem", operation_id="produtos_variantes_ordenar",
            response_model=schemas.Produto, responses=_errors(400, 401, 403, 404, 409))
def variantes_ordenar(produto_id: UUID, body: schemas.OrdemIn, actor: RequireHuman,
                      db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.variantes_ordenar(db, actor, produto_id, body))


@router.patch("/{produto_id}/variantes/{variante_id}", operation_id="produtos_variante_editar",
              response_model=schemas.Produto, responses=_errors(400, 401, 403, 404, 409))
def variante_editar(produto_id: UUID, variante_id: UUID, body: schemas.VarianteEditarIn,
                    actor: RequireHuman, db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.variante_editar(db, actor, produto_id, variante_id, body))


@router.post("/{produto_id}/variantes/{variante_id}/arquivar",
             operation_id="produtos_variante_arquivar", response_model=schemas.Produto,
             responses=_errors(400, 401, 403, 404, 409))
def variante_arquivar(produto_id: UUID, variante_id: UUID, body: VersionIn,
                      actor: RequireHuman, db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.variante_arquivar(db, actor, produto_id, variante_id,
                                                     body.version))


@router.post("/{produto_id}/variantes/{variante_id}/restaurar",
             operation_id="produtos_variante_restaurar", response_model=schemas.Produto,
             responses=_errors(401, 403, 404, 409))
def variante_restaurar(produto_id: UUID, variante_id: UUID, body: VersionIn,
                       actor: RequireHuman, db: Db) -> schemas.Produto:
    return svc.produto_out(db, svc.variante_restaurar(db, actor, produto_id, variante_id,
                                                      body.version))


@router.post("/{produto_id}/variantes/{variante_id}/refazer-recorte",
             operation_id="produtos_refazer_recorte", status_code=201,
             response_model=geracao_schemas.GeracaoResumo,
             responses=_errors(401, 403, 404, 409))
def refazer_recorte(produto_id: UUID, variante_id: UUID, body: VersionIn, actor: RequireHuman,
                    db: Db) -> geracao_schemas.GeracaoResumo:
    return geracao_service.resumo_out(db, svc.refazer_recorte(db, actor, produto_id,
                                                             variante_id, body.version))


@router.post("/{produto_id}/variantes/{variante_id}/refazer-flat",
             operation_id="produtos_refazer_flat", status_code=201,
             response_model=geracao_schemas.GeracaoResumo,
             responses=_errors(401, 403, 404, 409))
def refazer_flat(produto_id: UUID, variante_id: UUID, body: VersionIn, actor: RequireHuman,
                 db: Db) -> geracao_schemas.GeracaoResumo:
    return geracao_service.resumo_out(db, svc.refazer_flat(db, actor, produto_id, variante_id,
                                                          body.version))
