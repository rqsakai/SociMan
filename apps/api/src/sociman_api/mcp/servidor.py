"""Endpoint MCP `/mcp` (R1, R3, R10; contracts/mcp.md): Streamable HTTP sem estado.

Antes do SDK, um wrapper ASGI confere, nesta ordem:

1. `Origin` fora de `MCP_ORIGENS_PERMITIDAS` → 403 (antes de autenticar);
2. credencial na query string → 400; sem Bearer `smcp_` válido → 401 + `WWW-Authenticate:
   Bearer` (sem metadados OAuth);
3. interruptor desligado → 503 "acesso MCP desligado pelo dono"; cliente revogado ou vencido →
   401; suspenso → 403.

Depois, o `Server` de baixo nível do SDK `mcp` atende as duas eras do protocolo (`initialize`
da 2025-11-25 e `server/discover` da 2026-07-28), só com a capacidade `tools`. Cada requisição
usa um `StreamableHTTPSessionManager` próprio (sem estado, respostas JSON): nada fica entre
requisições, e o app não precisa de lifespan.

`tools/list` devolve as tools do escopo do cliente; `tools/call` valida os argumentos contra o
`inputSchema` e chama a API pela ponte (que passa de novo pelo portão).
"""

import contextvars
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

import jsonschema
import mcp_types as types
from fastapi import FastAPI
from mcp.server import Server
from mcp.server.context import ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.exceptions import MCPError
from mcp_types import INVALID_PARAMS
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.types import Receive, Scope, Send

from sociman_api.config import get_settings
from sociman_api.db import get_sessionmaker
from sociman_api.mcp import ferramentas, mapa, ponte, portao, registro
from sociman_api.mcp.models import McpResultado

DESCONHECIDA = "tool desconhecida"
QUERY_PROIBIDA = ("token", "access_token", "authorization", "api_key", "key")
ROTA = "POST /mcp"


@dataclass(frozen=True)
class _Contexto:
    app: FastAPI
    cliente: portao.Cliente
    token: str
    ip: str | None


_atual: contextvars.ContextVar[_Contexto] = contextvars.ContextVar("sociman_mcp_cliente")


def _versao_api() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("sociman-api")
    except PackageNotFoundError:  # pragma: no cover
        return "0"


def _registrar(ctx: _Contexto, tool: str, args: dict[str, Any] | None,
               resultado: McpResultado, codigo: str | None, inicio: float,
               escrita: bool = False) -> None:
    registro.gravar(cliente_id=ctx.cliente.id, via="mcp", tool=tool, metodo="POST",
                    rota=ROTA, args=args, resultado=resultado, status_http=None,
                    codigo_erro=codigo, duracao_ms=int((time.monotonic() - inicio) * 1000),
                    escrita=escrita, ip=ctx.ip)


async def _listar(ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
                  ) -> types.ListToolsResult:
    atual = _atual.get()
    defs = ferramentas.definicoes(atual.app, atual.cliente.escopo)
    return types.ListToolsResult(tools=[types.Tool.model_validate(d) for d in defs])


def _validar(schema: dict[str, Any], args: dict[str, Any]) -> list[str]:
    validador = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
    erros = []
    for e in sorted(validador.iter_errors(args), key=lambda e: list(e.absolute_path)):
        campo = ".".join(str(p) for p in e.absolute_path) or "(argumentos)"
        erros.append(f"{campo}: {e.message}")
    return erros


async def _chamar(ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
                  ) -> types.CallToolResult:
    atual = _atual.get()
    inicio = time.monotonic()
    nome = params.name
    args = dict(params.arguments or {})
    op = ferramentas.catalogo(atual.app).get(nome)
    if op is None:  # inexistente, PROIBIDA ou FORA: erro de protocolo
        await run_in_threadpool(_registrar, atual, nome, args, McpResultado.recusada,
                                "tool_desconhecida", inicio)
        raise MCPError(INVALID_PARAMS, f"{DESCONHECIDA}: {nome}")
    if not mapa.permitida(op.tool, atual.cliente.escopo):
        await run_in_threadpool(_registrar, atual, nome, args, McpResultado.recusada,
                                "escopo_mcp", inicio, op.tool.escrita)
        return ponte.erro("escopo_mcp", "escopo insuficiente", 403)
    erros = _validar(op.definicao["inputSchema"], args)
    if erros:
        await run_in_threadpool(_registrar, atual, nome, args, McpResultado.erro,
                                "validation_error", inicio, op.tool.escrita)
        return ponte.erro("validation_error", "Argumentos inválidos: " + "; ".join(erros),
                          400, {"campos": erros})
    return await ponte.chamar(atual.app, atual.token, op, args)


def _servidor() -> Server:
    return Server("sociman", version=_versao_api(), title="SociMan",
                  instructions="Leia o estado da agência e deixe propostas para o dono. "
                               "Aprovar, agendar e publicar são atos do dono.",
                  on_list_tools=_listar, on_call_tool=_chamar)


_SERVER = _servidor()


async def _json_rpc_erro(send: Send, status: int, mensagem: str, code: int = -32600,
                         headers: dict[str, str] | None = None) -> None:
    corpo = json.dumps({"jsonrpc": "2.0", "id": None,
                        "error": {"code": code, "message": mensagem}}).encode()
    cabecalhos = [(b"content-type", b"application/json"),
                  (b"content-length", str(len(corpo)).encode())]
    cabecalhos += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": cabecalhos})
    await send({"type": "http.response.body", "body": corpo})


def _autenticar(token: str) -> tuple[portao.Cliente | None, Any, bool]:
    """`(cliente, cliente_id_do_registro, interruptor_ligado)` (síncrono: roda em thread)."""
    cliente, cliente_id = portao.identificar(token)
    session = get_sessionmaker()()
    try:
        ligado = portao.interruptor_ligado(session)
    finally:
        session.close()
    return cliente, cliente_id, ligado


class Endpoint:
    """ASGI do `/mcp`: as guardas do wrapper e, depois, o transporte do SDK."""

    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            return
        request = Request(scope)
        inicio = time.monotonic()
        ip = request.headers.get("x-real-ip") or (request.client.host if request.client
                                                   else None)
        origem = request.headers.get("origin")
        if origem and origem not in get_settings().mcp_origens_permitidas:
            await _json_rpc_erro(send, 403, "Origem não permitida")
            return
        query = parse_qsl(scope.get("query_string", b"").decode("latin-1"))
        if any(k.lower() in QUERY_PROIBIDA or v.startswith("smcp_") for k, v in query):
            await _json_rpc_erro(send, 400, "Mande a credencial só no cabeçalho Authorization")
            return
        token = portao.bearer_token(request)
        if not portao.e_token_mcp(token):
            await _json_rpc_erro(send, 401, "Não autenticado",
                                 headers={"WWW-Authenticate": "Bearer"})
            return
        cliente, cliente_id, ligado = await run_in_threadpool(_autenticar, token)

        def anotar(resultado: McpResultado, codigo: str, status: int) -> None:
            registro.gravar(cliente_id=cliente_id, via="mcp", tool="(protocolo)",
                            metodo=request.method, rota=f"{request.method} /mcp", args=None,
                            resultado=resultado, status_http=status, codigo_erro=codigo,
                            duracao_ms=int((time.monotonic() - inicio) * 1000), escrita=False,
                            ip=ip)

        recusa = None
        if cliente is None:
            recusa = (McpResultado.nao_autenticado, "unauthorized", 401, "Não autenticado")
        elif not ligado:
            recusa = (McpResultado.recusada, "mcp_desligado", 503, portao.DESLIGADO.lower())
        elif (erro := portao.situacao(cliente)) is not None:
            recusa = ((McpResultado.nao_autenticado, "unauthorized", 401, "Não autenticado")
                      if erro.status == 401 else
                      (McpResultado.recusada, erro.code, erro.status, erro.message))
        if recusa is not None:
            resultado, codigo, status, mensagem = recusa
            await run_in_threadpool(anotar, resultado, codigo, status)
            headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
            await _json_rpc_erro(send, status, mensagem, headers=headers)
            return
        assert cliente is not None
        token_ctx = _atual.set(_Contexto(self.app, cliente, token, ip))
        try:
            manager = StreamableHTTPSessionManager(app=_SERVER, json_response=True,
                                                   stateless=True, max_request_body_size=1 << 20)
            async with manager.run():
                await manager.handle_request(scope, receive, send)
        finally:
            _atual.reset(token_ctx)


def montar(app: FastAPI) -> None:
    """Rota `/mcp` (sem barra no fim, fora do OpenAPI e fora de `/api`)."""
    app.add_route("/mcp", Endpoint(app), include_in_schema=False)
