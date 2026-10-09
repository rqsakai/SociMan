"""Rotas das vozes (contracts/http-api.md da spec 025). Ler: `RequireUser`. Escrever: só humano,
dono ou membro (`RequireHuman`). Revogar: só o dono humano (`RequireHumanOwner`). Reverter: só o
dono (`RequireHumanOwner`, como a revogação). Não existe rota DELETE.

Spec 029: a lista e o cadastro da biblioteca da agência (`/api/vozes`), com o perfil base
opcional; as rotas por perfil ficam obsoletas (`deprecated`), com o mesmo comportamento."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query

from sociman_api.assets.schemas_padrao import ConsentimentoIn, RevogarIn
from sociman_api.auth.deps import RequireHuman, RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.estudio.filtros import PerfilFiltro, filtro
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList
from sociman_api.vozes import schemas
from sociman_api.vozes import service as svc
from sociman_api.vozes.models import VozStatus

router = APIRouter(prefix="/api")

Db = DbSession


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/vozes", operation_id="vozes_listar_agencia", response_model=schemas.VozesLista,
            responses=_errors(400, 401, 403))
def listar_agencia(
    actor: RequireUser, db: Db, perfil_id: PerfilFiltro = None,
    status: Annotated[list[VozStatus] | None, Query()] = None,
    arquivadas: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limite: Annotated[int, Query(ge=1, le=svc.LIMITE_MAX)] = svc.LIMITE_PADRAO,
) -> schemas.VozesLista:
    return svc.listar_agencia(db, filtro(db, perfil_id), status=status or (),
                              arquivadas=arquivadas, q=q, cursor=cursor, limite=limite)


@router.post("/vozes", operation_id="vozes_criar_agencia", status_code=201,
             response_model=schemas.Voz, responses=_errors(400, 401, 403, 409))
def criar_agencia(body: schemas.VozInAgencia, actor: RequireHuman, db: Db) -> schemas.Voz:
    svc.perfil_base_novo(db, body.perfil_id)
    return svc.voz_out(db, svc.criar(db, actor, body.perfil_id, body))


@router.get("/perfis/{perfil_id}/vozes", operation_id="vozes_listar",
            response_model=schemas.VozesLista, responses=_errors(400, 401, 403, 404),
            deprecated=True)
def listar(
    perfil_id: UUID, actor: RequireUser, db: Db,
    status: Annotated[list[VozStatus] | None, Query()] = None,
    arquivadas: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limite: Annotated[int, Query(ge=1, le=svc.LIMITE_MAX)] = svc.LIMITE_PADRAO,
) -> schemas.VozesLista:
    return svc.listar(db, perfil_id, status=status or (), arquivadas=arquivadas, q=q,
                      cursor=cursor, limite=limite)


@router.post("/perfis/{perfil_id}/vozes", operation_id="vozes_criar", status_code=201,
             response_model=schemas.Voz, responses=_errors(400, 401, 403, 404, 409),
             deprecated=True)
def criar(perfil_id: UUID, body: schemas.VozIn, actor: RequireHuman, db: Db) -> schemas.Voz:
    return svc.voz_out(db, svc.criar(db, actor, perfil_id, body))


@router.get("/vozes/{voz_id}", operation_id="vozes_detalhe", response_model=schemas.Voz,
            responses=_errors(401, 403, 404))
def detalhe(voz_id: UUID, actor: RequireUser, db: Db) -> schemas.Voz:
    return svc.detalhe(db, voz_id, actor)


@router.patch("/vozes/{voz_id}", operation_id="vozes_update", response_model=schemas.Voz,
              responses=_errors(400, 401, 403, 404, 409))
def editar(voz_id: UUID, body: schemas.VozPatch, actor: RequireHuman, db: Db) -> schemas.Voz:
    return svc.voz_out(db, svc.editar(db, actor, voz_id, body))


@router.put("/vozes/{voz_id}/consentimento", operation_id="vozes_consentimento_registrar",
            response_model=schemas.Voz, responses=_errors(400, 401, 403, 404, 409))
def consentimento(voz_id: UUID, body: ConsentimentoIn, actor: RequireHuman,
                  db: Db) -> schemas.Voz:
    voz = svc.registrar_consentimento(db, actor, voz_id, body.version, body.nome, body.data,
                                      body.observacao,
                                      body.prova.model_dump() if body.prova else None)
    return svc.voz_out(db, voz)


@router.post("/vozes/{voz_id}/consentimento/revogar", operation_id="vozes_consentimento_revogar",
             response_model=schemas.RevogacaoVozOut,
             responses=_errors(400, 401, 403, 404, 409, 503))
def revogar(voz_id: UUID, body: RevogarIn, actor: RequireHumanOwner, db: Db,
            tarefas: BackgroundTasks) -> schemas.RevogacaoVozOut:
    from sociman_api import revogacao

    voz, apagados, objetos = revogacao.revogar_voz(db, actor, voz_id, body.version,
                                                   body.confirmo)
    tarefas.add_task(revogacao.apagar_objetos, objetos)  # depois do commit (R10)
    return schemas.RevogacaoVozOut(voz=svc.voz_out(db, voz), apagados=apagados,
                                   avatares_afetados=apagados.avatares_afetados)


@router.post("/vozes/{voz_id}/archive", operation_id="vozes_archive",
             response_model=schemas.Voz, responses=_errors(401, 403, 404, 409))
def arquivar(voz_id: UUID, body: VersionIn, actor: RequireHuman, db: Db) -> schemas.Voz:
    return svc.voz_out(db, svc.arquivar(db, actor, voz_id, body.version))


@router.post("/vozes/{voz_id}/restore", operation_id="vozes_restore",
             response_model=schemas.Voz, responses=_errors(401, 403, 404, 409))
def restaurar(voz_id: UUID, body: VersionIn, actor: RequireHuman, db: Db) -> schemas.Voz:
    return svc.voz_out(db, svc.restaurar(db, actor, voz_id, body.version))


@router.get("/vozes/{voz_id}/versoes", operation_id="vozes_versoes",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def versoes(voz_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return svc.versoes(db, voz_id)


@router.post("/vozes/{voz_id}/revert", operation_id="vozes_revert",
             response_model=schemas.Voz, responses=_errors(400, 401, 403, 404, 409))
def reverter(voz_id: UUID, body: RevertIn, actor: RequireHumanOwner, db: Db) -> schemas.Voz:
    return svc.voz_out(db, svc.reverter(db, actor, voz_id, body.version, body.to_version))
