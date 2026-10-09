"""T031 (US2): o endpoint `/mcp` com o cliente do SDK `mcp`, em processo, nas duas eras do
protocolo (2025-11-25 do OpenClaw e 2026-07-28), e as guardas do wrapper."""

import pytest
from mcp.shared.exceptions import MCPError

from integration.mcp_helpers import INIT, bearer, com_mcp, criar_cliente, ligar, post_mcp
from integration.postagem_helpers import criar_perfil, dono  # noqa: F401
from sociman_api.mcp import mapa

LEITURA = sorted(n for n, t in mapa.TOOLS.items() if t.escopo == "leitura")
TODAS = sorted(mapa.TOOLS)


@pytest.fixture
def leitor(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, "Analista", "leitura")
    return token


@pytest.fixture
def propositor(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, "Caçador", "propostas")
    return token


def test_contagem_do_mapa():
    # spec 010: +8 leituras de cena; spec 013: +2 do registro de importações da agência
    # spec 022: +1; spec 023: +7; spec 012: +3 leituras de produto; spec 025: +3 de vozes
    assert len(LEITURA) == 62 + 8 + 2 + 1 + 7 + 3 + 3 + 6 and \
        len(TODAS) == 67 + 8 + 2 + 1 + 7 + 3 + 3 + 6


@pytest.mark.parametrize("modo", ["legacy", "2026-07-28", "auto"])
def test_tools_list_por_escopo_nas_duas_eras(leitor, propositor, modo):
    async def nomes(c):
        return [t.name for t in (await c.list_tools()).tools]

    assert com_mcp(leitor, nomes, modo) == LEITURA
    assert com_mcp(propositor, nomes, modo) == TODAS


def test_versao_negociada(leitor):
    async def versao(c):
        return c.session.protocol_version

    assert com_mcp(leitor, versao, "legacy") == "2025-11-25"
    assert com_mcp(leitor, versao, "auto") == "2026-07-28"


def test_tools_tem_descricao_e_anotacoes(leitor):
    async def tools(c):
        return (await c.list_tools()).tools

    for t in com_mcp(leitor, tools):
        assert len(t.description or "") >= 20 and "terceiros" in t.description
        assert t.annotations.read_only_hint is True and t.input_schema["type"] == "object"


@pytest.mark.parametrize("modo", ["legacy", "2026-07-28"])
def test_call_de_leitura(client, dono, leitor, modo):  # noqa: F811
    _, h = dono
    criar_perfil(client, h, "Perfil Lido")

    async def chamar(c):
        return await c.call_tool("perfis_list", {})

    r = com_mcp(leitor, chamar, modo)
    assert not r.is_error
    assert [p["name"] for p in r.structured_content["items"]] == ["Perfil Lido"]


def test_sem_token_401(client):
    r = client.post("/mcp", json=INIT)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_token_invalido_401(client, leitor):
    r = post_mcp(client, "smcp_aaaaaaaa_" + "x" * 43, INIT)
    assert r.status_code == 401


def test_token_na_query_400(client, leitor):
    r = client.post(f"/mcp?token={leitor}", json=INIT, headers=bearer(leitor))
    assert r.status_code == 400


def test_origin_403(client, leitor):
    r = post_mcp(client, leitor, INIT, Origin="http://evil.example")
    assert r.status_code == 403


def test_interruptor_desligado_503(client, dono, leitor, mcp_habilitado):  # noqa: F811
    mcp_habilitado(False)
    r = post_mcp(client, leitor, INIT)
    assert r.status_code == 503
    assert "desligado pelo dono" in r.json()["error"]["message"]


def test_get_e_delete_nao_servem_stream(client, leitor):
    for metodo in ("GET", "DELETE"):
        r = client.request(metodo, "/mcp", headers={**bearer(leitor),
                                                    "MCP-Protocol-Version": "2026-07-28"})
        assert r.status_code in (400, 405), (metodo, r.status_code)


@pytest.mark.parametrize("nome", ["nao_existe", "destinos_aprovar", "kit_update"])
def test_tool_desconhecida_e_erro_de_protocolo(propositor, nome):
    async def chamar(c):
        return await c.call_tool(nome, {})

    with pytest.raises(MCPError) as exc:
        com_mcp(propositor, chamar)
    assert exc.value.code == -32602 and "tool desconhecida" in exc.value.message


def test_escrita_com_escopo_leitura(leitor):
    async def chamar(c):
        return await c.call_tool("anotacoes_create", {"alvoTipo": "perfil",
                                                      "alvoId": "00000000-0000-0000-0000-000000000000",
                                                      "texto": "oi"})

    r = com_mcp(leitor, chamar)
    assert r.is_error and r.structured_content["code"] == "escopo_mcp"
    assert "escopo insuficiente" in r.content[0].text


def test_argumentos_invalidos_ou_extras(leitor):
    async def chamar(c):
        return await c.call_tool("perfis_get", {"perfil_id": "x", "aprovar": True})

    r = com_mcp(leitor, chamar)
    assert r.is_error and r.structured_content["code"] == "validation_error"
    campos = " ".join(r.structured_content["detalhes"]["campos"])
    assert "aprovar" in campos and "perfil_id" in campos
