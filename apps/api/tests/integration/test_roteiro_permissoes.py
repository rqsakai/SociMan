"""Permissões dos roteiros (spec 011, T047, FR-046, SC-008): dono e membro criam, planejam,
aprovam e mudam portões; reverter é só do dono; o token MCP (e qualquer ator que não seja humano)
recebe 403 `somente_humano` com o evento `publicacao_recusada` nas escritas, e as leituras do
roteiro ficam fora do MCP (`escopo_mcp`). Todas as rotas da 011 estão classificadas no mapa."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

import pytest
from atores import ator_fake
from sqlalchemy import select

from integration.geracao_helpers import _buckets, member, owner  # noqa: F401 (fixtures)
from integration.mcp_helpers import bearer, criar_cliente, ligar
from integration.produtos_helpers import perfil
from sociman_api.auth.models import SecurityEvent
from sociman_api.errors import ApiError
from sociman_api.main import app
from sociman_api.mcp import mapa

_V = {"version": 1}
_R = "/api/roteiros/{r}"
_ESCRITAS = [
    ("post", "/api/perfis/{p}/roteiros", {"nome": "x", "produtos": [
        {"produtoId": str(uuid.uuid4())}]}),
    ("patch", _R, {"version": 1, "nome": "x"}),
    ("post", _R + "/planejar", _V),
    ("post", _R + "/aprovar", {"version": 1, "portao": "texto"}),
    ("put", _R + "/controle", {"version": 1, "modo": "automatico", "portoes": {}}),
    ("post", _R + "/tentar-de-novo", _V),
    ("post", _R + "/arquivar", _V),
    ("post", _R + "/versoes/1/reverter", _V),
    ("post", _R + "/posicoes/0/keyframe/regerar", _V),
    ("post", _R + "/posicoes/0/clipe/regerar", _V),
    ("put", _R + "/posicoes/0/tomada", {"version": 1, "tomadaId": str(uuid.uuid4())}),
    ("put", "/api/perfis/{p}/roteiro-padroes", {"version": 0, "modo": "automatico",
                                               "portoes": {}}),
    ("post", "/api/perfis/{p}/pronuncias", {"escrita": "leve", "falada": "lévi"}),
]


def _ids() -> dict:
    return {"r": str(uuid.uuid4())}


@pytest.mark.parametrize(("metodo", "rota", "corpo"), _ESCRITAS)
def test_token_mcp_recebe_somente_humano(client, owner, db, mcp_habilitado, metodo, rota,
                                         corpo):
    h = owner[1]
    pid = perfil(client, h)
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, escopo="propostas")
    url = rota.format(p=pid, **_ids())
    r = getattr(client, metodo)(url, headers=bearer(token), json=corpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano", r.text
    db.expire_all()
    assert db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()


def test_enviar_keyframe_pelo_mcp_e_recusado(client, owner, db, mcp_habilitado):
    h = owner[1]
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, escopo="propostas")
    r = client.post(f"/api/roteiros/{uuid.uuid4()}/posicoes/0/keyframe", headers=bearer(token),
                    data={"version": "1"}, files={"arquivo": ("k.png", b"x", "image/png")})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano", r.text


def test_leituras_fora_do_mcp_e_membro_le(client, owner, member, mcp_habilitado):
    h = owner[1]
    pid = perfil(client, h)
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, escopo="propostas")
    r = client.get(f"/api/perfis/{pid}/roteiros", headers=bearer(token))
    assert r.status_code == 403 and r.json()["error"]["code"] == "escopo_mcp"
    assert client.get(f"/api/perfis/{pid}/roteiros", headers=member[1]).status_code == 200
    assert client.get(f"/api/perfis/{pid}/roteiro-padroes", headers=member[1]).json()[
        "version"] == 0
    # O membro edita o padrão e as pronúncias (FR-010, FR-045).
    r = client.put(f"/api/perfis/{pid}/roteiro-padroes", headers=member[1], json={
        "version": 0, "modo": "automatico", "portoes": {"texto": False}})
    assert r.status_code == 200 and r.json()["modo"] == "automatico"
    assert r.json()["portoes"] == {"texto": False, "narracao": True, "keyframes": True,
                                   "clipes": True, "final": True}


def test_ator_system_nao_passa_pelo_require_human():
    from starlette.requests import Request

    from sociman_api.auth.deps import require_human

    req = Request({"type": "http", "method": "POST", "path": "/x", "headers": [],
                   "path_params": {}, "query_string": b""})
    for kind in ("system:roteiro", "system:gerador", "mcp_client"):
        with pytest.raises(ApiError) as exc:
            require_human(req, ator_fake(kind))
        assert exc.value.code == "somente_humano"


def test_todas_as_rotas_da_011_classificadas():
    for metodos in app.openapi()["paths"].values():
        for op in metodos.values():
            oid = op.get("operationId", "")
            if oid.startswith(("roteiros_", "roteiro_padroes_", "pronuncias_")):
                assert mapa.classificar(oid) in ("proibida", "fora"), oid
                escrita = op.get("requestBody") is not None
                assert (mapa.classificar(oid) == "proibida") == escrita, oid
