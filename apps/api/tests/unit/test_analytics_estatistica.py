"""Estatística do analytics (spec 019, T006; research R5): mediana, quartis, Spearman com
empates, leitura em palavras, lift e amostra mínima. Puro."""

import pytest

from sociman_api.analytics.estatistica import (
    MIN_CONTA_ESTAGNADO,
    MIN_CONTAS_RADAR,
    MIN_CORRELACAO,
    MIN_GRUPO,
    Amostra,
    leitura_correlacao,
    lift,
    mediana,
    postos,
    quartis,
    spearman,
)


def test_constantes_do_research():
    assert (MIN_GRUPO, MIN_CORRELACAO, MIN_CONTAS_RADAR, MIN_CONTA_ESTAGNADO) == (5, 8, 2, 5)


def test_mediana():
    assert mediana([]) is None
    assert mediana([7]) == 7
    assert mediana([3, 1, 2]) == 2
    assert mediana([4, 1, 3, 2]) == 2.5


def test_quartis_inclusive():
    q = quartis([1, 2, 3, 4, 5])
    assert (q.min, q.q1, q.mediana, q.q3, q.max) == (1, 2, 3, 4, 5)
    q = quartis([1, 2, 3, 4])
    assert (q.q1, q.mediana, q.q3) == (1.75, 2.5, 3.25)
    assert quartis([]) is None
    um = quartis([9])
    assert (um.min, um.q1, um.mediana, um.q3, um.max) == (9, 9, 9, 9, 9)


def test_postos_com_empates_pela_media():
    assert postos([10, 20, 20, 30]) == [1, 2.5, 2.5, 4]
    assert postos([5, 5, 5]) == [2, 2, 2]
    assert postos([3, 1, 2]) == [3, 1, 2]
    assert postos([]) == []


def test_spearman_valores_conhecidos():
    assert spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1)
    assert spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10]) == pytest.approx(-1)
    # monotônica mas não linear: ρ continua 1 (postos)
    assert spearman([1, 2, 3, 4, 5], [1, 4, 9, 16, 1000]) == pytest.approx(1)
    # exemplo clássico: d² = 0+1+1+0+4... → 1 − 6·Σd²/(n(n²−1))
    xs, ys = [1, 2, 3, 4, 5], [2, 1, 4, 3, 5]
    assert spearman(xs, ys) == pytest.approx(1 - 6 * 4 / (5 * 24))
    # ρ = 0
    assert spearman([1, 2, 3, 4], [1, 2, 2, 1]) == pytest.approx(0)


def test_spearman_com_empates():
    # postos x = [1, 2.5, 2.5, 4], y = [1, 2, 3, 4] → Pearson dos postos
    assert spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(0.9486833, abs=1e-6)


def test_spearman_sem_resposta():
    assert spearman([], []) is None
    assert spearman([1], [2]) is None
    assert spearman([1, 1, 1], [1, 2, 3]) is None  # um lado constante
    with pytest.raises(ValueError):
        spearman([1, 2], [1])


@pytest.mark.parametrize(("rho", "texto"), [
    (None, None), (0, "fraca"), (0.29, "fraca positiva"), (-0.1, "fraca negativa"),
    (0.3, "moderada positiva"), (-0.59, "moderada negativa"), (0.6, "forte positiva"),
    (-1, "forte negativa"),
])
def test_leitura_da_correlacao(rho, texto):
    assert leitura_correlacao(rho) == texto


def test_lift():
    assert lift(300, 100) == 3
    assert lift(50, 100) == 0.5
    assert lift(10, 0) is None  # sem base
    assert lift(10, None) is None
    assert lift(None, 100) is None


def test_amostra():
    a = Amostra(3, MIN_GRUPO)
    assert (a.suficiente, a.faltam) == (False, 2)
    b = Amostra(9, MIN_CORRELACAO)
    assert (b.suficiente, b.faltam) == (True, 0)
    assert Amostra(0, 2).faltam == 2
