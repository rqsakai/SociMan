"""Ponte da tool para a própria API, em processo (R3): `httpx.ASGITransport`.

A requisição passa por todas as dependências, validações, histórico e pelo portão, com o mesmo
Bearer do cliente e a marca `X-Sociman-Via: mcp` (o edge apaga a de fora, R9). O servidor MCP
não toca no banco nem tem regra de negócio (FR-011).

- 2xx: `structuredContent` = o corpo, mais o mesmo JSON em texto; acima de 256 KB, a lista
  principal é recortada com `truncado: true` e o aviso (FR-016); sem lista, vira erro;
- 4xx/5xx: `isError` com `"<code>: <mensagem>"` e `{code, message, status, detalhes?}`
  (FR-013; o 409 `version_conflict` traz `versaoAtual`, o 429 traz `retryAfterS`).
"""

import json
from typing import Any
from urllib.parse import quote

import httpx
import mcp_types as types
from fastapi import FastAPI

from sociman_api.mcp.ferramentas import Operacao

LIMITE_BYTES = 256 * 1024
AVISO_TRUNCADO = "resultado truncado, use filtros ou a próxima página"
BASE = "http://sociman.interno"


def _tamanho(corpo: Any) -> int:
    return len(json.dumps(corpo, ensure_ascii=False, default=str).encode())


def recortar(corpo: Any) -> tuple[Any, bool]:
    """`(corpo, cabe)`. Recorta a maior lista do topo até caber em 256 KB."""
    if _tamanho(corpo) <= LIMITE_BYTES:
        return corpo, True
    if not isinstance(corpo, dict):
        return corpo, False
    listas = [k for k, v in corpo.items() if isinstance(v, list) and v]
    if not listas:
        return corpo, False
    chave = max(listas, key=lambda k: _tamanho(corpo[k]))
    itens = corpo[chave]
    baixo, alto = 0, len(itens)
    while baixo < alto:  # o maior prefixo que cabe
        meio = (baixo + alto + 1) // 2
        teste = {**corpo, chave: itens[:meio], "truncado": True, "aviso": AVISO_TRUNCADO}
        if _tamanho(teste) <= LIMITE_BYTES:
            baixo = meio
        else:
            alto = meio - 1
    out = {**corpo, chave: itens[:baixo], "truncado": True, "aviso": AVISO_TRUNCADO}
    return out, _tamanho(out) <= LIMITE_BYTES


def erro(code: str, message: str, status: int | None = None,
         detalhes: dict[str, Any] | None = None) -> types.CallToolResult:
    estruturado: dict[str, Any] = {"code": code, "message": message}
    if status is not None:
        estruturado["status"] = status
    if detalhes:
        estruturado["detalhes"] = detalhes
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=f"{code}: {message}")],
        structured_content=estruturado, is_error=True)


def _requisicao(op: Operacao, args: dict[str, Any]) -> tuple[str, dict[str, Any], Any]:
    caminho = op.caminho
    for nome in op.path_params:
        caminho = caminho.replace("{" + nome + "}", quote(str(args[nome]), safe=""))
    query = {k: args[k] for k in op.query_params if k in args and args[k] is not None}
    if op.limite_param and op.limite_param not in query:
        query[op.limite_param] = op.definicao["inputSchema"]["properties"][op.limite_param][
            "default"]
    corpo = {k: args[k] for k in op.corpo if k in args}
    return caminho, query, corpo if op.corpo else None


async def chamar(app: FastAPI, token: str, op: Operacao, args: dict[str, Any]
                 ) -> types.CallToolResult:
    caminho, query, corpo = _requisicao(op, args)
    headers = {"Authorization": f"Bearer {token}", "X-Sociman-Via": "mcp",
               "Accept": "application/json"}
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 0))
    async with httpx.AsyncClient(transport=transport, base_url=BASE, timeout=60) as client:
        resposta = await client.request(op.metodo, caminho, params=query, json=corpo,
                                        headers=headers)
    try:
        dados = resposta.json()
    except ValueError:
        dados = None
    if resposta.status_code >= 400:
        err = (dados or {}).get("error") if isinstance(dados, dict) else None
        if not isinstance(err, dict):
            return erro("erro_http", f"A API respondeu {resposta.status_code}",
                        resposta.status_code)
        return erro(str(err.get("code")), str(err.get("message")), resposta.status_code,
                    err.get("details"))
    if dados is None:
        return erro("resposta_invalida", "A API não devolveu JSON", resposta.status_code)
    dados, cabe = recortar(dados)
    if not cabe:
        return erro("resposta_grande", AVISO_TRUNCADO, resposta.status_code)
    texto = json.dumps(dados, ensure_ascii=False)
    return types.CallToolResult(content=[types.TextContent(type="text", text=texto)],
                                structured_content=dados if isinstance(dados, dict) else None)
