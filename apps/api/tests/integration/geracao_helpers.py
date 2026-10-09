"""Dados e motores de teste da geração local (spec 021): o perfil com um cenário (e uma foto de
referência na biblioteca), os fakes do ComfyUI, do shop-tts e do `dockerctl` montados num
`Clientes`, e `rodar_gerador` (voltas da linha GPU e da linha Claude até a fila esvaziar).
Nada chama serviço real."""

import io
import threading
import uuid

import pytest
from fakes.comfyui_fake import ComfyFake
from fakes.dockerctl_fake import DockerctlFake
from fakes.shoptts_fake import ShopTtsFake
from PIL import Image as PILImage

from sociman_api import storage
from sociman_api.geracao import gerador

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


def img(size=(800, 800), color=(30, 120, 200)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def montar(client, h, slug: str = "casa") -> dict:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    pid = r.json()["perfil"]["id"]
    r = client.post(f"/api/perfis/{pid}/assets", headers=h,
                    json={"tipo": "cenario", "name": "Quarto claro", "prompt": "bright bedroom"})
    assert r.status_code == 201, r.text
    cenario = r.json()["asset"]
    r = client.post(f"/api/perfis/{pid}/assets/arquivo", headers=h,
                    data={"tipo": "imagem", "name": "Foto do quarto"},
                    files={"file": ("quarto.jpg", img(), "application/octet-stream")})
    assert r.status_code == 201, r.text
    foto = r.json()["asset"]
    r = client.get(f"/api/assets/{foto['id']}", headers=h)
    foto_image_id = r.json()["asset"]["files"][0]["image"]["id"]
    return {"perfil_id": pid, "cenario": cenario, "foto": foto, "foto_image_id": foto_image_id}


def pedir(client, h, b: dict, status: int = 201, **kw) -> dict:
    corpo = {"alvoTipo": "asset", "alvoId": b["cenario"]["id"], "passo": "cenario.cena",
             "instrucao": "cozy bright bedroom, morning sun"} | kw
    r = client.post(f"/api/perfis/{b['perfil_id']}/geracoes", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def detalhe(client, h, gid: str) -> dict:
    r = client.get(f"/api/geracoes/{gid}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def asset(client, h, asset_id: str) -> dict:
    r = client.get(f"/api/assets/{asset_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["asset"]


def acao(client, h, g: dict, nome: str, status: int = 200, **body) -> dict:
    r = client.post(f"/api/geracoes/{g['id']}/{nome}", headers=h,
                    json={"version": g["version"], **body})
    assert r.status_code == status, r.text
    return r.json()


class Motores:
    """Os três fakes e o `Clientes` do gerador com eles."""

    def __init__(self, memoria: bool = True):
        self.comfy = ComfyFake()
        self.tts = ShopTtsFake()
        self.dockerctl = DockerctlFake()
        self.ia_client = None
        self.clientes = gerador.Clientes(
            comfy=self.comfy.cliente(), tts=self.tts.cliente(),
            memoria=self.dockerctl.cliente() if memoria else None,
            ia=lambda: self.ia_client)

    def linha_gpu(self, stop: threading.Event | None = None) -> gerador.LinhaGpu:
        linha = gerador.LinhaGpu(self.clientes, stop or threading.Event())
        linha.executor.heartbeat_s = 0.05
        return linha

    def linha_claude(self, stop: threading.Event | None = None) -> gerador.LinhaClaude:
        linha = gerador.LinhaClaude(self.clientes, stop or threading.Event())
        linha.executor.heartbeat_s = 0.05
        return linha


@pytest.fixture
def motores(monkeypatch) -> Motores:
    from sociman_api.geracao import comfyui

    monkeypatch.setattr(comfyui, "POLL_S", 0.0)
    return Motores()


def rodar_gpu(m: Motores, voltas: int = 10, linha: gerador.LinhaGpu | None = None) -> list:
    """Voltas da linha GPU até ela não fazer nada (sem a espera do laço)."""
    linha = linha or m.linha_gpu()
    feitas = []
    for _ in range(voltas):
        r = linha.volta()
        if r is None:
            break
        feitas.append(r)
    return feitas


def sem_espera(db_engine_conn=None) -> None:
    """Zera o `next_attempt_at` de toda a fila (o teste não espera os 30 s de verdade)."""
    from sqlalchemy import text

    from sociman_api.db import get_engine

    with get_engine().begin() as conn:
        conn.execute(text("UPDATE geracoes SET next_attempt_at = NULL WHERE status = 'na_fila'"))


def uid(s: str) -> uuid.UUID:
    return uuid.UUID(s)
