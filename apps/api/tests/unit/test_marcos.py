"""Marcos 1 h/24 h/7 d/30 d, engajamento e velocidade (spec 016, T063; research R15). Puro."""

import pytest

from sociman_api.metricas.consulta import (
    D7,
    H1,
    H24,
    Ponto,
    engajamento,
    marco,
    velocidade,
    vizinhas,
)


def p(idade_s: int, views: int | None, likes: int | None = 0, comments: int | None = 0,
      shares: int | None = 0) -> Ponto:
    return Ponto(idade_s, views, likes, comments, shares)


def _m(pontos, t, idade_atual, metrica="views"):
    return marco(*vizinhas(pontos, t), t, idade_atual, metrica)


def test_foto_exata_no_marco():
    m = _m([p(1800, 50), p(3600, 100), p(7200, 300)], H1, 9000)
    assert (m.valor, m.estimado, m.motivo) == (100, False, None)


def test_interpolacao_linear_na_idade():
    m = _m([p(3300, 130), p(4000, 200)], H1, 9000)
    assert m.valor == pytest.approx(160) and not m.estimado


def test_ancora_zero_e_estimado_quando_as_fotos_estao_longe():
    # vídeo de fora descoberto com 3 h: o marco de 1 h sai de (0,0)–(3h, 300)
    m = _m([p(3 * 3600, 300)], H1, 5 * 3600)
    assert m.valor == pytest.approx(100) and m.estimado


def test_estimado_so_acima_de_25_por_cento():
    assert not _m([p(3000, 0), p(3900, 90)], H1, 9000).estimado  # 900 s = 25% de 1 h
    assert _m([p(3000, 0), p(3901, 90)], H1, 9000).estimado


def test_ainda_nao():
    m = _m([p(3600, 100)], H24, 2 * 3600)
    assert (m.valor, m.motivo) == (None, "ainda_nao")


def test_sem_dado_e_ultima_foto_perto():
    # a coleta parou: sem foto depois de 7 d; a última a até 10% de 7 d vale
    perto = _m([p(D7 - int(0.1 * D7), 700)], D7, 10 * 24 * 3600)
    assert perto.valor == 700 and perto.motivo is None
    longe = _m([p(D7 - int(0.1 * D7) - 1, 700)], D7, 10 * 24 * 3600)
    assert (longe.valor, longe.motivo) == (None, "sem_dado")
    assert _m([], H1, 9000).motivo == "sem_dado"


def test_contagem_que_cai_nao_e_forcada_a_subir():
    m = _m([p(3000, 200), p(4200, 100)], H1, 9000)
    assert m.valor == pytest.approx(150)


def test_contador_omitido_vira_sem_dado():
    m = _m([p(3000, 10, likes=None), p(4200, 20, likes=None)], H1, 9000, "likes")
    assert m.motivo == "sem_dado"


def test_engajamento():
    assert engajamento(p(3600, 200, 10, 5, 5)) == pytest.approx(0.1)
    assert engajamento(p(3600, 0, 10, 5, 5)) == 0
    assert engajamento(p(3600, None)) is None
    assert engajamento(None) is None


def test_velocidade_com_menos_e_com_mais_de_24h():
    assert velocidade(p(2 * 3600, 400), None, None) == pytest.approx(200)
    pontos = [p(h * 3600, 100 * h) for h in range(1, 31)]
    ultima = pontos[-1]
    antes, depois = vizinhas(pontos, ultima.idade_s - H24)
    assert velocidade(ultima, antes, depois) == pytest.approx(100)
    # a idade − 24 h cai entre fotos: interpola
    esparsas = [p(3 * 3600, 300), p(9 * 3600, 900), p(30 * 3600, 3000)]
    antes, depois = vizinhas(esparsas, 6 * 3600)
    assert velocidade(esparsas[-1], antes, depois) == pytest.approx((3000 - 600) / 24)
    assert velocidade(None, None, None) is None
