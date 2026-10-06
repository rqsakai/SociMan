"""Registro de chamadas MCP (R8): tabela `mcp_chamadas`, só de inserção.

- `RegistroMiddleware` (ASGI, no app inteiro): toda requisição que passou pelo portão com um token
  MCP (`scope[portao.CHAMADA]`) vira uma linha **depois** da resposta, numa sessão própria (a
  linha sobrevive ao rollback da recusa, armadilha 8);
- `gravar`: usado também pelo servidor MCP para o que não chega à API (não autenticado, tool
  desconhecida, escopo, argumentos inválidos, interruptor).

O resumo dos argumentos tem só os parâmetros (caminho, query e corpo JSON): chaves sensíveis viram
`"***"`, strings ≤ 200 caracteres, o JSON inteiro ≤ 2 KB e nenhum `smcp_…` passa.
"""

import ipaddress
import json
import logging
import re
import time
import uuid
from typing import Any
from urllib.parse import parse_qsl

from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sociman_api.db import get_sessionmaker
from sociman_api.mcp import portao
from sociman_api.mcp.models import McpChamada, McpResultado, McpVia

log = logging.getLogger(__name__)

SENSIVEIS = ("token", "senha", "password", "authorization", "secret", "segredo", "hash")
STR_MAX = 200
JSON_MAX = 2048
CORPO_MAX = 64 * 1024  # o que o middleware guarda do corpo para o resumo e a entidade
_TOKEN_RE = re.compile(r"smcp_[A-Za-z0-9_-]+")
RECUSAS = {"somente_humano", "escopo_mcp", "mcp_desligado", "mcp_suspenso", "mcp_origem",
           "mcp_indisponivel"}


# ---- resumo dos argumentos ----

def _limpar(valor: Any, chave: str = "") -> Any:
    if any(s in chave.lower() for s in SENSIVEIS):
        return "***"
    if isinstance(valor, dict):
        return {str(k): _limpar(v, str(k)) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpar(v) for v in valor]
    if isinstance(valor, str):
        valor = _TOKEN_RE.sub("smcp_***", valor)
        return valor if len(valor) <= STR_MAX else valor[:STR_MAX] + "…"
    return valor


def resumo_args(args: dict[str, Any] | None) -> dict[str, Any]:
    """Argumentos mascarados e cortados (≤ 2 KB serializados)."""
    limpo = _limpar(args or {})
    if len(json.dumps(limpo, ensure_ascii=False, default=str)) <= JSON_MAX:
        return limpo
    out: dict[str, Any] = {"_truncado": True}
    for k, v in limpo.items():
        tentativa = {**out, k: v}
        if len(json.dumps(tentativa, ensure_ascii=False, default=str)) > JSON_MAX:
            continue
        out = tentativa
    return out


def resultado_de(status: int, codigo: str | None) -> McpResultado:
    if status == 401:
        return McpResultado.nao_autenticado
    if status == 429 or codigo == "mcp_limite":
        return McpResultado.limite
    if codigo in RECUSAS:
        return McpResultado.recusada
    return McpResultado.ok if status < 400 else McpResultado.erro


def _ip(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return str(ipaddress.ip_address(valor.split(",")[0].strip()))
    except ValueError:
        return None


def gravar(*, cliente_id: uuid.UUID | None, via: str, tool: str, metodo: str, rota: str,
           args: dict[str, Any] | None, resultado: McpResultado, status_http: int | None,
           codigo_erro: str | None, duracao_ms: int, escrita: bool,
           entidade_tipo: str | None = None, entidade_id: uuid.UUID | None = None,
           ip: str | None = None) -> None:
    """Insere uma linha numa sessão própria, já commitada. Falha do registro só vai para o log."""
    session = get_sessionmaker()()
    try:
        session.add(McpChamada(
            cliente_id=cliente_id, via=McpVia(via), tool=tool[:128], metodo=metodo, rota=rota,
            args_resumo=resumo_args(args), resultado=resultado, status_http=status_http,
            codigo_erro=codigo_erro, duracao_ms=max(0, duracao_ms), escrita=escrita,
            entidade_tipo=entidade_tipo, entidade_id=entidade_id, ip=_ip(ip)))
        session.commit()
    except Exception:
        session.rollback()
        log.exception("falha ao registrar a chamada MCP %s", tool)
    finally:
        session.close()


# ---- middleware ----

def _json(raw: bytes) -> Any:
    if not raw or len(raw) >= CORPO_MAX:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _entidade_id(corpo: Any) -> uuid.UUID | None:
    """O `id` do item na resposta de uma escrita (`{"destino": {"id": …}}`)."""
    if not isinstance(corpo, dict):
        return None
    for valor in corpo.values():
        if isinstance(valor, dict) and "id" in valor:
            try:
                return uuid.UUID(str(valor["id"]))
            except ValueError:
                return None
    return None


class RegistroMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return
        inicio = time.monotonic()
        pedido = bytearray()
        resposta = bytearray()
        status = 500

        async def receive_espiao() -> Message:
            msg = await receive()
            if msg["type"] == "http.request" and len(pedido) < CORPO_MAX:
                pedido.extend(msg.get("body", b"")[:CORPO_MAX])
            return msg

        async def send_espiao(msg: Message) -> None:
            nonlocal status
            if msg["type"] == "http.response.start":
                status = msg["status"]
            elif msg["type"] == "http.response.body" and len(resposta) < CORPO_MAX \
                    and scope.get(portao.CHAMADA) is not None:
                resposta.extend(msg.get("body", b"")[:CORPO_MAX])
            await send(msg)

        try:
            await self.app(scope, receive_espiao, send_espiao)
        finally:
            chamada: portao.Chamada | None = scope.get(portao.CHAMADA)
            if chamada is not None:
                await run_in_threadpool(self._gravar, scope, chamada, status, bytes(pedido),
                                        bytes(resposta), inicio)

    @staticmethod
    def _gravar(scope: Scope, chamada: "portao.Chamada", status: int, pedido: bytes,
                resposta: bytes, inicio: float) -> None:
        corpo = _json(resposta)
        codigo = None
        if status >= 400 and isinstance(corpo, dict) and isinstance(corpo.get("error"), dict):
            codigo = corpo["error"].get("code")
        args: dict[str, Any] = dict(scope.get("path_params") or {})
        args.update(parse_qsl(scope.get("query_string", b"").decode("latin-1")))
        enviado = _json(pedido)
        if isinstance(enviado, dict):
            args.update(enviado)
        resultado = resultado_de(status, codigo)
        entidade_id = (_entidade_id(corpo) if chamada.escrita and resultado == McpResultado.ok
                       else None)
        headers = dict(scope.get("headers") or [])
        ip = (headers.get(b"x-real-ip") or headers.get(b"x-forwarded-for") or b"").decode()
        gravar(cliente_id=chamada.cliente_id, via=chamada.via, tool=chamada.tool,
               metodo=chamada.metodo, rota=chamada.rota, args=args, resultado=resultado,
               status_http=status, codigo_erro=codigo,
               duracao_ms=int((time.monotonic() - inicio) * 1000), escrita=chamada.escrita,
               entidade_tipo=chamada.entidade if entidade_id else None, entidade_id=entidade_id,
               ip=ip or None)
