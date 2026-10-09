"""US3: exportação do kit para o gerador de cortes (T017/T018; R9, FR-011)."""

import uuid
from datetime import UTC, datetime

import pytest

from sociman_api import midia
from sociman_api.marca.models import BrandFont, FontFormat
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
    p = r.json()["perfil"]
    r = client.post(f"/api/perfis/{p['id']}/contas", headers=h,
                    json={"platform": "tiktok", "handle": "meusqueridinhos10", "status": "ativa"})
    assert r.status_code == 201, r.text
    return p


def _export(client, h, perfil, **params):
    return client.get(f"/api/perfis/{perfil['id']}/kit/export", params=params, headers=h)


def _token(url: str) -> str:
    assert url.startswith("/api/midia/")
    return url.removeprefix("/api/midia/")


def test_default_export(client, h, perfil):
    r = _export(client, h, perfil)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["schema"] == "sociman.kit/1"
    assert doc["perfil"] == {"id": perfil["id"], "slug": "queridinhos", "name": "Queridinhos"}
    assert doc["kit"] == {"version": 0, "updatedAt": None}
    assert datetime.fromisoformat(doc["generatedAt"]).tzinfo is not None
    tokens = doc["tokens"]
    assert set(tokens) == {"palette", "caption", "hook", "watermark", "endCard", "catchphrases",
                           "series"}
    assert tokens["caption"]["cor_texto"] == "#FFFFFF"  # paleta:branco resolvida
    assert tokens["caption"]["fonte"] == {"ref": "padrao:anton", "name": "Anton",
                                          "family": "Anton", "style": "Regular",
                                          "url": "/api/fontes-padrao/anton"}
    assert tokens["watermark"]["texto"] == "@meusqueridinhos10"
    assert doc["openshorts"]["subtitle"]["font_name"] == "Anton"
    assert doc["openshorts"]["hook"]["enabled"] is False
    assert doc["openshorts"]["hook"]["style"] == "classic"
    assert doc["assets"] == {"fonts": [], "watermarkImage": None, "backgroundImages": []}


def test_export_with_own_font_and_watermark_image(client, h, perfil, db):
    pid = uuid.UUID(perfil["id"])
    font = BrandFont(perfil_id=pid, name="Pergaminho", family="Pergaminho Serif",
                     style="Regular", format=FontFormat.ttf,
                     object_key=f"perfis/{pid}/{uuid.uuid4()}.ttf", bytes=10, sha256="0" * 64)
    image = Image(perfil_id=pid, kind=ImageKind.watermark, object_key=f"perfis/{pid}/wm.png",
                  content_type="image/png", bytes=10, width=128, height=128, sha256="0" * 64)
    db.add_all([font, image])
    db.commit()
    kit = client.get(f"/api/perfis/{pid}/kit", headers=h).json()["kit"]
    body = {k: kit[k] for k in ("palette", "caption", "hook", "watermark", "endCard",
                                "catchphrases", "series")}
    body["palette"].append({"chave": "rosa", "nome": "Rosa Queridinhos", "valor": "#FF5FA2"})
    body["caption"] |= {"fonte": f"perfil:{font.id}", "cor_destaque": "paleta:rosa"}
    body["hook"] |= {"cor_fundo": "paleta:rosa", "cor_texto": "#FFFFFF"}
    body["watermark"] |= {"tipo": "imagem", "imagem_id": str(image.id)}
    r = client.put(f"/api/perfis/{pid}/kit", json={"version": 0, **body}, headers=h)
    assert r.status_code == 200, r.text

    doc = _export(client, h, perfil).json()
    assert doc["kit"]["version"] == 1 and doc["kit"]["updatedAt"] is not None
    sub = doc["openshorts"]["subtitle"]
    assert sub["highlight_color"] == "#FF5FA2"
    # fonte própria na legenda: o gerador não a tem; cai para a padrão parecida, com aviso
    assert sub["font_name"] == "Noto Serif"
    notes = doc["openshorts"]["approximations"]
    assert any(n.startswith("legenda: a fonte Pergaminho (do perfil)") for n in notes)
    assert "hook: fundo #FF5FA2 aproximado para o preset red (#DC2626); texto exato" in notes
    assert doc["openshorts"]["hook"]["enabled"] is False
    assert doc["openshorts"]["hook"]["exact"] is False

    [asset] = doc["assets"]["fonts"]
    assert asset["ref"] == f"perfil:{font.id}" and asset["name"] == "Pergaminho"
    assert asset["expiresAt"] is None
    claims = midia.verify(_token(asset["url"]))
    assert (claims.kind, claims.id, claims.exp) == ("fonte", font.id, None)
    assert doc["tokens"]["caption"]["fonte"]["url"] == asset["url"]

    wm = doc["assets"]["watermarkImage"]
    assert wm["id"] == str(image.id) and wm["expiresAt"] is None
    claims = midia.verify(_token(wm["url"]))
    assert (claims.kind, claims.id, claims.exp) == ("marca_dagua", image.id, None)
    assert doc["tokens"]["watermark"]["imagem_url"] == wm["url"]


def test_archived_font_still_exports(client, h, perfil, db):
    pid = uuid.UUID(perfil["id"])
    font = BrandFont(perfil_id=pid, name="Pergaminho", family="Pergaminho", style="Regular",
                     format=FontFormat.otf, object_key=f"perfis/{pid}/{uuid.uuid4()}.otf",
                     bytes=10, sha256="0" * 64)
    db.add(font)
    db.commit()
    kit = client.get(f"/api/perfis/{pid}/kit", headers=h).json()["kit"]
    body = {k: kit[k] for k in ("palette", "caption", "hook", "watermark", "endCard",
                                "catchphrases", "series")}
    body["endCard"] |= {"fonte": f"perfil:{font.id}"}
    assert client.put(f"/api/perfis/{pid}/kit", json={"version": 0, **body},
                      headers=h).status_code == 200
    font = db.get(BrandFont, font.id)
    font.archived_at = datetime.now(UTC)
    db.commit()
    doc = _export(client, h, perfil).json()
    assert [a["name"] for a in doc["assets"]["fonts"]] == ["Pergaminho"]


def test_download_sets_filename(client, h, perfil):
    kit = client.get(f"/api/perfis/{perfil['id']}/kit", headers=h).json()["kit"]
    body = {k: kit[k] for k in ("palette", "caption", "hook", "watermark", "endCard",
                                "catchphrases", "series")}
    assert client.put(f"/api/perfis/{perfil['id']}/kit", json={"version": 0, **body},
                      headers=h).status_code == 200
    r = _export(client, h, perfil, download=1)
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="kit-queridinhos-v1.json"'
    assert r.json()["schema"] == "sociman.kit/1" and r.json()["kit"]["version"] == 1


def test_export_requires_login_and_perfil(client, h, perfil):
    assert client.get(f"/api/perfis/{perfil['id']}/kit/export").status_code == 401
    assert client.get(f"/api/perfis/{uuid.uuid4()}/kit/export", headers=h).status_code == 404
