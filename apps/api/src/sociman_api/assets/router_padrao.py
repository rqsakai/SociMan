"""Rotas do cadastro padronizado do asset (contracts/http-api.md da spec 025): consentimento e
revogação. Registrar: só humano, dono ou membro (`RequireHuman`). Revogar e a prévia: só o dono
humano (`RequireHumanOwner`)."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks

from sociman_api.assets import schemas, schemas_padrao, service_padrao
from sociman_api.assets import service as svc
from sociman_api.auth.deps import RequireHuman, RequireHumanOwner
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope

router = APIRouter(prefix="/api/assets")

Db = DbSession


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.put("/{asset_id}/consentimento", operation_id="assets_consentimento_registrar",
            response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def registrar(asset_id: UUID, body: schemas_padrao.ConsentimentoIn, actor: RequireHuman,
              db: Db) -> schemas.AssetOut:
    asset = svc.get_asset_or_404(db, asset_id, lock=True)
    service_padrao.registrar_consentimento(
        db, actor, asset, body.version, body.nome, body.data, body.observacao,
        body.prova.model_dump() if body.prova else None)
    return schemas.AssetOut(asset=svc.asset_out(db, asset))


@router.get("/{asset_id}/consentimento/previa-revogacao",
            operation_id="assets_consentimento_previa",
            response_model=schemas_padrao.PreviaRevogacao, responses=_errors(401, 403, 404, 409))
def previa(asset_id: UUID, actor: RequireHumanOwner, db: Db) -> schemas_padrao.PreviaRevogacao:
    from sociman_api import revogacao

    return revogacao.previa_asset(db, svc.get_asset_or_404(db, asset_id))


@router.post("/{asset_id}/consentimento/revogar", operation_id="assets_consentimento_revogar",
             response_model=schemas.RevogacaoAssetOut,
             responses=_errors(400, 401, 403, 404, 409, 503))
def revogar(asset_id: UUID, body: schemas_padrao.RevogarIn, actor: RequireHumanOwner, db: Db,
            tarefas: BackgroundTasks) -> schemas.RevogacaoAssetOut:
    from sociman_api import revogacao

    asset, apagados, objetos = revogacao.revogar_asset(db, actor, asset_id, body.version,
                                                       body.confirmo)
    tarefas.add_task(revogacao.apagar_objetos, objetos)  # depois do commit (R10)
    return schemas.RevogacaoAssetOut(asset=svc.asset_out(db, asset), apagados=apagados,
                                     cenas_afetadas=apagados.cenas_afetadas)
