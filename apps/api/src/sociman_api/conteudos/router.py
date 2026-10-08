"""Rotas da central de conteúdos (contracts/http-api.md da spec 014, "Conteúdos").

Dono e membro (`RequireUser`), menos a reversão (`RequireOwner`, princípio VII). Nada aqui fala
com rede social (princípio I). Não existe rota DELETE.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.conteudos import schemas, service
from sociman_api.conteudos.models import ConteudoOrigem
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList

router = APIRouter(prefix="/api/conteudos")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _out(db: DbSession, conteudo) -> schemas.ConteudoOut:
    return schemas.ConteudoOut(conteudo=service.conteudo_out(db, conteudo.id))


PerfilIds = Annotated[list[UUID], Query(alias="perfilId", description="Repetível")]
ContaId = Annotated[UUID | None, Query(alias="contaId")]


@router.get("", operation_id="conteudos_list", response_model=schemas.ConteudosList,
            responses=_errors(400, 401, 403))
def list_conteudos(
    actor: RequireUser, db: DbSession,
    perfil_id: PerfilIds = [],  # noqa: B006 — o FastAPI copia o padrão
    conta_id: ContaId = None,
    plataforma: Annotated[Platform | None, Query()] = None,
    estado: Annotated[list[schemas.EstadoFiltro],
                      Query(description="Estado efetivo de algum destino, ou sem_conta; "
                                        "repetível")] = [],  # noqa: B006
    origem: Annotated[ConteudoOrigem | None, Query()] = None,
    agendado_de: Annotated[date | None, Query(alias="agendadoDe")] = None,
    agendado_ate: Annotated[date | None, Query(alias="agendadoAte")] = None,
    criado_de: Annotated[date | None, Query(alias="criadoDe")] = None,
    criado_ate: Annotated[date | None, Query(alias="criadoAte")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    atalho: Annotated[schemas.Atalho | None, Query()] = None,
    ordem: Annotated[schemas.OrdemConteudos, Query()] = schemas.OrdemConteudos.recentes,
    archived: Annotated[bool, Query()] = False,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = service.LIMIT_PADRAO,
    offset: Annotated[int | None, Query(ge=0, description="Página numerada; não use com "
                                                          "`cursor`")] = None,
) -> schemas.ConteudosList:
    filtros = service.Filtros(
        perfil_ids=perfil_id, conta_id=conta_id, plataforma=plataforma, estados=estado,
        origem=origem, agendado_de=agendado_de, agendado_ate=agendado_ate, criado_de=criado_de,
        criado_ate=criado_ate, q=q, atalho=atalho, ordem=ordem, archived=archived,
    )
    return service.list_conteudos(db, filtros, cursor, limit, offset)


@router.get("/resumo", operation_id="conteudos_resumo", response_model=schemas.Atalhos,
            responses=_errors(401, 403))
def resumo(actor: RequireUser, db: DbSession,
           perfil_id: PerfilIds = [],  # noqa: B006
           conta_id: ContaId = None) -> schemas.Atalhos:
    return service.resumo(db, perfil_id, conta_id)


@router.get("/{conteudo_id}", operation_id="conteudos_get", response_model=schemas.ConteudoOut,
            responses=_errors(401, 403, 404))
def get_conteudo(conteudo_id: UUID, actor: RequireUser, db: DbSession) -> schemas.ConteudoOut:
    return _out(db, service.get_conteudo_or_404(db, conteudo_id))


@router.patch("/{conteudo_id}", operation_id="conteudos_update",
              response_model=schemas.ConteudoOut, responses=_errors(400, 401, 403, 404, 409))
def update_conteudo(conteudo_id: UUID, body: schemas.UpdateConteudoIn, actor: RequireUser,
                    db: DbSession) -> schemas.ConteudoOut:
    return _out(db, service.update_titulo(db, actor, conteudo_id, body.version, body.titulo))


@router.post("/{conteudo_id}/archive", operation_id="conteudos_archive",
             response_model=schemas.ConteudoOut, responses=_errors(400, 401, 403, 404, 409))
def archive_conteudo(conteudo_id: UUID, body: VersionIn, actor: RequireUser,
                     db: DbSession) -> schemas.ConteudoOut:
    return _out(db, service.archive(db, actor, conteudo_id, body.version))


@router.post("/{conteudo_id}/restore", operation_id="conteudos_restore",
             response_model=schemas.ConteudoOut, responses=_errors(400, 401, 403, 404, 409))
def restore_conteudo(conteudo_id: UUID, body: VersionIn, actor: RequireUser,
                     db: DbSession) -> schemas.ConteudoOut:
    return _out(db, service.restore(db, actor, conteudo_id, body.version))


@router.get("/{conteudo_id}/versions", operation_id="conteudos_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def conteudo_versions(conteudo_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service.list_versions(db, conteudo_id)


@router.post("/{conteudo_id}/revert", operation_id="conteudos_revert",
             response_model=schemas.ConteudoOut, responses=_errors(400, 401, 403, 404, 409))
def revert_conteudo(conteudo_id: UUID, body: RevertIn, actor: RequireOwner,
                    db: DbSession) -> schemas.ConteudoOut:
    return _out(db, service.revert(db, actor, conteudo_id, body.version, body.to_version))
