"""US1: kit de marca do perfil (T011; contracts/http-api.md "Kit")."""

import uuid
from datetime import UTC, datetime

import pytest

from sociman_api.marca.models import BrandFont, FontFormat
from sociman_api.perfis.models import Image, ImageKind

PW = "senha-forte-123"


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def member(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


def _perfil(client, h, **overrides) -> dict:
    body = {"name": "Queridinhos", "slug": "queridinhos"} | overrides
    r = client.post("/api/perfis", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _conta(client, h, perfil: dict, handle: str = "meusqueridinhos10") -> dict:
    body = {"platform": "tiktok", "handle": handle, "status": "ativa"}
    r = client.post(f"/api/perfis/{perfil['id']}/contas", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["conta"]


def _font(db, perfil: dict, name: str = "Pergaminho", archived: bool = False) -> BrandFont:
    font = BrandFont(
        perfil_id=uuid.UUID(perfil["id"]), name=name, family=f"{name} Serif", style="Regular",
        format=FontFormat.ttf, object_key=f"perfis/{perfil['id']}/{uuid.uuid4()}.ttf",
        bytes=1234, sha256="0" * 64, archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(font)
    db.commit()
    return font


def _get(client, h, perfil: dict) -> dict:
    r = client.get(f"/api/perfis/{perfil['id']}/kit", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _body(kit: dict, **sections) -> dict:
    keys = ("version", "palette", "caption", "hook", "watermark", "endCard", "catchphrases",
            "series")
    return {k: kit[k] for k in keys} | sections


def _put(client, h, perfil: dict, body: dict):
    return client.put(f"/api/perfis/{perfil['id']}/kit", json=body, headers=h)


def _save(client, h, perfil: dict, kit: dict, **sections) -> dict:
    r = _put(client, h, perfil, _body(kit, **sections))
    assert r.status_code == 200, r.text
    return r.json()["kit"]


def _versions(client, h, perfil: dict) -> list[dict]:
    r = client.get(f"/api/perfis/{perfil['id']}/kit/versions", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ---- GET ----

def test_default_kit_has_version_zero(client, member):
    _, h = member
    perfil = _perfil(client, h)
    conta = _conta(client, h, perfil)
    data = _get(client, h, perfil)
    kit = data["kit"]
    assert kit["version"] == 0 and kit["persisted"] is False
    assert kit["perfilId"] == perfil["id"]
    assert kit["updatedAt"] is None and kit["updatedBy"] is None
    assert kit["caption"]["fonte"] == "padrao:anton"
    assert kit["watermark"]["conta_id"] == conta["id"] and kit["watermark"]["ligado"] is True
    assert [o["ref"] for o in data["fontOptions"]] == [
        "padrao:anton", "padrao:noto-serif-bold", "padrao:liberation-sans",
        "padrao:liberation-serif",
    ]
    assert data["fontOptions"][0]["url"] == "/api/fontes-padrao/anton"
    assert _versions(client, h, perfil) == []


def test_default_kit_without_conta_has_watermark_off(client, member):
    _, h = member
    perfil = _perfil(client, h)
    kit = _get(client, h, perfil)["kit"]
    assert kit["watermark"]["ligado"] is False and kit["watermark"]["conta_id"] is None
    # e é salvável como está
    assert _save(client, h, perfil, kit)["version"] == 1


def test_kit_requires_login_and_existing_perfil(client, member):
    _, h = member
    perfil = _perfil(client, h)
    assert client.get(f"/api/perfis/{perfil['id']}/kit").status_code == 401
    missing = uuid.uuid4()
    for r in (client.get(f"/api/perfis/{missing}/kit", headers=h),
              client.get(f"/api/perfis/{missing}/kit/versions", headers=h),
              _put(client, h, {"id": str(missing)}, _body(_get(client, h, perfil)["kit"]))):
        assert r.status_code == 404, r.text


def test_font_options_include_active_perfil_fonts(client, member, db):
    _, h = member
    perfil = _perfil(client, h)
    font = _font(db, perfil)
    _font(db, perfil, name="Velha", archived=True)
    options = _get(client, h, perfil)["fontOptions"]
    own = [o for o in options if o["ref"].startswith("perfil:")]
    assert [(o["ref"], o["name"]) for o in own] == [(f"perfil:{font.id}", "Pergaminho")]
    assert own[0]["url"].startswith("/api/midia/")


# ---- PUT ----

def test_first_save_creates_version_one(client, member):
    user, h = member
    perfil = _perfil(client, h)
    _conta(client, h, perfil)
    kit = _get(client, h, perfil)["kit"]
    hook = kit["hook"] | {"cor_fundo": "#ff5fa2", "cor_texto": "#FFFFFF"}
    saved = _save(client, h, perfil, kit, hook=hook, catchphrases=["Olha esse achadinho..."])
    assert saved["version"] == 1 and saved["persisted"] is True
    assert saved["hook"]["cor_fundo"] == "#FF5FA2"  # normalizado
    assert saved["catchphrases"] == ["Olha esse achadinho..."]
    assert saved["updatedBy"] == {"id": str(user.id), "name": "Membro"}
    assert saved["updatedAt"] is not None
    assert _get(client, h, perfil)["kit"] == saved
    versions = _versions(client, h, perfil)
    assert [(v["version"], v["action"]) for v in versions] == [(1, "created")]
    assert versions[0]["after"]["hook"]["cor_fundo"] == "#FF5FA2"


@pytest.mark.parametrize(("path", "value", "field"), [
    (("caption", "tamanho"), 500, "caption.tamanho"),
    (("caption", "cor_texto"), "vermelho", "caption.cor_texto"),
    (("hook", "posicao"), "lado", "hook.posicao"),
    (("hook", "duracao_s"), 1.2, "hook.duracao_s"),
    (("watermark", "escala_pct"), 80, "watermark.escala_pct"),
    (("endCard", "cta"), "x" * 81, "endCard.cta"),
    (("hook", "cor_fundo"), "paleta:rosa", "hook.cor_fundo"),
    (("hook", "fonte"), f"perfil:{uuid.uuid4()}", "hook.fonte"),
])
def test_invalid_kit_points_to_the_field(client, member, path, value, field):
    _, h = member
    perfil = _perfil(client, h)
    kit = _get(client, h, perfil)["kit"]
    section, key = path
    r = _put(client, h, perfil, _body(kit, **{section: kit[section] | {key: value}}))
    assert r.status_code == 400, r.text
    error = r.json()["error"]
    assert error["code"] == "invalid_kit"
    assert error["message"].startswith(f"{field}: "), error
    assert error["details"] == {"field": field}
    assert _get(client, h, perfil)["kit"]["version"] == 0  # nada foi salvo


def test_invalid_root_fields(client, member):
    _, h = member
    perfil = _perfil(client, h)
    kit = _get(client, h, perfil)["kit"]
    body = _body(kit)
    del body["version"]
    r = _put(client, h, perfil, body)
    assert r.status_code == 400 and r.json()["error"]["message"].startswith("version: ")
    r = _put(client, h, perfil, _body(kit, stickers=[]))
    assert r.json()["error"] == {"code": "invalid_kit",
                                 "message": "stickers: campo desconhecido",
                                 "details": {"field": "stickers"}}


def test_palette_references(client, member):
    _, h = member
    perfil = _perfil(client, h)
    kit = _get(client, h, perfil)["kit"]
    rosa = {"chave": "rosa", "nome": "Rosa Queridinhos", "valor": "#FF5FA2"}
    kit = _save(client, h, perfil, kit, palette=[*kit["palette"], rosa],
                hook=kit["hook"] | {"cor_fundo": "paleta:rosa"})
    assert kit["hook"]["cor_fundo"] == "paleta:rosa"
    # renomear a cor não quebra a referência (a chave é estável)
    palette = [c | {"nome": "Rosa Forte"} if c["chave"] == "rosa" else c for c in kit["palette"]]
    kit = _save(client, h, perfil, kit, palette=palette)
    # tirar da paleta uma cor em uso é recusado
    palette = [c for c in kit["palette"] if c["chave"] != "rosa"]
    r = _put(client, h, perfil, _body(kit, palette=palette))
    assert r.status_code == 400
    assert r.json()["error"]["message"].startswith("hook.cor_fundo: a cor paleta:rosa")


def test_perfil_font_must_be_active_and_own(client, member, db):
    _, h = member
    perfil = _perfil(client, h)
    other = _perfil(client, h, name="Taverna", slug="taverna")
    font = _font(db, perfil)
    archived = _font(db, perfil, name="Velha", archived=True)
    foreign = _font(db, other, name="Alheia")
    kit = _get(client, h, perfil)["kit"]
    for bad in (archived, foreign):
        r = _put(client, h, perfil, _body(kit, hook=kit["hook"] | {"fonte": f"perfil:{bad.id}"}))
        assert r.status_code == 400
        assert r.json()["error"]["message"].startswith("hook.fonte: ")
    saved = _save(client, h, perfil, kit, hook=kit["hook"] | {"fonte": f"perfil:{font.id}"})
    assert saved["hook"]["fonte"] == f"perfil:{font.id}"


def test_watermark_image_and_logo(client, member, db):
    _, h = member
    perfil = _perfil(client, h)
    image = Image(perfil_id=uuid.UUID(perfil["id"]), kind=ImageKind.watermark,
                  object_key=f"perfis/{perfil['id']}/wm.png", content_type="image/png",
                  bytes=100, width=256, height=256, sha256="0" * 64)
    db.add(image)
    db.commit()
    kit = _get(client, h, perfil)["kit"]
    wm = kit["watermark"] | {"ligado": True, "tipo": "logo"}
    r = _put(client, h, perfil, _body(kit, watermark=wm))
    assert r.json()["error"]["message"] == "watermark.tipo: o perfil não tem logo"
    wm = kit["watermark"] | {"ligado": True, "tipo": "imagem", "imagem_id": str(image.id)}
    saved = _save(client, h, perfil, kit, watermark=wm)
    assert saved["watermark"]["imagem_id"] == str(image.id)


def test_version_conflict(client, member):
    _, h = member
    perfil = _perfil(client, h)
    kit = _get(client, h, perfil)["kit"]
    r = _put(client, h, perfil, _body(kit, version=3))
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    v1 = _save(client, h, perfil, kit)
    r = _put(client, h, perfil, _body(kit))  # ainda com version 0
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "version_conflict",
                                 "message": "Este kit foi alterado por outra pessoa; recarregue"}
    assert _save(client, h, perfil, v1, series=["Achadinhos da semana"])["version"] == 2


def test_history_by_section_and_no_op(client, member):
    _, h = member
    perfil = _perfil(client, h)
    v1 = _save(client, h, perfil, _get(client, h, perfil)["kit"])
    v2 = _save(client, h, perfil, v1, hook=v1["hook"] | {"tamanho": "G"})
    assert v2["version"] == 2
    same = _save(client, h, perfil, v2)  # sem mudança real: sem versão nova
    assert same["version"] == 2
    v3 = _save(client, h, perfil, v2, caption=v2["caption"] | {"posicao": "topo"},
               endCard=v2["endCard"] | {"cta": "Me segue"})
    versions = _versions(client, h, perfil)
    assert [(v["version"], v["action"]) for v in versions] == [
        (3, "updated"), (2, "updated"), (1, "created")]
    assert versions[1]["changedFields"] == ["hook"]
    assert versions[1]["before"]["hook"]["tamanho"] == "M"
    assert versions[1]["after"]["hook"]["tamanho"] == "G"
    assert versions[0]["changedFields"] == ["caption", "end_card"]
    assert versions[0]["actor"]["name"] == "Membro"
    assert v3["version"] == 3


# ---- reversão ----

def test_revert_only_by_owner(client, owner, member):
    _, ho = owner
    _, hm = member
    perfil = _perfil(client, hm)
    v1 = _save(client, hm, perfil, _get(client, hm, perfil)["kit"])
    v2 = _save(client, hm, perfil, v1, hook=v1["hook"] | {"tamanho": "G"})
    body = {"version": v2["version"], "toVersion": 1}
    r = client.post(f"/api/perfis/{perfil['id']}/kit/revert", json=body, headers=hm)
    assert r.status_code == 403
    r = client.post(f"/api/perfis/{perfil['id']}/kit/revert", json=body, headers=ho)
    assert r.status_code == 200, r.text
    v3 = r.json()["kit"]
    assert v3["version"] == 3 and v3["hook"]["tamanho"] == "M"
    assert v3["updatedBy"]["name"] == "Dono"
    top = _versions(client, ho, perfil)[0]
    assert top["action"] == "reverted" and top["details"] == {"from_version": 1}
    assert top["changedFields"] == ["hook"]
    # versão desatualizada
    r = client.post(f"/api/perfis/{perfil['id']}/kit/revert",
                    json={"version": 2, "toVersion": 1}, headers=ho)
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    # versão inexistente
    r = client.post(f"/api/perfis/{perfil['id']}/kit/revert",
                    json={"version": 3, "toVersion": 9}, headers=ho)
    assert r.status_code == 404


def test_revert_blocked_by_archived_font(client, owner, db):
    _, h = owner
    perfil = _perfil(client, h)
    font = _font(db, perfil)
    kit = _get(client, h, perfil)["kit"]
    v1 = _save(client, h, perfil, kit, hook=kit["hook"] | {"fonte": f"perfil:{font.id}"})
    v2 = _save(client, h, perfil, v1, hook=v1["hook"] | {"fonte": "padrao:anton"})
    font = db.get(BrandFont, font.id)
    font.archived_at = datetime.now(UTC)
    db.commit()
    r = client.post(f"/api/perfis/{perfil['id']}/kit/revert",
                    json={"version": v2["version"], "toVersion": 1}, headers=h)
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "revert_conflict",
        "message": "A versão usa a fonte Pergaminho, que está arquivada; restaure-a antes",
    }


def test_revert_without_saved_kit_is_404(client, owner):
    _, h = owner
    perfil = _perfil(client, h)
    r = client.post(f"/api/perfis/{perfil['id']}/kit/revert",
                    json={"version": 1, "toVersion": 1}, headers=h)
    assert r.status_code == 404
