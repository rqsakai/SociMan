"""Fundo com imagem no gancho e no card final (T031; FR-005a, FR-005b; contracts/http-api.md
"Imagens de fundo"): envio e lista, referência no kit, compatibilidade e exportação."""

import io
import uuid

import pytest
from PIL import Image as PILImage
from sqlalchemy import select, text

from sociman_api import midia, storage
from sociman_api.config import get_settings
from sociman_api.perfis.models import Image, ImageKind

PW = "senha-forte-123"
KIT_KEYS = ("palette", "caption", "hook", "watermark", "endCard", "catchphrases", "series")


@pytest.fixture
def h(client, make_user, login):
    user = make_user(role="membro")
    return login(client, user.email, PW)


def _perfil(client, h, slug: str = "queridinhos") -> dict:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


@pytest.fixture
def perfil(client, h) -> dict:
    return _perfil(client, h)


def _img(size=(600, 800), fmt: str = "JPEG", mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    color = (30, 120, 200) if mode == "RGB" else (30, 120, 200, 128)
    PILImage.new(mode, size, color).save(buf, format=fmt)
    return buf.getvalue()


def _post(client, h, perfil, data: bytes):
    return client.post(f"/api/perfis/{perfil['id']}/fundos", headers=h,
                       files={"file": ("fundo.bin", data, "application/octet-stream")})


def _upload(client, h, perfil, data: bytes | None = None) -> dict:
    r = _post(client, h, perfil, data or _img())
    assert r.status_code == 201, r.text
    return r.json()["image"]


def _kit(client, h, perfil) -> dict:
    r = client.get(f"/api/perfis/{perfil['id']}/kit", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["kit"]


def _put(client, h, perfil, kit: dict, **sections):
    body = {k: kit[k] for k in KIT_KEYS} | sections
    return client.put(f"/api/perfis/{perfil['id']}/kit", headers=h,
                      json={"version": kit["version"], **body})


# ---- envio e lista (FR-005b) ----

def test_envio_e_lista(client, h, perfil, db, s3):
    img = _upload(client, h, perfil)
    assert (img["width"], img["height"]) == (600, 800)
    assert img["urls"]["thumb"].startswith("/img/")
    row = db.get(Image, uuid.UUID(img["id"]))
    assert row.kind == ImageKind.fundo and row.content_type == "image/jpeg"
    assert s3.keys() == [row.object_key]  # bucket `imagens`
    # Não altera o kit.
    kit = _kit(client, h, perfil)
    assert kit["version"] == 0 and kit["hook"]["fundo_tipo"] == "cor"

    img2 = _upload(client, h, perfil, _img(size=(540, 540), fmt="PNG", mode="RGBA"))
    img3 = _upload(client, h, perfil, _img(fmt="WEBP"))
    r = client.get(f"/api/perfis/{perfil['id']}/fundos", headers=h)
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [img3["id"], img2["id"], img["id"]]

    # Só as de fundo do próprio perfil (nem marca d'água, nem outro perfil).
    buf = io.BytesIO()
    PILImage.new("RGBA", (128, 128), (0, 0, 0, 0)).save(buf, format="PNG")
    assert client.post(f"/api/perfis/{perfil['id']}/marca-dagua", headers=h,
                       files={"file": ("wm.png", buf.getvalue(), "image/png")}
                       ).status_code == 201
    outro = _perfil(client, h, "outro")
    _upload(client, h, outro)
    r = client.get(f"/api/perfis/{perfil['id']}/fundos", headers=h)
    assert len(r.json()["items"]) == 3

    # O link sem validade serve a própria imagem (exportação).
    got = client.get(midia.link("fundo", row.id, ttl=None).url)
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert got.content == storage.get(row.object_key)
    # Um link de fundo não serve uma imagem de outro tipo.
    wm_id = client.get(f"/api/perfis/{perfil['id']}/marca-dagua",
                       headers=h).json()["items"][0]["id"]
    assert client.get(midia.link("fundo", uuid.UUID(wm_id), ttl=None).url).status_code == 404


@pytest.mark.parametrize(("data", "message"), [
    (_img(size=(539, 900)), "Imagem pequena demais"),
    (_img(size=(900, 500), fmt="PNG"), "Imagem pequena demais"),
    (_img(fmt="GIF"), "Formato não aceito"),
    (b"nada de imagem", "Formato não aceito"),
])
def test_invalida(client, h, perfil, db, data, message):
    r = _post(client, h, perfil, data)
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "invalid_image", "message": message}
    assert db.scalars(select(Image)).all() == []


def test_hd_fora_503(client, h, perfil, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = _post(client, h, perfil, _img())
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"


def test_perfil_inexistente_404_e_sem_login_401(client, h, perfil):
    assert _post(client, h, {"id": str(uuid.uuid4())}, _img()).status_code == 404
    assert client.get(f"/api/perfis/{uuid.uuid4()}/fundos", headers=h).status_code == 404
    assert client.get(f"/api/perfis/{perfil['id']}/fundos").status_code == 401
    assert client.post(f"/api/perfis/{perfil['id']}/fundos",
                       files={"file": ("f.jpg", _img(), "image/jpeg")}).status_code == 401


# ---- kit (FR-005a) ----

def test_kit_com_fundo_imagem(client, h, perfil):
    fundo = _upload(client, h, perfil)
    kit = _kit(client, h, perfil)
    assert kit["endCard"]["opacidade_fundo"] == 0.45

    # Imagem sem id, com a seção ligada.
    r = _put(client, h, perfil, kit, hook=kit["hook"] | {"fundo_tipo": "imagem"})
    assert r.status_code == 400
    assert r.json()["error"]["message"] == "hook.fundo_imagem_id: escolha a imagem de fundo"

    # Imagem que não existe.
    card = kit["endCard"] | {"ligado": True, "fundo_tipo": "imagem",
                             "fundo_imagem_id": str(uuid.uuid4())}
    r = _put(client, h, perfil, kit, endCard=card)
    assert r.status_code == 400
    assert r.json()["error"]["details"] == {"field": "endCard.fundo_imagem_id"}

    # Spec 029 (FR-013): a imagem de outro perfil vale (biblioteca da agência).
    outro = _upload(client, h, _perfil(client, h, "outro"))
    card = kit["endCard"] | {"ligado": True, "fundo_tipo": "imagem",
                             "fundo_imagem_id": outro["id"]}
    r = _put(client, h, perfil, kit, endCard=card)
    assert r.status_code == 200, r.text
    kit = r.json()["kit"]

    hook = kit["hook"] | {"fundo_tipo": "imagem", "fundo_imagem_id": fundo["id"]}
    card = kit["endCard"] | {"ligado": True, "fundo_tipo": "imagem",
                             "fundo_imagem_id": fundo["id"], "opacidade_fundo": 0.6}
    r = _put(client, h, perfil, kit, hook=hook, endCard=card)
    assert r.status_code == 200, r.text
    saved = r.json()["kit"]
    assert saved["hook"]["fundo_imagem_id"] == fundo["id"]
    assert saved["endCard"]["opacidade_fundo"] == 0.6


def test_marca_dagua_nao_serve_de_fundo(client, h, perfil):
    buf = io.BytesIO()
    PILImage.new("RGBA", (128, 128), (0, 0, 0, 0)).save(buf, format="PNG")
    wm = client.post(f"/api/perfis/{perfil['id']}/marca-dagua", headers=h,
                     files={"file": ("wm.png", buf.getvalue(), "image/png")}).json()["image"]
    kit = _kit(client, h, perfil)
    r = _put(client, h, perfil, kit,
             hook=kit["hook"] | {"fundo_tipo": "imagem", "fundo_imagem_id": wm["id"]})
    assert r.status_code == 400
    assert r.json()["error"]["message"] == \
        "hook.fundo_imagem_id: imagem de fundo não encontrada"


def test_kit_salvo_sem_os_campos_novos_continua_valido(client, h, perfil, db):
    kit = _kit(client, h, perfil)
    assert _put(client, h, perfil, kit).status_code == 200
    # Como um kit salvo antes do fundo com imagem.
    db.execute(text(
        "UPDATE brand_kits SET hook = hook - 'fundo_tipo' - 'fundo_imagem_id', "
        "end_card = end_card - 'fundo_tipo' - 'fundo_imagem_id' - 'opacidade_fundo' "
        "WHERE perfil_id = :p"), {"p": perfil["id"]})
    db.commit()
    kit = _kit(client, h, perfil)
    assert (kit["hook"]["fundo_tipo"], kit["hook"]["fundo_imagem_id"]) == ("cor", None)
    assert kit["endCard"]["opacidade_fundo"] == 0.45
    r = client.get(f"/api/perfis/{perfil['id']}/kit/export", headers=h)
    assert r.status_code == 200 and r.json()["assets"]["backgroundImages"] == []


# ---- exportação ----

def test_export_lista_a_imagem_de_fundo(client, h, perfil):
    fundo = _upload(client, h, perfil)
    kit = _kit(client, h, perfil)
    hook = kit["hook"] | {"fundo_tipo": "imagem", "fundo_imagem_id": fundo["id"]}
    card = kit["endCard"] | {"ligado": True, "fundo_tipo": "imagem",
                             "fundo_imagem_id": fundo["id"]}
    assert _put(client, h, perfil, kit, hook=hook, endCard=card).status_code == 200

    doc = client.get(f"/api/perfis/{perfil['id']}/kit/export", headers=h).json()
    [asset] = doc["assets"]["backgroundImages"]  # a mesma imagem nas duas seções: uma vez só
    assert asset["id"] == fundo["id"] and asset["expiresAt"] is None
    claims = midia.verify(asset["url"].removeprefix("/api/midia/"))
    assert (claims.kind, claims.id, claims.exp) == ("fundo", uuid.UUID(fundo["id"]), None)
    assert doc["tokens"]["hook"]["fundo_imagem_url"] == asset["url"]
    assert doc["tokens"]["endCard"]["fundo_imagem_url"] == asset["url"]
    assert doc["tokens"]["endCard"]["opacidade_fundo"] == 0.45
    assert "hook: o gerador não tem fundo com imagem; vale só a cor do fundo" in \
        doc["openshorts"]["approximations"]
