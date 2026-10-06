"""Visão geral (spec 019, US1, T023): os 6 indicadores com o anterior e a variação, "sem base de
comparação", a série diária por conta em SP, os principais por views ganhas, a anônima rotulada
e a medida com "aguardando". Cálculo de referência sobre a semeadura (`semear`: a foto k do
i-ésimo vídeo tem views = views_por_h·k·(i+1), likes = 10k, comments = shares = k; a conta tem
uma foto por dia com seguidores = 1000 + d)."""

import pytest

from integration.analytics_helpers import cena, local  # noqa: F401
from sociman_api.auth.deps import Actor
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import Serie


def _ind(corpo) -> dict:
    return {i["chave"]: i for i in corpo["indicadores"]}


def _cenario(c):
    """Conta A: 2 vídeos (D−4 e D−3 às 10:00), 30 fotos horárias. Conta B (outro perfil): 1
    vídeo em D−3 às 12:00, views 10·k. Período: o dia D−3; anterior: D−4."""
    a = c.semear(videos=2, fotos=30, inicio=local(4, 10))
    outra = c.segunda_conta("contab", outro_perfil=True)
    b = c.semear(outra, videos=1, fotos=30, inicio=local(3, 12), views_por_h=10)
    return a, b, outra


def test_indicadores_contra_o_anterior(cena):  # noqa: F811
    _cenario(cena)
    dia = str(local(3).date())
    corpo = cena.ok("visao-geral", de=dia, ate=dia)
    ind = _ind(corpo)
    assert list(ind) == ["views", "likes", "engajamento", "seguidores", "posts", "mediana_post"]
    # D−3: v0 vai de k=13 (1300) a k=30 (3000); v1 nasce e chega a k=13 (2600); B chega a k=11.
    # D−4: só v0, até k=13.
    assert (ind["views"]["valor"], ind["views"]["anterior"]) == (1700 + 2600 + 110, 1300)
    assert ind["views"]["variacaoPct"] == pytest.approx((4410 - 1300) / 1300)
    assert ind["views"]["n"] == 3
    assert (ind["likes"]["valor"], ind["likes"]["anterior"]) == (170 + 130 + 110, 130)
    interacoes = 410 + 2 * (17 + 13 + 11)
    assert ind["engajamento"]["valor"] == pytest.approx(interacoes / 4410)
    assert ind["engajamento"]["anterior"] == pytest.approx((130 + 13 + 13) / 1300)
    # seguidores: A 1000 → 1001 no dia; B só tem a 1ª foto no dia (0); anterior: A 0 → sem base
    assert (ind["seguidores"]["valor"], ind["seguidores"]["n"]) == (1, 2)
    assert ind["seguidores"]["anterior"] == 0 and ind["seguidores"]["variacaoPct"] is None
    assert (ind["posts"]["valor"], ind["posts"]["anterior"], ind["posts"]["variacaoPct"]) == (
        2, 1, 1.0)
    # mediana em 24 h: D−3 = mediana(4800, 240); D−4 = 2400
    assert (ind["mediana_post"]["valor"], ind["mediana_post"]["anterior"]) == (2520, 2400)
    assert ind["mediana_post"]["variacaoPct"] == pytest.approx(0.05)


def test_sem_base_de_comparacao(cena):  # noqa: F811
    cena.semear(videos=2, fotos=30, inicio=local(4, 10))
    ind = _ind(cena.ok("visao-geral"))  # 7 dias; o anterior não tem foto nem post
    for chave in ("views", "likes", "engajamento", "mediana_post"):
        assert ind[chave]["anterior"] is None and ind[chave]["variacaoPct"] is None, chave
    assert ind["views"]["valor"] == 3000 + 6000 and ind["likes"]["valor"] == 600
    assert ind["engajamento"]["valor"] == pytest.approx((600 + 60 + 60) / 9000)
    assert ind["seguidores"]["valor"] == 3  # 1ª foto do período (1000) → a última (1003)
    assert (ind["posts"]["valor"], ind["posts"]["anterior"], ind["posts"]["variacaoPct"]) == (
        2, 0, None)
    assert ind["mediana_post"]["valor"] == 3600


def test_serie_diaria_por_conta(cena):  # noqa: F811
    _, _, outra = _cenario(cena)
    de, ate = local(4).date(), local(2).date()
    corpo = cena.ok("visao-geral", de=str(de), ate=str(ate))
    serie = {d["dia"]: {c["rotulo"]: c["views"] for c in d["porConta"]}
             for d in corpo["serieDiaria"]}
    assert list(serie) == [str(local(k).date()) for k in (4, 3, 2)]
    assert serie[str(local(4).date())] == {"@atavernanerd": 1300, "@contab": 0}
    assert serie[str(local(3).date())] == {"@atavernanerd": 4300, "@contab": 110}
    # D−2: v1 de 2600 até k=30 (6000); B de 110 até k=30 (300)
    assert serie[str(local(2).date())] == {"@atavernanerd": 3400, "@contab": 190}
    ordem = [c["contaId"] for c in corpo["serieDiaria"][0]["porConta"]]
    assert ordem == sorted([cena.conta["id"], outra["id"]])


def test_principais_por_views_ganhas(cena):  # noqa: F811
    a, b, _ = _cenario(cena)
    dia = str(local(3).date())
    corpo = cena.ok("visao-geral", de=dia, ate=dia)
    top = [(p["videoId"], p["viewsPeriodo"]) for p in corpo["principais"]]
    assert top == [(str(a.videos[1]), 2600), (str(a.videos[0]), 1700), (str(b.videos[0]), 110)]
    p = corpo["principais"][0]
    assert p["rotuloConta"] == "@atavernanerd" and p["tituloCurto"] == "Post de teste #fyp"
    assert p["medida"] == {"valor": 4800, "estimado": False, "aguardando": False}
    assert p["viewsAtual"] == 6000 and p["publicadoEm"].endswith("-03:00")
    # o ranking da 016: publicados no dia, por views totais
    assert corpo["ranking"]["total"] == 2
    assert [v["id"] for v in corpo["ranking"]["items"]] == [str(a.videos[1]), str(b.videos[0])]
    assert [i["regra"] for i in corpo["insights"]] == [
        "horario", "dia", "duracao", "canal", "hashtag", "destaque"]
    assert all(i["pendente"] for i in corpo["insights"])  # 2 posts: amostra pequena


def test_anonima_rotulada(cena):  # noqa: F811
    _, b, _ = _cenario(cena)
    anonimizar.serie(cena.db, cena.db.get(Serie, b.serie_id), Actor(kind="user",
                                                                     user_id=cena.dono.id))
    cena.db.commit()
    dia = str(local(3).date())
    corpo = cena.ok("visao-geral", de=dia, ate=dia)
    contas = corpo["serieDiaria"][0]["porConta"]
    anonima = [c for c in contas if c["contaId"] is None]
    assert len(anonima) == 1 and anonima[0]["rotulo"].startswith("Conta anônima ")
    assert anonima[0]["views"] == 110 and contas[-1] == anonima[0]  # anônimas no fim
    p = next(p for p in corpo["principais"] if p["contaId"] is None)
    assert p["rotuloConta"] == anonima[0]["rotulo"] and p["link"] is None
    # filtrar pela conta tira a anônima
    so_a = cena.ok("visao-geral", de=dia, ate=dia, contaId=cena.conta["id"])
    assert _ind(so_a)["views"]["valor"] == 4300


def test_medida_e_aguardando(cena):  # noqa: F811
    cena.semear(videos=2, fotos=30, inicio=local(4, 10))
    d7 = cena.ok("visao-geral", medida="d7")
    assert d7["contexto"]["aguardando"] == 2
    assert _ind(d7)["mediana_post"]["valor"] is None and _ind(d7)["mediana_post"]["n"] == 0
    assert _ind(cena.ok("visao-geral", medida="h1"))["mediana_post"]["valor"] == 150
    assert all(not p["medida"]["aguardando"] for p in cena.ok("visao-geral")["principais"])
    assert all(p["medida"]["aguardando"] for p in d7["principais"])


def test_periodo_vazio(cena):  # noqa: F811
    cena.semear(videos=1, fotos=3, inicio=local(4, 10))
    vazio = cena.ok("visao-geral", de=str(local(60).date()), ate=str(local(50).date()))
    assert all(i["valor"] is None for i in vazio["indicadores"]
               if i["chave"] not in ("posts",))
    assert _ind(vazio)["posts"]["valor"] == 0 and vazio["principais"] == []
    assert len(vazio["serieDiaria"]) == 11
    assert vazio["ranking"]["items"] == [] and vazio["ranking"]["total"] == 0
