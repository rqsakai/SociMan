"""Dados e voltas de teste dos produtos (spec 012): o perfil, as fotos sintéticas, criar o
produto pela rota, o Claude falso nos `Motores` da 021 e `rodar_tudo` (linha Claude e linha GPU
até a fila esvaziar). Nada chama serviço real."""

import io

import pytest
from fakes.anthropic_fake import AnthropicFake
from PIL import Image as PILImage

from integration.geracao_helpers import Motores, rodar_gpu

CORES = ((20, 20, 20), (150, 150, 150), (20, 30, 90), (240, 240, 230), (90, 110, 50),
         (110, 20, 40))


def foto(size=(800, 900), cor=(20, 20, 20), fmt="JPEG") -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", size, cor).save(buf, format=fmt)
    return buf.getvalue()


def perfil(client, h, slug: str = "shop") -> str:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]["id"]


def criar(client, h, perfil_id: str, n_fotos: int = 1, status: int = 201, obs: str = "",
          fotos: list[bytes] | None = None, name: str = "shorts_canelado", **form) -> dict:
    fotos = fotos if fotos is not None else [foto(cor=CORES[i % 6]) for i in range(n_fotos)]
    files = [("fotos", (f"foto_{i + 1}.jpg", f, "application/octet-stream"))
             for i, f in enumerate(fotos)]
    data = {"name": name, "obs": obs, **form}
    r = client.post(f"/api/perfis/{perfil_id}/produtos", headers=h, data=data,
                    files=files or None)
    assert r.status_code == status, r.text
    return r.json()


def ver(client, h, produto_id: str) -> dict:
    r = client.get(f"/api/produtos/{produto_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def versoes(client, h, produto_id: str) -> list[dict]:
    r = client.get(f"/api/produtos/{produto_id}/versoes", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def passos(p: dict, passo: str) -> list[dict]:
    return [s for s in p["passos"] if s["passo"] == passo]


def com_claude(m: Motores) -> AnthropicFake:
    fake = AnthropicFake()
    m.ia_client = fake.ia_client()
    return fake


def rodar_tudo(m: Motores, voltas: int = 30) -> list:
    """Linha Claude e linha GPU até nenhuma das duas ter o que fazer."""
    claude, gpu = m.linha_claude(), m.linha_gpu()
    feitas = []
    for _ in range(voltas):
        c = claude.volta()
        g = rodar_gpu(m, voltas=1, linha=gpu)
        if c is None and not g:
            break
        feitas += [x for x in (c, *g) if x]
    return feitas


def escolher(client, h, produto: dict, geracao_id: str, numero: int = 1,
             status: int = 200) -> dict:
    g = client.get(f"/api/geracoes/{geracao_id}", headers=h).json()
    cand = next(c for c in g["candidatos"] if c["numero"] == numero)
    r = client.post(f"/api/geracoes/{geracao_id}/escolher", headers=h,
                    json={"candidatoId": cand["id"], "version": g["version"],
                          "alvoVersion": produto["version"]})
    assert r.status_code == status, r.text
    return r.json()


@pytest.fixture
def claude_fake(motores) -> AnthropicFake:
    return com_claude(motores)
