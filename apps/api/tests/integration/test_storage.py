"""storage.py com o MinIO real (buckets de teste) e a proteção do HD de dados (R5, FR-018)."""

import io
import uuid

import pytest
from PIL import Image as PILImage

from sociman_api import datadir, storage
from sociman_api.config import Settings, get_settings
from sociman_api.errors import ApiError


@pytest.fixture(scope="module", autouse=True)
def _buckets():
    storage.ensure_buckets()


@pytest.fixture
def hd_fora(tmp_path, monkeypatch):
    """HD sem o sentinela (desmontado): toda gravação tem de ser recusada."""
    settings = Settings(jwt_secret="x" * 32, data_dir=str(tmp_path / "hd-fora"))
    monkeypatch.setattr(datadir, "get_settings", lambda: settings)


@pytest.fixture
def hd_cheio(monkeypatch):
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**9)


def _key() -> str:
    return f"perfis/{uuid.uuid4()}/{uuid.uuid4()}.bin"


def test_buckets_de_teste_por_tipo():
    names = {b: storage.bucket_name(b) for b in ("imagens", "fontes", "videos")}
    assert len(set(names.values())) == 3
    assert not {"sociman", "sociman-fonts", "sociman-videos"} & set(names.values())
    for name in names.values():
        assert storage.get_client().bucket_exists(name)


@pytest.mark.parametrize("bucket", ["imagens", "fontes", "videos"])
def test_put_get_stat_por_bucket(bucket):
    key = _key()
    storage.put(key, b"abc", "application/octet-stream", bucket=bucket)
    assert storage.get(key, bucket=bucket) == b"abc"
    assert storage.stat(key, bucket=bucket).size == 3
    other = "videos" if bucket != "videos" else "fontes"
    with pytest.raises(Exception):  # noqa: B017 — cada tipo no seu bucket
        storage.stat(key, bucket=other)


def test_put_file_get_to_file_e_range(tmp_path):
    src = tmp_path / "original.mp4"
    data = bytes(range(256)) * 4096 + b"fim"  # ~1 MiB
    src.write_bytes(data)
    key = _key()
    assert storage.put_file(key, src, "video/mp4", bucket="videos") == len(data)
    st = storage.stat(key, bucket="videos")
    assert st.size == len(data) and st.content_type == "video/mp4"

    dst = tmp_path / "copia.mp4"
    storage.get_to_file(key, dst, bucket="videos")
    assert dst.read_bytes() == data

    assert b"".join(storage.get_range(key, 10, 100, bucket="videos")) == data[10:110]
    assert b"".join(storage.get_range(key, len(data) - 3, 3, bucket="videos")) == b"fim"


def test_get_range_de_objeto_inexistente_falha_na_hora():
    with pytest.raises(Exception):  # noqa: B017 — antes de devolver o iterador
        storage.get_range(_key(), 0, 10, bucket="videos")


def test_hd_fora_recusa_gravar_com_503(hd_fora, tmp_path):
    key = _key()
    with pytest.raises(ApiError) as e:
        storage.put(key, b"abc", "application/octet-stream", bucket="fontes")
    assert (e.value.status, e.value.code) == (503, "storage_unavailable")
    src = tmp_path / "a.bin"
    src.write_bytes(b"abc")
    with pytest.raises(ApiError):
        storage.put_file(key, src, "application/octet-stream", bucket="videos")
    with pytest.raises(Exception):  # noqa: B017 — nada foi gravado
        storage.stat(key, bucket="fontes")


def test_hd_cheio_recusa_gravar_com_507(hd_cheio):
    with pytest.raises(ApiError) as e:
        storage.put(_key(), b"abc", "application/octet-stream")
    assert (e.value.status, e.value.code) == (507, "storage_full")


def _png() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (256, 256), (200, 40, 90)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize(("fixture", "status", "code"), [
    ("hd_fora", 503, "storage_unavailable"), ("hd_cheio", 507, "storage_full"),
])
def test_logo_da_003_responde_503_507_com_o_hd_com_problema(
        request, client, make_user, login, db, s3, fixture, status, code):
    user = make_user(role="membro")
    h = login(client, user.email, "senha-forte-123")
    r = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"},
                    headers=h)
    assert r.status_code == 201, r.text
    p = r.json()["perfil"]

    request.getfixturevalue(fixture)
    r = client.put(f"/api/perfis/{p['id']}/logo", headers=h,
                   files={"file": ("logo.png", _png(), "image/png")},
                   data={"version": str(p["version"])})
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code
    assert s3.keys() == []
    r = client.get(f"/api/perfis/{p['id']}", headers=h)
    assert r.json()["perfil"]["logo"] is None and r.json()["perfil"]["version"] == p["version"]
