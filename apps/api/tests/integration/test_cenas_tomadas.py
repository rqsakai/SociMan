"""Tomadas da cena (spec 010, T028, FR-011): envio em streaming com ffprobe e miniatura, prompt
usado congelado, escolha, arquivar, HD fora/cheio e o link de vídeo com Range. ffmpeg real."""

# ruff: noqa: F811 — fixtures importadas de `cenas_helpers`

import uuid
from pathlib import Path

import pytest

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    ACHADINHOS,
    _buckets,
    acao,
    base,
    cena_pronta,
    criar_cena,
    get,
    mp4_sintetico,
    owner,
)
from sociman_api.cenas.models import CenaTomada
from sociman_api.config import get_settings


@pytest.fixture(scope="module")
def videos(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("tomadas")
    out = {
        "vertical": mp4_sintetico(d / "vertical.mp4", 8),
        "horizontal": mp4_sintetico(d / "horizontal.mp4", 2, 640, 360),
        "curto": mp4_sintetico(d / "curto.mp4", 0.5),
        "longo": mp4_sintetico(d / "longo.mp4", 31, 240, 426),
    }
    texto = d / "texto.mp4"
    texto.write_text("isto não é um vídeo\n" * 50)
    out["texto"] = texto
    return out


def enviar(client, h, cena_id, path: Path):
    with path.open("rb") as fh:
        return client.post(f"/api/cenas/{cena_id}/tomadas", headers=h,
                           files={"file": (path.name, fh, "video/mp4")})


def _err(r) -> str:
    return r.json()["error"]["code"]


def test_enviar_escolher_arquivar(client, db, base, videos):
    h = base["h"]
    cena = cena_pronta(client, h, base)
    r = enviar(client, h, cena["id"], videos["vertical"])
    assert r.status_code == 201, r.text
    t1 = r.json()
    assert t1["origem"] == "flow_manual"
    assert t1["duracaoMs"] == 8000 and (t1["largura"], t1["altura"]) == (360, 640)
    assert t1["naoVertical"] is False and t1["escolhida"] is True
    assert t1["promptUsado"] == cena["prompt"]["texto"] and t1["thumbUrl"]
    assert t1["videoUrl"].startswith("/api/midia/")

    r = client.get(t1["videoUrl"], headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.content) == 10

    t2 = enviar(client, h, cena["id"], videos["horizontal"]).json()
    assert t2["naoVertical"] is True and t2["escolhida"] is False

    lida = get(client, h, cena["id"])
    assert lida["tomadas"] == 2 and lida["tomadaEscolhida"]["id"] == t1["id"]
    escolhida = acao(client, h, lida, f"tomadas/{t2['id']}/escolher")
    assert escolhida["tomadaEscolhida"]["id"] == t2["id"]

    # remontar depois do envio não muda o prompt usado
    acao(client, h, escolhida, "remontar")
    assert db.get(CenaTomada, uuid.UUID(t1["id"])).prompt_usado == cena["prompt"]["texto"]

    r = client.patch(f"/api/cenas/tomadas/{t2['id']}", headers=h,
                     json={"version": t2["version"], "nota": "2ª tentativa, mão melhor"})
    assert r.status_code == 200 and r.json()["nota"] == "2ª tentativa, mão melhor"
    r = client.post(f"/api/cenas/tomadas/{t2['id']}/arquivar", headers=h,
                    json={"version": r.json()["version"]})
    assert r.status_code == 200 and r.json()["arquivada"] is True
    assert get(client, h, cena["id"])["tomadaEscolhida"] is None
    lista = client.get(f"/api/cenas/{cena['id']}/tomadas", headers=h).json()["items"]
    assert [t["id"] for t in lista] == [t1["id"]]
    todas = client.get(f"/api/cenas/{cena['id']}/tomadas", headers=h,
                       params={"arquivadas": True}).json()["items"]
    assert len(todas) == 2


def test_recusas_sem_gravar(client, db, base, videos):
    h = base["h"]
    cena = cena_pronta(client, h, base)
    for nome in ("curto", "longo", "texto"):
        r = enviar(client, h, cena["id"], videos[nome])
        assert r.status_code == 400 and _err(r) == "invalid_video", (nome, r.text)
    assert db.query(CenaTomada).count() == 0
    rascunho = criar_cena(client, h, base, nome="Rascunho")
    r = enviar(client, h, rascunho["id"], videos["vertical"])
    assert r.status_code == 409 and _err(r) == "cena_nao_pronta"
    assert db.query(CenaTomada).count() == 0


def test_hd_fora_e_cheio(client, base, videos, monkeypatch, tmp_path):
    h = base["h"]
    cena = cena_pronta(client, h, base)
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = enviar(client, h, cena["id"], videos["vertical"])
    assert r.status_code == 503 and _err(r) == "storage_unavailable"
    monkeypatch.undo()
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    r = enviar(client, h, cena["id"], videos["vertical"])
    assert r.status_code == 507 and _err(r) == "storage_full"
