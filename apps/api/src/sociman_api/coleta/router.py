"""Rotas da coleta (contracts/http-api.md da 026): as rotas **C** do protocolo do coletor
(`RequireColetor`; o portão `coleta/portao.py` já decidiu tudo antes), a gestão **HO** (só dono
humano: clientes, config, aceite de risco, pausar, continuar) e a leitura **U** (estado, rodadas,
eventos, fila do dia; dono e membro).

Nenhuma rota tem "tiktok" no caminho nem no `operationId` (guarda FR-057); a rede é um valor.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from pydantic import TypeAdapter, ValidationError

from sociman_api.auth.deps import (
    RequireColetor,
    RequireHumanOwner,
    RequireUser,
    RequireUserOuColetor,
)
from sociman_api.coleta import fila_api, ingestao, portao, schemas, service
from sociman_api.coleta.models import EventoTipo
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope
from sociman_api.mercado.constantes import IMAGENS_POR_CHAMADA_MAX
from sociman_api.mercado.models import ColetaEstado, FilaEstado
from sociman_api.perfis.schemas import VersionsList

router = APIRouter(prefix="/api/coleta")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/fila", operation_id="coleta_fila", response_model=schemas.FilaOut,
            responses=_errors(401, 403, 426, 429, 503))
def fila(request: Request, actor: RequireColetor, db: DbSession,
         limite: Annotated[int, Query(ge=1, le=50)] = 40,
         simular: Annotated[bool, Query()] = False) -> schemas.FilaOut:
    """Entrega e reserva as tarefas do dia; com a coleta desligada responde vazia."""
    cliente = portao.cliente_de(actor, db)
    return fila_api.fila(db, cliente, limite, portao.ligada(request), simular=simular)


@router.post("/coletas", operation_id="coleta_coletas_abrir", status_code=201,
             response_model=schemas.ColetaOut, responses=_errors(401, 403, 409, 426, 429, 503))
def coletas_abrir(body: schemas.AbrirColetaIn, actor: RequireColetor, db: DbSession
                  ) -> schemas.ColetaOut:
    cliente = portao.cliente_de(actor, db)
    return ingestao.coleta_out(ingestao.abrir_rodada(db, cliente, body))


@router.post("/coletas/{coleta_id}/itens", operation_id="coleta_itens_enviar",
             response_model=schemas.ItensOut,
             responses=_errors(400, 401, 403, 404, 409, 413, 426, 429, 503))
def itens_enviar(coleta_id: uuid.UUID, body: schemas.ItensIn, request: Request,
                 actor: RequireColetor, db: DbSession) -> schemas.ItensOut:
    cliente = portao.cliente_de(actor, db)
    tamanho = request.headers.get("content-length")
    return ingestao.receber_itens(db, cliente, coleta_id, body,
                                  int(tamanho) if tamanho and tamanho.isdigit() else None)


@router.post("/coletas/{coleta_id}/imagens", operation_id="coleta_imagens_enviar",
             response_model=schemas.ImagensOut,
             responses=_errors(400, 401, 403, 404, 409, 413, 426, 429, 503, 507))
async def imagens_enviar(coleta_id: uuid.UUID, actor: RequireColetor, db: DbSession,
                         arquivos: Annotated[list[UploadFile], File()],
                         manifesto: Annotated[str, Form()]) -> schemas.ImagensOut:
    """Até 10 arquivos (cada ≤ 5 MB) e o `manifesto` JSON `[{sha256, tarefaId, origem}]`."""
    cliente = portao.cliente_de(actor, db)
    if len(arquivos) > IMAGENS_POR_CHAMADA_MAX:
        raise ApiError(413, "lote_grande", "Lote grande demais (máximo 10 imagens)")
    try:
        itens = TypeAdapter(list[schemas.ManifestoImagem]).validate_python(json.loads(manifesto))
    except (ValueError, ValidationError) as exc:
        raise ApiError(400, "entrada_invalida", "manifesto: inválido",
                       details={"field": "manifesto"}) from exc
    lidos = [(a.filename or "", await a.read()) for a in arquivos]
    return ingestao.receber_imagens(db, cliente, coleta_id, lidos, itens)


@router.post("/coletas/{coleta_id}/batimento", operation_id="coleta_batimento",
             response_model=schemas.BatimentoOut,
             responses=_errors(401, 403, 404, 409, 426, 429, 503))
def batimento(coleta_id: uuid.UUID, body: schemas.BatimentoIn, actor: RequireColetor,
              db: DbSession) -> schemas.BatimentoOut:
    cliente = portao.cliente_de(actor, db)
    return ingestao.batimento(db, cliente, coleta_id, body)


@router.post("/coletas/{coleta_id}/fim", operation_id="coleta_coletas_fechar",
             response_model=schemas.ColetaOut, responses=_errors(401, 403, 404, 426, 429, 503))
def coletas_fechar(coleta_id: uuid.UUID, body: schemas.FimIn, actor: RequireColetor,
                   db: DbSession) -> schemas.ColetaOut:
    cliente = portao.cliente_de(actor, db)
    return ingestao.coleta_out(ingestao.fechar_rodada(db, cliente, coleta_id, body))


@router.post("/eventos", operation_id="coleta_eventos_enviar", status_code=201,
             response_model=schemas.EventoOut,
             responses=_errors(400, 401, 403, 404, 426, 429, 503))
def eventos_enviar(body: schemas.EventoIn, actor: RequireColetor, db: DbSession
                   ) -> schemas.EventoOut:
    cliente = portao.cliente_de(actor, db)
    ev, coleta, notificado = ingestao.evento(db, cliente, body)
    cfg = ingestao.comum.config_atual(db)
    return schemas.EventoOut(evento_id=ev.id, coleta=ingestao.coleta_out(coleta) if coleta else None,
                             pausada_ate=cfg.pausada_ate, notificado=notificado)


@router.get("/coletas/{coleta_id}/bruto/{tarefa_id}", operation_id="coleta_bruto_link",
            response_model=schemas.BrutoLinkOut,
            responses=_errors(401, 403, 404, 426, 429, 503))
def bruto_link(coleta_id: uuid.UUID, tarefa_id: uuid.UUID, actor: RequireColetor,
               db: DbSession) -> schemas.BrutoLinkOut:
    cliente = portao.cliente_de(actor, db)
    return ingestao.link_bruto(db, cliente, coleta_id, tarefa_id)


# ---- gestão (HO): clientes ----

def _sem_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/clientes", operation_id="coleta_clientes_listar", response_model=schemas.ColetaClientesList,
            responses=_errors(401, 403))
def clientes_listar(actor: RequireHumanOwner, db: DbSession) -> schemas.ColetaClientesList:
    return schemas.ColetaClientesList(itens=service.listar_clientes(db))


@router.post("/clientes", operation_id="coleta_clientes_criar", status_code=201,
             response_model=schemas.ColetaClienteComToken, responses=_errors(400, 401, 403, 409))
def clientes_criar(body: schemas.CriarClienteIn, response: Response, actor: RequireHumanOwner,
                   db: DbSession) -> schemas.ColetaClienteComToken:
    """Cria o cliente e devolve o token **uma única vez**."""
    cliente, token = service.criar_cliente(db, actor, body)
    _sem_cache(response)
    return schemas.ColetaClienteComToken(cliente=service.cliente_out(db, cliente), token=token)


@router.get("/clientes/{cliente_id}", operation_id="coleta_clientes_detalhe",
            response_model=schemas.ColetaCliente, responses=_errors(401, 403, 404))
def clientes_detalhe(cliente_id: uuid.UUID, actor: RequireHumanOwner, db: DbSession
                     ) -> schemas.ColetaCliente:
    return service.cliente_out(db, service._cliente(db, cliente_id))


@router.patch("/clientes/{cliente_id}", operation_id="coleta_clientes_editar",
              response_model=schemas.ColetaCliente, responses=_errors(400, 401, 403, 404, 409))
def clientes_editar(cliente_id: uuid.UUID, body: schemas.EditarClienteIn,
                    actor: RequireHumanOwner, db: DbSession) -> schemas.ColetaCliente:
    return service.cliente_out(db, service.editar_cliente(db, actor, cliente_id, body))


@router.post("/clientes/{cliente_id}/rotacionar", operation_id="coleta_clientes_rotacionar",
             response_model=schemas.ColetaClienteComToken, responses=_errors(400, 401, 403, 404, 409))
def clientes_rotacionar(cliente_id: uuid.UUID, body: schemas.ColetaVersionIn, response: Response,
                        actor: RequireHumanOwner, db: DbSession) -> schemas.ColetaClienteComToken:
    cliente, token = service.rotacionar(db, actor, cliente_id, body.version)
    _sem_cache(response)
    return schemas.ColetaClienteComToken(cliente=service.cliente_out(db, cliente), token=token)


@router.post("/clientes/{cliente_id}/suspender", operation_id="coleta_clientes_suspender",
             response_model=schemas.ColetaCliente, responses=_errors(400, 401, 403, 404, 409))
def clientes_suspender(cliente_id: uuid.UUID, body: schemas.ColetaVersionIn, actor: RequireHumanOwner,
                       db: DbSession) -> schemas.ColetaCliente:
    return service.cliente_out(db, service.suspender(db, actor, cliente_id, body.version))


@router.post("/clientes/{cliente_id}/reativar", operation_id="coleta_clientes_reativar",
             response_model=schemas.ColetaCliente, responses=_errors(400, 401, 403, 404, 409))
def clientes_reativar(cliente_id: uuid.UUID, body: schemas.ColetaVersionIn, actor: RequireHumanOwner,
                      db: DbSession) -> schemas.ColetaCliente:
    return service.cliente_out(db, service.reativar(db, actor, cliente_id, body.version))


@router.post("/clientes/{cliente_id}/revogar", operation_id="coleta_clientes_revogar",
             response_model=schemas.ColetaCliente, responses=_errors(400, 401, 403, 404, 409))
def clientes_revogar(cliente_id: uuid.UUID, body: schemas.ColetaVersionIn, actor: RequireHumanOwner,
                     db: DbSession) -> schemas.ColetaCliente:
    """Final: o cliente fica na lista como revogado e nunca volta."""
    return service.cliente_out(db, service.revogar(db, actor, cliente_id, body.version))


@router.get("/clientes/{cliente_id}/versions", operation_id="coleta_clientes_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def clientes_versions(cliente_id: uuid.UUID, actor: RequireHumanOwner, db: DbSession
                      ) -> VersionsList:
    return service.versoes_cliente(db, cliente_id)


# ---- gestão (HO): configuração ----

@router.get("/config", operation_id="coleta_config_get", response_model=schemas.ColetaConfig,
            responses=_errors(401, 403))
def config_get(actor: RequireHumanOwner, db: DbSession) -> schemas.ColetaConfig:
    return service.config_out(db, service.comum.config_atual(db))


@router.put("/config", operation_id="coleta_config_put", response_model=schemas.ColetaConfig,
            responses=_errors(400, 401, 403, 409))
def config_put(body: schemas.ColetaConfigIn, actor: RequireHumanOwner, db: DbSession
               ) -> schemas.ColetaConfig:
    """Ligar sem aceite de risco → 409 `risco_nao_aceito`."""
    return service.config_out(db, service.atualizar_config(db, actor, body))


@router.post("/config/aceitar-risco", operation_id="coleta_config_aceitar_risco",
             response_model=schemas.ColetaConfig, responses=_errors(400, 401, 403, 409))
def config_aceitar_risco(body: schemas.AceitarRiscoIn, actor: RequireHumanOwner, db: DbSession
                         ) -> schemas.ColetaConfig:
    return service.config_out(db, service.aceitar_risco(db, actor, body))


@router.post("/config/pausar", operation_id="coleta_config_pausar",
             response_model=schemas.ColetaConfig, responses=_errors(400, 401, 403, 409))
def config_pausar(body: schemas.PausarIn, actor: RequireHumanOwner, db: DbSession
                  ) -> schemas.ColetaConfig:
    return service.config_out(db, service.pausar(db, actor, body))


@router.post("/config/continuar", operation_id="coleta_config_continuar",
             response_model=schemas.ColetaConfig, responses=_errors(400, 401, 403, 409))
def config_continuar(body: schemas.ContinuarIn, actor: RequireHumanOwner, db: DbSession
                     ) -> schemas.ColetaConfig:
    """Depois de resolver o captcha ou o login na janela do Chrome (FR-018)."""
    return service.config_out(db, service.continuar(db, actor, body))


@router.get("/config/versions", operation_id="coleta_config_versions",
            response_model=VersionsList, responses=_errors(401, 403))
def config_versions(actor: RequireHumanOwner, db: DbSession) -> VersionsList:
    return service.versoes_config(db)


@router.post("/config/revert", operation_id="coleta_config_revert",
             response_model=schemas.ColetaConfig, responses=_errors(400, 401, 403, 404, 409))
def config_revert(body: schemas.ColetaRevertIn, actor: RequireHumanOwner, db: DbSession
                  ) -> schemas.ColetaConfig:
    return service.config_out(db, service.reverter_config(db, actor, body))


# ---- leitura (U) ----

@router.get("/estado", operation_id="coleta_estado", response_model=schemas.EstadoColetaMercado,
            responses=_errors(401, 403))
def estado(actor: RequireUser, db: DbSession) -> schemas.EstadoColetaMercado:
    """O estado da coleta, calculado na hora (o que o membro vê e o card do cockpit)."""
    return service.estado(db)


@router.get("/coletas", operation_id="coleta_coletas_listar", response_model=schemas.ColetasList,
            responses=_errors(400, 401, 403))
def coletas_listar(actor: RequireUserOuColetor, db: DbSession,
                   estado: Annotated[ColetaEstado | None, Query()] = None,
                   de: Annotated[datetime | None, Query()] = None,
                   ate: Annotated[datetime | None, Query()] = None,
                   limite: Annotated[int, Query(ge=1, le=50)] = 20,
                   cursor: Annotated[str | None, Query()] = None) -> schemas.ColetasList:
    """As rodadas; o token do coletor (`reprocessar --desde`) só vê as do próprio cliente."""
    return service.listar_coletas(db, estado, de, ate, limite, cursor,
                                  cliente_id=actor.coleta_cliente_id)


@router.get("/coletas/{coleta_id}", operation_id="coleta_coletas_detalhe",
            response_model=schemas.ColetaDetalhe, responses=_errors(401, 403, 404))
def coletas_detalhe(coleta_id: uuid.UUID, actor: RequireUserOuColetor, db: DbSession,
                    itens_limite: Annotated[int, Query(alias="itensLimite", ge=1, le=1000)] = 200
                    ) -> schemas.ColetaDetalhe:
    return service.detalhe_coleta(db, coleta_id, itens_limite,
                                  cliente_id=actor.coleta_cliente_id)


@router.get("/eventos", operation_id="coleta_eventos_listar", response_model=schemas.EventosList,
            responses=_errors(400, 401, 403))
def eventos_listar(actor: RequireUser, db: DbSession,
                   tipo: Annotated[EventoTipo | None, Query()] = None,
                   de: Annotated[datetime | None, Query()] = None,
                   ate: Annotated[datetime | None, Query()] = None,
                   limite: Annotated[int, Query(ge=1, le=100)] = 50,
                   cursor: Annotated[str | None, Query()] = None) -> schemas.EventosList:
    return service.listar_eventos(db, tipo, de, ate, limite, cursor)


@router.get("/fila/hoje", operation_id="coleta_fila_hoje", response_model=schemas.FilaHojeOut,
            responses=_errors(401, 403))
def fila_hoje(actor: RequireUser, db: DbSession,
              estado: Annotated[FilaEstado | None, Query()] = None,
              tipo: Annotated[str | None, Query()] = None,
              perfil_id: Annotated[uuid.UUID | None, Query(alias="perfilId")] = None
              ) -> schemas.FilaHojeOut:
    """A fila do dia (o `perfilId` é o operacional da tarefa, não dono do dado)."""
    return service.fila_hoje(db, estado, tipo, perfil_id)
