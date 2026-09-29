"""Links assinados e streaming de mídia (T010, R6; contracts/http-api.md "Mídia"), com o MinIO
real (buckets de teste)."""

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sociman_api import midia, storage
from sociman_api.config import get_settings
from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.marca.models import BrandFont, FontFormat
from sociman_api.perfis.models import Image, ImageKind

PW = "senha-forte-123"
VIDEO = bytes(range(256)) * 1024 + b"fim"  # 256 KiB + 3, conteúdo conferível por faixa


@pytest.fixture(scope="module", autouse=True)
def _buckets():
    storage.ensure_buckets()


@pytest.fixture
def h(client, make_user, login):
    user = make_user(role="membro")
    return login(client, user.email, PW)


@pytest.fixture
def perfil(client, h) -> dict:
    r = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


@pytest.fixture
def font(db, perfil) -> BrandFont:
    key = f"perfis/{perfil['id']}/{uuid.uuid4()}.ttf"
    storage.put(key, b"\x00\x01\x00\x00fonte", "font/ttf", bucket="fontes")
    row = BrandFont(perfil_id=uuid.UUID(perfil["id"]), name="Pergaminho Ç", family="P",
                    style="Bold", format=FontFormat.ttf, object_key=key, bytes=9,
                    sha256="0" * 64)
    db.add(row)
    db.commit()
    return row


def _image(db, perfil, kind: ImageKind) -> Image:
    key = f"perfis/{perfil['id']}/{uuid.uuid4()}.png"
    storage.put(key, b"\x89PNGfake", "image/png")
    row = Image(perfil_id=uuid.UUID(perfil["id"]), kind=kind, object_key=key,
                content_type="image/png", bytes=8, width=64, height=64, sha256="0" * 64)
    db.add(row)
    db.commit()
    return row


def _corte(db, perfil, status: CorteStatus = CorteStatus.pronto) -> Corte:
    pid = perfil["id"]
    original = f"cortes/{pid}/{uuid.uuid4()}/original.mov"
    storage.put(original, VIDEO, "video/quicktime", bucket="videos")
    result = None
    if status == CorteStatus.pronto:
        result = f"cortes/{pid}/{uuid.uuid4()}/marcado.mp4"
        storage.put(result, VIDEO[::-1], "video/mp4", bucket="videos")
    row = Corte(
        perfil_id=uuid.UUID(pid), hook_text="Olha isso", kit_version=0, kit_tokens={},
        status=status, original_filename="meu video.mov", original_key=original,
        original_content_type="video/quicktime", original_bytes=len(VIDEO), duration_ms=1000,
        width=1080, height=1920, fps=Decimal(30), video_codec="h264", original_sha256="0" * 64,
        result_key=result, result_bytes=len(VIDEO) if result else None,
        created_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    db.add(row)
    db.commit()
    return row


def _links(client, h, *items):
    return client.post("/api/midia/links", headers=h,
                       json={"items": [{"kind": k, "id": str(i)} for k, i in items]})


# ---- POST /api/midia/links ----

def test_links_para_cada_tipo(client, h, db, perfil, font):
    wm = _image(db, perfil, ImageKind.watermark)
    corte = _corte(db, perfil)
    before = time.time()
    r = _links(client, h, ("fonte", font.id), ("marca_dagua", wm.id),
               ("corte_original", corte.id), ("corte_marcado", corte.id))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 4
    for item in items:
        assert item["url"].startswith("/api/midia/")
        exp = datetime.fromisoformat(item["expiresAt"]).timestamp()
        assert before + 3590 <= exp <= time.time() + 3600
    assert client.get(items[0]["url"]).content == b"\x00\x01\x00\x00fonte"
    assert client.get(items[1]["url"]).content == b"\x89PNGfake"
    assert client.get(items[2]["url"]).content == VIDEO
    assert client.get(items[3]["url"]).content == VIDEO[::-1]


def test_validade_configuravel(client, h, font, monkeypatch):
    monkeypatch.setattr(get_settings(), "midia_link_ttl_s", 60)
    r = _links(client, h, ("fonte", font.id))
    exp = datetime.fromisoformat(r.json()["items"][0]["expiresAt"]).timestamp()
    assert exp <= time.time() + 60


def test_links_exigem_login(client, font):
    r = client.post("/api/midia/links", json={"items": [{"kind": "fonte", "id": str(font.id)}]})
    assert r.status_code == 401


def test_links_item_inexistente_ou_de_outro_tipo_404(client, h, db, perfil, font):
    logo = _image(db, perfil, ImageKind.logo)
    for item in (("fonte", uuid.uuid4()), ("marca_dagua", logo.id), ("marca_dagua", font.id),
                 ("corte_original", font.id)):
        r = _links(client, h, item)
        assert r.status_code == 404, item


def test_links_marcado_antes_de_pronto_409(client, h, db, perfil):
    corte = _corte(db, perfil, status=CorteStatus.processando)
    r = _links(client, h, ("corte_marcado", corte.id))
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_ready"
    assert _links(client, h, ("corte_original", corte.id)).status_code == 200


def test_links_limite_de_20(client, h, font):
    r = _links(client, h, *[("fonte", font.id)] * 21)
    assert r.status_code == 400
    assert _links(client, h).status_code == 400


# ---- GET /api/midia/{token} ----

@pytest.fixture
def video_url(db, perfil) -> str:
    corte = _corte(db, perfil)
    return midia.link("corte_original", corte.id).url


def test_arquivo_inteiro_com_headers(client, video_url):
    r = client.get(video_url)
    assert r.status_code == 200
    assert r.content == VIDEO
    assert r.headers["content-type"] == "video/quicktime"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == str(len(VIDEO))
    assert r.headers["cache-control"] == "private, max-age=3600"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-disposition" not in r.headers


@pytest.mark.parametrize(("header", "start", "end"), [
    ("bytes=0-99", 0, 99),
    ("bytes=1000-", 1000, len(VIDEO) - 1),
    ("bytes=-3", len(VIDEO) - 3, len(VIDEO) - 1),
    ("bytes=100-999999999", 100, len(VIDEO) - 1),
    ("bytes=-999999999", 0, len(VIDEO) - 1),
    ("bytes=5-5", 5, 5),
])
def test_range_206(client, video_url, header, start, end):
    r = client.get(video_url, headers={"Range": header})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes {start}-{end}/{len(VIDEO)}"
    assert r.headers["content-length"] == str(end - start + 1)
    assert r.content == VIDEO[start:end + 1]


@pytest.mark.parametrize("header", [f"bytes={len(VIDEO)}-", "bytes=999999999-", "bytes=-0"])
def test_range_fora_416(client, video_url, header):
    r = client.get(video_url, headers={"Range": header})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(VIDEO)}"


@pytest.mark.parametrize("header", ["bytes=0-1,5-6", "items=0-1", "bytes=9-3", "lixo"])
def test_range_ignorado_serve_inteiro(client, video_url, header):
    r = client.get(video_url, headers={"Range": header})
    assert r.status_code == 200 and r.content == VIDEO


def test_download_com_nome(client, db, perfil, font):
    corte = _corte(db, perfil)
    r = client.get(midia.link("corte_marcado", corte.id).url, params={"download": 1})
    assert r.status_code == 200
    assert r.headers["content-disposition"] == (
        'attachment; filename="queridinhos-2026-09-29-marcado.mp4"; '
        "filename*=UTF-8''queridinhos-2026-09-29-marcado.mp4")
    r = client.get(midia.link("corte_original", corte.id).url, params={"download": "1"})
    assert 'filename="queridinhos-2026-09-29-original.mov"' in r.headers["content-disposition"]
    r = client.get(midia.link("fonte", font.id, ttl=None).url, params={"download": "1"})
    assert r.headers["content-disposition"] == (
        "attachment; filename=\"Pergaminho C.ttf\"; filename*=UTF-8''Pergaminho%20%C3%87.ttf")


def test_link_sem_validade_de_fonte(client, font):
    url = midia.link("fonte", font.id, ttl=None).url
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "font/ttf"


@pytest.mark.parametrize("mutate", [
    lambda t: t[:-3] + ("AAA" if not t.endswith("AAA") else "BBB"),
    lambda t: "x" + t,
    lambda t: t.split(".")[0],
])
def test_token_adulterado_403(client, font, mutate):
    token = midia.sign("fonte", font.id)
    r = client.get(f"/api/midia/{mutate(token)}")
    assert r.status_code == 403
    assert r.json()["error"] == {"code": "invalid_link", "message": "Link inválido ou vencido"}


def test_token_vencido_403(client, font):
    token = midia.sign("fonte", font.id, ttl=10, now=time.time() - 60)
    r = client.get(f"/api/midia/{token}")
    assert r.status_code == 403 and r.json()["error"]["code"] == "invalid_link"


def test_marcado_ainda_nao_pronto_409(client, db, perfil):
    corte = _corte(db, perfil, status=CorteStatus.na_fila)
    r = client.get(midia.link("corte_marcado", corte.id).url)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_ready"


def test_entidade_inexistente_404(client):
    r = client.get(midia.link("fonte", uuid.uuid4()).url)
    assert r.status_code == 404


def test_objeto_sumiu_404(client, db, perfil):
    row = BrandFont(perfil_id=uuid.UUID(perfil["id"]), name="Sem arquivo", family="X",
                    style="Bold", format=FontFormat.otf,
                    object_key=f"perfis/{perfil['id']}/{uuid.uuid4()}.otf", bytes=1,
                    sha256="0" * 64)
    db.add(row)
    db.commit()
    r = client.get(midia.link("fonte", row.id).url)
    assert r.status_code == 404


def test_hd_fora_503(client, video_url, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = client.get(video_url)
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"


def test_minio_fora_503(client, video_url, monkeypatch):
    import urllib3

    def _down(*_a, **_k):
        raise urllib3.exceptions.MaxRetryError(None, "/", "minio fora")

    monkeypatch.setattr(storage, "stat", _down)
    r = client.get(video_url)
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
