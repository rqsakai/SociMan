"""Motor `tts` (spec 021, T053, contrato v2 do shop-tts) com o fake e aplicadores injetados de
`voz.design` e `voz.teste` (os reais chegam com a 025): os candidatos com o áudio e o teste e as
medidas; o `voz.teste` termina `entregue`; o lote é apagado do serviço."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import uuid

import pytest
from sqlalchemy import select

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    acao,
    detalhe,
    montar,
    motores,
    owner,
    pedir,
    rodar_gpu,
)
from sociman_api.geracao import aplicadores
from sociman_api.geracao.models import Audio


class _Voz(aplicadores.Aplicador):
    def validar_alvo(self, db, perfil_id, alvo_id, *, lock=False):
        return type("Alvo", (), {"version": 1, "perfil_id": perfil_id})()

    def montar_params(self, db, actor, alvo, pedido):
        return {"instrucao": pedido.instrucao, "referencias": [], "texto": pedido.texto}

    def conferir_referencias(self, db, geracao):
        return None


class _Design(_Voz):
    def pedido_tts(self, db, geracao):
        return {"op": "design", "nome": "voz_calma", "descricao": "calm warm female voice"}


class _Teste(_Voz):
    def pedido_tts(self, db, geracao):
        return {"op": "tts", "corpo": {"voice": "calma", "sentences": [geracao.params["texto"]]}}


@pytest.fixture
def vozes(monkeypatch):
    monkeypatch.setitem(aplicadores.APLICADORES, "voz.design", _Design())
    monkeypatch.setitem(aplicadores.APLICADORES, "voz.teste", _Teste())


def test_design_grava_candidatos_com_teste_e_apaga_o_lote(client, owner, motores, vozes, db):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b, alvoTipo="voz", alvoId=str(uuid.uuid4()), passo="voz.design",
              instrucao="voz calma")
    assert g["nOpcoes"] == 3 and g["motor"] == "tts"
    rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "revisao" and len(g["candidatos"]) == 3
    for c in g["candidatos"]:
        assert c["audio"]["formato"] == "wav" and c["audio"]["link"]["expiresAt"]
        assert c["testeAudio"]["id"] != c["audio"]["id"]
        assert {"segundos", "similaridade", "transcricao"} <= set(c["metricas"])
    assert motores.tts.lotes_apagados
    assert db.scalar(select(Audio).limit(1)) is not None
    # Antes do tts, o ComfyUI foi liberado (FR-022) e a RAM do ComfyUI não mexeu.
    assert {"unload_models": True, "free_memory": True} in \
        [p.corpo for p in motores.comfy.requests if p.caminho == "/free"]
    assert motores.dockerctl.historico == []


def test_voz_teste_entregue(client, owner, motores, vozes):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b, alvoTipo="voz", alvoId=str(uuid.uuid4()), passo="voz.teste",
              texto="Oi, gente! Olha que achado.")
    rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "entregue" and g["finishedAt"] and g["escolhidoId"] is None
    assert g["candidatos"][0]["audio"] and g["candidatos"][0]["metricas"]["texto"]
    assert motores.tts.lotes_apagados
    r = acao(client, h, g, "cancelar", status=409)
    assert r["error"]["code"] == "geracao_finalizada"


def test_503_do_tts_espera_com_sem_memoria(client, owner, motores, vozes):
    h = owner[1]
    b = montar(client, h)
    motores.tts.sem_memoria = 1
    g = pedir(client, h, b, alvoTipo="voz", alvoId=str(uuid.uuid4()), passo="voz.design",
              instrucao="voz")
    rodar_gpu(motores, voltas=1)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "na_fila" and g["erro"]["code"] == "sem_memoria"
    assert g["attempts"] == 1
