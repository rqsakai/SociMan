"""Baixar o original e copiar link (T035; research R7, FR-008): `MidiaKind imagem`."""

import hashlib
import uuid

from sociman_api import midia
from sociman_api.config import get_settings

from .test_assets import create, img, shortcut

PW = "senha-forte-123"


def _setup(client, make_user, login):
    user = make_user(role="membro")
    h = login(client, user.email, PW)
    perfil = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"},
                         headers=h).json()["perfil"]
    return h, perfil


def test_link_estavel_sem_login_e_download(client, make_user, login, s3):
    h, perfil = _setup(client, make_user, login)
    data = img((600, 800))
    r = shortcut(client, h, perfil, "fundo", data, filename="Pôr do sol.jpg")
    asset, f = r.json()["asset"], r.json()["file"]
    again = client.get(f"/api/assets/{asset['id']}", headers=h).json()["asset"]["files"][0]
    assert again["link"] == f["link"]  # estável
    claims = midia.verify(f["link"].removeprefix(midia.PATH_PREFIX))
    assert (claims.kind, claims.exp) == ("imagem", None)

    got = client.get(f["link"])  # sem login
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert hashlib.sha256(got.content).hexdigest() == hashlib.sha256(data).hexdigest()
    assert "content-disposition" not in got.headers

    dl = client.get(f["downloadUrl"])
    assert dl.status_code == 200
    assert 'filename="queridinhos-por-do-sol-1.jpg"' in dl.headers["content-disposition"]
    assert dl.content == data

    part = client.get(f["link"], headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == data[:10]

    # Continua valendo com o asset arquivado.
    client.post(f"/api/assets/{asset['id']}/archive", headers=h,
                json={"version": asset["version"]})
    assert client.get(f["link"]).status_code == 200

    body, sig = f["link"].removeprefix(midia.PATH_PREFIX).split(".")
    r = client.get(f"{midia.PATH_PREFIX}{body}.{sig[:-2]}AA")
    assert r.status_code == 403 and r.json()["error"]["code"] == "invalid_link"


def test_link_de_marca_dagua_para_sticker_e_links_de_1h(client, make_user, login, s3):
    h, perfil = _setup(client, make_user, login)
    st = shortcut(client, h, perfil, "sticker", img((100, 100), "PNG", alpha=0)).json()
    image_id = uuid.UUID(st["file"]["image"]["id"])
    assert client.get(midia.link("marca_dagua", image_id, ttl=None).url).status_code == 200
    r = client.post("/api/midia/links", headers=h,
                    json={"items": [{"kind": "imagem", "id": str(image_id)}]})
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["expiresAt"] is not None
    r = client.post("/api/midia/links", headers=h,
                    json={"items": [{"kind": "imagem", "id": str(uuid.uuid4())}]})
    assert r.status_code == 404


def test_hd_fora_503(client, make_user, login, s3, tmp_path, monkeypatch):
    h, perfil = _setup(client, make_user, login)
    f = shortcut(client, h, perfil, "imagem", img((64, 64))).json()["file"]
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = client.get(f["link"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
    create(client, h, perfil, tipo="avatar", name="Sem HD")  # a biblioteca segue listando
    assert client.get(f"/api/perfis/{perfil['id']}/assets", headers=h).status_code == 200
