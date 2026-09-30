"""`RequireHumanOwner` e `exigir_humano_dono` (spec 015, T017, research R15): só dono humano;
qualquer outro ator recebe 403 `somente_humano` e deixa o evento `publicacao_recusada`."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from sociman_api.auth.deps import Actor, RequireHumanOwner, current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.errors import ApiError, register_error_handlers
from sociman_api.publicacao.service import exigir_humano_dono

ROTA = "/x/contas/{conta_id}/acao"


def _app(actor: Actor) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.post(ROTA)
    def _acao(conta_id: uuid.UUID, who: RequireHumanOwner) -> dict:
        return {"ok": who.kind}

    app.dependency_overrides[current_user] = lambda: actor
    return TestClient(app)


def _eventos(db) -> list[SecurityEvent]:
    db.expire_all()
    return list(db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")))


@pytest.fixture
def dono(make_user):
    return make_user(role="dono")


@pytest.fixture
def membro(make_user):
    return make_user(role="membro")


def test_dono_humano_passa(dono, db):
    client = _app(Actor(kind="user", user_id=dono.id, user=dono))
    r = client.post(ROTA.format(conta_id=uuid.uuid4()))
    assert r.status_code == 200
    assert r.json() == {"ok": "user"}
    assert _eventos(db) == []


@pytest.mark.parametrize("kind", ["mcp_client", "system:cli", "system:publicacao"])
def test_nao_humano_recusado_com_evento(kind, dono, db):
    conta = uuid.uuid4()
    client = _app(Actor(kind=kind, user_id=dono.id, user=dono))
    r = client.post(ROTA.format(conta_id=conta))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "somente_humano"
    [ev] = _eventos(db)
    assert ev.outcome == "denied"
    assert ev.actor_kind == kind
    assert ev.details == {"rota": ROTA, "actorKind": kind, "contaId": str(conta)}


def test_membro_recebe_somente_dono_sem_evento(membro, db):
    client = _app(Actor(kind="user", user_id=membro.id, user=membro))
    r = client.post(ROTA.format(conta_id=uuid.uuid4()))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "somente_dono"
    assert _eventos(db) == []


# ---- dentro do service ----

def test_service_dono_humano_passa(dono, db):
    exigir_humano_dono(Actor(kind="user", user_id=dono.id, user=dono), "POST /api/x")
    assert _eventos(db) == []


@pytest.mark.parametrize("kind", ["mcp_client", "system:cli", "system:publicacao"])
def test_service_nao_humano(kind, dono, db):
    destino = uuid.uuid4()
    with pytest.raises(ApiError) as exc:
        exigir_humano_dono(Actor(kind=kind, user_id=dono.id, user=dono), "POST /api/agendamentos",
                           destino_id=destino)
    assert (exc.value.status, exc.value.code) == (403, "somente_humano")
    [ev] = _eventos(db)
    assert ev.details == {"rota": "POST /api/agendamentos", "actorKind": kind,
                          "destinoId": str(destino)}


def test_service_membro(membro, db):
    with pytest.raises(ApiError) as exc:
        exigir_humano_dono(Actor(kind="user", user_id=membro.id, user=membro), "POST /api/x")
    assert (exc.value.status, exc.value.code) == (403, "somente_dono")
    assert _eventos(db) == []


def test_evento_sobrevive_ao_rollback_de_quem_chama(dono, db):
    """O evento vai numa sessão própria: o rollback da transação do service não o apaga."""
    with pytest.raises(ApiError):
        exigir_humano_dono(Actor(kind="mcp_client", user_id=dono.id, user=dono), "POST /api/x")
    db.rollback()
    assert len(_eventos(db)) == 1
