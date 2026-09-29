"""Padrões de corte do perfil (T043; R8, contracts/http-api.md "Padrões de corte")."""

import pytest

from integration import envios_helpers

# Fixtures compartilhadas (atribuídas, e não importadas, para o ruff não acusar F811).
member = envios_helpers.member
owner = envios_helpers.owner
perfil = envios_helpers.perfil

PADRAO = {"clipMinS": 15, "clipMaxS": 60, "quantidade": None, "layout": "auto",
          "formato": "vertical", "legenda": "kit", "marcaAutomatica": False,
          "contaPadraoId": None}


def _url(perfil_id: str) -> str:
    return f"/api/perfis/{perfil_id}/padroes-corte"


def _put(client, h, perfil_id: str, version: int, **changes):
    return client.put(_url(perfil_id), json=PADRAO | {"version": version} | changes, headers=h)


def test_get_sem_linha_devolve_o_padrao(client, owner, perfil):
    r = client.get(_url(perfil["id"]), headers=owner[1])
    assert r.status_code == 200, r.text
    p = r.json()["padroes"]
    assert p["version"] == 0 and p["updatedBy"] is None
    assert {k: p[k] for k in PADRAO} == PADRAO
    assert client.get(_url(perfil["id"]) + "/versions", headers=owner[1]).json()["items"] == []


def test_put_cria_v1_e_atualiza_com_versoes(client, owner, member, perfil):
    _, h = member
    r = _put(client, h, perfil["id"], 0, clipMinS=20, quantidade=6, layout="split")
    assert r.status_code == 200, r.text
    p = r.json()["padroes"]
    assert (p["version"], p["clipMinS"], p["quantidade"], p["layout"]) == (1, 20, 6, "split")
    assert p["updatedBy"]["id"] == str(member[0].id)

    # sem mudança real não grava versão
    r = _put(client, h, perfil["id"], 1, clipMinS=20, quantidade=6, layout="split")
    assert r.json()["padroes"]["version"] == 1

    r = _put(client, h, perfil["id"], 1, clipMinS=20, quantidade=None, layout="split",
             legenda="gerador", marcaAutomatica=True)
    assert r.status_code == 200 and r.json()["padroes"]["version"] == 2
    items = client.get(_url(perfil["id"]) + "/versions", headers=h).json()["items"]
    assert [v["action"] for v in items] == ["updated", "created"]
    assert set(items[0]["changedFields"]) == {"quantidade", "legenda", "marca_automatica"}
    assert items[0]["actor"]["id"] == str(member[0].id)


def test_conflito_de_versao(client, owner, perfil):
    _, h = owner
    assert _put(client, h, perfil["id"], 0).status_code == 200
    r = _put(client, h, perfil["id"], 0, clipMinS=30)
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    r = client.put(_url(perfil["id"]), json=PADRAO | {"version": 3}, headers=h)
    assert r.status_code == 409


@pytest.mark.parametrize(("changes", "field"), [
    ({"clipMinS": 4}, "clipMinS"),
    ({"clipMinS": 176, "clipMaxS": 180}, "clipMinS"),
    ({"clipMaxS": 9}, "clipMaxS"),
    ({"clipMaxS": 181}, "clipMaxS"),
    ({"clipMinS": 30, "clipMaxS": 34}, "clipMaxS"),
    ({"quantidade": 0}, "quantidade"),
    ({"quantidade": 16}, "quantidade"),
    ({"layout": "grade"}, "layout"),
    ({"formato": "horizontal"}, "formato"),
    ({"legenda": "auto"}, "legenda"),
])
def test_faixas_invalidas(client, owner, perfil, changes, field):
    r = _put(client, owner[1], perfil["id"], 0, **changes)
    assert r.status_code == 400, r.text
    err = r.json()["error"]
    assert err["code"] == "invalid_padroes" and err["details"]["field"] == field


def test_conta_padrao_do_perfil_e_ativa(client, owner, perfil):
    _, h = owner
    r = client.post(f"/api/perfis/{perfil['id']}/contas",
                    json={"platform": "tiktok", "handle": "taverna"}, headers=h)
    assert r.status_code == 201, r.text
    conta = r.json()["conta"]
    outro = client.post("/api/perfis", json={"name": "Outro", "slug": "outro"}, headers=h)
    r2 = client.post(f"/api/perfis/{outro.json()['perfil']['id']}/contas",
                     json={"platform": "tiktok", "handle": "outro"}, headers=h)
    conta_outra = r2.json()["conta"]

    r = _put(client, h, perfil["id"], 0, contaPadraoId=conta_outra["id"])
    assert r.status_code == 400 and r.json()["error"]["details"]["field"] == "contaPadraoId"

    r = client.post(f"/api/contas/{conta['id']}/archive", json={"version": conta["version"]},
                    headers=h)
    assert r.status_code == 200, r.text
    r = _put(client, h, perfil["id"], 0, contaPadraoId=conta["id"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_padroes"

    r = client.post(f"/api/contas/{conta['id']}/restore", json={"version": conta["version"] + 1},
                    headers=h)
    assert r.status_code == 200, r.text
    r = _put(client, h, perfil["id"], 0, contaPadraoId=conta["id"])
    assert r.status_code == 200 and r.json()["padroes"]["contaPadraoId"] == conta["id"]


def test_revert_so_pelo_dono(client, owner, member, perfil):
    _, h = owner
    _put(client, h, perfil["id"], 0, clipMinS=20)
    _put(client, h, perfil["id"], 1, clipMinS=40, clipMaxS=90)

    r = client.post(_url(perfil["id"]) + "/revert", json={"version": 2, "toVersion": 1},
                    headers=member[1])
    assert r.status_code == 403

    r = client.post(_url(perfil["id"]) + "/revert", json={"version": 2, "toVersion": 1},
                    headers=h)
    assert r.status_code == 200, r.text
    p = r.json()["padroes"]
    assert (p["version"], p["clipMinS"], p["clipMaxS"]) == (3, 20, 60)
    (v, *_) = client.get(_url(perfil["id"]) + "/versions", headers=h).json()["items"]
    assert v["action"] == "reverted" and v["details"] == {"from_version": 1}

    r = client.post(_url(perfil["id"]) + "/revert", json={"version": 2, "toVersion": 1},
                    headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
