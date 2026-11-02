"""Grade de duração do vídeo guiado (spec 031, T007, research R1 e R4): funções puras."""

import pytest

from sociman_api.roteiros.grade import (
    GradeInvalida,
    duracao_posicao,
    opcoes,
    orcamento_chars,
    papeis,
    soma_fecha,
    valida_duracao,
)


def test_opcoes_de_5_a_30():
    assert opcoes(5, 6) == [5, 10, 15, 20, 25, 30]
    assert opcoes(8, 4) == [8, 16, 24, 32]
    assert opcoes(6, 1) == [6]
    with pytest.raises(GradeInvalida):
        opcoes(0, 6)
    with pytest.raises(GradeInvalida):
        opcoes(5, 0)


def test_duracao_fora_da_grade():
    assert valida_duracao(5, 5, 6)
    assert valida_duracao(30, 5, 6)
    for fora in (0, 4, 7, 12, 35, -5):
        assert not valida_duracao(fora, 5, 6)
    # A grade é a do roteiro: com base 8, 24 vale e 25 não.
    assert valida_duracao(24, 8, 4)
    assert not valida_duracao(25, 8, 4)


def test_orcamento_de_caracteres():
    assert orcamento_chars(5) == 59  # floor(59,5)
    assert orcamento_chars(10) == 119
    assert orcamento_chars(15) == 178  # floor(178,5)
    assert orcamento_chars(30) == 357
    assert orcamento_chars(0) == 0
    # Sem ruído de float: 0,85 × 20 × 14 = 238 exatos.
    assert orcamento_chars(20) == 238


def test_soma_das_posicoes_fecha_o_alvo():
    base = 5
    durs = [duracao_posicao(t, base) for t in (1, 3, 2)]
    assert durs == [5, 15, 10]
    assert soma_fecha(durs, 30)
    assert not soma_fecha(durs, 25)
    assert not soma_fecha([], 5)
    assert soma_fecha([2.5, 2.5], 5)
    with pytest.raises(GradeInvalida):
        duracao_posicao(4, base)
    with pytest.raises(GradeInvalida):
        duracao_posicao(0, base)


def test_papeis_por_numero_de_quadros():
    assert papeis(2) == ["inicio", "fim"]
    assert papeis(3) == ["inicio", "meio1", "fim"]
    assert papeis(4) == ["inicio", "meio1", "meio2", "fim"]
    for n in (0, 1, 5):
        with pytest.raises(GradeInvalida):
            papeis(n)
