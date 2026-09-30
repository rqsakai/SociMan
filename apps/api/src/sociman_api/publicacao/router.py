"""Rotas da publicação (contracts/http-api.md da 015): conexão da conta, interruptor e execução
dos destinos.

Nomes neutros de rede (research R21): nenhum caminho nem `operationId` contém `tiktok`,
`publish` ou `share`; a rede aparece só no corpo. As rotas **H** usam `RequireHumanOwner`
(dono **e** sessão humana, R15) e **nunca** podem virar tool do MCP (009): o MCP pode, no
máximo, ler `GET /api/contas/{id}/conexao` e `GET /api/destinos/{id}/tentativas`.
Não existe rota DELETE (desconectar é um POST que apaga só a credencial).
"""

from collections.abc import Iterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from sociman_api.auth.deps import RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.schemas import Version, VersionIn, VersionsList
from sociman_api.perfis.service_perfis import user_refs
from sociman_api.postagem import schemas as postagem_schemas
from sociman_api.postagem import service as postagem_service
from sociman_api.publicacao import conexoes, registro, schemas, service

router = APIRouter(prefix="/api")


def cliente_rede() -> Iterator[Any]:
    """Cliente HTTP da rede (só TikTok na 015). Os testes trocam por um com o fake."""
    client = registro.get_cliente()
    try:
        yield client
    finally:
        client.close()


Cliente = Annotated[Any, Depends(cliente_rede)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- conexão da conta ----

@router.get("/contas/{conta_id}/conexao", operation_id="conexoes_get",
            response_model=schemas.ConexaoOut, responses=_errors(401, 403, 404))
def conexao_get(conta_id: UUID, actor: RequireUser, db: DbSession) -> schemas.ConexaoOut:
    conta = conexoes.get_conta_or_404(db, conta_id)
    return schemas.ConexaoOut(
        conexao=conexoes.conexao_out(db, conta, conexoes.conexao_viva(db, conta.id)))


@router.post("/contas/{conta_id}/conexao/iniciar", operation_id="conexoes_iniciar",
             response_model=schemas.IniciarOut, responses=_errors(400, 401, 403, 404, 409, 503))
def conexao_iniciar(conta_id: UUID, request: Request, actor: RequireHumanOwner,
                    db: DbSession) -> schemas.IniciarOut:
    # O edge repassa `Host` (sem porta): IP da casa → Web; localhost → Desktop (R1).
    return conexoes.iniciar(db, actor, conta_id, request.url.hostname)


@router.post("/conexoes/retorno", operation_id="conexoes_retorno",
             response_model=schemas.RetornoOut,
             responses=_errors(400, 401, 403, 404, 409, 502, 503))
def conexao_retorno(body: schemas.RetornoIn, actor: RequireHumanOwner, db: DbSession,
                    client: Cliente) -> schemas.RetornoOut:
    conexao, conta = conexoes.concluir_retorno(db, actor, body, client)
    return schemas.RetornoOut(conexao=conexoes.conexao_out(db, conta, conexao),
                              conta_id=conta.id, perfil_id=conta.perfil_id)


@router.post("/contas/{conta_id}/conexao/desconectar", operation_id="conexoes_desconectar",
             response_model=schemas.DesconectarOut, responses=_errors(400, 401, 403, 404, 409))
def conexao_desconectar(conta_id: UUID, body: schemas.DesconectarIn,
                        actor: RequireHumanOwner, db: DbSession,
                        client: Cliente) -> schemas.DesconectarOut:
    conta, em_atencao, anonimizadas = conexoes.desconectar(
        db, actor, conta_id, body.version, client, body.confirmo_anonimizar)
    metricas = schemas.MetricasAnonimizadas(videos=anonimizadas[0], fotos=anonimizadas[1]) \
        if anonimizadas is not None else None
    return schemas.DesconectarOut(conexao=conexoes.conexao_out(db, conta, None),
                                  agendamentos_em_atencao=em_atencao,
                                  metricas_anonimizadas=metricas)


@router.get("/contas/{conta_id}/conexao/criador", operation_id="conexoes_criador",
            response_model=schemas.CriadorOut,
            responses=_errors(401, 403, 404, 409, 429, 502))
def conexao_criador(conta_id: UUID, actor: RequireHumanOwner, db: DbSession,
                    client: Cliente) -> schemas.CriadorOut:
    return schemas.CriadorOut(criador=service.criador(db, actor, conta_id, client))


@router.get("/contas/{conta_id}/conexao/versions", operation_id="conexoes_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def conexao_versions(conta_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    rows = conexoes.versions(db, conta_id)
    users = user_refs(db, [r.actor_user_id for r in rows])
    return VersionsList(items=[
        Version(version=r.version, action=r.action,
                actor=users.get(r.actor_user_id) if r.actor_user_id else None,
                actor_kind=r.actor_kind, occurred_at=r.occurred_at,
                changed_fields=list(r.changed_fields), before=r.before, after=r.after,
                details=r.details)
        for r in rows
    ])


# ---- interruptor ----

@router.get("/publicacao/config", operation_id="publicacao_config_get",
            response_model=schemas.PublicacaoConfigOut, responses=_errors(401, 403))
def config_get(actor: RequireUser, db: DbSession) -> schemas.PublicacaoConfigOut:
    return schemas.PublicacaoConfigOut(config=service.config_out(db))


@router.put("/publicacao/config", operation_id="publicacao_config_update",
            response_model=schemas.PublicacaoConfigOut, responses=_errors(400, 401, 403, 409))
def config_update(body: schemas.PublicacaoConfigIn, actor: RequireHumanOwner,
                  db: DbSession) -> schemas.PublicacaoConfigOut:
    return schemas.PublicacaoConfigOut(config=service.config_update(db, actor, body))


@router.get("/publicacao/config/versions", operation_id="publicacao_config_versions",
            response_model=VersionsList, responses=_errors(401, 403))
def config_versions(actor: RequireUser, db: DbSession) -> VersionsList:
    return service.config_versions(db)


# ---- execução dos destinos ----

@router.get("/destinos/{destino_id}/tentativas", operation_id="destinos_tentativas",
            response_model=schemas.TentativasList, responses=_errors(401, 403, 404))
def destino_tentativas(destino_id: UUID, actor: RequireUser,
                       db: DbSession) -> schemas.TentativasList:
    return schemas.TentativasList(items=service.tentativas(db, destino_id))


@router.post("/destinos/{destino_id}/tentar-de-novo", operation_id="destinos_tentar_de_novo",
             response_model=postagem_schemas.DestinoOut,
             responses=_errors(400, 401, 403, 404, 409))
def destino_tentar_de_novo(destino_id: UUID, body: schemas.TentarDeNovoIn,
                           actor: RequireHumanOwner,
                           db: DbSession) -> postagem_schemas.DestinoOut:
    destino = service.tentar_de_novo(db, actor, destino_id, body.version,
                                     body.confirmo_que_nao_chegou)
    return postagem_schemas.DestinoOut(destino=postagem_service.destino_out(db, destino))


@router.post("/destinos/{destino_id}/confirmar-envio", operation_id="destinos_confirmar_envio",
             response_model=postagem_schemas.DestinoOut,
             responses=_errors(400, 401, 403, 404, 409))
def destino_confirmar_envio(destino_id: UUID, body: VersionIn, actor: RequireHumanOwner,
                            db: DbSession) -> postagem_schemas.DestinoOut:
    destino = service.confirmar_envio(db, actor, destino_id, body.version)
    return postagem_schemas.DestinoOut(destino=postagem_service.destino_out(db, destino))
