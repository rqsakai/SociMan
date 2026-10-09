"""Contas, perfis e redes (spec 019, US5, T040): tabela por conta e por perfil (indicadores da
visão geral), radar com 2 contas (índice = valor ÷ média × 100, corte em 200 com `acima`), com
1 conta `radar = null` e o motivo, anônimas fora, e o filtro de conta. Cálculo de referência
sobre a semeadura (SC-002)."""

import pytest

from integration.analytics_helpers import cena, local  # noqa: F401
from sociman_api.analytics import contas
from sociman_api.auth.deps import Actor
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import Serie


def _duas(c):
    """A (@atavernanerd): 2 vídeos (há 3 e 2 dias), views 100·k e 200·k nas fotos k = 1..3;
    B (@outraconta, outro perfil): 1 vídeo (há 2 dias), views 50·k. Em toda foto k: likes 10·k,
    comments k, shares k. Seguidores: 1000 + dia (A: 4 fotos, B: 3)."""
    a = c.semear(videos=2, fotos=3, inicio=local(3, 10))
    outra = c.segunda_conta("outraconta", outro_perfil=True)
    b = c.semear(outra, videos=1, fotos=3, views_por_h=50, inicio=local(2, 10))
    return a, outra, b


def _ind(linha) -> dict:
    return {i["chave"]: i for i in linha["indicadores"]}


def _eixos(r) -> dict:
    return {e["chave"]: e for e in r["eixos"]}


def test_tabela_por_conta_e_por_perfil(cena):  # noqa: F811
    _duas(cena)
    corpo = cena.ok("contas", medida="h1")
    linhas = {c["rotulo"]: c for c in corpo["contas"]}
    assert list(linhas) == ["@atavernanerd", "@outraconta"]
    a = _ind(linhas["@atavernanerd"])
    assert a["views"]["valor"] == 300 + 600 and a["likes"]["valor"] == 60
    assert a["engajamento"]["valor"] == pytest.approx(72 / 900)
    assert a["seguidores"]["valor"] == 3 and a["posts"]["valor"] == 2
    assert a["mediana_post"]["valor"] == 150
    assert a["views"]["anterior"] is None and a["views"]["variacaoPct"] is None
    b = _ind(linhas["@outraconta"])
    assert (b["views"]["valor"], b["posts"]["valor"], b["seguidores"]["valor"]) == (150, 1, 2)
    assert linhas["@atavernanerd"]["perfil"]["id"] == cena.perfil["id"]
    assert linhas["@atavernanerd"]["rede"] == "tiktok"
    perfis = {p["perfil"]["name"]: _ind(p) for p in corpo["perfis"]}
    assert len(perfis) == 2 and perfis["Outro Perfil"]["views"]["valor"] == 150
    assert perfis[linhas["@atavernanerd"]["perfil"]["name"]]["posts"]["valor"] == 2


def test_radar_com_duas_contas(cena):  # noqa: F811
    _duas(cena)
    corpo = cena.ok("contas", medida="h1")
    assert corpo["radarMotivo"] is None
    radar = {r["rotulo"]: _eixos(r) for r in corpo["radar"]}
    a, b = radar["@atavernanerd"], radar["@outraconta"]
    # views por post (mediana h1): A 150, B 50 → média 100
    assert (a["views_por_post"]["valor"], a["views_por_post"]["media"]) == (150, 100)
    assert a["views_por_post"]["indice"] == pytest.approx(150)
    assert b["views_por_post"]["indice"] == pytest.approx(50)
    # engajamento: A 72/900, B 36/150
    media = (72 / 900 + 36 / 150) / 2
    assert a["engajamento"]["indice"] == pytest.approx(72 / 900 / media * 100)
    # frequência: 2/7 e 1/7 posts por dia
    assert a["frequencia"]["valor"] == pytest.approx(2 / 7)
    assert a["frequencia"]["indice"] == pytest.approx(2 / 1.5 * 100)
    # crescimento: 3/1000 e 2/1000
    assert a["crescimento"]["valor"] == pytest.approx(0.003)
    assert b["crescimento"]["indice"] == pytest.approx(0.002 / 0.0025 * 100)
    # velocidade 1 h = mediana do marco h1, mesmo com outra medida escolhida
    v = {r["rotulo"]: _eixos(r) for r in cena.ok("contas", medida="h24")["radar"]}
    assert v["@atavernanerd"]["velocidade_1h"]["valor"] == 150
    # acima da mediana geral (mediana de 100, 200, 50 = 100): A 1/2, B 0 → A no teto exato
    assert a["acima_mediana"]["valor"] == 0.5 and b["acima_mediana"]["valor"] == 0
    assert a["acima_mediana"]["indice"] == pytest.approx(200) and not a["acima_mediana"]["acima"]
    assert b["acima_mediana"]["indice"] == 0


def test_eixo_corta_em_200():
    e = contas.eixo("engajamento", 3.0, 1.0)
    assert (e.indice, e.acima) == (200, True)
    assert contas.eixo("engajamento", None, 1.0).indice is None
    assert contas.eixo("engajamento", 1.0, 0).indice is None


def test_uma_conta_sem_radar(cena):  # noqa: F811
    cena.semear(videos=2, fotos=3, inicio=local(3, 10))
    corpo = cena.ok("contas")
    assert corpo["radar"] is None and "pelo menos 2 contas" in corpo["radarMotivo"]
    assert [c["rotulo"] for c in corpo["contas"]] == ["@atavernanerd"]


def test_anonima_fora_da_tabela_e_do_radar(cena):  # noqa: F811
    _, _, b = _duas(cena)
    anonimizar.serie(cena.db, cena.db.get(Serie, b.serie_id),
                     Actor(kind="user", user_id=cena.dono.id))
    cena.db.commit()
    corpo = cena.ok("contas")
    assert [c["rotulo"] for c in corpo["contas"]] == ["@atavernanerd"]
    assert len(corpo["perfis"]) == 1
    assert corpo["radar"] is None
    assert corpo["contexto"]["postsNoPeriodo"] == 3  # a anônima continua nos totais


def test_filtro_de_conta(cena):  # noqa: F811
    _, outra, _ = _duas(cena)
    corpo = cena.ok("contas", medida="h1", contaId=outra["id"])
    assert [c["rotulo"] for c in corpo["contas"]] == ["@outraconta"]
    # o radar da conta filtrada continua contra a média das contas
    [r] = corpo["radar"]
    assert r["contaId"] == outra["id"]
    assert _eixos(r)["views_por_post"]["media"] == 100
    assert corpo["contexto"]["postsNoPeriodo"] == 1
    # sem post no período: sem radar
    longe = cena.ok("contas", contaId=outra["id"], de=str(local(40).date()),
                    ate=str(local(30).date()))
    assert longe["contas"] == [] and longe["radar"] is None
