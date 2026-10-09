"""Regras por tipo de campo (spec 008, T034; US2, R2): padrão no código, edição pelo dono com
histórico, "voltar ao padrão", reversão e a regra em vigor na geração seguinte."""

import uuid

import pytest
from fakes.anthropic_fake import anthropic_fake  # noqa: F401
from sqlalchemy import select

from sociman_api.history import EntityVersion
from sociman_api.ia import regras_padrao
from sociman_api.ia.cliente import get_ia_client
from sociman_api.ia.models import IaChamada, IaRegra
from sociman_api.ia.tipos import TIPOS
from sociman_api.main import app

PW = "senha-forte-123"
URL = "/api/ia/tipos/postagem.titulo"


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


def _put(client, h, texto, version):
    return client.put(f"{URL}/regras", headers=h, json={"version": version, "texto": texto})


def test_lista_os_13_tipos_no_padrao(client, membro):
    r = client.get("/api/ia/tipos", headers=membro[1])
    assert r.status_code == 200
    items = r.json()["items"]
    # Spec 017: o `guia.testar` usa as regras de `postagem.textos` e fica fora da lista.
    assert [t["id"] for t in items] == [t for t in TIPOS if TIPOS[t].listar_regras]
    for t in items:
        assert t["regras"]["personalizada"] is False and t["regras"]["version"] == 0
        assert t["regras"]["texto"] == t["regras"]["padrao"] == TIPOS[t["id"]].padrao
        assert t["regras"]["padraoAtualizado"] is False
    bordoes = next(t for t in items if t["id"] == "kit.bordoes")
    assert bordoes["formato"] == "sugestoes" and bordoes["limites"]["maxSugestoes"] == 10
    assert bordoes["limites"]["maxCharsItem"] == 120
    r = client.get(URL, headers=membro[1])
    assert r.json()["tipo"]["limites"]["maxChars"] == 100
    assert r.json()["tipo"]["limites"]["umaLinha"] is True


def test_tipo_inexistente_404(client, dono):
    h = dono[1]
    for r in (client.get("/api/ia/tipos/nao.existe", headers=h),
              client.put("/api/ia/tipos/nao.existe/regras", headers=h,
                         json={"version": 0, "texto": "x"}),
              client.get("/api/ia/tipos/nao.existe/versions", headers=h)):
        assert r.status_code == 404 and r.json()["error"]["code"] == "ia_tipo_not_found"


def test_dono_edita_com_historico_e_conflito(client, db, dono):
    user, h = dono
    r = _put(client, h, "Sempre com emoji no começo.", 0)
    assert r.status_code == 200, r.text
    regras = r.json()["tipo"]["regras"]
    assert regras["personalizada"] and regras["version"] == 1
    assert regras["texto"] == "Sempre com emoji no começo."
    assert regras["updatedBy"]["id"] == str(user.id)
    assert _put(client, h, "outra", 0).status_code == 409  # versão velha
    r = _put(client, h, "Sempre com emoji.", 1)
    assert r.status_code == 200 and r.json()["tipo"]["regras"]["version"] == 2
    vs = client.get(f"{URL}/versions", headers=h).json()["items"]
    assert [v["action"] for v in vs] == ["updated", "created"]
    assert vs[0]["actor"]["id"] == str(user.id) and vs[0]["changedFields"] == ["texto"]
    row = db.scalar(select(EntityVersion).where(EntityVersion.entity_type == "ia_regra",
                                                EntityVersion.version == 1))
    assert row.after == {"tipo_campo": "postagem.titulo", "texto": "Sempre com emoji no começo."}


@pytest.mark.parametrize("texto", ["", "   ", "x" * 8001])
def test_texto_vazio_ou_grande_400(client, dono, texto):
    assert _put(client, dono[1], texto, 0).status_code == 400


def test_membro_so_le(client, dono, membro):
    h = membro[1]
    assert _put(client, h, "x", 0).status_code == 403
    assert client.post(f"{URL}/padrao", headers=h, json={"version": 0}).status_code == 403
    assert client.post(f"{URL}/revert", headers=h,
                       json={"version": 1, "toVersion": 1}).status_code == 403
    assert client.get(f"{URL}/versions", headers=h).status_code == 200


def test_voltar_ao_padrao_e_reverter(client, db, dono):
    h = dono[1]
    _put(client, h, "Regra do dono.", 0)
    r = client.post(f"{URL}/padrao", headers=h, json={"version": 1})
    assert r.status_code == 200, r.text
    regras = r.json()["tipo"]["regras"]
    assert not regras["personalizada"] and regras["version"] == 2
    assert regras["texto"] == TIPOS["postagem.titulo"].padrao
    assert db.scalar(select(IaRegra.texto)) is None
    vs = client.get(f"{URL}/versions", headers=h).json()["items"]
    assert vs[0]["details"] == {"padrao": True}
    # Já no padrão: nada a fazer.
    assert client.post(f"{URL}/padrao", headers=h, json={"version": 2}).status_code == 400
    r = client.post(f"{URL}/revert", headers=h, json={"version": 2, "toVersion": 1})
    assert r.status_code == 200, r.text
    regras = r.json()["tipo"]["regras"]
    assert regras["texto"] == "Regra do dono." and regras["version"] == 3
    vs = client.get(f"{URL}/versions", headers=h).json()["items"]
    assert vs[0]["action"] == "reverted" and vs[0]["details"] == {"from_version": 1}
    assert client.post(f"{URL}/revert", headers=h,
                       json={"version": 1, "toVersion": 1}).status_code == 409


def test_padrao_nunca_editado(client, dono):
    h = dono[1]
    r = client.post(f"{URL}/padrao", headers=h, json={"version": 0})
    assert r.status_code == 400
    assert client.get(f"{URL}/versions", headers=h).json()["items"] == []


def test_padrao_atualizado(client, dono, monkeypatch):
    h = dono[1]
    _put(client, h, "Regra do dono.", 0)
    versao, texto = regras_padrao.PADROES["postagem.titulo"]
    monkeypatch.setitem(regras_padrao.PADROES, "postagem.titulo", (versao + 1, texto + " Novo."))
    regras = client.get(URL, headers=h).json()["tipo"]["regras"]
    assert regras["padraoAtualizado"] is True and regras["padrao"].endswith("Novo.")


def test_geracao_seguinte_usa_a_regra_nova(client, db, dono, anthropic_fake):  # noqa: F811
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    h = dono[1]
    perfil = client.post("/api/perfis", headers=h,
                         json={"name": "P", "slug": "p-regra"}).json()["perfil"]
    _put(client, h, "REGRA NOVA DO DONO", 0)
    r = client.post("/api/ia/gerar", headers=h, json={
        "tipoCampo": "perfil.bio", "perfilId": perfil["id"],
        "alvo": {"entityType": "perfil", "entityId": perfil["id"]},
        "sessaoId": str(uuid.uuid4())})
    assert r.status_code == 200
    assert r.json()["chamada"]["regrasVersion"] == 0  # outra regra: padrão
    assert TIPOS["perfil.bio"].padrao in anthropic_fake.bodies[-1]["system"][1]["text"]

    client.put("/api/ia/tipos/perfil.bio/regras", headers=h,
               json={"version": 0, "texto": "REGRA NOVA DO DONO"})
    r = client.post("/api/ia/gerar", headers=h, json={
        "tipoCampo": "perfil.bio", "perfilId": perfil["id"],
        "alvo": {"entityType": "perfil", "entityId": perfil["id"]},
        "sessaoId": str(uuid.uuid4())})
    assert r.json()["chamada"]["regrasVersion"] == 1
    assert "REGRA NOVA DO DONO" in anthropic_fake.bodies[-1]["system"][1]["text"]
    row = db.get(IaChamada, uuid.UUID(r.json()["chamada"]["id"]))
    assert row.padrao_versao is None
