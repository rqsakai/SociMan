"""Permissões dos produtos (spec 012, T046, R15): o membro faz todas as escritas, menos reverter;
o token MCP e o ator `system:*` recebem 403 `somente_humano` com o evento de recusa; as leituras
aceitam membro e MCP."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

import pytest
from atores import ator_fake
from sqlalchemy import select

from integration.geracao_helpers import _buckets, member, owner  # noqa: F401 (fixtures)
from integration.mcp_helpers import bearer, criar_cliente, ligar
from integration.produtos_helpers import criar, foto, perfil, ver
from sociman_api.auth.models import SecurityEvent
from sociman_api.errors import ApiError

_V = {"version": 1}
_ESCRITAS = [
    ("patch", "/api/produtos/{p}", {"version": 1, "name": "x"}),
    ("put", "/api/produtos/{p}/ficha", {"version": 1, "ficha": {}, "cores": []}),
    ("post", "/api/produtos/{p}/ficha/pedir", _V),
    ("post", "/api/produtos/{p}/aprovar", _V),
    ("post", "/api/produtos/{p}/arquivar", _V),
    ("post", "/api/produtos/{p}/restaurar", _V),
    ("post", "/api/produtos/{p}/revert", {"version": 1, "toVersion": 1}),
    ("put", "/api/produtos/{p}/variantes/ordem", {"version": 1, "ids": [str(uuid.uuid4())]}),
    ("patch", "/api/produtos/{p}/variantes/{v}", {"version": 1, "corEn": "x"}),
    ("post", "/api/produtos/{p}/variantes/{v}/arquivar", _V),
    ("post", "/api/produtos/{p}/variantes/{v}/restaurar", _V),
    ("post", "/api/produtos/{p}/variantes/{v}/refazer-flat", _V),
]


def test_membro_escreve_menos_reverter(client, owner, member):
    hm = member[1]
    pid = perfil(client, owner[1])
    p = criar(client, hm, pid, n_fotos=1)
    r = client.patch(f"/api/produtos/{p['id']}", headers=hm,
                     json={"version": p["version"], "name": "do membro"})
    assert r.status_code == 200, r.text
    p = r.json()
    r = client.post(f"/api/produtos/{p['id']}/variantes", headers=hm,
                    data={"version": str(p["version"])},
                    files={"foto": ("v.jpg", foto(), "image/jpeg")})
    assert r.status_code == 201, r.text
    p = r.json()
    r = client.post(f"/api/produtos/{p['id']}/arquivar", headers=hm,
                    json={"version": p["version"]})
    assert r.status_code == 200
    p = r.json()
    r = client.post(f"/api/produtos/{p['id']}/restaurar", headers=hm,
                    json={"version": p["version"]})
    assert r.status_code == 200
    p = r.json()
    r = client.post(f"/api/produtos/{p['id']}/revert", headers=hm,
                    json={"version": p["version"], "toVersion": 1})
    assert r.status_code == 403
    assert client.get(f"/api/produtos/{p['id']}/versoes", headers=hm).status_code == 200


@pytest.mark.parametrize(("metodo", "rota", "corpo"), _ESCRITAS)
def test_token_mcp_recebe_somente_humano(client, owner, db, mcp_habilitado, metodo, rota,
                                         corpo):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, escopo="propostas")
    url = rota.format(p=p["id"], v=p["variantes"][0]["id"])
    r = getattr(client, metodo)(url, headers=bearer(token), json=corpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano", r.text
    db.expire_all()
    assert db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()
    # As leituras passam.
    assert client.get(f"/api/produtos/{p['id']}", headers=bearer(token)).status_code == 200
    assert ver(client, h, p["id"])["version"] == p["version"]


def test_ator_system_nao_passa_pelo_require_human():
    from starlette.requests import Request

    from sociman_api.auth.deps import require_human

    req = Request({"type": "http", "method": "POST", "path": "/x", "headers": [],
                   "path_params": {}, "query_string": b""})
    with pytest.raises(ApiError) as exc:
        require_human(req, ator_fake("system:gerador"))
    assert exc.value.code == "somente_humano"
