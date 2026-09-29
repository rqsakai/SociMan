"""US3: logo e banner (T020, contracts/http-api.md "Perfis"), com o MinIO real (bucket de teste)."""

import io

import pytest
from PIL import Image as PILImage
from sqlalchemy import func, select

from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Image, ImageKind, Perfil


@pytest.fixture
def member(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, "senha-forte-123")


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, "senha-forte-123")


def _create(client, headers):
    r = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"},
                    headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _img(fmt: str = "PNG", size: tuple[int, int] = (256, 256), color=(200, 40, 90)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def _put(client, headers, perfil_id, kind, data, version, name="imagem.png"):
    return client.put(f"/api/perfis/{perfil_id}/{kind}", headers=headers,
                      files={"file": (name, data, "application/octet-stream")},
                      data={"version": str(version)})


def _versions(db, perfil_id):
    db.expire_all()
    return db.scalars(
        select(EntityVersion).where(EntityVersion.entity_type == "perfil",
                                    EntityVersion.entity_id == perfil_id)
        .order_by(EntityVersion.version)
    ).all()


def _image_count(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Image))


@pytest.mark.parametrize(("fmt", "content_type", "ext"), [
    ("PNG", "image/png", "png"), ("JPEG", "image/jpeg", "jpg"), ("WEBP", "image/webp", "webp"),
])
def test_upload_de_logo_valido(client, member, db, s3, fmt, content_type, ext):
    user, h = member
    p = _create(client, h)
    r = _put(client, h, p["id"], "logo", _img(fmt), p["version"], name="qualquer.bin")
    assert r.status_code == 200, r.text
    perfil = r.json()["perfil"]
    assert perfil["version"] == 2
    assert perfil["logo"]["width"] == 256 and perfil["logo"]["height"] == 256
    assert perfil["logo"]["urls"]["thumb"].startswith("/img/")
    assert perfil["logo"]["urls"]["medium"].startswith("/img/")
    assert perfil["banner"] is None

    [key] = s3.keys()
    assert key.startswith(f"perfis/{p['id']}/") and key.endswith(f".{ext}")
    assert s3.client.stat_object(s3.name, key).content_type == content_type

    img = db.get(Image, perfil["logo"]["id"])
    assert img.object_key == key and img.kind == ImageKind.logo
    assert img.content_type == content_type and img.created_by == user.id

    v = _versions(db, p["id"])[-1]
    assert v.action == "updated" and v.actor_user_id == user.id
    assert list(v.changed_fields) == ["logo_image_id"]


def test_upload_de_banner(client, member, s3):
    _, h = member
    p = _create(client, h)
    r = _put(client, h, p["id"], "banner", _img("PNG", (1500, 500)), p["version"])
    assert r.status_code == 200, r.text
    banner = r.json()["perfil"]["banner"]
    assert banner["width"] == 1500 and banner["urls"]["medium"].startswith("/img/")
    assert "rs:fit:1200:300" in banner["urls"]["medium"]
    assert r.json()["perfil"]["logo"] is None
    assert len(s3.keys()) == 1


@pytest.mark.parametrize(("kind", "data", "message"), [
    ("logo", b"isto nao e uma imagem\n" * 100, "Formato não aceito"),
    ("logo", b"\x89PNG" + b"\0" * (6 * 1024 * 1024), "Arquivo maior que 5 MB"),
    ("logo", _img("PNG", (100, 100)), "Imagem pequena demais"),
    ("banner", _img("PNG", (800, 200)), "Imagem pequena demais"),
])
def test_imagem_invalida_nao_grava_nada(client, member, db, s3, kind, data, message):
    _, h = member
    p = _create(client, h)
    r = _put(client, h, p["id"], kind, data, p["version"], name="foto.png")
    assert r.status_code == 400, r.text
    assert r.json()["error"] == {"code": "invalid_image", "message": message}
    assert s3.keys() == []
    assert _image_count(db) == 0
    assert len(_versions(db, p["id"])) == 1
    assert db.get(Perfil, p["id"]).version == 1


def test_versao_desatualizada_da_409_sem_gravar(client, member, db, s3):
    _, h = member
    p = _create(client, h)
    r = _put(client, h, p["id"], "logo", _img(), version=7)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "version_conflict"
    assert s3.keys() == [] and _image_count(db) == 0


def test_sem_sessao_e_perfil_inexistente(client, member, s3):
    _, h = member
    p = _create(client, h)
    assert _put(client, {}, p["id"], "logo", _img(), 1).status_code == 401
    missing = "00000000-0000-4000-8000-000000000000"
    assert _put(client, h, missing, "logo", _img(), 1).status_code == 404


def test_trocar_logo_mantem_o_objeto_antigo(client, member, db, s3):
    _, h = member
    p = _create(client, h)
    first = _put(client, h, p["id"], "logo", _img(color=(255, 0, 0)), 1).json()["perfil"]
    second = _put(client, h, p["id"], "logo", _img(color=(0, 0, 255)), 2).json()["perfil"]
    assert second["version"] == 3
    assert second["logo"]["id"] != first["logo"]["id"]
    assert len(s3.keys()) == 2
    assert _image_count(db) == 2


def test_clear_remove_so_a_referencia(client, member, db, s3):
    _, h = member
    p = _create(client, h)
    up = _put(client, h, p["id"], "logo", _img(), 1).json()["perfil"]
    r = client.post(f"/api/perfis/{p['id']}/logo/clear", json={"version": up["version"]},
                    headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["perfil"]["logo"] is None
    assert r.json()["perfil"]["version"] == 3
    assert len(s3.keys()) == 1 and _image_count(db) == 1
    v = _versions(db, p["id"])[-1]
    assert list(v.changed_fields) == ["logo_image_id"] and v.after["logo_image_id"] is None

    # Sem imagem, clear não gera versão.
    r = client.post(f"/api/perfis/{p['id']}/banner/clear", json={"version": 3}, headers=h)
    assert r.status_code == 200 and r.json()["perfil"]["version"] == 3


def test_url_nao_expoe_a_chave_e_chave_tem_uuid(client, member, s3):
    _, h = member
    p = _create(client, h)
    perfil = _put(client, h, p["id"], "logo", _img(), 1).json()["perfil"]
    [key] = s3.keys()
    name = key.rsplit("/", 1)[1].split(".")[0]
    assert len(name) == 36 and name[14] == "4"  # uuid4
    assert key not in perfil["logo"]["urls"]["thumb"]


def test_reverter_traz_o_logo_antigo(client, owner, s3):
    _, h = owner
    p = _create(client, h)
    first = _put(client, h, p["id"], "logo", _img(color=(255, 0, 0)), 1).json()["perfil"]
    _put(client, h, p["id"], "logo", _img(color=(0, 0, 255)), 2)
    r = client.post(f"/api/perfis/{p['id']}/revert", json={"version": 3, "toVersion": 2},
                    headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["perfil"]["logo"]["id"] == first["logo"]["id"]
    assert r.json()["perfil"]["logo"]["urls"] == first["logo"]["urls"]
