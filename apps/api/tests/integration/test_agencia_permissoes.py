"""Permissões da importação (spec 013, T015, SC-005): prévia, confirmar e desfazer só para dono
humano; membro → 403 `somente_dono`; não humano → 403 `somente_humano` + evento; estado, lista e
detalhe abertos ao membro."""

import uuid

import pytest
from atores import ator_fake
from sqlalchemy import select

from integration.agencia_helpers import _buckets, agencia, dono, membro, yt  # noqa: F401
from sociman_api.auth.deps import Actor, require_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.main import app

H = [("post", "/api/agencia/previa", None),
     ("post", "/api/agencia/importacoes", {"previaId": str(uuid.uuid4())}),
     ("post", f"/api/agencia/importacoes/{uuid.uuid4()}/desfazer", {"version": 1})]


@pytest.mark.parametrize(("metodo", "url", "corpo"), H)
def test_membro_recebe_somente_dono(client, membro, agencia, metodo, url, corpo):  # noqa: F811
    _, h = membro
    r = getattr(client, metodo)(url, headers=h, json=corpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_dono"


@pytest.mark.parametrize("kind", ["mcp_client", "system:cli"])
@pytest.mark.parametrize(("metodo", "url", "corpo"), H)
def test_nao_humano_recebe_somente_humano_e_evento(client, db, dono, agencia, kind, metodo,  # noqa: F811
                                                   url, corpo):
    user, _ = dono
    ator: Actor = ator_fake(kind, user)
    app.dependency_overrides[require_user] = lambda: ator
    r = getattr(client, metodo)(url, json=corpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    ev = db.scalars(select(SecurityEvent).where(SecurityEvent.type == "publicacao_recusada")).all()
    assert ev and ev[-1].details["actorKind"] == kind


def test_membro_le_estado_lista_e_detalhe(client, membro, agencia):  # noqa: F811
    _, h = membro
    assert client.get("/api/agencia/estado", headers=h).status_code == 200
    r = client.get("/api/agencia/importacoes", headers=h)
    assert r.status_code == 200 and r.json() == {"items": []}
    r = client.get(f"/api/agencia/importacoes/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404
