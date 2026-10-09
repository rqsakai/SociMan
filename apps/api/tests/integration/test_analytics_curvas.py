"""Curvas (spec 019, US4, T036): pontos (idade_h, views) por vídeo, meia-vida interpolada entre
as fotos (vídeo com menos de 7 dias → null), limite de vídeos e quartis da medida por conta, com
cálculo de referência sobre a semeadura (SC-002)."""

import pytest

from integration.analytics_helpers import cena, local  # noqa: F401
from sociman_api.analytics import curvas


def test_pontos_e_meia_vida(cena):  # noqa: F811
    # Velho: publicado há 10 dias, 9 fotos diárias (24 h … 216 h) com views = 100·k.
    # Marco de 7 d = foto k = 7 → 700; metade = 350, entre 72 h (300) e 96 h (400) → 84 h.
    velho = cena.semear(videos=1, fotos=9, passo_h=24, inicio=local(10, 10))
    # Novo: 2 dias, 30 fotos horárias → meia-vida ainda não calculável.
    novo = cena.semear(videos=1, fotos=30, inicio=local(2, 10), serie_id=velho.serie_id)
    corpo = cena.ok("curvas", de=str(local(12).date()), ate=str(local(0).date()))
    por_id = {c["videoId"]: c for c in corpo["curvas"]}
    assert [c["videoId"] for c in corpo["curvas"]] == [str(novo.videos[0]),
                                                       str(velho.videos[0])]
    v = por_id[str(velho.videos[0])]
    assert v["pontos"] == [{"idadeH": 24.0 * k, "views": 100 * k} for k in range(1, 10)]
    assert v["meiaVidaH"] == pytest.approx(84.0)
    assert v["conta"] == "@atavernanerd" and v["contaId"] == cena.conta["id"]
    n = por_id[str(novo.videos[0])]
    assert len(n["pontos"]) == 30 and n["pontos"][0] == {"idadeH": 1.0, "views": 100}
    assert n["meiaVidaH"] is None


def test_meia_vida_pura():
    pontos = [(24.0, 300), (48.0, 600), (168.0, 1000)]
    # metade de 1000 = 500: entre 24 h (300) e 48 h (600) → 24 + 200·24/300 = 40 h
    assert curvas.meia_vida_h(pontos, 1000) == pytest.approx(40.0)
    # antes da 1ª foto, pela âncora (0, 0): metade de 400 = 200 → 24·200/300 = 16 h
    assert curvas.meia_vida_h(pontos, 400) == pytest.approx(16.0)
    assert curvas.meia_vida_h(pontos, None) is None
    assert curvas.meia_vida_h(pontos, 0) is None
    assert curvas.meia_vida_h([], 100) is None


def test_no_maximo_os_mais_recentes(cena, monkeypatch):  # noqa: F811
    monkeypatch.setattr(curvas, "MAX_CURVAS", 2)
    s = cena.semear(videos=3, fotos=3, inicio=local(4, 10))
    corpo = cena.ok("curvas")
    assert [c["videoId"] for c in corpo["curvas"]] == [str(s.videos[2]), str(s.videos[1])]
    assert corpo["contexto"]["postsNoPeriodo"] == 3


def test_distribuicao_por_conta(cena):  # noqa: F811
    # Medida h1 da principal: 100, 200, 300; da outra conta: 50
    cena.semear(videos=3, fotos=30, inicio=local(5, 10))
    outra = cena.segunda_conta("outraconta", outro_perfil=True)
    cena.semear(outra, videos=1, fotos=3, views_por_h=50, inicio=local(3, 10))
    corpo = cena.ok("curvas", medida="h1")
    dist = {d["rotulo"]: d for d in corpo["distribuicao"]}
    a = dist["@atavernanerd"]
    assert (a["min"], a["q1"], a["mediana"], a["q3"], a["max"]) == (100, 150, 200, 250, 300)
    assert a["amostra"] == {"n": 3, "minimo": 5, "suficiente": False, "faltam": 2}
    b = dist["@outraconta"]
    assert (b["min"], b["mediana"], b["max"]) == (50, 50, 50) and b["amostra"]["n"] == 1
    assert b["contaId"] == outra["id"]
    # com d7, todos aguardando: a conta aparece sem números
    d7 = {d["rotulo"]: d for d in cena.ok("curvas", medida="d7")["distribuicao"]}
    assert d7["@atavernanerd"]["mediana"] is None and d7["@atavernanerd"]["amostra"]["n"] == 0
