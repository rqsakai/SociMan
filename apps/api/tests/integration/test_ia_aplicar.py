"""US1 (T018): o campo `ia` nos saves do asset, do perfil e do kit (research R10).

As chamadas são semeadas direto em `ia_chamadas` (sem o Claude): aqui só interessa o que o
save faz com o `ia`.
"""

import uuid

import pytest
from sqlalchemy import select

from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaChamada, IaDesfecho

PW = "senha-forte-123"


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def member(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


@pytest.fixture
def h(member):
    return member[1]


@pytest.fixture
def perfil(client, h) -> dict:
    r = client.post("/api/perfis", json={"name": "Achadinhos", "slug": "achadinhos"},
                    headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _avatar(client, h, perfil) -> dict:
    r = client.post(f"/api/perfis/{perfil['id']}/assets", headers=h,
                    json={"tipo": "avatar", "name": "Achadinhos", "prompt": "old",
                          "voiceTone": "neutro"})
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def _chamada(db, perfil, tipo_campo, proposta, entity_type, entity_id) -> uuid.UUID:
    c = IaChamada(tipo_campo=tipo_campo, perfil_id=uuid.UUID(perfil["id"]),
                  entity_type=entity_type,
                  entity_id=uuid.UUID(entity_id) if entity_id else None, proposta=proposta,
                  model="claude-sonnet-5-5", prompt_version="ia/1", duration_ms=900)
    db.add(c)
    db.commit()
    return c.id


def _row(db, chamada_id) -> IaChamada:
    db.expire_all()
    return db.get(IaChamada, chamada_id)


def _versions(db, entity_type, entity_id) -> list[EntityVersion]:
    db.expire_all()
    return list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == entity_type,
        EntityVersion.entity_id == uuid.UUID(entity_id),
    ).order_by(EntityVersion.version)))


def _ia(tipo, cid, itens=None) -> list[dict]:
    item = {"tipoCampo": tipo, "chamadaId": str(cid)}
    if itens is not None:
        item["itens"] = itens
    return [item]


# ---- asset ----

def test_asset_aplicar_so_o_campo_marca_a_versao(client, h, member, db, perfil):
    a = _avatar(client, h, perfil)
    cid = _chamada(db, perfil, "avatar.descricao_prompt", {"texto": "A woman, 30s"}, "asset",
                   a["id"])
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "prompt": "A woman, 30s",
                           "ia": _ia("avatar.descricao_prompt", cid)})
    assert r.status_code == 200, r.text
    novo = r.json()["asset"]
    assert novo["prompt"] == "A woman, 30s" and novo["voiceTone"] == "neutro"

    v = _versions(db, "asset", a["id"])[-1]
    assert v.version == novo["version"]
    assert v.actor_kind == "user" and v.actor_user_id == member[0].id
    assert v.changed_fields == ["prompt"]
    assert v.details == {"ia": [{"campo": "prompt", "tipoCampo": "avatar.descricao_prompt",
                                 "chamadaId": str(cid), "desfecho": "aplicada"}]}
    row = _row(db, cid)
    assert row.desfecho == IaDesfecho.aplicada
    assert row.aplicada_versao == novo["version"]
    assert row.desfecho_por == member[0].id

    # US1-7: o próximo save (outro campo, sem ia) usa a versão nova e não dá 409
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": novo["version"], "voiceTone": "leve"})
    assert r.status_code == 200, r.text
    assert _versions(db, "asset", a["id"])[-1].details == {}


def test_asset_editada_e_versao_aparece_na_api(client, h, db, perfil):
    a = _avatar(client, h, perfil)
    cid = _chamada(db, perfil, "avatar.tom_de_voz", {"texto": "Leve"}, "asset", a["id"])
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "voiceTone": "Leve e direto",
                           "ia": _ia("avatar.tom_de_voz", cid)})
    assert r.status_code == 200, r.text
    assert _row(db, cid).desfecho == IaDesfecho.editada
    r = client.get(f"/api/assets/{a['id']}/versions", headers=h)
    assert r.json()["items"][0]["details"]["ia"][0]["desfecho"] == "editada"


def test_version_conflict_nao_grava_nada(client, h, db, perfil):
    a = _avatar(client, h, perfil)
    cid = _chamada(db, perfil, "avatar.descricao_prompt", {"texto": "x"}, "asset", a["id"])
    n = len(_versions(db, "asset", a["id"]))
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"] + 5, "prompt": "x",
                           "ia": _ia("avatar.descricao_prompt", cid)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    assert len(_versions(db, "asset", a["id"])) == n
    row = _row(db, cid)
    assert row.desfecho == IaDesfecho.sem_acao and row.aplicada_versao is None


def test_itens_que_nao_casam_nao_quebram_o_save(client, h, db, perfil):
    a = _avatar(client, h, perfil)
    outro = _avatar(client, h, perfil)
    alheia = _chamada(db, perfil, "avatar.descricao_prompt", {"texto": "y"}, "asset",
                      outro["id"])
    ia = [*_ia("avatar.descricao_prompt", alheia),
          *_ia("avatar.tom_de_voz", uuid.uuid4())]  # não existe
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "prompt": "y", "ia": ia})
    assert r.status_code == 200, r.text
    assert _versions(db, "asset", a["id"])[-1].details == {}
    assert _row(db, alheia).desfecho == IaDesfecho.sem_acao


def test_revert_de_versao_com_ia_pelo_dono(client, h, owner, db, perfil):
    a = _avatar(client, h, perfil)
    cid = _chamada(db, perfil, "avatar.descricao_prompt", {"texto": "novo"}, "asset", a["id"])
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "prompt": "novo",
                           "ia": _ia("avatar.descricao_prompt", cid)})
    novo = r.json()["asset"]
    r = client.post(f"/api/assets/{a['id']}/revert", headers=owner[1],
                    json={"version": novo["version"], "toVersion": a["version"]})
    assert r.status_code == 200, r.text
    assert r.json()["asset"]["prompt"] == "old"
    assert _versions(db, "asset", a["id"])[-1].action == "reverted"


# ---- perfil ----

def test_perfil_bio(client, h, member, db, perfil):
    cid = _chamada(db, perfil, "perfil.bio", {"texto": "Achados que valem"}, "perfil",
                   perfil["id"])
    r = client.patch(f"/api/perfis/{perfil['id']}", headers=h,
                     json={"version": perfil["version"], "bio": "Achados que valem",
                           "ia": _ia("perfil.bio", cid)})
    assert r.status_code == 200, r.text
    novo = r.json()["perfil"]
    v = _versions(db, "perfil", perfil["id"])[-1]
    assert v.changed_fields == ["bio"] and v.actor_user_id == member[0].id
    assert v.details["ia"][0]["chamadaId"] == str(cid)
    row = _row(db, cid)
    assert row.desfecho == IaDesfecho.aplicada and row.aplicada_versao == novo["version"]


# ---- kit ----

def _kit(client, h, perfil) -> dict:
    r = client.get(f"/api/perfis/{perfil['id']}/kit", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["kit"]


def _body(kit: dict, **sections) -> dict:
    keys = ("version", "palette", "caption", "hook", "watermark", "endCard", "catchphrases",
            "series")
    return {k: kit[k] for k in keys} | sections


def test_kit_nunca_salvo_cria_v1_com_o_selo(client, h, db, perfil):
    kit = _kit(client, h, perfil)
    assert kit["version"] == 0
    cid = _chamada(db, perfil, "kit.bordoes", {"itens": ["Bora achar!", "Achou?"]}, "kit",
                   None)
    r = client.put(f"/api/perfis/{perfil['id']}/kit", headers=h,
                   json=_body(kit, catchphrases=["Bora achar!"])
                   | {"ia": _ia("kit.bordoes", cid, ["Bora achar!"])})
    assert r.status_code == 200, r.text
    novo = r.json()["kit"]
    assert novo["version"] == 1 and novo["catchphrases"] == ["Bora achar!"]
    row = _row(db, cid)
    assert row.desfecho == IaDesfecho.aplicada and row.aplicada_versao == 1
    assert row.itens_aplicados == ["Bora achar!"]


def test_kit_tokens_salvos_mais_bordoes_so_muda_os_bordoes(client, h, db, perfil):
    kit = _kit(client, h, perfil)
    r = client.put(f"/api/perfis/{perfil['id']}/kit", headers=h,
                   json=_body(kit, catchphrases=["Oi gente"]))
    salvo = r.json()["kit"]
    cid = _chamada(db, perfil, "kit.bordoes", {"itens": ["Bora!", "Olha isso"]}, "kit", None)
    r = client.put(f"/api/perfis/{perfil['id']}/kit", headers=h,
                   json=_body(salvo, catchphrases=["Oi gente", "Bora!", "Olha isso aqui"])
                   | {"ia": _ia("kit.bordoes", cid, ["Bora!", "Olha isso aqui", "Oi gente"])})
    assert r.status_code == 200, r.text
    versions = client.get(f"/api/perfis/{perfil['id']}/kit/versions", headers=h).json()
    v = versions["items"][0]
    assert v["changedFields"] == ["catchphrases"]
    assert v["details"]["ia"] == [{"campo": "catchphrases", "tipoCampo": "kit.bordoes",
                                   "chamadaId": str(cid), "desfecho": "editada",
                                   "itens": ["Bora!", "Olha isso aqui"]}]
    assert "ia" not in v["after"]
    row = _row(db, cid)
    assert row.desfecho == IaDesfecho.editada and row.aplicada_versao == 2


def test_kit_version_conflict_chamada_continua_sem_acao(client, h, db, perfil):
    kit = _kit(client, h, perfil)
    client.put(f"/api/perfis/{perfil['id']}/kit", headers=h, json=_body(kit))
    cid = _chamada(db, perfil, "kit.series", {"itens": ["Achado do dia"]}, "kit", None)
    r = client.put(f"/api/perfis/{perfil['id']}/kit", headers=h,
                   json=_body(kit, series=["Achado do dia"])  # version 0: já existe v1
                   | {"ia": _ia("kit.series", cid, ["Achado do dia"])})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    assert _row(db, cid).desfecho == IaDesfecho.sem_acao
