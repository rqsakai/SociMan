"""Áudios (spec 021, T053, US5): wav e m4a válidos com duração, formato, taxa e sha256; > 25 MB
→ 413; vídeo ou texto renomeado → 400; HD sem sentinela → 503; link com Range → 206; nenhuma
rota de alteração."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import hashlib
import subprocess

from fakes.shoptts_fake import wav_sintetico

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    member,
    montar,
    owner,
)
from sociman_api.main import app


def m4a() -> bytes:
    res = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                          "sine=frequency=440:duration=2", "-c:a", "aac", "-f", "ipod",
                          "-movflags", "frag_keyframe+empty_moov", "pipe:1"],
                         capture_output=True, check=True)
    return res.stdout


def video() -> bytes:
    res = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                          "testsrc=size=320x240:rate=10:duration=1", "-f", "lavfi", "-i",
                          "sine=duration=1", "-shortest", "-c:v", "mpeg4", "-c:a", "aac", "-f",
                          "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1"],
                         capture_output=True, check=True)
    return res.stdout


def _enviar(client, h, pid, dados: bytes, nome: str = "voz.wav"):
    return client.post(f"/api/perfis/{pid}/audios", headers=h,
                       files={"arquivo": (nome, dados, "application/octet-stream")})


def test_wav_e_m4a_validos(client, owner):
    h = owner[1]
    b = montar(client, h)
    wav = wav_sintetico(segundos=1.5)
    r = _enviar(client, h, b["perfil_id"], wav)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["formato"] == "wav" and a["sampleRate"] == 24000
    assert abs(a["duracaoMs"] - 1500) <= 20
    assert a["sha256"] == hashlib.sha256(wav).hexdigest() and a["bytes"] == len(wav)
    assert a["link"]["expiresAt"] is not None
    r = _enviar(client, h, b["perfil_id"], m4a(), "voz.m4a")
    assert r.status_code == 201, r.text
    assert r.json()["formato"] == "m4a"
    assert client.get(f"/api/audios/{a['id']}", headers=h).json()["id"] == a["id"]


def test_recusas(client, owner, monkeypatch):
    h = owner[1]
    b = montar(client, h)
    r = _enviar(client, h, b["perfil_id"], b"isto nao e audio" * 10, "texto.wav")
    assert r.status_code == 400 and r.json()["error"]["code"] == "audio_invalido"
    r = _enviar(client, h, b["perfil_id"], video(), "video.mp4")
    assert r.status_code == 400 and r.json()["error"]["code"] == "audio_invalido"
    from sociman_api.geracao import audios

    monkeypatch.setattr(audios, "MAX_BYTES", 1000)
    r = _enviar(client, h, b["perfil_id"], wav_sintetico(segundos=1.0))
    assert r.status_code == 413 and r.json()["error"]["code"] == "arquivo_grande"


def test_hd_sem_sentinela(client, owner, monkeypatch):
    from sociman_api import datadir

    h = owner[1]
    b = montar(client, h)
    monkeypatch.setattr(datadir, "status", lambda *a, **k: datadir.DataDirStatus(
        False, "sem_sentinela", None, None, 0))
    r = _enviar(client, h, b["perfil_id"], wav_sintetico())
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"


def test_link_com_range(client, owner):
    h = owner[1]
    b = montar(client, h)
    a = _enviar(client, h, b["perfil_id"], wav_sintetico(segundos=1.0)).json()
    r = client.get(a["link"]["url"], headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    assert r.headers["content-type"].startswith("audio/wav")
    assert client.get(a["link"]["url"]).status_code == 200


def test_sem_rota_de_alteracao():
    for path, ops in app.openapi()["paths"].items():
        if "/audios" in path:
            assert set(ops) <= {"get", "post"}, (path, set(ops))
    ops = {op["operationId"] for p, v in app.openapi()["paths"].items() if "/audios" in p
           for op in v.values()}
    assert ops == {"audios_enviar", "audios_detalhe"}


def test_membro_envia_e_mcp_nao(client, owner, member):
    b = montar(client, owner[1])
    assert _enviar(client, member[1], b["perfil_id"], wav_sintetico()).status_code == 201
