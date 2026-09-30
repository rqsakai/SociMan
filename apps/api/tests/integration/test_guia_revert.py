"""Histórico e reversão do guia (spec 017, T018; US1-5, research R12, SC-004): versões com
autor, reversão só do dono (`reverted` com `from_version`), a versão alvo revalidada com as
regras de hoje, conta arquivada e históricos separados da conta e do guia."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Conta, Perfil, Platform

PW = "senha-forte-123"


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


@pytest.fixture
def perfil(db) -> Perfil:
    p = Perfil(slug=f"taverna-{uuid.uuid4().hex[:6]}", name="A Taverna")
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def conta(db, perfil) -> Conta:
    c = Conta(perfil_id=perfil.id, platform=Platform.tiktok, handle="atavernanerd",
              url="https://www.tiktok.com/@atavernanerd")
    db.add(c)
    db.commit()
    return c


def _put(client, h, url, version, **campos):
    r = client.put(url, headers=h, json={"version": version, "campos": campos})
    return r


def _revert(client, h, url, version, to_version):
    return client.post(f"{url}/revert", headers=h,
                       json={"version": version, "toVersion": to_version})


def test_versions_e_revert_do_perfil(client, dono, membro, perfil):
    url = f"/api/perfis/{perfil.id}/guia"
    h = dono[1]
    assert _put(client, h, url, 0, tom="Nerd").status_code == 200
    assert _put(client, h, url, 1, tom="Sério", faca=["Cite a fonte"]).status_code == 200
    items = client.get(f"{url}/versions", headers=membro[1]).json()["items"]
    assert [(v["version"], v["action"], v["actor"]["name"]) for v in items] == [
        (2, "updated", "Dono"), (1, "created", "Dono")]
    assert set(items[0]["changedFields"]) == {"tom", "faca"}

    r = _revert(client, membro[1], url, 2, 1)
    assert r.status_code == 403
    r = _revert(client, h, url, 1, 1)
    assert r.status_code == 409  # versão velha
    r = _revert(client, h, url, 2, 1)
    assert r.status_code == 200, r.text
    g = r.json()["guia"]
    assert g["version"] == 3 and g["campos"]["tom"] == "Nerd" and g["campos"]["faca"] == []
    v = client.get(f"{url}/versions", headers=h).json()["items"][0]
    assert v["action"] == "reverted" and v["details"] == {"from_version": 1}
    assert _revert(client, h, url, 3, 3).status_code == 400  # a versão atual
    assert _revert(client, h, url, 3, 9).status_code == 404
    assert _revert(client, h, f"/api/perfis/{uuid.uuid4()}/guia", 1, 2).status_code == 404


def test_revert_sem_guia_404(client, dono, perfil, conta):
    for url in (f"/api/perfis/{perfil.id}/guia", f"/api/contas/{conta.id}/guia"):
        assert _revert(client, dono[1], url, 1, 2).status_code == 404


def test_revert_para_versao_que_hoje_viola_a_validacao(client, dono, perfil, conta):
    h = dono[1]
    url_c = f"/api/contas/{conta.id}/guia"
    url_p = f"/api/perfis/{perfil.id}/guia"
    assert _put(client, h, url_c, 0, vocabulario=["clickbait"]).status_code == 200
    assert _put(client, h, url_c, 1, vocabulario=["taverneiro"]).status_code == 200
    assert _put(client, h, url_p, 0, proibidas=["clickbait"]).status_code == 200
    r = _revert(client, h, url_c, 2, 1)
    assert r.status_code == 400
    assert r.json()["error"]["details"]["fields"] == {
        "vocabulario.0": "usa a palavra proibida 'clickbait'"}
    # Soma das fixas: a versão antiga da conta com 5 fixas não cabe com a fixa nova do perfil.
    assert _put(client, h, url_c, 2, hashtagsFixas=[f"#c{i}" for i in range(4)]).status_code \
        == 200
    assert _put(client, h, url_c, 3).status_code == 200
    assert _put(client, h, url_p, 1, proibidas=["clickbait"],
                hashtagsFixas=["#taverna", "#rpg"]).status_code == 200
    r = _revert(client, h, url_c, 4, 3)
    assert r.status_code == 400
    assert "hashtagsFixas" in r.json()["error"]["details"]["fields"]


def test_revert_da_conta_e_historicos_separados(client, dono, perfil, conta, db):
    h = dono[1]
    url = f"/api/contas/{conta.id}/guia"
    assert _put(client, h, url, 0, tom="Zoeiro").status_code == 200
    assert _put(client, h, url, 1, tom="Sério").status_code == 200
    r = _revert(client, h, url, 2, 1)
    assert r.status_code == 200
    body = r.json()
    assert body["guia"]["version"] == 3 and body["guia"]["campos"]["tom"] == "Zoeiro"
    assert body["perfil"]["version"] == 0
    # O histórico da conta (spec 003) não ganhou versão com o guia.
    assert db.scalar(select(func.count()).select_from(EntityVersion).where(
        EntityVersion.entity_type == "conta", EntityVersion.entity_id == conta.id)) == 0
    antes = client.get(f"{url}/versions", headers=h).json()["items"]
    # Mexer na conta (PATCH da spec 003) não muda o histórico do guia.
    r = client.patch(f"/api/contas/{conta.id}", headers=h,
                     json={"version": conta.version, "notes": "nota"})
    assert r.status_code == 200, r.text
    assert client.get(f"{url}/versions", headers=h).json()["items"] == antes


def test_revert_com_conta_arquivada_409(client, dono, perfil, conta, db):
    h = dono[1]
    url = f"/api/contas/{conta.id}/guia"
    assert _put(client, h, url, 0, tom="Zoeiro").status_code == 200
    assert _put(client, h, url, 1, tom="Sério").status_code == 200
    conta.archived_at = datetime.now(UTC)
    db.commit()
    r = _revert(client, h, url, 2, 1)
    assert r.status_code == 409 and r.json()["error"]["message"] == "Esta conta está arquivada"
    assert len(client.get(f"{url}/versions", headers=h).json()["items"]) == 2
