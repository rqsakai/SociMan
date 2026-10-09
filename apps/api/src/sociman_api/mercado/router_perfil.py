"""Rotas de mercado **por perfil** (FR-037..FR-039): interesses (acompanhamentos), a configuração
do nicho (categorias, lojas seguidas, teto de relacionados) e seguir/deixar de seguir loja.

Leituras para dono e membro (e para as tools MCP). Escritas só por humano (`RequireHuman`:
cliente MCP → 403 `somente_humano`); a configuração do nicho é só do dono humano.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from sociman_api.auth.deps import RequireHuman, RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope
from sociman_api.mercado import apresentacao as ap
from sociman_api.mercado import interesses, schemas
from sociman_api.mercado.models import InteresseOrigem, InteresseSituacao
from sociman_api.perfis.schemas import VersionsList

router = APIRouter(prefix="/api/perfis/{perfil_id}/mercado")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/interesses", operation_id="mercado_interesses_listar",
            response_model=schemas.InteressesList, responses=_errors(401, 403, 404))
def interesses_listar(perfil_id: uuid.UUID, actor: RequireUser, db: DbSession,
                      origem: Annotated[InteresseOrigem | None, Query()] = None,
                      situacao: Annotated[InteresseSituacao | None, Query()] = None,
                      limite: Annotated[int, Query(ge=1, le=500)] = 200) -> schemas.InteressesList:
    """Os acompanhamentos do perfil (com os de vitrine, que valem para todos), com o cartão do
    produto."""
    interesses.perfil_ou_404(db, perfil_id)
    itens = interesses.listar(db, perfil_id, origem, situacao, limite=limite)
    return ap.interesses_out(db, itens)


@router.post("/interesses", operation_id="mercado_interesses_criar", status_code=201,
             response_model=schemas.InteresseOut, responses=_errors(400, 401, 403, 404, 409))
def interesses_criar(perfil_id: uuid.UUID, body: schemas.InteresseCriarIn, actor: RequireHuman,
                     db: DbSession) -> schemas.InteresseOut:
    """Acompanhar por link (interesse `manual`) ou "Acompanhar neste perfil" um produto do lago."""
    if bool(body.url) == bool(body.mercado_produto_id):
        raise ApiError(400, "entrada_invalida", "Informe o link ou o produto, um dos dois",
                       details={"field": "url"})
    if body.url:
        interesse = interesses.acompanhar_por_link(db, actor, perfil_id, body.url, body.nota)
    else:
        assert body.mercado_produto_id is not None
        interesse = interesses.acompanhar_produto(db, actor, perfil_id, body.mercado_produto_id,
                                                  body.nota)
    return ap.interesses_out(db, [interesse]).itens[0]


@router.get("/config", operation_id="mercado_perfil_config_get",
            response_model=schemas.PerfilConfigOut, responses=_errors(401, 403, 404))
def config_ler(perfil_id: uuid.UUID, actor: RequireUser, db: DbSession) -> schemas.PerfilConfigOut:
    """Categorias do nicho, lojas seguidas e o teto de acompanhamentos automáticos."""
    interesses.perfil_ou_404(db, perfil_id)
    return ap.config_out(db, interesses.config_perfil(db, perfil_id))


@router.put("/config", operation_id="mercado_perfil_config_put",
            response_model=schemas.PerfilConfigOut, responses=_errors(400, 401, 403, 404, 409))
def config_atualizar(perfil_id: uuid.UUID, body: schemas.PerfilConfigIn, actor: RequireHumanOwner,
                     db: DbSession) -> schemas.PerfilConfigOut:
    """Só o dono humano (FR-037): até 5 categorias da taxonomia observada."""
    cfg = interesses.atualizar_config(db, actor, perfil_id, body.version,
                                      categoria_ids=body.categoria_ids,
                                      max_relacionados_dia=body.max_relacionados_dia,
                                      avisar_novo_em_alta=body.avisar_novo_em_alta,
                                      mercado=body.mercado)
    return ap.config_out(db, cfg)


@router.post("/config/revert", operation_id="mercado_perfil_config_revert",
             response_model=schemas.PerfilConfigOut, responses=_errors(400, 401, 403, 404, 409))
def config_revert(perfil_id: uuid.UUID, body: schemas.InteresseRevertIn, actor: RequireHumanOwner,
                  db: DbSession) -> schemas.PerfilConfigOut:
    """Só o dono humano (princípio VII)."""
    return ap.config_out(db, interesses.reverter_config(db, actor, perfil_id, body.version,
                                                        body.to_version))


@router.get("/config/versions", operation_id="mercado_perfil_config_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def config_versions(perfil_id: uuid.UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return ap.versions_list(db, interesses.versoes_config(db, perfil_id))


@router.post("/lojas/{loja_id}/seguir", operation_id="mercado_lojas_seguir",
             response_model=schemas.PerfilConfigOut, responses=_errors(401, 403, 404, 409))
def lojas_seguir(perfil_id: uuid.UUID, loja_id: uuid.UUID, body: schemas.SeguirLojaIn,
                 actor: RequireHuman, db: DbSession) -> schemas.PerfilConfigOut:
    """Qualquer humano (FR-039): a loja entra nas seguidas do perfil; seus produtos novos viram
    acompanhamentos automáticos."""
    return ap.config_out(db, interesses.seguir_loja(db, actor, perfil_id, loja_id, body.version))


@router.post("/lojas/{loja_id}/deixar-de-seguir", operation_id="mercado_lojas_deixar_de_seguir",
             response_model=schemas.PerfilConfigOut, responses=_errors(401, 403, 404, 409))
def lojas_deixar(perfil_id: uuid.UUID, loja_id: uuid.UUID, body: schemas.SeguirLojaIn,
                 actor: RequireHuman, db: DbSession) -> schemas.PerfilConfigOut:
    return ap.config_out(db, interesses.deixar_de_seguir(db, actor, perfil_id, loja_id,
                                                         body.version))
