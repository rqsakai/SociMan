"""Rotas de destinos, agendamentos, sugestões (deprecated) e calendário (contracts/http-api.md
da 014, "Destinos", "Agendamentos" e "Calendário"; as rotas de postagem da 006 saíram no T045).

Dono e membro (`RequireUser`), menos aprovar, recusar, aprovar em lote e reverter
(`RequireOwner`, princípios I e VII). `postado` só muda pela rota humana; nada aqui publica.
Não existe rota DELETE.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from sociman_api.auth.deps import RequireHumanOwner, RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.ia.cliente import IaClient, get_ia_client
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList
from sociman_api.postagem import schemas, service

router = APIRouter(prefix="/api")

Textos = Annotated[IaClient | None, Depends(get_ia_client)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- sugestões ----

# Deprecated desde a spec 008: o painel usa `POST /api/ia/gerar` (`postagem.textos`).
@router.post("/cortes/{corte_id}/sugestoes", operation_id="postagens_sugerir",
             response_model=schemas.SugestaoOut, deprecated=True,
             responses=_errors(400, 401, 403, 404, 502, 503, 504))
def sugerir(corte_id: UUID, body: schemas.SugestaoIn, actor: RequireUser, db: DbSession,
            client: Textos) -> schemas.SugestaoOut:
    row = service.sugerir(db, actor, corte_id, body, client)
    return schemas.SugestaoOut(sugestao=service.sugestao_out(row))


@router.get("/cortes/{corte_id}/sugestoes", operation_id="postagens_sugestoes",
            response_model=schemas.SugestoesList, responses=_errors(401, 403, 404),
            deprecated=True)
def list_sugestoes(corte_id: UUID, actor: RequireUser, db: DbSession) -> schemas.SugestoesList:
    return schemas.SugestoesList(items=service.list_sugestoes(db, corte_id))


# ---- postagens ----

# ---- calendário ----

@router.get("/calendario", operation_id="postagens_calendario",
            response_model=schemas.CalendarioOut, responses=_errors(400, 401, 403))
def calendario(
    actor: RequireUser, db: DbSession,
    de: Annotated[date, Query(description="Primeiro dia (local, APP_TZ)")],
    ate: Annotated[date, Query(description="Último dia, inclusive (até 62 dias)")],
    perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
    plataforma: Annotated[Platform | None, Query()] = None,
    conta_id: Annotated[UUID | None, Query(alias="contaId")] = None,
) -> schemas.CalendarioOut:
    return service.calendario(db, de, ate, perfil_id, plataforma, conta_id)


# ---- spec 014: destinos (contracts/http-api.md da 014, "Destinos") ----

def _destino(db: DbSession, destino) -> schemas.DestinoOut:
    return schemas.DestinoOut(destino=service.destino_out(db, destino))


# As rotas em lote vêm antes das `/destinos/{id}/…` (o caminho casaria com o id).

@router.post("/destinos/lote/aprovar", operation_id="destinos_lote_aprovar",
             response_model=schemas.LoteResultado, responses=_errors(400, 401, 403))
def lote_aprovar(body: schemas.LoteAprovarIn, actor: RequireOwner,
                 db: DbSession) -> schemas.LoteResultado:
    return service.lote_aprovar(db, actor, body)


@router.post("/destinos/lote/pedir-aprovacao", operation_id="destinos_lote_pedir_aprovacao",
             response_model=schemas.LoteResultado, responses=_errors(400, 401, 403))
def lote_pedir_aprovacao(body: schemas.LotePedirIn, actor: RequireUser,
                         db: DbSession) -> schemas.LoteResultado:
    return service.lote_pedir_aprovacao(db, actor, body)


@router.post("/conteudos/{conteudo_id}/destinos", operation_id="conteudos_add_destino",
             status_code=201, response_model=schemas.DestinoOut,
             responses=_errors(400, 401, 403, 404, 409))
def add_destino(conteudo_id: UUID, body: schemas.CreateDestinoIn, actor: RequireUser,
                db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.add_destino(db, actor, conteudo_id, body))


@router.get("/destinos/{destino_id}", operation_id="destinos_get",
            response_model=schemas.DestinoOut, responses=_errors(401, 403, 404))
def get_destino(destino_id: UUID, actor: RequireUser, db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.get_destino_or_404(db, destino_id))


@router.patch("/destinos/{destino_id}", operation_id="destinos_update",
              response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def update_destino(destino_id: UUID, body: schemas.UpdateDestinoIn, actor: RequireUser,
                   db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.update_textos(db, actor, destino_id, body))


@router.post("/destinos/{destino_id}/pedir-aprovacao", operation_id="destinos_pedir_aprovacao",
             response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def pedir_aprovacao(destino_id: UUID, body: schemas.PedirAprovacaoIn, actor: RequireUser,
                    db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.pedir_aprovacao(db, actor, destino_id, body.version, body.nota))


@router.post("/destinos/{destino_id}/aprovar", operation_id="destinos_aprovar",
             response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def aprovar(destino_id: UUID, body: VersionIn, actor: RequireOwner,
            db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.aprovar(db, actor, destino_id, body.version))


@router.post("/destinos/{destino_id}/recusar", operation_id="destinos_recusar",
             response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def recusar(destino_id: UUID, body: schemas.RecusarIn, actor: RequireOwner,
            db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.recusar(db, actor, destino_id, body.version, body.motivo))


@router.post("/destinos/{destino_id}/postado", operation_id="destinos_marcar_postado",
             response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def destino_postado(destino_id: UUID, body: schemas.PostadoIn, actor: RequireUser,
                    db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.marcar_postado(db, actor, destino_id, body.version,
                                               body.posted_url))


@router.post("/destinos/{destino_id}/archive", operation_id="destinos_archive",
             response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def archive_destino(destino_id: UUID, body: VersionIn, actor: RequireUser,
                    db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.archive_destino(db, actor, destino_id, body.version))


@router.post("/destinos/{destino_id}/restore", operation_id="destinos_restore",
             response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def restore_destino(destino_id: UUID, body: VersionIn, actor: RequireUser,
                    db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.restore_destino(db, actor, destino_id, body.version))


@router.get("/destinos/{destino_id}/versions", operation_id="destinos_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def destino_versions(destino_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return service.list_destino_versions(db, destino_id)


@router.post("/destinos/{destino_id}/revert", operation_id="destinos_revert",
             response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def revert_destino(destino_id: UUID, body: RevertIn, actor: RequireOwner,
                   db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.revert_destino(db, actor, destino_id, body.version,
                                               body.to_version))


@router.get("/contas/{conta_id}/modos", operation_id="contas_modos",
            response_model=schemas.ModosOut, responses=_errors(401, 403, 404))
def contas_modos(conta_id: UUID, actor: RequireUser, db: DbSession) -> schemas.ModosOut:
    return schemas.ModosOut(modos=[
        schemas.ModoInfo(modo=m.modo, disponivel=m.disponivel, motivo=m.motivo,
                         aviso=getattr(m, "aviso", None))
        for m in service.modos(db, conta_id)
    ])


# ---- spec 014: agendamentos ("Agendamentos") ----

@router.post("/agendamentos", operation_id="agendamentos_create", status_code=201,
             response_model=schemas.DestinoOut, responses={
                 200: {"description": "O destino já existia", "model": schemas.DestinoOut},
                 **_errors(400, 401, 403, 404, 409)})
def agendar(body: schemas.AgendarIn, actor: RequireUser, db: DbSession,
            response: Response) -> schemas.DestinoOut:
    destino, criou = service.agendar(db, actor, body)
    if not criou:
        response.status_code = 200
    return _destino(db, destino)


@router.patch("/destinos/{destino_id}/agendamento", operation_id="agendamentos_update",
              response_model=schemas.DestinoOut, responses=_errors(400, 401, 403, 404, 409))
def reagendar(destino_id: UUID, body: schemas.ReagendarIn, actor: RequireUser,
              db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.reagendar(db, actor, destino_id, body))


@router.post("/destinos/{destino_id}/enviar-agora", operation_id="destinos_enviar_agora",
             response_model=schemas.EnviarAgoraOut, responses=_errors(400, 401, 403, 404, 409))
def enviar_agora(destino_id: UUID, body: schemas.EnviarAgoraIn, actor: RequireHumanOwner,
                 db: DbSession) -> schemas.EnviarAgoraOut:
    """Só dono humano (princípio I): agenda para já; a trilha envia na volta seguinte."""
    destino, aviso = service.enviar_agora(db, actor, destino_id, body)
    return schemas.EnviarAgoraOut(destino=service.destino_out(db, destino), aviso=aviso)


@router.post("/destinos/{destino_id}/agendamento/cancelar",
             operation_id="agendamentos_cancelar", response_model=schemas.DestinoOut,
             responses=_errors(400, 401, 403, 404, 409))
def cancelar_agendamento(destino_id: UUID, body: VersionIn, actor: RequireUser,
                         db: DbSession) -> schemas.DestinoOut:
    return _destino(db, service.cancelar_agendamento(db, actor, destino_id, body.version))


@router.post("/agendamentos/lote/reagendar", operation_id="agendamentos_lote_reagendar",
             response_model=schemas.LoteResultado, responses=_errors(400, 401, 403))
def lote_reagendar(body: schemas.LoteReagendarIn, actor: RequireUser,
                   db: DbSession) -> schemas.LoteResultado:
    return service.lote_reagendar(db, actor, body)


@router.post("/agendamentos/lote/cancelar", operation_id="agendamentos_lote_cancelar",
             response_model=schemas.LoteResultado, responses=_errors(400, 401, 403))
def lote_cancelar(body: schemas.LoteCancelarIn, actor: RequireUser,
                  db: DbSession) -> schemas.LoteResultado:
    return service.lote_cancelar(db, actor, body)


@router.post("/agendamentos/sequencia/previa", operation_id="agendamentos_sequencia_previa",
             response_model=schemas.Previa, responses=_errors(400, 401, 403, 409))
def sequencia_previa(body: schemas.SequenciaIn, actor: RequireUser,
                     db: DbSession) -> schemas.Previa:
    return service.sequencia_previa(db, actor, body)


@router.post("/agendamentos/sequencia", operation_id="agendamentos_sequencia",
             response_model=schemas.LoteResultado, responses=_errors(400, 401, 403, 409))
def sequencia(body: schemas.SequenciaConfirmarIn, actor: RequireUser,
              db: DbSession) -> schemas.LoteResultado:
    return service.aplicar_sequencia(db, actor, body)
