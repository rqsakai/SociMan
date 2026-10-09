"""O que funciona (spec 019, US3, T032): dispersões duração/gancho/score com ρ de referência
(sem ρ abaixo de 8), canais-fonte com direito, lift de hashtags normalizadas (n ≥ 5), modos,
padrões vindos de `envios.config` e `excluidosSemVinculo`. Medida: 1 h (= `views_por_h`)."""

import pytest

from integration.analytics_helpers import CONFIG, cena, local  # noqa: F401
from sociman_api.canais.models import CanalDireito
from sociman_api.conteudos.models import Modo

# score fora de ordem: postos [3,1,4,2,8,6,7,5] contra 1..8 → Σd² = 28
SCORES = (30, 10, 40, 20, 80, 60, 70, 50)
RHO_SCORE = 1 - 6 * 28 / (8 * 63)


def _cenario(c, vinculados: int = 8):
    """`vinculados` posts ligados (j = 0..7: 1 h = 100·(j+1), duração 10·(j+1) s, gancho com
    20 − j caracteres, score de SCORES): canal A (parceiro) em j < 5 e B (sem acordo) no resto;
    lembrete em j < 6 e rascunho no resto; o j = 7 com outro padrão de corte. Hashtags do
    destino: "Marvel" em j < 5, "Ação" em j ≥ 4, "rara" em j < 2. Mais 2 posts fora do SociMan:
    1 h = 50 com "#ação #fyp" e 1 h = 60 com "#MARVEL"."""
    a = c.canal(CanalDireito.parceiro, "Canal A")
    b = c.canal(CanalDireito.sem_acordo, "Canal B")
    serie = None
    ids = []
    for j in range(vinculados):
        s = c.semear(videos=1, fotos=2, inicio=local(3, j), views_por_h=100 * (j + 1),
                     duracao=10 * (j + 1), serie_id=serie)
        serie = s.serie_id
        [vid] = s.videos
        tags = (["Marvel"] if j < 5 else []) + (["Ação"] if j >= 4 else []) + \
            (["rara"] if j < 2 else [])
        config = {**CONFIG, "clip_min_s": 30, "clip_max_s": 90, "layout": "split"} \
            if j == 7 else None
        c.vincular(vid, canal=a if j < 5 else b,
                   modo=Modo.lembrete if j < 6 else Modo.criar_rascunho, hashtags=tags,
                   score=SCORES[j], gancho="x" * (20 - j), config=config)
        ids.append(vid)
    for hora, views, legenda in ((9, 50, "Teste #ação #fyp"), (10, 60, "Olha #MARVEL")):
        c.semear(videos=1, fotos=2, inicio=local(2, hora), views_por_h=views, legenda=legenda,
                 serie_id=serie)
    return ids, a, b


def test_dispersoes_com_correlacao(cena):  # noqa: F811
    ids, _, _ = _cenario(cena)
    corpo = cena.ok("o-que-funciona", medida="h1")
    d = corpo["dispersoes"]
    dur = d["duracao"]
    assert [(p["x"], p["y"]) for p in dur["pontos"]] == [
        (10.0 * (j + 1), 100.0 * (j + 1)) for j in range(8)]
    assert [p["videoId"] for p in dur["pontos"]] == [str(i) for i in ids]
    assert dur["pontos"][0]["tituloCurto"] == "Post de teste #fyp"
    assert dur["pontos"][0]["conta"] == "@atavernanerd" and not dur["pontos"][0]["estimado"]
    # o id da conta vai no ponto, para a SPA pintar pela cor fixa da conta (FR-006)
    assert {p["contaId"] for k in ("duracao", "gancho", "score") for p in d[k]["pontos"]} == \
        {str(cena.conta["id"])}
    assert dur["correlacao"] == {"rho": pytest.approx(1), "leitura": "forte positiva",
                                 "amostra": {"n": 8, "minimo": 8, "suficiente": True,
                                             "faltam": 0}}
    assert d["gancho"]["correlacao"]["rho"] == pytest.approx(-1)
    assert d["gancho"]["correlacao"]["leitura"] == "forte negativa"
    assert [p["x"] for p in d["gancho"]["pontos"]] == [20.0 - j for j in range(8)]
    assert d["score"]["correlacao"]["rho"] == pytest.approx(RHO_SCORE)
    assert d["score"]["correlacao"]["leitura"] == "forte positiva"
    assert corpo["excluidosSemVinculo"] == 2


def test_abaixo_de_8_so_os_pontos(cena):  # noqa: F811
    _cenario(cena, vinculados=7)
    d = cena.ok("o-que-funciona", medida="h1")["dispersoes"]["duracao"]
    assert len(d["pontos"]) == 7
    assert d["correlacao"] == {"rho": None, "leitura": None, "amostra": {
        "n": 7, "minimo": 8, "suficiente": False, "faltam": 1}}


def test_canais_com_direito_e_lift(cena):  # noqa: F811
    _, a, b = _cenario(cena)
    canais = cena.ok("o-que-funciona", medida="h1")["canais"]
    # geral dos vinculados = mediana(100..800) = 450; B (n = 3) sem lift
    assert [c["rotulo"] for c in canais] == ["Canal B", "Canal A"]
    cb, ca = canais
    assert (cb["chave"], cb["n"], cb["mediana"], cb["lift"], cb["direito"]) == (
        str(b.id), 3, 700, None, "sem_acordo")
    assert cb["amostra"]["suficiente"] is False and cb["amostra"]["faltam"] == 2
    assert (ca["chave"], ca["n"], ca["mediana"], ca["direito"]) == (str(a.id), 5, 300,
                                                                      "parceiro")
    assert ca["lift"] == pytest.approx(300 / 450)


def test_lift_de_hashtags_normalizadas(cena):  # noqa: F811
    _cenario(cena)
    tags = cena.ok("o-que-funciona", medida="h1")["hashtags"]
    # geral (10 posts) = mediana(50, 60, 100..800) = 350
    # #acao: j = 4..7 (500..800) + o fora com 50 → 600; #fyp: os 8 + o fora com 50 → 400;
    # #marvel: j = 0..4 + o fora com 60 → 250; #rara (n = 2) fica de fora
    assert [(t["rotulo"], t["n"]) for t in tags] == [("#acao", 5), ("#fyp", 9), ("#marvel", 6)]
    assert [t["lift"] for t in tags] == [pytest.approx(600 / 350), pytest.approx(400 / 350),
                                         pytest.approx(250 / 350)]
    assert tags[0]["chave"] == "acao" and all(t["direito"] is None for t in tags)


def test_modos_e_padroes(cena):  # noqa: F811
    _cenario(cena)
    corpo = cena.ok("o-que-funciona", medida="h1")
    modos = {m["chave"]: m for m in corpo["modos"]}
    assert set(modos) == {"lembrete", "criar_rascunho"}
    lembrete, rascunho = modos["lembrete"], modos["criar_rascunho"]
    assert (lembrete["rotulo"], lembrete["n"], lembrete["mediana"]) == ("Lembrete", 6, 350)
    assert lembrete["lift"] == pytest.approx(350 / 450)
    # engajamento da última foto (k = 2): (20 + 2 + 2) / (2·views_por_h) = 12 / views_por_h
    assert lembrete["engajamento"] == pytest.approx((12 / 300 + 12 / 400) / 2)
    assert (rascunho["n"], rascunho["mediana"], rascunho["lift"]) == (2, 750, None)
    padroes = {p["rotulo"]: (p["n"], p["mediana"]) for p in corpo["padroes"]}
    assert padroes == {"15–60 s · auto": (7, 400), "30–90 s · split": (1, 800)}
    assert [p["rotulo"] for p in corpo["padroes"]] == ["30–90 s · split", "15–60 s · auto"]


def test_sem_vinculo_fica_fora_das_analises_de_corte(cena):  # noqa: F811
    cena.semear(videos=3, fotos=2, inicio=local(3, 9))
    corpo = cena.ok("o-que-funciona", medida="h1")
    assert corpo["excluidosSemVinculo"] == 3
    assert all(corpo["dispersoes"][k]["pontos"] == [] for k in ("duracao", "gancho", "score"))
    assert corpo["canais"] == corpo["modos"] == corpo["padroes"] == []
