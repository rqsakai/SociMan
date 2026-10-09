"""Imagem própria de marca d'água (T020; contracts/http-api.md "Imagem de marca d'água")."""

import io
import uuid

import pytest
from PIL import Image as PILImage
from sqlalchemy import select

from sociman_api import midia, storage
from sociman_api.config import get_settings
from sociman_api.perfis.models import Image, ImageKind

PW = "senha-forte-123"


@pytest.fixture
def h(client, make_user, login):
    user = make_user(role="membro")
    return login(client, user.email, PW)


@pytest.fixture
def perfil(client, h) -> dict:
    r = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _png(alpha: int = 0, size=(128, 96), fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    mode = "RGB" if fmt == "JPEG" else "RGBA"
    color = (255, 95, 162) if mode == "RGB" else (255, 95, 162, alpha)
    PILImage.new(mode, size, color).save(buf, format=fmt)
    return buf.getvalue()


def _post(client, h, perfil, data: bytes):
    return client.post(f"/api/perfis/{perfil['id']}/marca-dagua", headers=h,
                       files={"file": ("wm.bin", data, "application/octet-stream")})


def test_envio_e_lista(client, h, perfil, db, s3):
    r1 = _post(client, h, perfil, _png())
    assert r1.status_code == 201, r1.text
    img = r1.json()["image"]
    assert (img["width"], img["height"]) == (128, 96)
    assert img["urls"]["thumb"].startswith("/img/") and img["urls"]["medium"].startswith("/img/")
    row = db.get(Image, uuid.UUID(img["id"]))
    assert row.kind == ImageKind.watermark and row.content_type == "image/png"
    assert s3.keys() == [row.object_key]  # bucket `imagens` (o que o imgproxy lê)
    # Não altera o kit nem o perfil.
    kit = client.get(f"/api/perfis/{perfil['id']}/kit", headers=h).json()["kit"]
    assert kit["version"] == 0 and kit["watermark"]["imagem_id"] is None

    img2 = _post(client, h, perfil, _png(alpha=100, fmt="WEBP")).json()["image"]
    r = client.get(f"/api/perfis/{perfil['id']}/marca-dagua", headers=h)
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [img2["id"], img["id"]]

    # O link assinado serve a própria imagem (para a exportação e o worker).
    got = client.get(midia.link("marca_dagua", uuid.UUID(img["id"]), ttl=None).url)
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    assert got.content == storage.get(row.object_key)


def test_lista_so_marca_dagua_do_perfil(client, h, perfil):
    logo = io.BytesIO()
    PILImage.new("RGB", (256, 256), (1, 2, 3)).save(logo, format="PNG")
    r = client.put(f"/api/perfis/{perfil['id']}/logo", headers=h,
                   files={"file": ("l.png", logo.getvalue(), "image/png")},
                   data={"version": str(perfil["version"])})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/perfis/{perfil['id']}/marca-dagua",
                      headers=h).json()["items"] == []


@pytest.mark.parametrize(("data", "message"), [
    (_png(alpha=255), "A imagem precisa ter fundo transparente"),
    (_png(fmt="JPEG"), "Formato não aceito"),
    (b"GIF89a nada", "Formato não aceito"),
    (_png(size=(40, 40)), "Imagem pequena demais"),
])
def test_invalida(client, h, perfil, db, data, message):
    r = _post(client, h, perfil, data)
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "invalid_image", "message": message}
    assert db.scalars(select(Image)).all() == []


def test_maior_que_5mb(client, h, perfil):
    r = _post(client, h, perfil, b"\x89PNG" + b"\x00" * (5 * 1024 * 1024))
    assert r.status_code == 400 and r.json()["error"]["message"] == "Arquivo maior que 5 MB"


def test_hd_fora_503(client, h, perfil, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = _post(client, h, perfil, _png())
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"


def test_perfil_inexistente_404_e_sem_login_401(client, h, perfil):
    assert _post(client, h, {"id": str(uuid.uuid4())}, _png()).status_code == 404
    assert client.get(f"/api/perfis/{uuid.uuid4()}/marca-dagua", headers=h).status_code == 404
    assert client.get(f"/api/perfis/{perfil['id']}/marca-dagua").status_code == 401
