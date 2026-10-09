"""Permissões das cenas (spec 010, T045, FR-010): o membro faz tudo menos reverter; os 3
reverts são do dono humano (`somente_dono` para o membro; `somente_humano` + evento para
`system:*`, e para o token de agente em `test_cenas_mcp`)."""

# ruff: noqa: F811 — fixtures importadas de `cenas_helpers`

import uuid

import pytest
from sqlalchemy import select

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    base,
    criar_cena,
    member,
    mp4_sintetico,
    owner,
    patch,
)
from integration.test_cenas_usos import video_proprio
from sociman_api.auth.deps import Actor, current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.main import app


@pytest.fixture(scope="module")
def tomada(tmp_path_factory):
    return mp4_sintetico(tmp_path_factory.mktemp("perm") / "t.mp4", 2)


def test_membro_faz_o_ciclo(client, db, base, member, tomada):
    hm = member[1]
    cena = criar_cena(client, hm, base)
    cena = patch(client, hm, cena, nome="Do membro")
    cena = acao(client, hm, cena, "pronta")
    with tomada.open("rb") as fh:
        r = client.post(f"/api/cenas/{cena['id']}/tomadas", headers=hm,
                        files={"file": ("t.mp4", fh, "video/mp4")})
    assert r.status_code == 201, r.text
    c = video_proprio(db, base["perfil"]["id"])
    r = client.put(f"/api/conteudos/{c.id}/cenas", headers=hm,
                   json={"version": 1, "cenaIds": [cena["id"]]})
    assert r.status_code == 200, r.text
    r = client.put(f"/api/perfis/{base['perfil']['id']}/cenas/padroes", headers=hm,
                   json={"version": 0, "estilo": "cinematic", "negative": "blur"})
    assert r.status_code == 200 and r.json()["version"] == 1


def _reverts(client, base, h):
    cena = criar_cena(client, base["h"], base)
    pid = base["perfil"]["id"]
    urls = (f"/api/cenas/{cena['id']}/revert", f"/api/cenas/tomadas/{uuid.uuid4()}/revert",
            f"/api/perfis/{pid}/cenas/padroes/revert")
    return [client.post(u, headers=h, json={"version": 1, "toVersion": 1}) for u in urls]


def test_membro_nao_reverte(client, base, member):
    for r in _reverts(client, base, member[1]):
        assert r.status_code == 403 and r.json()["error"]["code"] == "somente_dono", r.text


@pytest.mark.parametrize("kind", ["system:cli", "system:agente"])
def test_sistema_nao_reverte(client, db, base, kind):
    dono = base["user"]
    app.dependency_overrides[current_user] = lambda: Actor(kind=kind, user=dono)
    try:
        respostas = _reverts(client, base, {})
    finally:
        app.dependency_overrides.pop(current_user, None)
    for r in respostas:
        assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano", r.text
    eventos = db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()
    assert len(eventos) == 3 and {e.actor_kind for e in eventos} == {kind}
