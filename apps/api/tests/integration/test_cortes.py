"""Rotas dos cortes (T026; contracts/http-api.md "Cortes" e `/api/armazenamento`)."""

import subprocess
import uuid
from pathlib import Path

import pytest

from sociman_api import storage
from sociman_api.config import get_settings
from sociman_api.cortes import worker
from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.db import get_sessionmaker

PW = "senha-forte-123"


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
def perfil(client, owner) -> dict:
    _, h = owner
    r = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"},
                    headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args],
                   check=True, timeout=300)


@pytest.fixture(scope="module")
def videos(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("videos")
    out = {
        "vertical": d / "vertical.mp4",
        "webm": d / "clip.webm",
        "longo": d / "longo.mp4",
    }
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:s=1080x1920:d=3:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(out["vertical"]))
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:s=360x640:d=2:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "200k",
            "-c:a", "libopus", str(out["webm"]))
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:s=240x426:d=181:r=5",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(out["longo"]))
    text_file = d / "texto.mp4"
    text_file.write_text("isto não é um vídeo\n" * 50)
    out["texto"] = text_file
    return out


def _upload(client, h, perfil_id: str, path: Path, hook: str | None = "Olha esse achadinho",
            headers: dict | None = None):
    data = {"hookText": hook} if hook is not None else {}
    with path.open("rb") as fh:
        return client.post(f"/api/perfis/{perfil_id}/cortes", headers=h | (headers or {}),
                           data=data, files={"file": (path.name, fh, "video/mp4")})


def _videos_keys(prefix: str) -> list[str]:
    client = storage.get_client()
    return [o.object_name for o in client.list_objects(storage.bucket_name("videos"),
                                                       prefix=prefix, recursive=True)]


def _spool_files() -> list[Path]:
    return list((Path(get_settings().data_dir) / "work" / "tmp").glob("corte-*"))


# ---- envio ----

def test_envio_cria_corte_na_fila(client, owner, perfil, videos):
    user, h = owner
    r = _upload(client, h, perfil["id"], videos["vertical"])
    assert r.status_code == 201, r.text
    c = r.json()["corte"]
    assert c["status"] == "na_fila" and c["queuePosition"] == 1 and c["progress"] == 0
    assert c["kitVersion"] == 0 and c["hookText"] == "Olha esse achadinho"
    assert (c["width"], c["height"], c["durationMs"]) == (1080, 1920, 3000)
    assert c["hasAudio"] is True and c["bytes"] == videos["vertical"].stat().st_size
    assert c["originalFilename"] == "vertical.mp4"
    assert c["createdBy"]["id"] == str(user.id) and c["version"] == 1
    assert c["posterUrl"] is None and c["resultBytes"] is None

    with get_sessionmaker()() as s:
        row = s.get(Corte, uuid.UUID(c["id"]))
        tokens = row.kit_tokens
        assert row.original_sha256 and len(row.original_sha256) == 64
        key = row.original_key
    assert key == f"perfis/{perfil['id']}/cortes/{c['id']}/original.mp4"
    assert storage.stat(key, bucket="videos").size == c["bytes"]
    # Tokens resolvidos no envio: hex e fonte padrão pela chave.
    assert tokens["hook"]["cor_fundo"] == "#FFFFFF"
    assert tokens["hook"]["fonte"]["padrao"] == "noto-serif-bold"
    assert _spool_files() == []

    r = client.get(f"/api/cortes/{c['id']}/versions", headers=h)
    assert r.status_code == 200
    (v,) = r.json()["items"]
    assert v["action"] == "created" and v["after"]["status"] == "na_fila"


def test_envio_grava_versao_do_kit(client, owner, perfil, videos):
    _, h = owner
    kit = client.get(f"/api/perfis/{perfil['id']}/kit", headers=h).json()["kit"]
    body = {k: kit[k] for k in ("version", "palette", "caption", "hook", "watermark",
                                "endCard", "catchphrases", "series")}
    body["hook"] = kit["hook"] | {"cor_fundo": "paleta:amarelo-destaque"}
    r = client.put(f"/api/perfis/{perfil['id']}/kit", json=body, headers=h)
    assert r.status_code == 200, r.text

    r = _upload(client, h, perfil["id"], videos["webm"])
    assert r.status_code == 201, r.text
    c = r.json()["corte"]
    assert c["kitVersion"] == 1 and c["width"] == 360
    with get_sessionmaker()() as s:
        row = s.get(Corte, uuid.UUID(c["id"]))
        assert row.kit_tokens["hook"]["cor_fundo"] == "#FFE500"
        assert row.original_content_type == "video/webm"
        assert row.original_key.endswith("/original.webm")


def test_membro_tambem_envia(client, member, perfil, videos):
    _, h = member
    assert _upload(client, h, perfil["id"], videos["webm"]).status_code == 201


@pytest.mark.parametrize(("name", "message"), [
    ("texto", "Não é um vídeo aceito"),
    ("longo", "Vídeo mais longo que 3 minutos"),
])
def test_video_recusado(client, owner, perfil, videos, name, message):
    _, h = owner
    r = _upload(client, h, perfil["id"], videos[name])
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "invalid_video", "message": message}
    assert _videos_keys(f"perfis/{perfil['id']}/") == []
    assert _spool_files() == []


def test_gancho_longo_ou_vazio(client, owner, perfil, videos):
    _, h = owner
    r = _upload(client, h, perfil["id"], videos["vertical"], hook="x" * 121)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_hook"
    # 4 linhas explícitas passam de 3 na fonte do kit.
    r = _upload(client, h, perfil["id"], videos["vertical"], hook="um\ndois\ntrês\nquatro")
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "invalid_hook", "message": "Gancho longo demais"}
    r = _upload(client, h, perfil["id"], videos["vertical"], hook=None)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_hook"
    assert _videos_keys(f"perfis/{perfil['id']}/") == []


def test_sem_arquivo(client, owner, perfil):
    _, h = owner
    r = client.post(f"/api/perfis/{perfil['id']}/cortes", headers=h,
                    data={"hookText": "oi"}, files={"outro": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 400


def test_content_length_grande_recusado_antes_do_corpo(client, owner, perfil):
    _, h = owner
    r = client.post(f"/api/perfis/{perfil['id']}/cortes",
                    headers=h | {"content-type": "multipart/form-data; boundary=x",
                                 "content-length": str(600 * 1024 * 1024)},
                    content=b"--x--\r\n")
    assert r.status_code == 413
    assert r.json()["error"] == {"code": "payload_too_large",
                                 "message": "Arquivo maior que 500 MB"}


def test_hd_fora_503_sem_gravar(client, owner, perfil, videos, tmp_path, monkeypatch):
    _, h = owner
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = _upload(client, h, perfil["id"], videos["vertical"])
    assert r.status_code == 503
    assert r.json()["error"] == {"code": "storage_unavailable",
                                 "message": "O HD de dados não está disponível"}
    assert _videos_keys(f"perfis/{perfil['id']}/") == []
    # Lista e armazenamento seguem respondendo.
    assert client.get(f"/api/perfis/{perfil['id']}/cortes", headers=h).status_code == 200
    a = client.get("/api/armazenamento", headers=h).json()
    assert a["available"] is False and a["reason"] == "sem_sentinela" and a["freeBytes"] is None


def test_hd_cheio_507(client, owner, perfil, videos, monkeypatch):
    _, h = owner
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    r = _upload(client, h, perfil["id"], videos["vertical"])
    assert r.status_code == 507
    assert r.json()["error"] == {"code": "storage_full", "message": "Pouco espaço no HD de dados"}
    a = client.get("/api/armazenamento", headers=h).json()
    assert a["available"] is False and a["reason"] == "pouco_espaco"


def test_perfil_arquivado_e_inexistente(client, owner, perfil, videos):
    _, h = owner
    r = client.post(f"/api/perfis/{perfil['id']}/archive", json={"version": perfil["version"]},
                    headers=h)
    assert r.status_code == 200, r.text
    r = _upload(client, h, perfil["id"], videos["vertical"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "perfil_archived"
    r = _upload(client, h, str(uuid.uuid4()), videos["vertical"])
    assert r.status_code == 404


def test_sem_login(client, perfil, videos):
    assert _upload(client, {}, perfil["id"], videos["vertical"]).status_code == 401
    assert client.get("/api/armazenamento").status_code == 401


# ---- consultas ----

def test_lista_com_cursor_e_filtro(client, owner, perfil, videos):
    _, h = owner
    ids = [_upload(client, h, perfil["id"], videos["webm"]).json()["corte"]["id"]
           for _ in range(3)]
    r = client.get(f"/api/perfis/{perfil['id']}/cortes", headers=h, params={"limit": 2})
    items = r.json()["items"]
    assert [c["id"] for c in items] == ids[::-1][:2]
    assert [c["queuePosition"] for c in items] == [3, 2]
    r = client.get(f"/api/perfis/{perfil['id']}/cortes", headers=h,
                   params={"limit": 2, "before": items[-1]["createdAt"]})
    assert [c["id"] for c in r.json()["items"]] == [ids[0]]
    r = client.get(f"/api/perfis/{perfil['id']}/cortes", headers=h,
                   params={"status": "pronto"})
    assert r.json()["items"] == []
    assert client.get(f"/api/perfis/{uuid.uuid4()}/cortes", headers=h).status_code == 404

    a = client.get("/api/armazenamento", headers=h).json()
    assert a["available"] is True and a["reason"] == "ok"
    assert a["cortesBytes"] == 3 * videos["webm"].stat().st_size
    assert a["freeBytes"] > 0 and a["totalBytes"] >= a["freeBytes"]


def test_get_404(client, owner):
    _, h = owner
    assert client.get(f"/api/cortes/{uuid.uuid4()}", headers=h).status_code == 404


# ---- processamento e "tentar de novo" ----

def test_processa_e_tenta_de_novo(client, owner, perfil, videos, monkeypatch):
    _, h = owner
    c = _upload(client, h, perfil["id"], videos["vertical"]).json()["corte"]

    r = client.post(f"/api/cortes/{c['id']}/retry", json={"version": 1}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"

    # Falha por falta de espaço, depois tenta de novo e fica pronto.
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    assert worker.run_once() == "falhou"
    monkeypatch.undo()
    falhou = client.get(f"/api/cortes/{c['id']}", headers=h).json()["corte"]
    assert falhou["status"] == "falhou"
    assert falhou["errorMessage"] == "Pouco espaço no HD de dados"
    assert falhou["attempts"] == 1

    r = client.post(f"/api/cortes/{c['id']}/retry", json={"version": 5}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    r = client.post(f"/api/cortes/{c['id']}/retry", json={"version": 1}, headers=h)
    assert r.status_code == 200, r.text
    again = r.json()["corte"]
    assert again["status"] == "na_fila" and again["version"] == 2
    assert again["errorMessage"] is None and again["attempts"] == 0

    assert worker.run_once() == "pronto"
    done = client.get(f"/api/cortes/{c['id']}", headers=h).json()["corte"]
    assert done["status"] == "pronto" and done["progress"] == 100
    assert done["resultBytes"] > 0 and done["processingMs"] > 0
    assert done["posterUrl"].startswith("/img/") and done["finishedAt"]
    assert done["queuePosition"] is None

    versions = client.get(f"/api/cortes/{c['id']}/versions", headers=h).json()["items"]
    assert [v["action"] for v in versions] == ["updated", "created"]
    assert versions[0]["before"]["status"] == "falhou"
    with get_sessionmaker()() as s:
        assert s.get(Corte, uuid.UUID(c["id"])).status == CorteStatus.pronto


def test_nenhuma_rota_delete():
    from sociman_api.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if "cortes" in path or "armazenamento" in path:
            assert "DELETE" not in getattr(route, "methods", set())
