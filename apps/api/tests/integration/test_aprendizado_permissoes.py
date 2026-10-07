"""Permissões do aprendizado (spec 023, T059; SC-006): toda rota H com membro → 403
`somente_dono`; as leituras aceitam membro. O token MCP em todas as escritas é o
`test_mcp_proibidas.py` (parametrizado por `mapa.PROIBIDAS`)."""

import uuid

import pytest

from integration.analytics_helpers import cena  # noqa: F401
from integration.aprendizado_helpers import ap, err, membro  # noqa: F401
from sociman_api.main import app
from sociman_api.mcp import mapa

OPS = {op["operationId"]: (m.upper(), path) for path, item in app.openapi()["paths"].items()
       for m, op in item.items() if op["operationId"].startswith("aprendizado_")}
ESCRITAS = sorted(o for o, (m, _) in OPS.items() if m != "GET")
LEITURAS = sorted(o for o, (m, _) in OPS.items() if m == "GET")


def _url(ap, caminho: str) -> str:  # noqa: F811
    return (caminho.replace("{perfil_id}", ap.perfil_id).replace("{indice}", "0")
            .replace("{item}", "restrito").replace("{tema_id}", str(uuid.uuid4()))
            .replace("{video_id}", str(uuid.uuid4())).replace("{decisao_id}", str(uuid.uuid4()))
            .replace("{analise_id}", str(uuid.uuid4())))


def test_todas_as_escritas_sao_proibidas_no_mcp():
    assert ESCRITAS and all(op in mapa.PROIBIDAS for op in ESCRITAS)


@pytest.mark.parametrize("op", ESCRITAS)
def test_membro_recebe_somente_dono(ap, membro, op):  # noqa: F811
    _, hm = membro
    metodo, caminho = OPS[op]
    r = ap.client.request(metodo, _url(ap, caminho), headers=hm, json={"version": 0})
    assert r.status_code == 403 and err(r) == "somente_dono", (op, r.text)


@pytest.mark.parametrize("op", LEITURAS)
def test_membro_le(ap, membro, op):  # noqa: F811
    _, hm = membro
    metodo, caminho = OPS[op]
    r = ap.client.request(metodo, _url(ap, caminho), headers=hm)
    assert r.status_code in (200, 404), (op, r.text)
