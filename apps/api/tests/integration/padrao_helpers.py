"""Dados e voltas de teste do cadastro padronizado (spec 025, T011): o avatar e o cenário pela
rota da 007, os passos pela rota de gerações da 021, escolher pela rota da 021, o kit inteiro
com os fakes (ComfyUI, shop-tts e Claude), as vozes e o consentimento. Nada chama serviço
real."""

import io

from fakes.anthropic_fake import AnthropicFake
from PIL import Image as PILImage

from integration.geracao_helpers import Motores, rodar_gpu

PESSOA = "an adult woman in her early thirties with dark curly hair and warm brown skin"


def img(size=(800, 900), cor=(30, 120, 200)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", size, cor).save(buf, format="JPEG")
    return buf.getvalue()


def perfil(client, h, slug: str = "kit") -> str:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]["id"]


def avatar(client, h, perfil_id: str, name: str = "Ana") -> dict:
    r = client.post(f"/api/perfis/{perfil_id}/assets", headers=h,
                    json={"tipo": "avatar", "name": name})
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def cenario(client, h, perfil_id: str, name: str = "Cozinha retrô",
            prompt: str = "retro kitchen with mint countertops") -> dict:
    r = client.post(f"/api/perfis/{perfil_id}/assets", headers=h,
                    json={"tipo": "cenario", "name": name, "prompt": prompt})
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def ver(client, h, asset_id: str) -> dict:
    r = client.get(f"/api/assets/{asset_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["asset"]


def pedir(client, h, perfil_id: str, alvo_id: str, passo: str, status: int = 201,
          alvo_tipo: str = "asset", **kw) -> dict:
    corpo = {"alvoTipo": alvo_tipo, "alvoId": alvo_id, "passo": passo, "instrucao": ""} | kw
    r = client.post(f"/api/perfis/{perfil_id}/geracoes", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def geracao(client, h, gid: str) -> dict:
    r = client.get(f"/api/geracoes/{gid}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def escolher_opcao(client, h, gid: str, numero: int, alvo_version: int,
                   status: int = 200) -> dict:
    g = geracao(client, h, gid)
    cand = next(c for c in g["candidatos"] if c["numero"] == numero)
    r = client.post(f"/api/geracoes/{gid}/escolher", headers=h,
                    json={"candidatoId": cand["id"], "version": g["version"],
                          "alvoVersion": alvo_version})
    assert r.status_code == status, r.text
    return r.json()


def com_claude(m: Motores) -> AnthropicFake:
    fake = AnthropicFake()
    m.ia_client = fake.ia_client()
    return fake


def passo_e_escolha(client, h, m: Motores, perfil_id: str, asset_id: str, passo: str,
                    numero: int = 1, **kw) -> dict:
    g = pedir(client, h, perfil_id, asset_id, passo, **kw)
    rodar_gpu(m)
    assert geracao(client, h, g["id"])["status"] == "revisao"
    escolher_opcao(client, h, g["id"], numero, ver(client, h, asset_id)["version"])
    return g


def avatar_com_slots(client, h, m: Motores, perfil_id: str, n: int = 5,
                     name: str = "Ana") -> dict:
    """O avatar com os `n` primeiros passos do kit escolhidos (1 origem, 2 frontal, 3 par 3/4,
    4 corpo-base; 5 = o kit inteiro, com a checagem de identidade rodada pela linha Claude)."""
    a = avatar(client, h, perfil_id, name)
    ordem = (("avatar.rosto_origem", {"instrucao": PESSOA}), ("avatar.rosto_frontal", {}),
             ("avatar.rostos_34", {}), ("avatar.corpo_base", {}))
    for passo, kw in ordem[:min(n, 4)]:
        passo_e_escolha(client, h, m, perfil_id, a["id"], passo, **kw)
    if n == 5:
        m.linha_claude().volta()
    return ver(client, h, a["id"])


def cenario_com_cena(client, h, m: Motores, perfil_id: str) -> dict:
    c = cenario(client, h, perfil_id)
    passo_e_escolha(client, h, m, perfil_id, c["id"], "cenario.cena")
    return ver(client, h, c["id"])


def consentimento(client, h, asset_id: str, version: int, status: int = 200,
                  rota: str = "assets", **kw) -> dict:
    corpo = {"version": version, "nome": "Ana Souza", "data": "2026-10-01",
             "observacao": "termo assinado"} | kw
    r = client.put(f"/api/{rota}/{asset_id}/consentimento", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def voz(client, h, perfil_id: str, origem: str = "gravacao", name: str = "Ana vendas",
        status: int = 201, **kw) -> dict:
    corpo = {"name": name, "origem": origem, "tom": "vendas animada"} | kw
    if origem == "sintetica":
        corpo.setdefault("descricao", "warm adult female voice, energetic sales tone")
    r = client.post(f"/api/perfis/{perfil_id}/vozes", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def ver_voz(client, h, voz_id: str) -> dict:
    r = client.get(f"/api/vozes/{voz_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def enviar_audio(client, h, perfil_id: str, dados: bytes, nome: str = "gravacao.wav") -> dict:
    r = client.post(f"/api/perfis/{perfil_id}/audios", headers=h,
                    files={"arquivo": (nome, dados, "audio/wav")})
    assert r.status_code == 201, r.text
    return r.json()
