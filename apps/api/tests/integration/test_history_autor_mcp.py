"""T009 (VII, R6): o cliente MCP como autor no histórico e nos eventos de segurança."""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from integration.mcp_helpers import bearer, criar_cliente, ligar
from integration.postagem_helpers import criar_perfil, dono  # noqa: F401
from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.auth.events import record_event
from sociman_api.auth.models import SecurityEvent
from sociman_api.history import EntityVersion


class _Ent:
    __versioned_fields__ = ("x",)

    def __init__(self):
        self.id = uuid.uuid4()
        self.version = 0
        self.x = 1


@pytest.fixture
def cliente_id(client, dono):  # noqa: F811
    _, h = dono
    cliente, _ = criar_cliente(client, h, "Revisor", "propostas")
    return uuid.UUID(cliente["id"])


def test_record_grava_o_cliente(db, cliente_id):
    ator = Actor(kind="mcp_client", mcp_client_id=cliente_id, mcp_escopo="propostas")
    ent = _Ent()
    history.record(db, ator, "teste", ent, "created", None, history.snapshot(ent))
    db.commit()
    row = db.scalar(select(EntityVersion).where(EntityVersion.entity_id == ent.id))
    assert row.actor_kind == "mcp_client" and row.actor_mcp_client_id == cliente_id
    assert row.actor_user_id is None


@pytest.mark.parametrize("tabela", ["entity_versions", "security_events"])
def test_check_do_ator(db, cliente_id, tabela):
    base = {
        "entity_versions": "INSERT INTO entity_versions (entity_type, entity_id, version, action, "
                           "actor_kind, actor_mcp_client_id, after, changed_fields) VALUES "
                           "('t', gen_random_uuid(), 1, 'created', :k, :c, '{}', '{}')",
        "security_events": "INSERT INTO security_events (type, outcome, actor_kind, "
                           "actor_mcp_client_id) VALUES ('t', 'ok', :k, :c)",
    }[tabela]
    for kind, cid in (("mcp_client", None), ("user", cliente_id), ("system:cli", cliente_id)):
        with pytest.raises(IntegrityError):
            db.execute(text(base), {"k": kind, "c": cid})
        db.rollback()
    db.execute(text(base), {"k": "mcp_client", "c": cliente_id})
    db.execute(text(base), {"k": "system:cli", "c": None})
    db.commit()


def test_evento_com_cliente(db, cliente_id):
    ator = Actor(kind="mcp_client", mcp_client_id=cliente_id)
    record_event(db, "publicacao_recusada", "denied", ator, details={"rota": "x"})
    db.commit()
    ev = db.scalar(select(SecurityEvent).where(SecurityEvent.type == "publicacao_recusada"))
    assert ev.actor_mcp_client_id == cliente_id and ev.actor_kind == "mcp_client"


def test_versions_trazem_o_autor(client, dono, mcp_habilitado):  # noqa: F811
    user, h = dono
    ligar(client, h, mcp_habilitado)
    perfil = criar_perfil(client, h)
    cliente, token = criar_cliente(client, h, "Revisor", "propostas")
    r = client.post("/api/anotacoes", headers=bearer(token), json={
        "alvoTipo": "perfil", "alvoId": perfil["id"], "texto": "Bio pode citar o nicho"})
    assert r.status_code == 201, r.text
    anotacao = r.json()["anotacao"]
    versoes = client.get(f"/api/anotacoes/{anotacao['id']}/versions", headers=h).json()["items"]
    assert versoes[0]["autor"] == {"tipo": "mcp_client", "id": cliente["id"], "nome": "Revisor"}
    assert versoes[0]["actorKind"] == "mcp_client" and versoes[0]["actor"] is None
    # e o de um humano continua "usuario"
    perfis = client.get(f"/api/perfis/{perfil['id']}/versions", headers=h).json()["items"]
    assert perfis[0]["autor"] == {"tipo": "usuario", "id": str(user.id), "nome": "Dono"}
    # eventos: a gestão do cliente aparece com o nome do agente quando o ator é o cliente
    eventos = client.get("/api/security-events?type=mcp_cliente_criado", headers=h).json()
    assert eventos["items"][0]["actorMcpClient"] is None  # quem criou foi o dono
