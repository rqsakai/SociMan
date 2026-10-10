"""Rotas do roteiro, por posição, e das pronúncias (contracts/http-api.md da 011). Ler:
`RequireUser` (dono e membro; fora do MCP). Escrever: só humano, dono ou membro
(`RequireHuman`; outro ator → 403 `somente_humano` + `publicacao_recusada`). Reverter: só o dono
humano (`RequireHumanOwner`). Escolher uma opção de keyframe é a rota da 021
(`POST /api/geracoes/{id}/escolher`). Não existe rota DELETE.

A lista da agência (`GET /api/roteiros`) é a do item "Vídeos" do AI Studio (FR-051), com o filtro
de perfil."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile

from sociman_api.auth.deps import RequireHuman, RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.estudio.filtros import PerfilFiltro, filtro
from sociman_api.perfis.base import SEM
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_imagens import read_limited
from sociman_api.roteiros import aplicadores as _aplicadores  # noqa: F401 — registra os passos
from sociman_api.roteiros import schemas
from sociman_api.roteiros import service as svc
from sociman_api.roteiros import service_pronuncias as pron
from sociman_api.roteiros.models import RoteiroStatus

router = APIRouter(prefix="/api")

Db = DbSession


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- lista da agência ----

@router.get("/roteiros", operation_id="roteiros_listar_agencia",
            response_model=schemas.RoteirosPagina, responses=_errors(400, 401, 403))
def listar_agencia(
    actor: RequireUser, db: Db, perfil_id: PerfilFiltro = None,
    status: Annotated[list[RoteiroStatus] | None, Query(description="Estados (OU)")] = None,
    produto_id: Annotated[UUID | None, Query(alias="produtoId")] = None,
    archived: Annotated[bool, Query(description="true = só os arquivados")] = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=svc.LIMITE_MAX)] = svc.LIMITE_PADRAO,
) -> schemas.RoteirosPagina:
    """O perfil do vídeo: ausente = todos; `sem` = nenhum (o roteiro sempre tem perfil); um id."""
    f = filtro(db, perfil_id)
    if f == SEM:
        return schemas.RoteirosPagina(itens=[], proximo=None)
    return svc.listar(db, f, status=status, produto_id=produto_id, arquivados=archived, q=q,
                      cursor=cursor, limite=limit)


# ---- um roteiro ----

@router.get("/roteiros/{roteiro_id}", operation_id="roteiros_detalhe",
            response_model=schemas.RoteiroDetalhe, responses=_errors(401, 403, 404))
def detalhe(roteiro_id: UUID, actor: RequireUser, db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe(db, roteiro_id)


@router.patch("/roteiros/{roteiro_id}", operation_id="roteiros_editar",
              response_model=schemas.RoteiroDetalhe,
              responses=_errors(400, 401, 403, 404, 409))
def editar(roteiro_id: UUID, body: schemas.RoteiroPatch, actor: RequireHuman,
           db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.editar(db, actor, roteiro_id, body))


@router.post("/roteiros/{roteiro_id}/planejar", operation_id="roteiros_planejar",
             response_model=schemas.RoteiroDetalhe,
             responses=_errors(400, 401, 403, 404, 409, 503))
def planejar(roteiro_id: UUID, body: schemas.RoteiroVersionIn, actor: RequireHuman,
             db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.planejar(db, actor, roteiro_id, body.version))


@router.post("/roteiros/{roteiro_id}/aprovar", operation_id="roteiros_aprovar",
             response_model=schemas.RoteiroDetalhe,
             responses=_errors(400, 401, 403, 404, 409))
def aprovar(roteiro_id: UUID, body: schemas.AprovarIn, actor: RequireHuman,
            db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.aprovar(db, actor, roteiro_id, body))


@router.put("/roteiros/{roteiro_id}/controle", operation_id="roteiros_controle",
            response_model=schemas.RoteiroDetalhe, responses=_errors(400, 401, 403, 404, 409))
def controle(roteiro_id: UUID, body: schemas.ControleIn, actor: RequireHuman,
             db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.controle(db, actor, roteiro_id, body))


@router.post("/roteiros/{roteiro_id}/tentar-de-novo", operation_id="roteiros_tentar_de_novo",
             response_model=schemas.RoteiroDetalhe,
             responses=_errors(400, 401, 403, 404, 409))
def tentar_de_novo(roteiro_id: UUID, body: schemas.RoteiroVersionIn, actor: RequireHuman,
                   db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.tentar_de_novo(db, actor, roteiro_id, body.version))


@router.post("/roteiros/{roteiro_id}/arquivar", operation_id="roteiros_arquivar",
             response_model=schemas.RoteiroDetalhe, responses=_errors(400, 401, 403, 404, 409))
def arquivar(roteiro_id: UUID, body: schemas.RoteiroVersionIn, actor: RequireHuman,
             db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.arquivar(db, actor, roteiro_id, body.version))


@router.post("/roteiros/{roteiro_id}/restaurar", operation_id="roteiros_restaurar",
             response_model=schemas.RoteiroDetalhe, responses=_errors(400, 401, 403, 404, 409))
def restaurar(roteiro_id: UUID, body: schemas.RoteiroVersionIn, actor: RequireHuman,
              db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.restaurar(db, actor, roteiro_id, body.version))


@router.get("/roteiros/{roteiro_id}/versoes", operation_id="roteiros_versoes",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def versoes(roteiro_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return svc.versoes(db, roteiro_id)


@router.post("/roteiros/{roteiro_id}/versoes/{versao}/reverter",
             operation_id="roteiros_reverter", response_model=schemas.RoteiroDetalhe,
             responses=_errors(400, 401, 403, 404, 409))
def reverter(roteiro_id: UUID, versao: int, body: schemas.RoteiroVersionIn,
             actor: RequireHumanOwner, db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.reverter(db, actor, roteiro_id, body.version, versao))


# ---- por posição ----

@router.post("/roteiros/{roteiro_id}/posicoes/{ordem}/keyframe/regerar",
             operation_id="roteiros_regerar_keyframe", response_model=schemas.RoteiroDetalhe,
             responses=_errors(400, 401, 403, 404, 409, 503))
def regerar_keyframe(roteiro_id: UUID, ordem: int, body: schemas.RegerarKeyframeIn,
                     actor: RequireHuman, db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.regerar_keyframe(db, actor, roteiro_id, ordem, body))


@router.post("/roteiros/{roteiro_id}/posicoes/{ordem}/keyframe",
             operation_id="roteiros_enviar_keyframe", response_model=schemas.RoteiroDetalhe,
             responses=_errors(400, 401, 403, 404, 409, 413, 503, 507))
def enviar_keyframe(
    roteiro_id: UUID, ordem: int, actor: RequireHuman, db: Db,
    version: Annotated[int, Form(ge=1)],
    arquivo: Annotated[UploadFile, File(description="PNG, JPG ou WebP, até 20 MB, na proporção "
                                                    "da cena")],
) -> schemas.RoteiroDetalhe:
    data = read_limited(arquivo.file, svc.KEYFRAME_MAX_BYTES)
    return svc.detalhe_out(db, svc.enviar_keyframe(db, actor, roteiro_id, ordem, version, data))


@router.post("/roteiros/{roteiro_id}/posicoes/{ordem}/clipe/regerar",
             operation_id="roteiros_regerar_clipe", response_model=schemas.RoteiroDetalhe,
             responses=_errors(400, 401, 403, 404, 409, 503))
def regerar_clipe(roteiro_id: UUID, ordem: int, body: schemas.RegerarClipeIn,
                  actor: RequireHuman, db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.regerar_clipe(db, actor, roteiro_id, ordem, body))


@router.put("/roteiros/{roteiro_id}/posicoes/{ordem}/tomada",
            operation_id="roteiros_escolher_tomada", response_model=schemas.RoteiroDetalhe,
            responses=_errors(400, 401, 403, 404, 409))
def escolher_tomada(roteiro_id: UUID, ordem: int, body: schemas.EscolherTomadaIn,
                    actor: RequireHuman, db: Db) -> schemas.RoteiroDetalhe:
    return svc.detalhe_out(db, svc.escolher_tomada(db, actor, roteiro_id, ordem, body))


# ---- uma pronúncia ----

@router.patch("/pronuncias/{pronuncia_id}", operation_id="pronuncias_editar",
              response_model=schemas.Pronuncia, responses=_errors(400, 401, 403, 404, 409))
def pronuncia_editar(pronuncia_id: UUID, body: schemas.PronunciaPatch, actor: RequireHuman,
                     db: Db) -> schemas.Pronuncia:
    return pron.pronuncia_out(pron.editar(db, actor, pronuncia_id, body))


@router.post("/pronuncias/{pronuncia_id}/arquivar", operation_id="pronuncias_arquivar",
             response_model=schemas.Pronuncia, responses=_errors(400, 401, 403, 404, 409))
def pronuncia_arquivar(pronuncia_id: UUID, body: schemas.RoteiroVersionIn, actor: RequireHuman,
                       db: Db) -> schemas.Pronuncia:
    return pron.pronuncia_out(pron.arquivar(db, actor, pronuncia_id, body.version))


@router.post("/pronuncias/{pronuncia_id}/restaurar", operation_id="pronuncias_restaurar",
             response_model=schemas.Pronuncia, responses=_errors(400, 401, 403, 404, 409))
def pronuncia_restaurar(pronuncia_id: UUID, body: schemas.RoteiroVersionIn,
                        actor: RequireHuman, db: Db) -> schemas.Pronuncia:
    return pron.pronuncia_out(pron.restaurar(db, actor, pronuncia_id, body.version))


@router.get("/pronuncias/{pronuncia_id}/versoes", operation_id="pronuncias_versoes",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def pronuncia_versoes(pronuncia_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return pron.versoes(db, pronuncia_id)
