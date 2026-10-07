"""`GET /api/integracoes` ganha o bloco `geracao` (spec 021, T038): o que o gerador publicou há
menos de 1 min (a API não alcança a rede `gpu-local`), sem nenhum valor de chave ou token."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import threading

from pydantic import SecretStr

from integration.geracao_helpers import Motores, owner  # noqa: F401 (fixtures)
from sociman_api.config import get_settings
from sociman_api.geracao import gerador

TOKEN = "token-de-teste-dockerctl"


def test_gerador_parado(client, owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "dockerctl_token", SecretStr(""))
    g = client.get("/api/integracoes", headers=owner[1]).json()["geracao"]
    assert g == {"comfyui": "fora", "shopTts": "fora", "memoriaComfyui": "nao_configurado",
                 "gpu": "desconhecida", "gerador": "parado"}


def test_gerador_ativo_publica_o_estado(client, owner, monkeypatch):
    m = Motores()
    linha = gerador.LinhaGpu(m.clientes, threading.Event())
    gerador.publicar_estado(linha)
    r = client.get("/api/integracoes", headers=owner[1])
    g = r.json()["geracao"]
    assert g == {"comfyui": "ok", "shopTts": "ok", "memoriaComfyui": "ok", "gpu": "livre",
                 "gerador": "ativo"}
    assert TOKEN not in r.text
    m.comfy.fora = True
    linha.travada = True
    gerador.publicar_estado(linha, agora=10**9)
    g = client.get("/api/integracoes", headers=owner[1]).json()["geracao"]
    assert g["comfyui"] == "fora" and g["memoriaComfyui"] == "travada"
    assert g["gpu"] == "desconhecida"
