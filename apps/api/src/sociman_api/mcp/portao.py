"""Portão da API para tokens MCP (R5): vale para **qualquer** requisição com `Bearer smcp_…`,
venha pela ponte do `/mcp` ou direto na API (um agente com `exec` e `curl`).

Ordem das recusas (contracts/http-api.md, "Recusas do portão"):

1. credencial que não confere → 401 `unauthorized` (mensagem neutra);
2. interruptor desligado (`MCP_HABILITADO` ou o botão da tela) → 403 `mcp_desligado`;
3. cliente revogado ou vencido → 401; suspenso → 403 `mcp_suspenso`;
4. `Origin` presente (navegador) → 403 `mcp_origem`;
5. operação em `PROIBIDAS` → 403 `somente_humano` + evento `publicacao_recusada`; fora de
   `TOOLS` ou do escopo → 403 `escopo_mcp`;
6. limites (R7) → 429 `mcp_limite` (ou 503 `mcp_indisponivel` sem Redis).

O portão roda como dependência global do app (`dependencia`), antes de qualquer validação da
rota, e deixa em `request.scope[CHAMADA]` o que o registro (`registro.py`) grava depois.
Usa sessões próprias: a recusa não depende do commit da requisição (armadilha 8).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import or_, select, update

from sociman_api.auth.deps import (
    SOMENTE_HUMANO,
    Actor,
    _unauthorized,
    bearer_token,
    registrar_recusa,
)
from sociman_api.auth.events import record_event
from sociman_api.config import get_settings
from sociman_api.db import get_sessionmaker
from sociman_api.errors import ApiError
from sociman_api.mcp import credenciais, limites, mapa
from sociman_api.mcp.models import McpCliente, McpConfig, McpSituacao

log = logging.getLogger(__name__)

CHAMADA = "sociman.mcp.chamada"  # chave no scope ASGI (lida pelo registro)
_ATOR = "sociman.mcp.ator"
VIA_HEADER = "x-sociman-via"  # só a ponte em processo manda; o edge apaga o de fora (R9)
DESLIGADO = "Acesso MCP desligado pelo dono"
SUSPENSO = "Este cliente MCP está suspenso pelo dono"
ORIGEM = "Token de agente não vale em navegador"
ESCOPO = "Escopo insuficiente: esta operação não está disponível para este cliente"
USO_INTERVALO = timedelta(minutes=1)


@dataclass
class Chamada:
    """O que o registro precisa saber de uma requisição com token MCP."""

    via: str
    tool: str
    metodo: str
    rota: str
    escrita: bool
    entidade: str | None
    cliente_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Cliente:
    """Dados do cliente que o portão e o servidor MCP usam (sem hash)."""

    id: uuid.UUID
    nome: str
    escopo: str
    situacao: McpSituacao
    expira_em: datetime | None
    limite_por_minuto: int
    limite_escritas_dia: int
    ultimo_uso_em: datetime | None

    @classmethod
    def de(cls, c: McpCliente) -> "Cliente":
        return cls(c.id, c.nome, c.escopo.value, c.situacao, c.expira_em, c.limite_por_minuto,
                   c.limite_escritas_dia, c.ultimo_uso_em)

    def ator(self) -> Actor:
        return Actor(kind="mcp_client", mcp_client_id=self.id, mcp_escopo=self.escopo)


def e_token_mcp(token: str | None) -> bool:
    return bool(token) and token.startswith(credenciais.PREFIXO)


def interruptor_ligado(db) -> bool:
    if not get_settings().mcp_habilitado:
        return False
    cfg = db.get(McpConfig, 1)
    return bool(cfg is not None and cfg.habilitado)


def identificar(token: str) -> tuple[Cliente | None, uuid.UUID | None]:
    """`(cliente, cliente_id_do_registro)`: o cliente quando a credencial confere; senão None e,
    se o `<id>` existe (segredo errado), o id para o registro e o evento `mcp_auth_falhou`."""
    session = get_sessionmaker()()
    try:
        cliente = credenciais.verificar(session, token)
        if cliente is not None:
            return Cliente.de(cliente), cliente.id
        token_id = credenciais.token_id_de(token)
        cliente_id = None
        if token_id is not None:
            cliente_id = session.scalar(select(McpCliente.id)
                                        .where(McpCliente.token_id == token_id))
        if cliente_id is not None:
            record_event(session, "mcp_auth_falhou", "denied", Actor(kind="anonymous"),
                         details={"clienteId": str(cliente_id), "credencial": token_id})
            session.commit()
        return None, cliente_id
    finally:
        session.close()


def situacao(cliente: Cliente) -> ApiError | None:
    """A recusa pela situação do cliente (revogado/vencido → 401; suspenso → 403)."""
    if cliente.situacao == McpSituacao.revogado or (
            cliente.expira_em is not None and cliente.expira_em <= datetime.now(UTC)):
        return _unauthorized()
    if cliente.situacao == McpSituacao.suspenso:
        return ApiError(403, "mcp_suspenso", SUSPENSO)
    return None


def marcar_uso(cliente: Cliente) -> None:
    """`ultimo_uso_em` no máximo 1 vez por minuto (sem mexer no `updated_at` nem na versão)."""
    agora = datetime.now(UTC)
    if cliente.ultimo_uso_em is not None and agora - cliente.ultimo_uso_em < USO_INTERVALO:
        return
    session = get_sessionmaker()()
    try:
        session.execute(
            update(McpCliente)
            .where(McpCliente.id == cliente.id,
                   or_(McpCliente.ultimo_uso_em.is_(None),
                       McpCliente.ultimo_uso_em < agora - USO_INTERVALO))
            .values(ultimo_uso_em=agora, updated_at=McpCliente.updated_at))
        session.commit()
    except Exception:  # o uso é informativo: a chamada segue
        session.rollback()
        log.exception("falha ao marcar o último uso do cliente MCP")
    finally:
        session.close()


def _chamada(request: Request) -> Chamada:
    route = request.scope.get("route")
    op = getattr(route, "unique_id", None) or request.url.path
    tool = mapa.TOOLS.get(op)
    escrita = tool.escrita if tool is not None else request.method not in ("GET", "HEAD")
    rota = f"{request.method} {getattr(route, 'path', None) or request.url.path}"
    via = "mcp" if request.headers.get(VIA_HEADER) == "mcp" else "api"
    return Chamada(via=via, tool=op, metodo=request.method, rota=rota, escrita=escrita,
                   entidade=tool.entidade if tool is not None else None)


def _decidir(request: Request, token: str) -> Actor:
    chamada = _chamada(request)
    request.scope[CHAMADA] = chamada
    cliente, chamada.cliente_id = identificar(token)
    if cliente is None:
        raise _unauthorized()
    session = get_sessionmaker()()
    try:
        ligado = interruptor_ligado(session)
    finally:
        session.close()
    if not ligado:
        raise ApiError(403, "mcp_desligado", DESLIGADO)
    if (erro := situacao(cliente)) is not None:
        raise erro
    if request.headers.get("origin"):
        raise ApiError(403, "mcp_origem", ORIGEM)
    actor = cliente.ator()
    classe = mapa.classificar(chamada.tool)
    if classe == "proibida":
        params = request.path_params
        registrar_recusa(actor, chamada.rota, request, params.get("conta_id"),
                         params.get("destino_id"))
        raise ApiError(403, "somente_humano", SOMENTE_HUMANO)
    tool = mapa.TOOLS.get(chamada.tool)
    if tool is None or not mapa.permitida(tool, cliente.escopo):
        raise ApiError(403, "escopo_mcp", ESCOPO)
    limites.verificar(cliente.id, cliente.limite_por_minuto, cliente.limite_escritas_dia,
                      tool.escrita)
    marcar_uso(cliente)
    return actor


def ator(request: Request) -> Actor:
    """O ator `mcp_client` da requisição (decidido uma vez só: os limites contam uma vez)."""
    cached = request.scope.get(_ATOR)
    if cached is not None:
        return cached
    token = bearer_token(request) or ""
    actor = _decidir(request, token)
    request.scope[_ATOR] = actor
    return actor


def dependencia(request: Request) -> None:
    """Dependência global do app: passa todo token MCP pelo portão, mesmo em rota sem ator
    (login, health, mídia por link), antes da validação dos parâmetros."""
    if e_token_mcp(bearer_token(request)):
        ator(request)
