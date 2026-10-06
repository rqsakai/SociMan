"""Sonda manual do endpoint MCP do SociMan (spec 009, quickstart §3) com o cliente do SDK `mcp`.

O token vem SÓ da variável de ambiente `SOCIMAN_MCP_TOKEN` (nunca de argumento) e nunca é
impresso. Exemplo, sem mostrar o token na tela:

    set -a; . ~/.config/openclaw/sociman-mcp.env; set +a
    SOCIMAN_MCP_TOKEN="$SOCIMAN_MCP_ANALISTA" \\
        uv run --directory apps/api python scripts/mcp_sonda.py --modo legacy --tool perfis_list

Saída: a versão de protocolo negociada, quantas tools o escopo vê e o resultado da `tools/call`
(resumido). `--url` padrão: `http://localhost:8180/mcp` (pelo edge).
"""

import argparse
import asyncio
import json
import os
import sys

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def _sondar(url: str, token: str, modo: str, tool: str | None, args: dict,
                  verificar_tls: bool | str) -> int:
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30,
                           verify=verificar_tls) as http,
        Client(streamable_http_client(url, http_client=http), mode=modo, cache=None) as c,
    ):
        print(f"protocolo negociado: {c.session.protocol_version}")
        tools = (await c.list_tools()).tools
        print(f"tools visíveis: {len(tools)}")
        if tool is None:
            return 0
        r = await c.call_tool(tool, args)
        if r.is_error:
            print(f"erro de execução: {r.content[0].text}")
            return 1
        texto = json.dumps(r.structured_content, ensure_ascii=False)
        print(f"{tool}: ok ({len(texto)} bytes) {texto[:400]}")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", default="http://localhost:8180/mcp")
    p.add_argument("--modo", default="legacy", help="legacy (2025-11-25), auto ou 2026-07-28")
    p.add_argument("--tool", help="uma tool para chamar depois do tools/list")
    p.add_argument("--args", default="{}", help="argumentos da tool em JSON")
    p.add_argument("--ca", help="CA da casa (PEM) para o https://192.168.86.47:8543/mcp")
    a = p.parse_args()
    token = os.environ.get("SOCIMAN_MCP_TOKEN", "")
    if not token.startswith("smcp_"):
        print("defina SOCIMAN_MCP_TOKEN (smcp_…) no ambiente; o token nunca vai em argumento",
              file=sys.stderr)
        return 2
    try:
        return asyncio.run(_sondar(a.url, token, a.modo, a.tool, json.loads(a.args),
                                   a.ca or True))
    except BaseException as exc:  # noqa: BLE001 — mostra só o tipo e a mensagem, sem token
        folha = exc
        while isinstance(folha, BaseExceptionGroup) and folha.exceptions:
            folha = folha.exceptions[0]
        print(f"falhou: {type(folha).__name__}: {str(folha).replace(token, 'smcp_***')}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
