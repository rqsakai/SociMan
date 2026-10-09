"""Leitura das seções de público (spec 022, T011; research R1, R4 e R14): % em cada formato e
misturada, somas de gênero e territórios, rótulos, hora, (dia, hora) repetido, data da foto,
`undefined` → sem dado e o arquivo só com o cabeçalho."""

from datetime import date

import pytest
from integration.studio_helpers import csv_bytes

from sociman_api.metricas.studio import formato, publico


def _ler(cab, linhas, nome="x.csv"):
    return formato.ler(nome, csv_bytes(cab, linhas))


@pytest.mark.parametrize(("brutos", "esperado"), [
    (["52%", "48%"], [52.0, 48.0]),
    (["52", "48"], [52.0, 48.0]),
    (["52.3", "47.7"], [52.3, 47.7]),
    (["52,3", "47,7"], [52.3, 47.7]),
    (["0.52", "0.48"], [52.0, 48.0]),
    (["undefined", "48%"], [None, 48.0]),
    (["", "1"], [None, 100.0]),  # um valor só ≤ 1: lido como fração
])
def test_pcts_validas(brutos, esperado):
    valores, motivo = publico.pcts(brutos)
    assert motivo is None
    assert valores == esperado


@pytest.mark.parametrize(("brutos", "motivo"), [
    (["52%", "48"], "misturados"), (["abc"], "não é uma porcentagem"),
    (["101%"], "acima de 100"), (["1.234,5"], "não é uma porcentagem")])
def test_pcts_recusadas(brutos, motivo):
    valores, m = publico.pcts(brutos)
    assert valores == [] and motivo in m


def _genero(*itens):
    return publico.ler_distribuicao(_ler(("Gender", "Distribution"), itens))


def test_genero_soma_80_100_101_5():
    itens, problemas = _genero(("Female", "61%"), ("Male", "37.5%"), ("Other", "1.5%"))
    assert problemas == [] and [(i.rotulo, i.pct) for i in itens] == [
        ("feminino", 61.0), ("masculino", 37.5), ("outro", 1.5)]
    itens, problemas = _genero(("Female", "61%"), ("Male", "40.5%"))
    assert problemas == [] and len(itens) == 2  # 101,5 cabe na tolerância de 2 p.p.
    itens, problemas = _genero(("Female", "40%"), ("Male", "40%"))
    assert itens == [] and "soma do gênero dá 80%" in problemas[0].motivo


def test_territorios_soma_100_1_e_99():
    lt = _ler(("Top territories", "Distribution"), [("BR", "90%"), ("PT", "9%")])
    assert publico.ler_distribuicao(lt)[1] == []
    lt = _ler(("Top territories", "Distribution"), [("BR", "95%"), ("PT", "5.1%")])
    assert publico.ler_distribuicao(lt)[1] == []  # 100,1 cabe na tolerância
    lt = _ler(("Top territories", "Distribution"), [("BR", "95%"), ("PT", "8%")])
    [p] = publico.ler_distribuicao(lt)[1]
    assert "mais de 100%" in p.motivo


def test_rotulo_desconhecido_repetido_e_negativo():
    _, ps = _genero(("Female", "50%"), ("Robô", "50%"))
    assert [(p.linha, p.motivo) for p in ps] == [(3, "gênero desconhecido")]
    _, ps = _genero(("Female", "50%"), ("Mulher", "50%"))
    assert ps[0].motivo.startswith("rótulo repetido (linha 2)")
    _, ps = _genero(("Female", "-5%"), ("Male", "105%"))
    assert ps[0].motivo == "porcentagem negativa"
    lt = _ler(("Top territories", "Distribution"), [("BR", "50%"), ("br", "40%")])
    assert publico.ler_distribuicao(lt)[1][0].motivo.startswith("rótulo repetido")


@pytest.mark.parametrize(("bruto", "esperado"), [
    ("0", 0), ("23", 23), ("05", 5), ("5:00", 5), ("05:00", 5), ("24", None), ("x", None),
    ("-1", None), ("5:30", None)])
def test_hora(bruto, esperado):
    assert publico.hora(bruto) == esperado


def test_atividade_dia_hora_repetido():
    cab = ("Date", "Hour", "Active followers")
    lt = _ler(cab, [("May 1", "5", "3"), ("May 1", "05:00", "3"), ("May 1", "6", "4")])
    linhas, ps = publico.ler_atividade(lt)
    assert ps == [] and [(x.hora, x.ativos) for x in linhas] == [(5, 3), (6, 4)]
    lt = _ler(cab, [("May 1", "5", "3"), ("May 1", "5", "9")])
    _, ps = publico.ler_atividade(lt)
    assert ps[0].motivo == "dia e hora repetidos (linha 2) com números diferentes"
    lt = _ler(cab, [("May 1", "24", "3")])
    assert publico.ler_atividade(lt)[1][0].motivo == "hora fora de 0 a 23"


def test_data_foto():
    hoje = date(2026, 10, 2)
    assert publico.data_foto([date(2026, 9, 25), date(2026, 10, 1)], hoje) == (
        date(2026, 10, 2), "historico")  # o caso real: 01/10 → 02/10
    assert publico.data_foto([date(2026, 10, 2)], hoje) == (hoje, "historico")  # limitado a hoje
    assert publico.data_foto([date(2026, 9, 20)], hoje) == (date(2026, 9, 21), "historico")
    assert publico.data_foto(None, hoje) == (hoje, "importacao")


def test_undefined_vira_sem_dado_so_no_publico():
    lt = _ler(("Date", "Total Viewers", "New Viewers", "Returning Viewers"),
              [("May 1", "undefined", "0", "0"), ("May 2", "104", "", "0")])
    assert lt.problemas == [] and lt.sem_dado == 2
    assert lt.linhas[0].valores == {"espectadores": None, "espectadores_novos": 0,
                                    "espectadores_recorrentes": 0}
    vg = _ler(("Date", "Video Views"), [("May 1", "undefined")])
    assert vg.problemas[0].motivo == formato.MOTIVO_NUMERO  # a 020 não muda


@pytest.mark.parametrize("cab", [("Gender", "Distribution"), ("Top territories", "Distribution"),
                                 ("Date", "Hour", "Active followers"),
                                 ("Date", "Total Viewers", "New Viewers", "Returning Viewers")])
def test_so_cabecalho_e_vazia(cab):
    lt = _ler(cab, [])
    assert lt.vazia and lt.linhas == [] and lt.problemas == []


def test_provisorios_listados():
    itens = publico.provisorios()
    assert any("homem" in i for i in itens) and any("0.52" in i for i in itens)
    assert publico.FUSO_ATIVIDADE is None and publico.TOLERANCIA_GENERO == 2.0
