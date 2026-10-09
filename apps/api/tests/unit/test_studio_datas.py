"""Datas e ano do Studio (spec 020, T009; research R3): o caso do arquivo real (25/09–01/10 com o
epoch 1790891174), a virada de ano pelo nome do ZIP e pela dedução, o nome que não bate, fora de
ordem, hoje, sufixo " (1)" e handle com `.` e `_`."""

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from sociman_api.metricas.studio import datas

TZ = ZoneInfo("America/Sao_Paulo")


def _lidas(*textos: str) -> list[datas.DataLida]:
    out = [datas.ler_data(t) for t in textos]
    assert all(out), textos
    return out  # type: ignore[return-value]


def _seq(de: date, n: int) -> list[str]:
    from datetime import timedelta

    meses = ("January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December")
    return [f"{meses[(de + timedelta(days=k)).month - 1]} {(de + timedelta(days=k)).day}"
            for k in range(n)]


def test_nome_do_zip_do_caso_real():
    nome = datas.nome_zip("Overview_2026-09-25_1790891174_atavernanerd.zip", TZ)
    assert nome == datas.NomeZip("visao_geral", "atavernanerd", date(2026, 9, 25),
                                 date(2026, 10, 1))
    dias = datas.pelo_nome(_lidas(*_seq(date(2026, 9, 25), 7)), nome.inicio, nome.fim)
    assert dias == [date(2026, 9, 25 + k) for k in range(6)] + [date(2026, 10, 1)]


@pytest.mark.parametrize(("nome", "esperado"), [
    ("Followers_meus.queridinhos_10.zip", datas.NomeZip("seguidores", "meus.queridinhos_10")),
    ("Followers_ContaTeste (1).zip", datas.NomeZip("seguidores", "contateste")),
    ("Overview_2026-09-25_1790891174_conta_x (2).zip",
     datas.NomeZip("visao_geral", "conta_x", date(2026, 9, 25), date(2026, 10, 1))),
    ("Content_conta.zip", datas.NomeZip("outra", "conta", outra="Content")),
    ("dados.zip", None), ("Overview_2026-13-01_1790891174_x1.zip", None),
])
def test_nomes_de_zip(nome, esperado):
    assert datas.nome_zip(nome, TZ) == esperado


@pytest.mark.parametrize(("texto", "lida"), [
    ("September 25", datas.DataLida(9, 25)), ("Sep 25", datas.DataLida(9, 25)),
    ("Sept 25", datas.DataLida(9, 25)), ("October 1", datas.DataLida(10, 1)),
    ("25 de setembro", datas.DataLida(9, 25)), ("setembro 25", datas.DataLida(9, 25)),
    ("25 set", datas.DataLida(9, 25)), ("1 de março", datas.DataLida(3, 1)),
    ("2026-09-25", datas.DataLida(9, 25, 2026)), ("25/09/2026", datas.DataLida(9, 25, 2026)),
    ("February 29", datas.DataLida(2, 29)),
])
def test_formatos_de_data(texto, lida):
    assert datas.ler_data(texto) == lida


@pytest.mark.parametrize("texto", ["Smarch 3", "September 31", "2026-02-30", "25/13/2026",
                                   "ontem", "", "September"])
def test_datas_invalidas(texto):
    assert datas.ler_data(texto) is None


def test_virada_de_ano_pelo_nome_do_zip():
    lidas = _lidas("December 30", "December 31", "January 1", "January 2")
    dias = datas.pelo_nome(lidas, date(2025, 12, 30), date(2026, 1, 2))
    assert dias == [date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)]


def test_virada_de_ano_pela_deducao():
    lidas = _lidas("Dec 30", "Dec 31", "Jan 1", "Jan 2")
    dias = datas.deduzir(lidas, date(2026, 1, 3))
    assert dias == [date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)]


def test_deducao_usa_a_ocorrencia_mais_recente_que_nao_passa_de_hoje():
    assert datas.deduzir(_lidas("September 30", "October 1"), date(2026, 10, 5)) == [
        date(2026, 9, 30), date(2026, 10, 1)]
    # "October 6" ainda não chegou em 2026: é o de 2025
    assert datas.deduzir(_lidas("October 5", "October 6"), date(2026, 10, 5)) == [
        date(2025, 10, 5), date(2025, 10, 6)]
    # hoje vale (o chamador ignora a linha de hoje)
    assert datas.deduzir(_lidas("October 5"), date(2026, 10, 5)) == [date(2026, 10, 5)]


@pytest.mark.parametrize(("inicio", "fim", "motivo"), [
    (date(2026, 9, 24), date(2026, 10, 1), "o 1º dia é outro"),
    (date(2026, 9, 25), date(2026, 10, 2), "o último dia é outro"),
])
def test_nome_do_zip_que_nao_bate(inicio, fim, motivo):
    with pytest.raises(datas.DatasErro, match=motivo):
        datas.pelo_nome(_lidas(*_seq(date(2026, 9, 25), 7)), inicio, fim)


@pytest.mark.parametrize("textos", [
    ("September 25", "September 27", "September 26"),
    ("September 25", "September 25"),
    ("September 25", "March 3"),  # salto grande demais (o Studio exporta todos os dias)
])
def test_fora_de_ordem(textos):
    with pytest.raises(datas.DatasErro):
        datas.deduzir(_lidas(*textos), date(2026, 10, 5))


def test_com_ano_fora_de_ordem_e_salto():
    assert datas.com_ano(_lidas("2026-09-25", "2026-09-27")) == [date(2026, 9, 25),
                                                                date(2026, 9, 27)]
    with pytest.raises(datas.DatasErro):
        datas.com_ano(_lidas("2026-09-25", "2026-09-24"))
    with pytest.raises(datas.DatasErro):
        datas.com_ano(_lidas("2024-09-25", "2026-09-24"))


def test_29_de_fevereiro_sem_ano_bissexto():
    with pytest.raises(datas.DatasErro):
        datas.pelo_nome(_lidas("February 28", "February 29"), date(2026, 2, 28),
                        date(2026, 3, 1))
    assert datas.deduzir(_lidas("February 28", "February 29"), date(2026, 10, 5)) == [
        date(2024, 2, 28), date(2024, 2, 29)]


def test_mesmo_mapa_da_visao_geral():
    vg = _lidas("December 31", "January 1", "January 2")
    anos = [date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)]
    assert datas.mesmo_mapa(_lidas("January 1", "January 2"), vg, anos) == anos[1:]
    assert datas.mesmo_mapa(_lidas("January 3"), vg, anos) is None


def test_handle_normalizado():
    assert datas.normalizar_handle(" @AtavernaNerd ") == "atavernanerd"


# ---- spec 022 ----

def test_atividade_dias_distintos_por_dia_e_por_hora_com_virada():
    por_dia = [datas.ler_data(t) for t in ("Dec 31", "Dec 31", "Jan 1", "Jan 1")]
    por_hora = [datas.ler_data(t) for t in ("Dec 31", "Jan 1", "Dec 31", "Jan 1")]
    for ds in (por_dia, por_hora):
        distintos = datas.dias_distintos(ds)
        assert [(d.mes, d.dia) for d in distintos] == [(12, 31), (1, 1)]
        assert datas.deduzir(distintos, date(2027, 1, 5)) == [date(2026, 12, 31),
                                                              date(2027, 1, 1)]


@pytest.mark.parametrize("nome", ["Viewers_contateste.zip", "Viewers_contateste (1).zip"])
def test_nome_do_zip_de_espectadores(nome):
    n = datas.nome_zip(nome, TZ)
    assert n is not None and (n.secao, n.handle) == ("espectadores", "contateste")
