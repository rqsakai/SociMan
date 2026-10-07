"""Erros, espera e tentativas (spec 021, T008, R8): a GPU ocupada não conta tentativa nem
falha; `sem_memoria` e `servico_fora` esperam de 30 s a 15 min e falham na 7ª; entrada e
interno falham na hora; nenhuma mensagem vaza o texto do serviço."""

from datetime import timedelta

import pytest

from sociman_api.geracao import erros
from sociman_api.geracao.erros import MotorErro


def test_gpu_ocupada_nao_conta_nem_falha():
    for n in (1, 6, 50):
        e = erros.decidir(MotorErro("gpu_ocupada"), n)
        assert e.acao == "esperar" and not e.conta_tentativa
        assert e.depois == timedelta(seconds=30)
        assert e.mensagem == "Aguardando a GPU ficar livre"


@pytest.mark.parametrize("codigo", ["sem_memoria", "servico_fora"])
def test_espera_crescente_e_falha_na_setima(codigo):
    esperas = [erros.decidir(MotorErro(codigo), n).depois for n in range(1, 7)]
    assert esperas == [timedelta(seconds=30), timedelta(minutes=1), timedelta(minutes=2),
                       timedelta(minutes=4), timedelta(minutes=8), timedelta(minutes=15)]
    assert all(erros.decidir(MotorErro(codigo), n).conta_tentativa for n in range(1, 7))
    final = erros.decidir(MotorErro(codigo), 7)
    assert final.acao == "falhar" and final.codigo == codigo


@pytest.mark.parametrize("codigo", ["entrada_invalida", "internal"])
def test_falha_na_hora(codigo):
    assert erros.decidir(MotorErro(codigo), 1).acao == "falhar"


def test_mensagens_nao_vazam_o_servico():
    cru = "Traceback: torch.OutOfMemoryError at /opt/ComfyUI/nodes.py"
    for codigo in erros.CODIGOS:
        e = MotorErro(codigo, detalhe=cru)
        assert e.mensagem == erros.MENSAGENS[codigo]
        assert cru not in erros.decidir(e, 7).mensagem
    assert set(erros.MENSAGENS) == set(erros.CODIGOS)
