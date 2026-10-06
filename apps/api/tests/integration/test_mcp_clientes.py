"""T022 e T023 (US1): clientes MCP e interruptor, só pelo dono humano."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from integration.mcp_helpers import bearer, criar_cliente, ligar
from integration.postagem_helpers import dono, membro  # noqa: F401
from sociman_api.auth.models import SecurityEvent
from sociman_api.history import EntityVersion

ROTAS = [("GET", "/api/mcp/clientes"), ("POST", "/api/mcp/clientes"),
         ("GET", "/api/mcp/clientes/{id}"), ("PATCH", "/api/mcp/clientes/{id}"),
         ("POST", "/api/mcp/clientes/{id}/suspender"), ("POST", "/api/mcp/clientes/{id}/reativar"),
         ("POST", "/api/mcp/clientes/{id}/rotacionar"), ("POST", "/api/mcp/clientes/{id}/revogar"),
         ("GET", "/api/mcp/clientes/{id}/versions"), ("GET", "/api/mcp/config"),
         ("PUT", "/api/mcp/config"), ("GET", "/api/mcp/config/versions"),
         ("GET", "/api/mcp/chamadas")]


def _acao(client, h, cliente, nome):
    return client.post(f"/api/mcp/clientes/{cliente['id']}/{nome}", headers=h,
                       json={"version": cliente["version"]})


def test_token_uma_vez_no_store(client, dono):  # noqa: F811
    _, h = dono
    r = client.post("/api/mcp/clientes", headers=h, json={"nome": "Caçador", "escopo": "leitura"})
    assert r.status_code == 201 and r.headers["cache-control"] == "no-store"
    token, cliente = r.json()["token"], r.json()["cliente"]
    assert token.startswith(f"smcp_{cliente['tokenId']}_")
    assert cliente["situacao"] == "ativo" and cliente["ultimoUsoEm"] is None
    for url in ("/api/mcp/clientes", f"/api/mcp/clientes/{cliente['id']}",
                f"/api/mcp/clientes/{cliente['id']}/versions"):
        corpo = client.get(url, headers=h).text
        assert token not in corpo and token.rsplit("_", 1)[1] not in corpo
        assert '"token"' not in corpo and "hash" not in corpo.lower()


def test_nome_unico_sem_caixa_nem_acento(client, dono):  # noqa: F811
    _, h = dono
    criar_cliente(client, h, "Caçador")
    r = client.post("/api/mcp/clientes", headers=h, json={"nome": "  CACADOR ", "escopo": "leitura"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "nome_em_uso"


def test_suspender_e_reativar(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    cliente, token = criar_cliente(client, h)
    cliente = _acao(client, h, cliente, "suspender").json()["cliente"]
    assert cliente["situacao"] == "suspenso"
    assert client.get("/api/perfis", headers=bearer(token)).status_code == 403
    cliente = _acao(client, h, cliente, "reativar").json()["cliente"]
    assert cliente["situacao"] == "ativo"
    assert client.get("/api/perfis", headers=bearer(token)).status_code == 200


def test_rotacionar(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    cliente, antigo = criar_cliente(client, h)
    r = _acao(client, h, cliente, "rotacionar")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    novo = r.json()["token"]
    assert r.json()["cliente"]["tokenId"] != cliente["tokenId"] and novo != antigo
    assert client.get("/api/perfis", headers=bearer(antigo)).status_code == 401
    assert client.get("/api/perfis", headers=bearer(novo)).status_code == 200
    versoes = client.get(f"/api/mcp/clientes/{cliente['id']}/versions", headers=h).json()["items"]
    assert versoes[0]["details"]["rotacao"] is True and "token_hash" not in versoes[0]["after"]
    assert "token_id" in versoes[0]["changedFields"]


def test_revogar_e_final(client, dono, mcp_habilitado):  # noqa: F811
    user, h = dono
    ligar(client, h, mcp_habilitado)
    cliente, token = criar_cliente(client, h)
    cliente = _acao(client, h, cliente, "revogar").json()["cliente"]
    assert cliente["situacao"] == "revogado" and cliente["revogadoPor"]["id"] == str(user.id)
    assert client.get("/api/perfis", headers=bearer(token)).status_code == 401
    for nome in ("revogar", "rotacionar", "reativar", "suspender"):
        r = _acao(client, h, cliente, nome)
        assert r.status_code == 409 and r.json()["error"]["code"] == "mcp_cliente_revogado", nome
    r = client.patch(f"/api/mcp/clientes/{cliente['id']}", headers=h,
                     json={"version": cliente["version"], "nome": "Outro"})
    assert r.status_code == 409
    assert [c["id"] for c in client.get("/api/mcp/clientes", headers=h).json()["clientes"]] == [
        cliente["id"]]


def test_vencimento(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    passado = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    r = client.post("/api/mcp/clientes", headers=h,
                    json={"nome": "X", "escopo": "leitura", "expiraEm": passado})
    assert r.status_code == 400 and r.json()["error"]["code"] == "expira_no_passado"
    breve = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    cliente, _ = criar_cliente(client, h, "Y", expiraEm=breve)
    assert cliente["venceEmBreve"] is True
    longe = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    cliente, _ = criar_cliente(client, h, "Z", expiraEm=longe)
    assert cliente["venceEmBreve"] is False
    r = client.patch(f"/api/mcp/clientes/{cliente['id']}", headers=h,
                     json={"version": cliente["version"], "expiraEm": None})
    assert r.status_code == 200 and r.json()["cliente"]["expiraEm"] is None


def test_escopo_vale_na_chamada_seguinte(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    perfil = client.post("/api/perfis", headers=h, json={"name": "P", "slug": "p-1"}).json()
    cliente, token = criar_cliente(client, h, escopo="leitura")
    corpo = {"alvoTipo": "perfil", "alvoId": perfil["perfil"]["id"], "texto": "oi"}
    assert client.post("/api/anotacoes", headers=bearer(token), json=corpo).status_code == 403
    r = client.patch(f"/api/mcp/clientes/{cliente['id']}", headers=h,
                     json={"version": cliente["version"], "escopo": "propostas"})
    assert r.status_code == 200
    assert client.post("/api/anotacoes", headers=bearer(token), json=corpo).status_code == 201


@pytest.mark.parametrize("metodo,rota", ROTAS)
def test_membro_e_mcp_recebem_somente_humano(client, dono, membro, mcp_habilitado,  # noqa: F811
                                             metodo, rota):
    _, h = dono
    ligar(client, h, mcp_habilitado)
    cliente, token = criar_cliente(client, h, escopo="propostas")
    url = rota.format(id=cliente["id"])
    _, hm = membro
    r = client.request(metodo, url, headers=hm, json={})
    assert r.status_code == 403 and r.json()["error"]["code"] in ("somente_dono", "forbidden")
    r = client.request(metodo, url, headers=bearer(token), json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"


def test_historico_e_eventos_sem_segredo(client, dono, db):  # noqa: F811
    _, h = dono
    cliente, token = criar_cliente(client, h)
    _acao(client, h, cliente, "rotacionar")
    segredos = (token, token.rsplit("_", 1)[1])
    for row in db.scalars(select(EntityVersion)):
        assert not any(s in str(row.after) + str(row.before) + str(row.details) for s in segredos)
    tipos = {e.type for e in db.scalars(select(SecurityEvent))}
    assert {"mcp_cliente_criado", "mcp_cliente_rotacionado"} <= tipos
    for e in db.scalars(select(SecurityEvent)):
        assert not any(s in str(e.details) for s in segredos)


# ---- T023: interruptor ----

def test_config(client, dono, mcp_habilitado):  # noqa: F811
    user, h = dono
    cfg = client.get("/api/mcp/config", headers=h).json()
    assert cfg == {"habilitado": False, "servidorHabilitado": False, "version": 1}
    mcp_habilitado(True)
    assert client.get("/api/mcp/config", headers=h).json()["servidorHabilitado"] is True
    r = client.put("/api/mcp/config", headers=h, json={"habilitado": True, "version": 1})
    assert r.status_code == 200 and r.json()["habilitado"] is True and r.json()["version"] == 2
    r = client.put("/api/mcp/config", headers=h, json={"habilitado": False, "version": 1})
    assert r.status_code == 409
    versoes = client.get("/api/mcp/config/versions", headers=h).json()["items"]
    assert versoes[0]["autor"]["id"] == str(user.id) and versoes[0]["details"]["acao"] == "ligado"
    eventos = client.get("/api/security-events?type=mcp_config_alterada", headers=h).json()
    assert len(eventos["items"]) == 1


def test_qualquer_nivel_desligado_recusa(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    _, token = criar_cliente(client, h)
    mcp_habilitado(True)  # só o .env
    r = client.get("/api/perfis", headers=bearer(token))
    assert r.status_code == 403 and r.json()["error"]["code"] == "mcp_desligado"
    ligar(client, h, mcp_habilitado)
    assert client.get("/api/perfis", headers=bearer(token)).status_code == 200
