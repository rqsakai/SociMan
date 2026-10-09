"""Permissões do cadastro padronizado (spec 025, T035, R18): o cliente MCP lê o kit, as vozes e
o consentimento sem a prova; toda escrita nova é 403 `somente_humano` com o evento; o membro
registra consentimento (com o autor gravado) mas não revoga nem reverte."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

import pytest
from sqlalchemy import select

from integration.geracao_helpers import _buckets, member, owner  # noqa: F401 (fixtures)
from integration.mcp_helpers import bearer, criar_cliente, ligar
from integration.padrao_helpers import avatar, consentimento, perfil, voz
from sociman_api.auth.models import SecurityEvent

ESCRITAS = [
    ("post", "/api/perfis/{p}/vozes", {"name": "x", "origem": "gravacao", "tom": "t"}),
    ("patch", "/api/vozes/{v}", {"version": 1, "tom": "t"}),
    ("post", "/api/vozes/{v}/archive", {"version": 1}),
    ("post", "/api/vozes/{v}/restore", {"version": 1}),
    ("post", "/api/vozes/{v}/revert", {"version": 1, "toVersion": 1}),
    ("put", "/api/vozes/{v}/consentimento", {"version": 1, "nome": "x", "data": "2026-10-01"}),
    ("post", "/api/vozes/{v}/consentimento/revogar", {"version": 1, "confirmo": True}),
    ("put", "/api/assets/{a}/consentimento", {"version": 1, "nome": "x", "data": "2026-10-01"}),
    ("post", "/api/assets/{a}/consentimento/revogar", {"version": 1, "confirmo": True}),
    ("get", "/api/assets/{a}/consentimento/previa-revogacao", None),
]


@pytest.mark.parametrize(("metodo", "rota", "corpo"), ESCRITAS)
def test_mcp_recebe_somente_humano(client, owner, db, mcp_habilitado, metodo, rota, corpo):
    h = owner[1]
    pid = perfil(client, h)
    a, v = avatar(client, h, pid), voz(client, h, pid)
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, escopo="propostas")
    url = rota.format(p=pid, a=a["id"], v=v["id"])
    kw = {"json": corpo} if corpo is not None else {}
    r = getattr(client, metodo)(url, headers=bearer(token), **kw)
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano", r.text
    db.expire_all()
    assert db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()


def test_mcp_le_sem_a_prova(client, owner, mcp_habilitado):
    h = owner[1]
    pid = perfil(client, h)
    a = avatar(client, h, pid)
    img_id = client.post(f"/api/perfis/{pid}/assets/arquivo", headers=h,
                         data={"tipo": "imagem", "name": "termo"},
                         files={"file": ("t.jpg", _img(), "image/jpeg")}).json()["asset"]
    prova = client.get(f"/api/assets/{img_id['id']}", headers=h).json()["asset"]["files"][0]
    consentimento(client, h, a["id"], a["version"], prova={"imageId": prova["image"]["id"]})
    assert client.get(f"/api/assets/{a['id']}", headers=h).json()["asset"][
        "consentimento"]["prova"]["imageId"]
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, escopo="leitura")
    lido = client.get(f"/api/assets/{a['id']}", headers=bearer(token)).json()["asset"]
    assert lido["consentimento"]["prova"] is None and lido["consentimento"]["temProva"] is True
    assert client.get(f"/api/perfis/{pid}/vozes", headers=bearer(token)).status_code == 200


def test_membro_registra_mas_nao_revoga(client, owner, member):
    pid = perfil(client, owner[1])
    a = avatar(client, member[1], pid)
    out = consentimento(client, member[1], a["id"], a["version"])["asset"]
    assert out["consentimento"]["registradoPor"]["id"] == str(member[0].id)
    r = client.post(f"/api/assets/{a['id']}/consentimento/revogar", headers=member[1],
                    json={"version": out["version"], "confirmo": True})
    assert r.status_code == 403
    assert uuid.UUID(out["id"])


def _img() -> bytes:
    from integration.padrao_helpers import img

    return img()
