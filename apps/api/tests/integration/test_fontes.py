"""US2: fontes padrão e fontes do perfil (T009/T014/T015; contracts/http-api.md "Fontes").

A OTF de teste (`tests/fixtures/SocimanTeste-Bold.otf`, 1 KB, CFF) foi gerada com o
`fontTools.fontBuilder`: um retângulo por letra da amostra.
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from sociman_api import storage
from sociman_api.config import get_settings
from sociman_api.history import EntityVersion
from sociman_api.marca import fontes
from sociman_api.marca.models import BrandFont

PW = "senha-forte-123"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TTF = (fontes.FONTS_DIR / "LiberationSerif-Bold.ttf").read_bytes()
OTF = (FIXTURES / "SocimanTeste-Bold.otf").read_bytes()


@pytest.fixture(scope="module", autouse=True)
def _buckets():
    storage.ensure_buckets()


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def member(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


@pytest.fixture
def perfil(client, member) -> dict:
    _, h = member
    r = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _upload(client, h, perfil, data: bytes, name: str = "Pergaminho",
            filename: str = "fonte.ttf"):
    return client.post(f"/api/perfis/{perfil['id']}/fontes", headers=h,
                       files={"file": (filename, data, "application/octet-stream")},
                       data={"name": name})


def _ok(r, status: int = 200) -> dict:
    assert r.status_code == status, r.text
    return r.json()


# ---- fontes padrão (sem login) ----

def test_fontes_padrao_lista_e_arquivo(client):
    items = _ok(client.get("/api/fontes-padrao"))["items"]
    assert [f["key"] for f in items] == ["anton", "noto-serif-bold", "liberation-sans",
                                         "liberation-serif"]
    assert items[0] == {"key": "anton", "name": "Anton", "family": "Anton",
                        "url": "/api/fontes-padrao/anton"}
    for f in items:
        r = client.get(f["url"])
        assert r.status_code == 200
        assert r.headers["content-type"] == "font/ttf"
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert r.content[:4] == b"\x00\x01\x00\x00"
        assert fontes.validate_font(r.content).family == f["family"]


def test_fonte_padrao_inexistente_404(client):
    r = client.get("/api/fontes-padrao/comic-sans")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get("/api/fontes-padrao/..%2Fmodels.py").status_code == 404


def test_licencas_ao_lado_das_fontes():
    for name in ("OFL-Anton.txt", "OFL-NotoSerif.txt", "OFL-Liberation.txt"):
        text = (fontes.FONTS_DIR / name).read_text()
        assert "SIL OPEN FONT LICENSE Version 1.1" in text


# ---- envio ----

@pytest.mark.parametrize(("data", "fmt", "family", "style"), [
    (TTF, "ttf", "Liberation Serif", "Bold"),
    (OTF, "otf", "Sociman Teste", "Bold"),
])
def test_envio_ttf_e_otf(client, member, perfil, db, data, fmt, family, style):
    user, h = member
    f = _ok(_upload(client, h, perfil, data, filename="qualquer.bin"), 201)["fonte"]
    assert f["name"] == "Pergaminho" and f["format"] == fmt
    assert f["family"] == family and f["style"] == style
    assert f["bytes"] == len(data) and f["version"] == 1 and f["archived"] is False
    assert f["perfilId"] == perfil["id"] and f["createdBy"] == {"id": str(user.id),
                                                                  "name": "Membro"}
    row = db.get(BrandFont, uuid.UUID(f["id"]))
    assert row.object_key.startswith(f"perfis/{perfil['id']}/")
    assert row.object_key.endswith(f".{fmt}")
    # Objeto no bucket de fontes (nunca no `imagens`, que o imgproxy lê).
    st = storage.stat(row.object_key, bucket="fontes")
    assert st.size == len(data) and st.content_type == f"font/{fmt}"
    assert storage.get(row.object_key, bucket="fontes") == data
    [v] = db.scalars(select(EntityVersion).where(EntityVersion.entity_id == row.id)).all()
    assert v.entity_type == "fonte" and v.action == "created"
    assert v.after == {"name": "Pergaminho", "archived": False}

    items = _ok(client.get(f"/api/perfis/{perfil['id']}/fontes", headers=h))["items"]
    assert [i["id"] for i in items] == [f["id"]]


@pytest.mark.parametrize("data", [
    b"isto nao e uma fonte, so texto com extensao .ttf" * 10,
    b"\x00\x01\x00\x00" + b"\x00" * 200,  # assinatura certa, corpo quebrado
    b"ttcf" + TTF[4:],  # coleção
    b"wOFF" + TTF[4:],
])
def test_fonte_invalida(client, member, perfil, s3, data):
    _, h = member
    r = _upload(client, h, perfil, data)
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "invalid_font", "message": "Não é uma fonte TTF/OTF"}


def test_fonte_maior_que_10mb(client, member, perfil):
    _, h = member
    r = _upload(client, h, perfil, TTF + b"\x00" * (fontes.MAX_BYTES + 1 - len(TTF)))
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "invalid_font", "message": "Arquivo maior que 10 MB"}


def test_nome_repetido_entre_ativas(client, member, perfil):
    _, h = member
    _ok(_upload(client, h, perfil, TTF, name="Pergaminho"), 201)
    r = _upload(client, h, perfil, OTF, name="  pergaminho ")
    assert r.status_code == 409 and r.json()["error"]["code"] == "font_name_in_use"


def test_nome_vazio(client, member, perfil):
    _, h = member
    r = _upload(client, h, perfil, TTF, name="   ")
    assert r.status_code == 400


def test_perfil_inexistente_404(client, member):
    _, h = member
    r = _upload(client, h, {"id": str(uuid.uuid4())}, TTF)
    assert r.status_code == 404


def test_sem_login_401(client, perfil):
    r = client.post(f"/api/perfis/{perfil['id']}/fontes",
                    files={"file": ("f.ttf", TTF, "font/ttf")}, data={"name": "X"})
    assert r.status_code == 401


def test_hd_fora_503_sem_gravar(client, member, perfil, db, tmp_path, monkeypatch):
    _, h = member
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = _upload(client, h, perfil, TTF)
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
    assert db.scalars(select(BrandFont)).all() == []


def test_hd_cheio_507(client, member, perfil, monkeypatch):
    _, h = member
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    r = _upload(client, h, perfil, TTF)
    assert r.status_code == 507 and r.json()["error"]["code"] == "storage_full"


# ---- renomear, arquivar, restaurar ----

def _kit_with_font(client, h, perfil, ref: str, sections=("hook",)) -> None:
    kit = _ok(client.get(f"/api/perfis/{perfil['id']}/kit", headers=h))["kit"]
    body = {k: kit[k] for k in ("version", "palette", "caption", "hook", "watermark", "endCard",
                                "catchphrases", "series")}
    for s in sections:
        body[s] = body[s] | {"fonte": ref}
    _ok(client.put(f"/api/perfis/{perfil['id']}/kit", json=body, headers=h))


def test_renomear(client, member, perfil):
    _, h = member
    a = _ok(_upload(client, h, perfil, TTF, name="A"), 201)["fonte"]
    b = _ok(_upload(client, h, perfil, OTF, name="B"), 201)["fonte"]
    r = client.patch(f"/api/fontes/{a['id']}", json={"version": 1, "name": "b"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "font_name_in_use"
    f = _ok(client.patch(f"/api/fontes/{a['id']}", json={"version": 1, "name": " Nova "},
                         headers=h))["fonte"]
    assert f["name"] == "Nova" and f["version"] == 2
    r = client.patch(f"/api/fontes/{a['id']}", json={"version": 1, "name": "Outra"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    assert b["name"] == "B"


def test_arquivar_em_uso_409_com_campos(client, member, perfil):
    _, h = member
    f = _ok(_upload(client, h, perfil, TTF), 201)["fonte"]
    _kit_with_font(client, h, perfil, f"perfil:{f['id']}", sections=("hook", "caption"))
    r = client.post(f"/api/fontes/{f['id']}/archive", json={"version": 1}, headers=h)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "font_in_use"
    assert err["details"] == {"fields": ["caption.fonte", "hook.fonte"]}
    assert err["message"] == "Esta fonte é usada na legenda e no gancho; troque antes de arquivar"


def test_arquivar_e_restaurar(client, member, perfil, db):
    _, h = member
    f = _ok(_upload(client, h, perfil, TTF, name="Pergaminho"), 201)["fonte"]
    a = _ok(client.post(f"/api/fontes/{f['id']}/archive", json={"version": 1},
                        headers=h))["fonte"]
    assert a["archived"] is True and a["version"] == 2
    r = client.post(f"/api/fontes/{f['id']}/archive", json={"version": 2}, headers=h)
    assert r.status_code == 409
    url = f"/api/perfis/{perfil['id']}/fontes"
    assert _ok(client.get(url, headers=h))["items"] == []
    assert [i["id"] for i in _ok(client.get(url, params={"archived": "true"},
                                            headers=h))["items"]] == [f["id"]]
    # O nome fica livre enquanto a fonte está arquivada; restaurar com o nome ocupado é 409.
    other = _ok(_upload(client, h, perfil, OTF, name="pergaminho"), 201)["fonte"]
    r = client.post(f"/api/fontes/{f['id']}/restore", json={"version": 2}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "font_name_in_use"
    _ok(client.patch(f"/api/fontes/{other['id']}", json={"version": 1, "name": "Outra"},
                     headers=h))
    r = _ok(client.post(f"/api/fontes/{f['id']}/restore", json={"version": 2},
                        headers=h))["fonte"]
    assert r["archived"] is False and r["version"] == 3
    # O arquivo nunca é apagado.
    row = db.get(BrandFont, uuid.UUID(f["id"]))
    assert storage.stat(row.object_key, bucket="fontes").size == len(TTF)

    versions = _ok(client.get(f"/api/fontes/{f['id']}/versions", headers=h))["items"]
    assert [v["action"] for v in versions] == ["restored", "archived", "created"]
    assert versions[1]["changedFields"] == ["archived"]


def test_versions_404(client, member):
    _, h = member
    r = client.get(f"/api/fontes/{uuid.uuid4()}/versions", headers=h)
    assert r.status_code == 404


def test_fonte_aparece_nas_opcoes_do_kit(client, member, perfil):
    _, h = member
    f = _ok(_upload(client, h, perfil, TTF, name="Pergaminho"), 201)["fonte"]
    options = _ok(client.get(f"/api/perfis/{perfil['id']}/kit", headers=h))["fontOptions"]
    mine = [o for o in options if o["ref"] == f"perfil:{f['id']}"]
    assert mine and mine[0]["url"].startswith("/api/midia/")
    r = client.get(mine[0]["url"])  # o @font-face da prévia, sem Authorization
    assert r.status_code == 200 and r.content == TTF
    assert r.headers["content-type"] == "font/ttf"
