"""Estatística do aprendizado (spec 023, T008; R1 e R2): casos de referência calculados à mão."""

import math

import pytest

from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import estatistica as e
from sociman_api.aprendizado.estatistica import Item


def test_encolhimento_com_3_posts_cai_a_3_8_e_viral_puxa():
    # 3 posts de peso 1, desvio bruto médio 1,2: encolhido = 3,6 / (3 + 5) = 0,45 (3/8 de 1,2)
    itens = [Item(0.2, 1.0, views=10), Item(0.4, 1.0, views=20), Item(3.0, 1.0, views=2000)]
    assert e.encolhido(itens) == pytest.approx(3.6 / 8)
    assert e.encolhido(itens) == pytest.approx(3 / 8 * (3.6 / 3))
    assert e.concentracao(itens)  # 2000 / 2030 > 0,5: "puxado por 1"
    resto = e.sem_maior(itens)
    assert [i.views for i in resto] == [10, 20]
    assert e.encolhido(resto) == pytest.approx(0.6 / 7)


def test_grupo_0_1_com_mediana_geral_0_nao_da_infinito():
    assert e.medida_log(0) == 0.0
    assert e.medida_log(1) == pytest.approx(math.log(2))
    # base da conta 0 (todos com 0 views): o desvio é o próprio log, finito
    itens = [Item(e.medida_log(v), 1.0, v) for v in (0, 1, 0, 1, 0)]
    efeito = e.efeito_rendimento(itens)
    assert math.isfinite(efeito) and math.isfinite(e.exibir(efeito, "rendimento"))


def test_peso_de_30_dias_e_meio():
    assert e.peso(0) == 1.0
    assert e.peso(30) == pytest.approx(0.5)
    assert e.peso(60) == pytest.approx(0.25)
    assert e.peso(-3) == 1.0


def test_mesma_semente_mesmo_intervalo():
    itens = [Item(d / 10, 1.0) for d in (-3, 1, 2, 5, 8, 9, 12)]
    s = e.semente("perfil", "tema", "x")
    a = e.intervalo(itens, s)
    assert a == e.intervalo(itens, s)
    assert a != e.intervalo(itens, e.semente("perfil", "tema", "y"))
    assert a[0] <= e.encolhido(itens) <= a[1]
    assert e.semente("a", 1) == e.semente("a", 1)


@pytest.mark.parametrize(("n", "dias", "iv", "efeito", "parte", "esperado"), [
    (4, 3, (0.1, 0.9), 0.6, "rendimento", "amostra_pequena"),
    (5, 1, (0.1, 0.9), 0.6, "rendimento", "amostra_pequena"),
    (5, 2, (0.1, 0.9), 0.6, "rendimento", "moderada"),
    (9, 2, (0.1, 0.9), 0.6, "rendimento", "moderada"),
    (10, 2, (0.1, 0.9), 0.6, "rendimento", "forte"),
    (10, 2, (0.1, 0.9), 0.3, "rendimento", "moderada"),  # abaixo de ln 1,5
    (10, 2, (-0.1, 0.9), 0.3, "rendimento", "fraca"),  # cruza 0, mas ≥ ln 1,3
    (10, 2, (-0.1, 0.9), 0.1, "rendimento", "indicio"),
    (10, 2, (0.05, 0.3), 0.2, "entrega", "forte"),  # ≥ 15 p.p.
    (10, 2, (-0.05, 0.3), 0.1, "entrega", "fraca"),  # ≥ 8 p.p.
])
def test_faixas_de_confianca_nas_bordas(n, dias, iv, efeito, parte, esperado):
    assert e.confianca(n, dias, iv, efeito, parte) == esperado


def test_faltam():
    assert e.faltam(3, 2) == 2
    assert e.faltam(5, 1) == 1
    assert e.faltam(5, 2) is None
    assert K.MIN_GRUPO == 5 and K.MIN_DIAS == 2


def test_exibir_e_percentil():
    assert e.exibir(0.35, "entrega") == 35.0
    assert e.exibir(math.log(2.4), "rendimento") == 2.4
    assert e.percentil([1, 2, 3, 4, 5], 0.5) == 3
    assert e.percentil([1, 2], 0.9) == pytest.approx(1.9)
    assert e.jaccard({1, 2, 3, 4, 5}, {1, 2, 3, 4}) == pytest.approx(0.8)
