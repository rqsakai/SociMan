"""Rotas dos roteiros, do padrão de portões e das pronúncias de um perfil (contracts/http-api.md
da 011). Ler: `RequireUser`; escrever: `RequireHuman` (dono e membro)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from sociman_api.auth.deps import RequireHuman, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.schemas import VersionsList
from sociman_api.roteiros import aplicadores as _aplicadores  # noqa: F401 — registra os passos
from sociman_api.roteiros import schemas
from sociman_api.roteiros import service as svc
from sociman_api.roteiros import service_padroes as padroes
from sociman_api.roteiros import service_pronuncias as pron
from sociman_api.roteiros.models import RoteiroStatus

router = APIRouter(prefix="/api/perfis/{perfil_id}")

Db = DbSession


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/roteiros", operation_id="roteiros_listar", response_model=schemas.RoteirosPagina,
            responses=_errors(400, 401, 403, 404))
def listar(
    perfil_id: UUID, actor: RequireUser, db: Db,
    status: Annotated[list[RoteiroStatus] | None, Query(description="Estados (OU)")] = None,
    produto_id: Annotated[UUID | None, Query(alias="produtoId")] = None,
    arquivados: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limite: Annotated[int, Query(ge=1, le=svc.LIMITE_MAX)] = svc.LIMITE_PADRAO,
) -> schemas.RoteirosPagina:
    return svc.listar(db, perfil_id, status=status, produto_id=produto_id,
                      arquivados=arquivados, q=q, cursor=cursor, limite=limite)


@router.post("/roteiros", operation_id="roteiros_criar", status_code=201,
             response_model=schemas.RoteiroDetalhe, responses=_errors(400, 401, 403, 404, 409))
def criar(perfil_id: UUID, body: schemas.RoteiroIn, actor: RequireHuman,
          db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.criar(db, actor, perfil_id, body))


@router.get("/roteiro-padroes", operation_id="roteiro_padroes_ler",
            response_model=schemas.RoteiroPadroes, responses=_errors(401, 403, 404))
def padroes_ler(perfil_id: UUID, actor: RequireUser, db: Db) -> schemas.RoteiroPadroes:
    return padroes.obter(db, perfil_id)


@router.put("/roteiro-padroes", operation_id="roteiro_padroes_salvar",
            response_model=schemas.RoteiroPadroes, responses=_errors(400, 401, 403, 404, 409))
def padroes_salvar(perfil_id: UUID, body: schemas.RoteiroPadroesIn, actor: RequireHuman,
                   db: Db) -> schemas.RoteiroPadroes:
    return padroes.salvar(db, actor, perfil_id, body)


@router.get("/roteiro-padroes/versoes", operation_id="roteiro_padroes_versoes",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def padroes_versoes(perfil_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return padroes.versoes(db, perfil_id)


@router.get("/pronuncias", operation_id="pronuncias_listar",
            response_model=schemas.PronunciasList, responses=_errors(401, 403, 404))
def pronuncias_listar(perfil_id: UUID, actor: RequireUser, db: Db,
                      arquivadas: bool = False) -> schemas.PronunciasList:
    return pron.listar(db, perfil_id, arquivadas)


@router.post("/pronuncias", operation_id="pronuncias_criar", status_code=201,
             response_model=schemas.Pronuncia, responses=_errors(400, 401, 403, 404, 409))
def pronuncias_criar(perfil_id: UUID, body: schemas.PronunciaIn, actor: RequireHuman,
                     db: Db) -> schemas.Pronuncia:
    return pron.pronuncia_out(pron.criar(db, actor, perfil_id, body))
