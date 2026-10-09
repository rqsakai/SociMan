"""Produtos pelo MCP (spec 012, T044, US6, R14): o cliente "só leitura" lista os aprovados (o
padrão da tool) e lê a ficha, com a chamada registrada; o cliente "propostas" deixa uma
`observacao` no produto, sem mudar a ficha; `proposta_texto` num produto é recusada; nenhuma
tool de escrita de produto existe."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import json

import pytest
from sqlalchemy import select

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401
from integration.mcp_helpers import bearer, com_mcp, criar_cliente, ligar
from integration.produtos_helpers import (  # noqa: F401 (fixtures)
    claude_fake,
    criar,
    perfil,
    rodar_tudo,
    ver,
)
from sociman_api.main import app
from sociman_api.mcp import mapa
from sociman_api.mcp.models import McpChamada

ESCRITAS = sorted(op["operationId"] for p in app.openapi()["paths"].values()
                  for op in p.values() if op["operationId"].startswith("produtos_")
                  and op["operationId"] not in ("produtos_listar", "produtos_ver",
                                                "produtos_versoes"))


@pytest.fixture
def cena(client, owner, motores, claude_fake, mcp_habilitado) -> dict:
    h = owner[1]
    pid = perfil(client, h)
    aprovado = criar(client, h, pid, n_fotos=1, obs="sem flat")
    rascunho = criar(client, h, pid, n_fotos=0, name="Rascunho")
    rodar_tudo(motores)
    aprovado = ver(client, h, aprovado["id"])
    r = client.post(f"/api/produtos/{aprovado['id']}/aprovar", headers=h,
                    json={"version": aprovado["version"]})
    assert r.status_code == 200, r.text
    ligar(client, h, mcp_habilitado)
    _, leitor = criar_cliente(client, h, "Leitor", "leitura")
    _, diretor = criar_cliente(client, h, "Diretor", "propostas")
    return {"h": h, "pid": pid, "aprovado": r.json(), "rascunho": rascunho, "leitor": leitor,
            "diretor": diretor}


def test_leitor_lista_os_aprovados_e_le_a_ficha(client, cena, db):
    async def chamar(c):
        nomes = {t.name for t in (await c.list_tools()).tools}
        lista = await c.call_tool("produtos_listar", {"perfil_id": cena["pid"]})
        lido = await c.call_tool("produtos_ver", {"produto_id": cena["aprovado"]["id"]})
        return nomes, lista, lido

    nomes, lista, lido = com_mcp(cena["leitor"], chamar)
    assert {"produtos_listar", "produtos_ver", "produtos_versoes"} <= nomes
    assert not nomes & set(ESCRITAS)
    itens = json.loads(lista.content[0].text)["itens"]
    assert [i["id"] for i in itens] == [cena["aprovado"]["id"]]  # padrão: só aprovados
    ficha = json.loads(lido.content[0].text)["ficha"]
    assert ficha["materialEn"] == "ribbed knit"
    db.expire_all()
    ops = {r.tool for r in db.scalars(select(McpChamada))}
    assert {"produtos_listar", "produtos_ver"} <= ops


def test_diretor_deixa_observacao_sem_mudar_a_ficha(client, cena):
    alvo = cena["aprovado"]
    r = client.post("/api/anotacoes", headers=bearer(cena["diretor"]), json={
        "alvoTipo": "produto", "alvoId": alvo["id"], "tipo": "observacao",
        "texto": "O logo LS parece branco, não cinza."})
    assert r.status_code == 201, r.text
    caixa = client.get("/api/anotacoes", headers=cena["h"],
                       params={"alvoTipo": "produto", "alvoId": alvo["id"]}).json()
    assert [a["texto"] for a in caixa["anotacoes"]] == ["O logo LS parece branco, não cinza."]
    assert ver(client, cena["h"], alvo["id"])["version"] == alvo["version"]
    r = client.post("/api/anotacoes", headers=bearer(cena["diretor"]), json={
        "alvoTipo": "produto", "alvoId": alvo["id"], "tipo": "proposta_texto",
        "texto": "x", "campos": {"titulo": "y"}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "proposta_so_em_destino"


@pytest.mark.parametrize("op", ESCRITAS)
def test_escritas_de_produto_sao_proibidas(op):
    assert op in mapa.PROIBIDAS and op not in mapa.TOOLS


def test_token_mcp_nao_escreve(client, cena):
    alvo = cena["aprovado"]
    r = client.post(f"/api/produtos/{alvo['id']}/aprovar", headers=bearer(cena["diretor"]),
                    json={"version": alvo["version"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
