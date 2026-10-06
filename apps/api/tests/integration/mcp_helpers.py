"""Apoio dos testes da spec 009: clientes MCP pela API, interruptor ligado e um cliente MCP do
SDK `mcp`, em processo (`httpx2.ASGITransport`), nas duas eras do protocolo.

Os tokens nascem no próprio teste e nunca são impressos nem gravados em arquivo.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from sociman_api.main import app

BASE = "http://testserver"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                   "clientInfo": {"name": "teste", "version": "1"}}}


class Segredo(str):
    """O token como `str`, mas mascarado no `repr` (o pytest mostra `repr` nas falhas)."""

    def __repr__(self) -> str:
        return "'smcp_***'"


class Cabecalhos(dict):
    def __repr__(self) -> str:
        return "{'Authorization': 'Bearer smcp_***'}"


def criar_cliente(client, h, nome: str = "Caçador", escopo: str = "leitura",
                  **extra) -> tuple[dict, str]:
    r = client.post("/api/mcp/clientes", headers=h, json={"nome": nome, "escopo": escopo, **extra})
    assert r.status_code == 201, r.status_code
    return r.json()["cliente"], Segredo(r.json()["token"])


def ligar(client, h, mcp_habilitado) -> None:
    """Os dois níveis do interruptor ligados (o `.env` por override, a tela pela API)."""
    mcp_habilitado(True)
    atual = client.get("/api/mcp/config", headers=h).json()
    if not atual["habilitado"]:
        r = client.put("/api/mcp/config", headers=h,
                       json={"habilitado": True, "version": atual["version"]})
        assert r.status_code == 200, r.text


def bearer(token: str) -> dict[str, str]:
    return Cabecalhos(Authorization=f"Bearer {token}")


def com_mcp(token: str, fn: Callable[[Client], Awaitable[Any]], modo: str = "legacy") -> Any:
    """Roda `fn(client)` com um cliente MCP conectado ao `/mcp` do app, em processo.

    `modo="legacy"` faz o `initialize` da 2025-11-25 (o OpenClaw); `"2026-07-28"` adota a versão
    moderna direto; `"auto"` sonda o `server/discover`."""

    async def _run() -> Any:
        transporte = httpx2.ASGITransport(app=app)
        async with (
            httpx2.AsyncClient(transport=transporte, base_url=BASE, headers=bearer(token),
                               timeout=30) as http,
            Client(streamable_http_client(f"{BASE}/mcp", http_client=http), mode=modo,
                   cache=None) as c,
        ):
            return await fn(c)

    try:
        return anyio.run(_run)
    except BaseExceptionGroup as grupo:  # as task groups do SDK embrulham o erro
        folha: BaseException = grupo
        while isinstance(folha, BaseExceptionGroup) and len(folha.exceptions) == 1:
            folha = folha.exceptions[0]
        raise folha from None


def post_mcp(client, token: str | None, corpo: dict, versao: str = "2025-11-25",
             **headers) -> Any:
    """Um POST JSON-RPC cru no `/mcp` (para os casos de borda do wrapper)."""
    h = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": versao,
         **headers}
    if token is not None:
        h.update(bearer(token))
    return client.post("/mcp", headers=h, json=corpo)
