"""Vídeo próprio (spec 014, US5, R9): envio em streaming, ffprobe, miniatura, mídia e o
conteúdo `video_proprio` aprovado e agendado como um corte. ffmpeg real (vídeos com `lavfi`).
Nada é publicado."""

import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from integration.postagem_helpers import acao, add_destino, agendar
from sociman_api import storage
from sociman_api.config import get_settings
from sociman_api.conteudos import video_proprio
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.history import EntityVersion

PW = "senha-forte-123"
SP = ZoneInfo("America/Sao_Paulo")


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
    r = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"},
                    headers=owner[1])
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args],
                   check=True, timeout=300)


def _gerar(path: Path, size: str, seconds: float, rate: int = 30) -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"color=c=0x808080:s={size}:d={seconds}:r={rate}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(path))
    return path


@pytest.fixture(scope="module")
def videos(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("proprios")
    out = {
        "vertical": _gerar(d / "vertical.mp4", "360x640", 2),
        "horizontal": _gerar(d / "horizontal.mp4", "640x360", 2),
        "quadrado": _gerar(d / "quadrado.mp4", "480x480", 2),
        "curto": _gerar(d / "curto.mp4", "360x640", 0.5),
        "longo": _gerar(d / "longo.mp4", "240x426", 601, rate=1),
    }
    texto = d / "texto.mp4"
    texto.write_text("isto não é um vídeo\n" * 50)
    out["texto"] = texto
    return out


def _enviar(client, h, perfil_id, path: Path, titulo: str | None = "Meu vídeo",
            headers: dict | None = None):
    data = {"titulo": titulo} if titulo is not None else {}
    with path.open("rb") as fh:
        return client.post(f"/api/perfis/{perfil_id}/conteudos/arquivo",
                           headers=h | (headers or {}), data=data,
                           files={"file": (path.name, fh, "video/mp4")})


def _keys(bucket: str, prefix: str) -> list[str]:
    client = storage.get_client()
    return [o.object_name for o in client.list_objects(storage.bucket_name(bucket),
                                                       prefix=prefix, recursive=True)]


def _err(r) -> str:
    return r.json()["error"]["code"]


def test_vertical_vira_conteudo_pronto(client, db, owner, perfil, videos):
    user, h = owner
    r = _enviar(client, h, perfil["id"], videos["vertical"])
    assert r.status_code == 201, r.text
    c = r.json()["conteudo"]
    assert c["origem"] == "video_proprio" and c["situacao"] == "pronto"
    assert c["titulo"] == "Meu vídeo" and c["naoVertical"] is False
    assert (c["width"], c["height"], c["durationMs"]) == (360, 640, 2000)
    assert c["posterUrl"] and c["semConta"] is True and c["corteId"] is None

    row = db.get(Conteudo, uuid.UUID(c["id"]))
    assert row.origem == ConteudoOrigem.video_proprio
    assert row.video_key == f"conteudos/{c['id']}/video.mp4"
    assert row.video_sha256 and len(row.video_sha256) == 64
    assert row.video_bytes == videos["vertical"].stat().st_size
    assert _keys("videos", f"conteudos/{c['id']}/") == [row.video_key]
    assert row.poster_key in _keys("imagens", f"perfis/{perfil['id']}/conteudos/{c['id']}/")
    (v,) = db.scalars(select(EntityVersion).where(EntityVersion.entity_type == "conteudo",
                                                  EntityVersion.entity_id == row.id)).all()
    assert v.action == "created" and v.actor_user_id == user.id
    assert list((Path(get_settings().data_dir) / "work" / "tmp").glob("proprio-*")) == []


def test_titulo_padrao_e_nome_do_arquivo(client, owner, perfil, videos):
    r = _enviar(client, owner[1], perfil["id"], videos["vertical"], titulo=None)
    assert r.status_code == 201 and r.json()["conteudo"]["titulo"] == "vertical"


@pytest.mark.parametrize("nome", ["horizontal", "quadrado"])
def test_nao_vertical_aceito_com_aviso(client, owner, perfil, videos, nome):
    r = _enviar(client, owner[1], perfil["id"], videos[nome])
    assert r.status_code == 201, r.text
    assert r.json()["conteudo"]["naoVertical"] is True


@pytest.mark.parametrize(("nome", "msg"), [
    ("curto", video_proprio.TOO_SHORT), ("longo", video_proprio.TOO_LONG),
    ("texto", "Não é um vídeo aceito"),
])
def test_recusas(client, db, owner, perfil, videos, nome, msg):
    r = _enviar(client, owner[1], perfil["id"], videos[nome])
    assert r.status_code == 400, r.text
    assert r.json()["error"] == {"code": "invalid_video", "message": msg}
    assert db.query(Conteudo).filter_by(origem=ConteudoOrigem.video_proprio).count() == 0


def test_acima_do_limite_413(client, db, owner, perfil, videos, monkeypatch):
    monkeypatch.setattr(video_proprio, "max_bytes", lambda: 1024)
    r = _enviar(client, owner[1], perfil["id"], videos["vertical"])
    assert r.status_code == 413 and _err(r) == "payload_too_large"
    assert r.json()["error"]["message"] == video_proprio.TOO_BIG
    assert db.query(Conteudo).count() == 0


def test_hd_fora_e_cheio(client, owner, perfil, videos, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = _enviar(client, owner[1], perfil["id"], videos["vertical"])
    assert r.status_code == 503 and _err(r) == "storage_unavailable"
    monkeypatch.undo()
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    r = _enviar(client, owner[1], perfil["id"], videos["vertical"])
    assert r.status_code == 507 and _err(r) == "storage_full"


def test_perfil_arquivado_e_inexistente(client, owner, perfil, videos):
    _, h = owner
    r = _enviar(client, h, str(uuid.uuid4()), videos["vertical"])
    assert r.status_code == 404
    client.post(f"/api/perfis/{perfil['id']}/archive", json={"version": perfil["version"]},
                headers=h)
    r = _enviar(client, h, perfil["id"], videos["vertical"])
    assert r.status_code == 409


def test_envio_interrompido_nao_cria_linha(client, db, owner, perfil):
    r = client.post(f"/api/perfis/{perfil['id']}/conteudos/arquivo", headers=owner[1] | {
        "content-type": "multipart/form-data; boundary=x"}, content=b"--x\r\nlixo")
    assert r.status_code == 400
    assert db.query(Conteudo).count() == 0


def test_filtro_origem_midia_aprovar_agendar_arquivar(client, db, owner, member, perfil, videos):
    _, h = owner
    c = _enviar(client, h, perfil["id"], videos["vertical"]).json()["conteudo"]

    r = client.get("/api/conteudos", headers=h, params={"origem": "video_proprio"})
    if r.status_code == 200:  # rota da trilha A
        assert [i["id"] for i in r.json()["items"]] == [c["id"]]

    r = client.post("/api/midia/links", headers=member[1],
                    json={"items": [{"kind": "conteudo_video", "id": c["id"]}]})
    assert r.status_code == 200, r.text
    link = r.json()["items"][0]
    assert link["expiresAt"] is not None
    r = client.get(link["url"], headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.content) == 10
    assert r.headers["content-type"].startswith("video/mp4")
    r = client.get(link["url"] + "?download=1")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    r = client.post("/api/midia/links", headers=h,
                    json={"items": [{"kind": "conteudo_video", "id": str(uuid.uuid4())}]})
    assert r.status_code == 404

    conta = client.post(f"/api/perfis/{perfil['id']}/contas", headers=h,
                        json={"platform": "tiktok", "handle": "meusqueridinhos10",
                              "status": "ativa"}).json()["conta"]
    d = add_destino(client, h, c["id"], conta["id"])
    d = acao(client, h, d, "aprovar").json()["destino"]
    assert d["estado"] == "aprovado"
    amanha = (datetime.now(SP) + timedelta(days=1)).replace(hour=19, minute=0, second=0,
                                                           microsecond=0)
    r = agendar(client, member[1], c["id"], conta["id"], amanha)
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "agendado"

    r = client.post(f"/api/conteudos/{c['id']}/archive", headers=h,
                    json={"version": c["version"]})
    if r.status_code == 200:  # rota da trilha A: arquivar cancela os agendamentos
        d = client.get(f"/api/destinos/{d['id']}", headers=h).json()["destino"]
        assert d["estado"] == "aprovado" and d["plannedAt"] is None
