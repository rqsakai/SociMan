"""Dados de teste das cenas (spec 010, T013): o perfil com o avatar "Achadinhos" (descrição de
`persona.md`, um look e uma pose), o cenário "Cozinha retrô", a foto do produto, o guia com a
proibida "milagre" e MP4 sintético via ffmpeg (`testsrc`). Nada chama serviço real."""

import io
import subprocess
from pathlib import Path

import pytest
from PIL import Image as PILImage

from integration.guia_ia_helpers import campos
from sociman_api import storage

PW = "senha-forte-123"
ACHADINHOS = ("A cheerful 1950s pin-up style woman in her early 30s, with dark brown voluminous "
              "curled hair in a vintage updo, fair skin, red lipstick, pearl earrings and a pearl "
              "necklace, wearing a red dress with small white polka dots and white cotton gloves.")
REGRAS = "Mãos longe do rosto nas cenas com fala"
COZINHA = ("1950s kitchen with mint-green countertops, wooden cabinets, copper pots hanging, "
           "pastel bowls on shelves, a stainless steel gas stove")


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


def img(size=(300, 300), color=(30, 120, 200)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def criar_perfil(client, h, slug: str = "achadinhos") -> dict:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def criar_asset(client, h, perfil_id, **body) -> dict:
    r = client.post(f"/api/perfis/{perfil_id}/assets", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def add_file(client, h, asset_id, size=(600, 600), **form) -> dict:
    r = client.post(f"/api/assets/{asset_id}/arquivos", headers=h, data=form,
                    files={"file": ("f.jpg", img(size), "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()["file"]


def produto_foto(client, h, perfil_id, nome="Foto panela") -> dict:
    r = client.post(f"/api/perfis/{perfil_id}/assets/arquivo", headers=h,
                    data={"tipo": "imagem", "name": nome},
                    files={"file": ("panela.jpg", img(), "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def montar_perfil(client, h, slug: str = "achadinhos", proibida: str | None = "milagre") -> dict:
    """O perfil com avatar (look + pose), cenário, foto do produto e o guia."""
    perfil = criar_perfil(client, h, slug)
    pid = perfil["id"]
    avatar = criar_asset(client, h, pid, tipo="avatar", name="Achadinhos", prompt=ACHADINHOS,
                         imageRules=REGRAS)
    look = add_file(client, h, avatar["id"], role="referencia", look="Cozinha, corpo inteiro")
    pose = add_file(client, h, avatar["id"], role="pose", label="Diner, busto")
    cenario = criar_asset(client, h, pid, tipo="cenario", name="Cozinha retrô", prompt=COZINHA)
    cen_file = add_file(client, h, cenario["id"], role="referencia")
    produto = produto_foto(client, h, pid)
    if proibida:
        r = client.put(f"/api/perfis/{pid}/guia", headers=h,
                       json={"version": 0, "campos": campos(proibidas=[proibida])})
        assert r.status_code == 200, r.text
    return {"perfil": perfil, "avatar": avatar, "look": look, "pose": pose, "cenario": cenario,
            "cenario_file": cen_file, "produto": produto}


@pytest.fixture
def base(client, owner) -> dict:
    return montar_perfil(client, owner[1]) | {"h": owner[1], "user": owner[0]}


def corpo_cena(b: dict, **kw) -> dict:
    corpo = {"nome": "Achadinhos abre a panela", "avatarId": b["avatar"]["id"],
             "avatarArquivoId": b["look"]["id"], "cenarioId": b["cenario"]["id"],
             "plano": "medio", "movimento": "parada", "acao": "lifts the lid and steam comes out",
             "fala": "Gente, olha essa panela!", "audio": "soft kitchen ambience",
             "duracaoS": 8, "modo": "ingredientes", "produtoNome": "Panela",
             "produtoImagemId": b["produto"]["id"], "tags": ["abertura"]}
    return corpo | kw


def criar_cena(client, h, b: dict, status: int = 201, **kw) -> dict:
    r = client.post(f"/api/perfis/{b['perfil']['id']}/cenas", headers=h, json=corpo_cena(b, **kw))
    assert r.status_code == status, r.text
    return r.json()


def acao(client, h, cena: dict, nome: str, status: int = 200, **body) -> dict:
    r = client.post(f"/api/cenas/{cena['id']}/{nome}", headers=h,
                    json={"version": cena["version"], **body})
    assert r.status_code == status, r.text
    return r.json()


def cena_pronta(client, h, b: dict, **kw) -> dict:
    return acao(client, h, criar_cena(client, h, b, **kw), "pronta")


def patch(client, h, cena: dict, status: int = 200, **body) -> dict:
    r = client.patch(f"/api/cenas/{cena['id']}", headers=h,
                     json={"version": cena["version"], **body})
    assert r.status_code == status, r.text
    return r.json()


def get(client, h, cena_id) -> dict:
    r = client.get(f"/api/cenas/{cena_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args],
                   check=True, timeout=300)


def mp4_sintetico(path: Path, segundos: float, largura: int = 360, altura: int = 640) -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"testsrc=size={largura}x{altura}:rate=15:duration={segundos}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path))
    return path
