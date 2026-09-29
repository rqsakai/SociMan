"""Onde é usado, kit e arquivamento (T023, T034; research R5 e R6, Q1 = A): só o kit bloqueia
arquivar; cortes só informam."""

import uuid
from decimal import Decimal

import pytest

from sociman_api.cortes.models import Corte
from sociman_api.cortes.service import resolve_corte_tokens
from sociman_api.marca.service_kit import current_tokens
from sociman_api.perfis.models import Image, Perfil

from .test_assets import add_file, create, error, img, shortcut

PW = "senha-forte-123"
KIT_KEYS = ("palette", "caption", "hook", "watermark", "endCard", "catchphrases", "series")


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def h(owner):
    return owner[1]


@pytest.fixture
def perfil(client, h) -> dict:
    r = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"},
                    headers=h)
    return r.json()["perfil"]


def _kit(client, h, perfil) -> dict:
    return client.get(f"/api/perfis/{perfil['id']}/kit", headers=h).json()["kit"]


def _put(client, h, perfil, kit: dict, **sections):
    body = {k: kit[k] for k in KIT_KEYS} | sections
    return client.put(f"/api/perfis/{perfil['id']}/kit", headers=h,
                      json={"version": kit["version"], **body})


def _card(kit, image_id, **extra) -> dict:
    return kit["endCard"] | {"ligado": True, "fundo_tipo": "imagem",
                             "fundo_imagem_id": image_id} | extra


def _cenario(client, h, perfil) -> tuple[dict, dict]:
    a = create(client, h, perfil, tipo="cenario", name="Cozinha retrô", prompt="1950s kitchen")
    return add_file(client, h, a, img((600, 600)), role="referencia")


def _archive(client, h, asset):
    return client.post(f"/api/assets/{asset['id']}/archive", headers=h,
                       json={"version": asset["version"]})


def _fresh(client, h, asset) -> dict:
    return client.get(f"/api/assets/{asset['id']}", headers=h).json()


def test_kit_aceita_cenario_e_sticker(client, h, perfil):
    _, ref = _cenario(client, h, perfil)
    st = shortcut(client, h, perfil, "sticker", img((100, 100), "PNG", alpha=0)).json()
    kit = _kit(client, h, perfil)
    r = _put(client, h, perfil, kit, endCard=_card(kit, ref["image"]["id"]),
             watermark=kit["watermark"] | {"tipo": "imagem",
                                           "imagem_id": st["file"]["image"]["id"]})
    assert r.status_code == 200, r.text
    # Um sticker não serve de fundo (classe watermark), nem um cenário de marca d'água.
    kit = r.json()["kit"]
    r = _put(client, h, perfil, kit, hook=kit["hook"] | {
        "fundo_tipo": "imagem", "fundo_imagem_id": st["file"]["image"]["id"]})
    assert r.status_code == 400


def test_corte_aceita_fundo_de_cenario(client, h, perfil, db):
    _, ref = _cenario(client, h, perfil)
    kit = _kit(client, h, perfil)
    assert _put(client, h, perfil, kit, endCard=_card(kit, ref["image"]["id"])).status_code == 200
    p = db.get(Perfil, uuid.UUID(perfil["id"]))
    tokens, _ = current_tokens(db, p.id)
    resolved = resolve_corte_tokens(db, p, tokens)
    image = db.get(Image, uuid.UUID(ref["image"]["id"]))
    assert resolved["end_card"]["fundo_imagem_key"] == image.object_key


def test_arquivar_com_uso_no_kit(client, h, perfil):
    cen, ref = _cenario(client, h, perfil)
    kit = _kit(client, h, perfil)
    # Mesmo com o fundo em cor: o id guardado ainda é validado pelo kit.
    r = _put(client, h, perfil, kit, endCard=_card(kit, ref["image"]["id"], fundo_tipo="cor"))
    assert r.status_code == 200, r.text
    kit = r.json()["kit"]
    detail = _fresh(client, h, cen)
    assert detail["asset"]["inUse"] is True
    [uso] = detail["usos"]
    assert uso == {"origem": "kit", "rotulo": f"Card final (kit v{kit['version']})",
                   "campo": "endCard.fundo_imagem_id", "fileId": ref["id"], "bloqueia": True,
                   "href": f"/app/perfis/{perfil['id']}?aba=marca"}

    r = _archive(client, h, detail["asset"])
    assert error(r) == (409, "asset_in_use", f"Em uso em: Card final (kit v{kit['version']})")
    assert r.json()["error"]["details"]["usos"][0]["campo"] == "endCard.fundo_imagem_id"
    r = client.post(f"/api/assets/{cen['id']}/arquivos/{ref['id']}/archive", headers=h,
                    json={"version": detail["asset"]["version"]})
    assert error(r)[:2] == (409, "asset_in_use")
    items = client.get(f"/api/perfis/{perfil['id']}/assets", headers=h).json()["items"]
    assert items[0]["inUse"] is True

    # Troca no kit e arquiva.
    r = _put(client, h, perfil, kit, endCard=kit["endCard"] | {"fundo_imagem_id": None})
    assert r.status_code == 200, r.text
    kit_sem = r.json()["kit"]
    r = _archive(client, h, _fresh(client, h, cen)["asset"])
    assert r.status_code == 200, r.text

    # Imagem arquivada: o kit recusa salvar e reverter, os seletores não a mostram.
    r = _put(client, h, perfil, kit_sem, endCard=_card(kit_sem, ref["image"]["id"]))
    assert error(r) == (400, "invalid_kit",
                        "endCard.fundo_imagem_id: imagem arquivada; restaure-a na biblioteca")
    r = client.post(f"/api/perfis/{perfil['id']}/kit/revert", headers=h,
                    json={"version": kit_sem["version"], "toVersion": kit["version"]})
    assert error(r)[:2] == (409, "revert_conflict")
    r = client.get(f"/api/perfis/{perfil['id']}/assets/imagens?tipo=cenario", headers=h)
    assert r.json()["items"] == []


def test_uso_em_cortes_so_informa(client, h, perfil, db):
    fundo = shortcut(client, h, perfil, "fundo", img((600, 600))).json()
    image = db.get(Image, uuid.UUID(fundo["file"]["image"]["id"]))
    for i in range(7):
        db.add(Corte(
            perfil_id=uuid.UUID(perfil["id"]), hook_text="gancho", kit_version=1,
            kit_tokens={"end_card": {"fundo_imagem_key": image.object_key},
                        "hook": {"fundo_imagem_key": image.object_key}},
            original_filename="v.mp4", original_key=f"perfis/x/{uuid.uuid4()}.mp4",
            original_content_type="video/mp4", original_bytes=1, duration_ms=1000, width=1080,
            height=1920, fps=Decimal(30), video_codec="h264", original_sha256="0" * 64,
        ))
    db.commit()
    detail = _fresh(client, h, fundo["asset"])
    assert detail["asset"]["inUse"] is True
    usos = detail["usos"]
    assert usos[0]["rotulo"] == "7 cortes" and usos[0]["bloqueia"] is False
    assert len(usos) == 1 + 5  # o total e os 5 mais recentes
    assert all(u["origem"] == "corte" and not u["bloqueia"] for u in usos)
    assert usos[1]["href"].startswith("/app/cortes/")

    r = _archive(client, h, detail["asset"])  # Q1 = A: não bloqueia
    assert r.status_code == 200, r.text
    assert _fresh(client, h, fundo["asset"])["usos"][0]["rotulo"] == "7 cortes"


def test_reversao_do_asset_que_arquivaria_arquivo_em_uso(client, h, perfil):
    cen = create(client, h, perfil, tipo="cenario", name="Cozinha")
    v1 = cen["version"]
    cen, ref = add_file(client, h, cen, img((600, 600)), role="referencia")
    kit = _kit(client, h, perfil)
    assert _put(client, h, perfil, kit, endCard=_card(kit, ref["image"]["id"])).status_code == 200
    r = client.post(f"/api/assets/{cen['id']}/revert", headers=h,
                    json={"version": cen["version"], "toVersion": v1})
    assert error(r)[:2] == (409, "revert_conflict")
    assert r.json()["error"]["message"].startswith("A versão arquivaria a imagem usada em ")


def test_rotas_antigas_criam_o_asset_e_omitem_arquivadas(client, h, perfil):
    r = client.post(f"/api/perfis/{perfil['id']}/fundos", headers=h,
                    files={"file": ("f.jpg", img((600, 600)), "image/jpeg")})
    assert r.status_code == 201, r.text
    image_id = r.json()["image"]["id"]
    r = client.post(f"/api/perfis/{perfil['id']}/marca-dagua", headers=h,
                    files={"file": ("w.png", img((100, 100), "PNG", alpha=0), "image/png")})
    assert r.status_code == 201, r.text
    items = client.get(f"/api/perfis/{perfil['id']}/assets", headers=h).json()["items"]
    assert sorted((a["tipo"], a["name"]) for a in items) == [
        ("fundo", "Fundo 1"), ("marca_dagua", "Marca d'água 1")]
    fundo = next(a for a in items if a["tipo"] == "fundo")
    assert fundo["cover"]["id"] == image_id

    assert _archive(client, h, fundo).status_code == 200
    assert client.get(f"/api/perfis/{perfil['id']}/fundos", headers=h).json()["items"] == []
    assert len(client.get(f"/api/perfis/{perfil['id']}/marca-dagua",
                          headers=h).json()["items"]) == 1
    ops = client.get("/api/openapi.json").json()["paths"]
    assert ops["/api/perfis/{perfil_id}/fundos"]["post"]["deprecated"] is True
    assert ops["/api/perfis/{perfil_id}/marca-dagua"]["get"]["deprecated"] is True
