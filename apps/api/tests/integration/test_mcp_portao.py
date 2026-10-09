"""T010 (R5): o portão da API para tokens MCP, direto na API (sem a ponte)."""

import pytest
from sqlalchemy import select, text

from integration.mcp_helpers import bearer, criar_cliente, ligar
from integration.postagem_helpers import criar_perfil, dono  # noqa: F401
from sociman_api.auth.models import SecurityEvent
from sociman_api.history import EntityVersion


@pytest.fixture
def ligado(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    return h


def _versao(client, h, cliente_id):
    return client.get(f"/api/mcp/clientes/{cliente_id}", headers=h).json()["cliente"]["version"]


def test_leitura_passa_como_mcp_client(client, ligado):
    criar_perfil(client, ligado)
    _, token = criar_cliente(client, ligado, "Analista", "leitura")
    r = client.get("/api/perfis", headers=bearer(token))
    assert r.status_code == 200 and len(r.json()["items"]) == 1


def test_jwt_continua_igual(client, ligado):
    assert client.get("/api/perfis", headers=ligado).status_code == 200


def test_revogado_e_vencido_401(client, ligado, db):
    cliente, token = criar_cliente(client, ligado, "A", "leitura")
    r = client.post(f"/api/mcp/clientes/{cliente['id']}/revogar", headers=ligado,
                    json={"version": cliente["version"]})
    assert r.status_code == 200
    assert client.get("/api/perfis", headers=bearer(token)).status_code == 401
    cliente, token = criar_cliente(client, ligado, "B", "leitura")
    db.execute(text(
        "UPDATE mcp_clientes SET expira_em = now() - interval '1 minute' WHERE id = :id"),
        {"id": cliente["id"]})
    db.commit()
    r = client.get("/api/perfis", headers=bearer(token))
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_suspenso_403(client, ligado):
    cliente, token = criar_cliente(client, ligado, "A", "leitura")
    client.post(f"/api/mcp/clientes/{cliente['id']}/suspender", headers=ligado,
                json={"version": cliente["version"]})
    r = client.get("/api/perfis", headers=bearer(token))
    assert r.status_code == 403 and r.json()["error"]["code"] == "mcp_suspenso"


def test_origin_403(client, ligado):
    _, token = criar_cliente(client, ligado, "A", "leitura")
    r = client.get("/api/perfis", headers={**bearer(token), "Origin": "http://localhost:8180"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "mcp_origem"


@pytest.mark.parametrize("nivel", ["env", "tela"])
def test_interruptor_403(client, ligado, mcp_habilitado, nivel):
    _, token = criar_cliente(client, ligado, "A", "leitura")
    if nivel == "env":
        mcp_habilitado(False)
    else:
        v = client.get("/api/mcp/config", headers=ligado).json()["version"]
        client.put("/api/mcp/config", headers=ligado, json={"habilitado": False, "version": v})
    r = client.get("/api/perfis", headers=bearer(token))
    assert r.status_code == 403 and r.json()["error"]["code"] == "mcp_desligado"


def test_fora_403_escopo(client, ligado):
    _, token = criar_cliente(client, ligado, "A", "propostas")
    r = client.post("/api/perfis", headers=bearer(token),
                    json={"name": "X", "slug": "x-1"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "escopo_mcp"


def test_escrita_com_leitura_403_escopo(client, ligado):
    perfil = criar_perfil(client, ligado)
    _, token = criar_cliente(client, ligado, "A", "leitura")
    r = client.post("/api/anotacoes", headers=bearer(token),
                    json={"alvoTipo": "perfil", "alvoId": perfil["id"], "texto": "oi"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "escopo_mcp"


def test_proibida_somente_humano_com_evento(client, ligado, db):
    cliente, token = criar_cliente(client, ligado, "A", "propostas")
    r = client.get("/api/users", headers=bearer(token))
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    ev = db.scalar(select(SecurityEvent).where(SecurityEvent.type == "publicacao_recusada"))
    assert str(ev.actor_mcp_client_id) == cliente["id"] and ev.details["rota"] == "GET /api/users"


def test_proibida_sem_dependencia_de_ator_tambem(client, ligado):
    """A rota de login não pede ator, mas o portão vale para qualquer token MCP."""
    _, token = criar_cliente(client, ligado, "A", "propostas")
    r = client.post("/api/auth/login", headers=bearer(token), json={"email": "a@b.c",
                                                                    "password": "x" * 12})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"


def test_revogado_no_meio_da_sequencia(client, ligado, db):
    perfil = criar_perfil(client, ligado)
    cliente, token = criar_cliente(client, ligado, "A", "propostas")
    corpo = {"alvoTipo": "perfil", "alvoId": perfil["id"], "texto": "um"}
    assert client.post("/api/anotacoes", headers=bearer(token), json=corpo).status_code == 201
    antes = len(db.scalars(select(EntityVersion)).all())
    client.post(f"/api/mcp/clientes/{cliente['id']}/revogar", headers=ligado,
                json={"version": _versao(client, ligado, cliente["id"])})
    depois_revogar = len(db.scalars(select(EntityVersion)).all())
    assert client.post("/api/anotacoes", headers=bearer(token), json=corpo).status_code == 401
    assert len(db.scalars(select(EntityVersion)).all()) == depois_revogar > antes
