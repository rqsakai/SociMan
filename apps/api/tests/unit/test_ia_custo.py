"""Custo aproximado pelo `usage` (spec 008, T009, R7)."""

import logging
from decimal import Decimal
from types import SimpleNamespace as NS

from sociman_api.ia import custo
from sociman_api.ia.custo import Uso, somar

SONNET = "claude-sonnet-5-5"


def _resposta(model=SONNET, iterations=None, **usage):
    base = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "iterations": iterations}
    return NS(model=model, usage=NS(**(base | usage)))


def test_sem_cache():
    uso = Uso()
    somar(uso, _resposta(input_tokens=2500, output_tokens=400), SONNET)
    # 2500 × 2 + 400 × 10 = 9.000 por milhão
    assert uso.custo_usd == Decimal("0.009000")
    assert (uso.input_tokens, uso.output_tokens) == (2500, 400)
    assert uso.model_servido == SONNET and custo.PRECOS_VERSAO == "2026-09"


def test_com_leitura_e_escrita_de_cache_e_soma_das_tentativas():
    uso = Uso()
    somar(uso, _resposta(input_tokens=100, output_tokens=200, cache_creation_input_tokens=2000),
          SONNET)
    somar(uso, _resposta(input_tokens=100, output_tokens=200, cache_read_input_tokens=2000),
          SONNET)
    # (100×2 + 200×10 + 2000×2,5) + (100×2 + 200×10 + 2000×0,2) = 7.200 + 2.600
    assert uso.custo_usd == Decimal("0.009800")
    assert (uso.cache_creation_tokens, uso.cache_read_tokens) == (2000, 2000)
    assert (uso.input_tokens, uso.output_tokens) == (200, 400)


def test_fallback_para_o_opus_preca_cada_iteracao():
    iteracoes = [
        NS(type="message", model=None, input_tokens=1000, output_tokens=10,
           cache_read_input_tokens=0, cache_creation_input_tokens=0),
        NS(type="fallback_message", model="claude-opus-5-5", input_tokens=1000,
           output_tokens=300, cache_read_input_tokens=0, cache_creation_input_tokens=0),
    ]
    uso = Uso()
    somar(uso, _resposta(model="claude-opus-5-5", iterations=iteracoes, input_tokens=2000,
                         output_tokens=310), SONNET)
    # Sonnet: 1000×2 + 10×10 = 2.100; Opus: 1000×4 + 300×20 = 10.000
    assert uso.custo_usd == Decimal("0.012100")
    assert uso.model_servido == "claude-opus-5-5"


def test_modelo_desconhecido_usa_o_sonnet_e_avisa(caplog):
    uso = Uso()
    with caplog.at_level(logging.WARNING, logger="sociman_api.ia.custo"):
        somar(uso, _resposta(model="claude-futuro-9", input_tokens=1000, output_tokens=100),
              SONNET)
    assert uso.custo_usd == Decimal("0.003000")
    assert "claude-futuro-9" in caplog.text


def test_sem_usage_nao_tem_custo():
    uso = Uso()
    somar(uso, None, SONNET)
    assert uso.custo_usd is None and uso.input_tokens is None
