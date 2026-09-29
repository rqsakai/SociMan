"""Seleção de vídeos para corte (T035; R4, R16, contracts/http-api.md "Envios").

Os canais e vídeos entram direto pelo modelo (sem a Trilha A).
"""

import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from integration import envios_helpers
from integration.envios_helpers import (
    criar_canal,
    criar_video,
    envio_row,
    selecionado,
    selecionar,
)
from sociman_api import storage
from sociman_api.canais.models import CanalDireito
from sociman_api.config import get_settings
from sociman_api.db import get_engine
from sociman_api.envios import upload
from sociman_api.envios.models import EnvioStatus

# Fixtures compartilhadas (atribuídas, e não importadas, para o ruff não acusar F811).
_buckets = envios_helpers._buckets
member = envios_helpers.member
owner = envios_helpers.owner
perfil = envios_helpers.perfil

def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args],
                   check=True, timeout=300)


@pytest.fixture(scope="module")
def arquivos(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("avulsos")
    out = {"ok": d / "longo.mp4", "curto": d / "curto.mp4", "texto": d / "texto.mp4"}
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:s=320x240:d=46:r=5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=46",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(out["ok"]))
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:s=320x240:d=30:r=5",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out["curto"]))
    out["texto"].write_text("isto não é um vídeo\n" * 50)
    return out


def _arquivo(client, h, perfil_id: str, path: Path, titulo: str | None = "Minha live",
             headers: dict | None = None):
    data = {"titulo": titulo} if titulo is not None else {}
    with path.open("rb") as fh:
        return client.post(f"/api/perfis/{perfil_id}/envios/arquivo",
                           headers=h | (headers or {}), data=data,
                           files={"file": (path.name, fh, "video/mp4")})


# ---- vídeo de canal ----

def test_selecionar_video_de_canal(client, owner, perfil, db):
    user, h = owner
    canal = criar_canal(CanalDireito.proprio, "The IT Nerd")
    video = criar_video(canal, title="Como montar um PC")
    r = selecionar(client, h, perfil["id"], videoFonteId=str(video.id))
    assert r.status_code == 201, r.text
    e = r.json()["envio"]
    assert e["status"] == "selecionado" and e["origem"] == "canal" and e["config"] is None
    assert e["sourceTitle"] == "Como montar um PC" and e["precisaAviso"] is False
    assert e["sourceUrl"] == f"https://www.youtube.com/watch?v={video.youtube_video_id}"
    assert e["video"]["id"] == str(video.id) and e["canal"]["direito"] == "proprio"
    assert e["createdBy"]["id"] == str(user.id) and e["version"] == 1

    (v,) = client.get(f"/api/envios/{e['id']}/versions", headers=h).json()["items"]
    assert v["action"] == "created" and v["details"] == {"duplicado": False}
    assert envio_row(db, e["id"]).canal_fonte_id == canal.id


def test_sem_acordo_precisa_de_aviso(client, owner, perfil):
    video = criar_video(criar_canal(CanalDireito.sem_acordo))
    e = selecionado(client, owner[1], perfil["id"], video)
    assert e["precisaAviso"] is True


def test_duplicado_pede_confirmacao(client, owner, perfil, db):
    _, h = owner
    video = criar_video(criar_canal())
    e1 = selecionado(client, h, perfil["id"], video)

    r = selecionar(client, h, perfil["id"], videoFonteId=str(video.id))
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "already_selected" and err["details"]["envioId"] == e1["id"]

    # enviado → already_sent
    r = client.post("/api/envios/enviar", headers=h, json={
        "items": [{"envioId": e1["id"], "version": 1}], "confirmarAviso": True})
    assert r.status_code == 200, r.text
    r = selecionar(client, h, perfil["id"], videoFonteId=str(video.id))
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_sent"
    assert r.json()["error"]["details"]["envioId"] == e1["id"]

    r = selecionar(client, h, perfil["id"], videoFonteId=str(video.id), confirmarDuplicado=True)
    assert r.status_code == 201, r.text
    e2 = r.json()["envio"]
    assert e2["id"] != e1["id"]
    (v,) = client.get(f"/api/envios/{e2['id']}/versions", headers=h).json()["items"]
    assert v["details"] == {"duplicado": True}

    # outro perfil não conta como duplicado
    outro = client.post("/api/perfis", json={"name": "Outro", "slug": "outro"}, headers=h)
    r = selecionar(client, h, outro.json()["perfil"]["id"], videoFonteId=str(video.id))
    assert r.status_code == 201


def test_video_indisponivel(client, owner, perfil):
    video = criar_video(criar_canal(), disponivel=False)
    r = selecionar(client, owner[1], perfil["id"], videoFonteId=str(video.id))
    assert r.status_code == 409 and r.json()["error"]["code"] == "video_unavailable"


def test_video_inexistente_e_entrada_ambigua(client, owner, perfil):
    _, h = owner
    r = selecionar(client, h, perfil["id"], videoFonteId=str(uuid.uuid4()))
    assert r.status_code == 404
    r = selecionar(client, h, perfil["id"])
    assert r.status_code == 400
    r = selecionar(client, h, perfil["id"], videoFonteId=str(uuid.uuid4()), url="https://x.y/z")
    assert r.status_code == 400


def test_perfil_arquivado(client, owner, perfil):
    _, h = owner
    r = client.post(f"/api/perfis/{perfil['id']}/archive", json={"version": perfil["version"]},
                    headers=h)
    assert r.status_code == 200, r.text
    video = criar_video(criar_canal())
    r = selecionar(client, h, perfil["id"], videoFonteId=str(video.id))
    assert r.status_code == 409 and r.json()["error"]["code"] == "perfil_archived"


# ---- avulso por link ----

def test_avulso_por_link(client, member, perfil):
    _, h = member
    r = selecionar(client, h, perfil["id"], url=" https://vimeo.com/12345 ",
                   titulo="  Palestra   boa ")
    assert r.status_code == 201, r.text
    e = r.json()["envio"]
    assert e["origem"] == "avulso_link" and e["sourceUrl"] == "https://vimeo.com/12345"
    assert e["sourceTitle"] == "Palestra boa" and e["precisaAviso"] is True
    assert e["video"] is None and e["canal"] is None

    r = selecionar(client, h, perfil["id"], url="https://vimeo.com/12345")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_selected"

    r = selecionar(client, h, perfil["id"], url="https://vimeo.com/999")
    assert r.json()["envio"]["sourceTitle"] == "https://vimeo.com/999"


@pytest.mark.parametrize("url", ["ftp://x.com/a", "vimeo.com/1", "https://", "javascript:alert(1)",
                                 "https://a.com/" + "x" * 2000, "https://a.com/com espaço"])
def test_link_invalido(client, owner, perfil, url):
    r = selecionar(client, owner[1], perfil["id"], url=url)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_url"


# ---- avulso por arquivo ----

def test_avulso_por_arquivo(client, owner, perfil, arquivos, db):
    _, h = owner
    r = _arquivo(client, h, perfil["id"], arquivos["ok"])
    assert r.status_code == 201, r.text
    e = r.json()["envio"]
    assert e["origem"] == "avulso_arquivo" and e["sourceTitle"] == "Minha live"
    assert e["status"] == "selecionado" and e["precisaAviso"] is True
    row = envio_row(db, e["id"])
    assert row.upload_key == f"envios/{e['id']}/fonte.mp4"
    assert row.upload_bytes == arquivos["ok"].stat().st_size
    assert 45_000 < row.upload_duration_ms < 47_000 and len(row.upload_sha256) == 64
    assert storage.stat(row.upload_key, bucket="videos").size == row.upload_bytes
    spool = Path(get_settings().data_dir) / "work" / "tmp"
    assert list(spool.glob("envio-*")) == []

    r = _arquivo(client, h, perfil["id"], arquivos["ok"], titulo=None)
    assert r.json()["envio"]["sourceTitle"] == "longo"


@pytest.mark.parametrize(("nome", "mensagem"), [
    ("texto", "Não é um vídeo aceito"),
    ("curto", "Vídeo com menos de 45 segundos"),
])
def test_arquivo_invalido(client, owner, perfil, arquivos, nome, mensagem):
    r = _arquivo(client, owner[1], perfil["id"], arquivos[nome])
    assert r.status_code == 400, r.text
    assert r.json()["error"] == {"code": "invalid_video", "message": mensagem}


def test_arquivo_longo_demais(client, owner, perfil, arquivos, monkeypatch):
    monkeypatch.setattr(upload, "MAX_DURATION_S", 40)  # no lugar de um vídeo de 3 h
    r = _arquivo(client, owner[1], perfil["id"], arquivos["ok"])
    assert r.status_code == 400
    assert r.json()["error"]["message"] == "Vídeo com mais de 3 horas"


def test_arquivo_maior_que_2gb(client, owner, perfil, arquivos):
    r = _arquivo(client, owner[1], perfil["id"], arquivos["ok"],
                 headers={"content-length": str(upload.MAX_BODY + 1)})
    assert r.status_code == 413
    assert r.json()["error"] == {"code": "payload_too_large", "message": "Arquivo maior que 2 GB"}


def test_arquivo_sem_hd(client, owner, perfil, arquivos, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = _arquivo(client, owner[1], perfil["id"], arquivos["ok"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
    monkeypatch.undo()
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    r = _arquivo(client, owner[1], perfil["id"], arquivos["ok"])
    assert r.status_code == 507 and r.json()["error"]["code"] == "storage_full"


# ---- descartar e listar ----

def test_descartar_selecionado(client, owner, perfil, db):
    _, h = owner
    video = criar_video(criar_canal())
    e = selecionado(client, h, perfil["id"], video)
    row = envio_row(db, e["id"])
    assert row.config is None and row.direito_no_envio is None  # o caminho real: sem envio
    db.rollback()
    r = client.post(f"/api/envios/{e['id']}/archive", json={"version": 1}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()["envio"]
    assert d["status"] == "descartado" and d["archived"] is True and d["version"] == 2
    row = envio_row(db, e["id"])  # a linha fica, ainda sem config
    assert row.status == EnvioStatus.descartado and row.config is None

    r = client.post(f"/api/envios/{e['id']}/archive", json={"version": 2}, headers=h)
    assert r.status_code == 409
    # descartado não conta como duplicado
    assert selecionar(client, h, perfil["id"], videoFonteId=str(video.id)).status_code == 201


def test_descartar_em_andamento_da_409(client, owner, perfil):
    _, h = owner
    e = selecionado(client, h, perfil["id"], criar_video(criar_canal(CanalDireito.proprio)))
    r = client.post("/api/envios/enviar", headers=h,
                    json={"items": [{"envioId": e["id"], "version": 1}]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/envios/{e['id']}/archive", json={"version": 2}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


def test_listar_e_obter(client, owner, perfil):
    _, h = owner
    canal = criar_canal()
    e1 = selecionado(client, h, perfil["id"], criar_video(canal))
    e2 = selecionado(client, h, perfil["id"], criar_video(canal))
    outro = client.post("/api/perfis", json={"name": "Outro", "slug": "outro"}, headers=h)
    selecionado(client, h, outro.json()["perfil"]["id"], criar_video(canal))

    items = client.get("/api/envios", params={"perfilId": perfil["id"]}, headers=h).json()["items"]
    assert [i["id"] for i in items] == [e2["id"], e1["id"]]
    r = client.get("/api/envios", params=[("status", "selecionado"), ("status", "na_fila")],
                   headers=h)
    assert len(r.json()["items"]) == 3
    assert client.get("/api/envios", params={"status": "pronto"}, headers=h).json()["items"] == []

    r = client.get(f"/api/envios/{e1['id']}", headers=h)
    assert r.status_code == 200 and r.json()["envio"]["id"] == e1["id"]
    assert r.json()["cortes"] == []
    assert client.get(f"/api/envios/{uuid.uuid4()}", headers=h).status_code == 404


def test_check_do_envio_aceita_descartado_sem_config(client, owner, perfil):
    """O check do banco aceita `descartado` sem config; com a definição antiga ("só
    `selecionado` dispensa config") o mesmo UPDATE falharia. A troca é feita numa transação
    desfeita no fim (DDL do Postgres é transacional)."""
    e = selecionado(client, owner[1], perfil["id"], url="https://vimeo.com/7")
    with get_engine().connect() as conn:
        definicao = conn.execute(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_envios_enviado_config'")).scalar_one()
        assert "descartado" in definicao
        # na mesma transação (autobegin), desfeita no fim: nada disto fica no banco
        conn.execute(text("ALTER TABLE envios DROP CONSTRAINT ck_envios_enviado_config"))
        conn.execute(text(
            "ALTER TABLE envios ADD CONSTRAINT ck_envios_enviado_config CHECK "
            "(status = 'selecionado' OR (config IS NOT NULL "
            "AND direito_no_envio IS NOT NULL)) NOT VALID"))
        with pytest.raises(IntegrityError), conn.begin_nested():
            conn.execute(text("UPDATE envios SET status = 'descartado' WHERE id = :id"),
                         {"id": e["id"]})
        conn.rollback()
    r = client.post(f"/api/envios/{e['id']}/archive", json={"version": 1}, headers=owner[1])
    assert r.status_code == 200 and r.json()["envio"]["status"] == "descartado"
