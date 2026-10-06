"""Proposta de cena pelo MCP (spec 010, T041, US5, SC-004): o agente lê e propõe; criar,
editar, mudar status, tomadas e vínculo são do humano (`escopo_mcp`); os reverts são
`somente_humano` (cobertos também por `test_mcp_proibidas`)."""

# ruff: noqa: F811 — fixtures importadas de `cenas_helpers`

import uuid

import pytest
from mcp.shared.exceptions import MCPError
from sqlalchemy import select

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    base,
    cena_pronta,
    criar_cena,
    get,
    montar_perfil,
    owner,
)
from integration.mcp_helpers import bearer, com_mcp, criar_cliente, ligar
from sociman_api.anotacoes.models import Anotacao, AnotacaoSituacao
from sociman_api.auth.models import SecurityEvent
from sociman_api.main import app
from sociman_api.mcp import mapa

_OPS = {op["operationId"]: (m.upper(), path)
        for path, ops in app.openapi()["paths"].items() for m, op in ops.items()}
ESCRITAS = sorted(op for op in _OPS if (op.startswith("cenas_") or op == "conteudos_cenas_put")
                  and op in mapa.FORA)
REVERTS = ("cenas_revert", "cenas_tomadas_revert", "cenas_padroes_revert")


@pytest.fixture
def agente(client, base, mcp_habilitado):
    ligar(client, base["h"], mcp_habilitado)
    cliente, token = criar_cliente(client, base["h"], "Diretor", "propostas",
                                   limitePorMinuto=600)
    _, leitor = criar_cliente(client, base["h"], "Leitor", "leitura")
    return {"cliente": cliente, "token": token, "leitor": leitor}


def _propor(client, token, alvo_tipo, alvo_id, status=201, **campos):
    r = client.post("/api/anotacoes", headers=bearer(token), json={
        "alvoTipo": alvo_tipo, "alvoId": alvo_id, "tipo": "proposta_cena",
        "texto": "Proposta do diretor", "campos": campos})
    assert r.status_code == status, r.text
    return r.json()


def test_proposta_no_perfil_e_aceitar(client, db, base, agente):
    h, pid = base["h"], base["perfil"]["id"]
    out = _propor(client, agente["token"], "perfil", pid, nome="Abre a panela",
                  avatarId=base["avatar"]["id"], acao="lifts the lid", duracaoS=8)
    proposta = out["anotacao"]
    assert proposta["autor"]["tipo"] == "mcp_client" and proposta["campos"]["acao"] == \
        "lifts the lid"
    caixa = client.get("/api/anotacoes", headers=h, params={"tipo": "proposta_cena"}).json()
    assert [a["id"] for a in caixa["anotacoes"]] == [proposta["id"]]

    r = client.post(f"/api/perfis/{pid}/cenas", headers=h, json={
        "nome": "Abre a panela", "avatarId": base["avatar"]["id"], "acao": "lifts the lid",
        "propostaId": proposta["id"]})
    assert r.status_code == 201, r.text
    cena = r.json()
    assert cena["status"] == "rascunho" and cena["autor"]["tipo"] == "usuario"
    db.expire_all()
    row = db.get(Anotacao, uuid.UUID(proposta["id"]))
    assert row.situacao == AnotacaoSituacao.aplicada and row.resolvida_por == base["user"].id
    # a mesma proposta não aplica duas vezes
    r = client.post(f"/api/perfis/{pid}/cenas", headers=h, json={
        "nome": "De novo", "acao": "x", "propostaId": proposta["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "anotacao_fechada"


def test_proposta_na_cena_aplicada_pelo_patch(client, db, base, agente):
    h = base["h"]
    cena = criar_cena(client, h, base)
    proposta = _propor(client, agente["token"], "cena", cena["id"],
                       acao="opens the lid slowly")["anotacao"]
    r = client.patch(f"/api/cenas/{cena['id']}", headers=h, json={
        "version": cena["version"], "acao": "opens the lid slowly",
        "propostaId": proposta["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["acao"] == "opens the lid slowly" and r.json()["nome"] == cena["nome"]
    db.expire_all()
    assert db.get(Anotacao, uuid.UUID(proposta["id"])).situacao == AnotacaoSituacao.aplicada
    # proposta de outra cena não serve
    outra = criar_cena(client, h, base, nome="Outra")
    p2 = _propor(client, agente["token"], "cena", outra["id"], nome="x")["anotacao"]
    r = client.patch(f"/api/cenas/{cena['id']}", headers=h, json={
        "version": r.json()["version"], "nome": "y", "propostaId": p2["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "proposta_invalida"


def test_recusas_da_proposta(client, db, base, agente):
    h, pid, token = base["h"], base["perfil"]["id"], agente["token"]
    cena = cena_pronta(client, h, base)
    erro = _propor(client, token, "conta", str(uuid.uuid4()), status=422, acao="x")["error"]
    assert erro["code"] == "proposta_alvo_invalido"
    outro = montar_perfil(client, h, "outro", proibida=None)
    erro = _propor(client, token, "perfil", pid, status=422,
                   avatarId=outro["avatar"]["id"])["error"]
    assert erro["code"] == "proposta_invalida"
    # cena usada → 409
    from integration.test_cenas_usos import video_proprio

    c = video_proprio(db, pid)
    r = client.put(f"/api/conteudos/{c.id}/cenas", headers=h,
                   json={"version": 1, "cenaIds": [cena["id"]]})
    assert r.status_code == 200, r.text
    erro = _propor(client, token, "cena", cena["id"], status=409, acao="x")["error"]
    assert erro["code"] == "cena_usada"


@pytest.mark.parametrize("op", ESCRITAS)
def test_escritas_de_cena_recusadas_para_o_agente(client, db, base, agente, op):
    metodo, caminho = _OPS[op]
    url = caminho
    while "{" in url:
        ini, fim = url.index("{"), url.index("}")
        url = url[:ini] + str(uuid.uuid4()) + url[fim + 1:]
    r = client.request(metodo, url, headers=bearer(agente["token"]), json={"version": 1})
    assert r.status_code == 403 and r.json()["error"]["code"] == "escopo_mcp", (op, r.text)


def test_reverts_somente_humano(client, db, base, agente):
    cena = criar_cena(client, base["h"], base)
    for op in REVERTS:
        metodo, caminho = _OPS[op]
        url = caminho.replace("{cena_id}", cena["id"]).replace(
            "{perfil_id}", base["perfil"]["id"]).replace("{tomada_id}", str(uuid.uuid4()))
        r = client.request(metodo, url, headers=bearer(agente["token"]),
                           json={"version": 1, "toVersion": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano", op
    eventos = db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()
    assert len(eventos) == len(REVERTS)


def test_leitura_pelo_mcp_sem_video(client, base, agente):
    h = base["h"]
    cena = cena_pronta(client, h, base)
    leitor = agente["leitor"]
    r = client.get(f"/api/perfis/{base['perfil']['id']}/cenas", headers=bearer(leitor))
    assert r.status_code == 200 and r.json()["items"][0]["id"] == cena["id"]
    r = client.get(f"/api/cenas/{cena['id']}", headers=bearer(leitor))
    assert r.status_code == 200 and r.json()["prompt"]["congelado"] is True

    async def tools(c):
        nomes = {t.name for t in (await c.list_tools()).tools}
        lida = await c.call_tool("cenas_get", {"cena_id": cena["id"]})
        try:
            await c.call_tool("cenas_create", {})
            criou = "chamou"
        except MCPError as exc:
            criou = exc.code
        return nomes, lida, criou

    nomes, lida, criou = com_mcp(leitor, tools)
    assert {"cenas_list", "cenas_get", "cenas_tomadas_list"} <= nomes
    assert not nomes & set(ESCRITAS)
    assert not lida.is_error and criou == -32602


def test_proposta_conta_no_limite_de_escritas(client, base, agente, mcp_habilitado):
    h = base["h"]
    _, token = criar_cliente(client, h, "Contido", "propostas", limiteEscritasDia=1)
    _propor(client, token, "perfil", base["perfil"]["id"], acao="a")
    r = client.post("/api/anotacoes", headers=bearer(token), json={
        "alvoTipo": "perfil", "alvoId": base["perfil"]["id"], "tipo": "proposta_cena",
        "texto": "outra", "campos": {"acao": "b"}})
    assert r.status_code == 429, r.text
