"""Leitura dos CSVs do Studio (spec 020, T009; research R1): cabeçalhos en e pt-BR, ordem das
colunas, opcional ausente, desconhecida ignorada, números, dias repetidos e seções erradas."""

import pytest
from integration.studio_helpers import csv_bytes, csv_overview, csv_seguidores, overview_dias

from sociman_api.errors import ApiError
from sociman_api.metricas.studio import formato


def _ler(cab, linhas, nome="Overview.csv"):
    return formato.ler(nome, csv_bytes(cab, linhas))


def test_overview_em_ingles_como_o_real():
    linhas = overview_dias(n=7)
    lt = formato.ler("Overview.csv", csv_overview(linhas))
    assert lt.secao == "visao_geral" and not lt.provisorio
    assert lt.reconhecidas == ["Date", "Video Views", "Profile Views", "Likes", "Comments",
                               "Shares"]
    assert lt.ausentes == [] and lt.ignoradas == [] and lt.problemas == []
    assert [ln.valores["views"] for ln in lt.linhas] == [x.views for x in linhas]
    assert lt.linhas[0].numero == 2 and lt.linhas[0].dia_bruto.startswith(
        ("January", "February", "March", "April", "May", "June", "July", "August", "September",
         "October", "November", "December"))


def test_seguidores_em_pt_br_marca_provisorio():
    lt = formato.ler("FollowerHistory.csv", csv_seguidores(
        [(d.dia, 10 + k, 1) for k, d in enumerate(overview_dias(n=3))], pt=True))
    assert lt.secao == "seguidores" and lt.provisorio
    assert [ln.valores for ln in lt.linhas][1] == {"seguidores": 11, "seguidores_dif": 1}


def test_ordem_diferente_opcional_ausente_e_desconhecida():
    lt = _ler(("Likes", "VIDEO VIEWS", "date", "Coisa nova"),
              [("5", "100", "September 25", "x")])
    assert lt.secao == "visao_geral"
    assert lt.linhas[0].valores == {"views": 100, "visitas_perfil": None, "likes": 5,
                                    "comments": None, "shares": None}
    assert lt.ausentes == ["Profile Views", "Comments", "Shares"]
    assert lt.ignoradas == ["Coisa nova"]


def test_sinonimos_provisorios_listados():
    assert "Data" in formato.provisorios() and "Curtidas" in formato.provisorios()
    assert "Date" not in formato.provisorios()


@pytest.mark.parametrize(("bruto", "esperado"), [
    ("1234", 1234), (" 12 ", 12), ("1,234", 1234), ("1.234", 1234), ("1,234,567", 1234567),
    ("0", 0)])
def test_numeros_validos(bruto, esperado):
    assert formato.numero(bruto) == esperado


@pytest.mark.parametrize(("bruto", "motivo"), [
    ("12.5", "não é um número inteiro"), ("1.2K", "abreviado"), ("3M", "abreviado"),
    ("-4", "negativo"), ("abc", "não é um número inteiro"), ("1,23", "não é um número inteiro"),
    ("1.234,567", "não é um número inteiro")])
def test_numeros_recusados(bruto, motivo):
    lido = formato.numero(bruto)
    assert isinstance(lido, str) and lido.startswith(motivo)


def test_diferenca_de_seguidores_pode_ser_negativa():
    assert formato.numero("-3", pode_negativo=True) == -3
    lt = _ler(("Date", "Followers", "Difference in followers from previous day"),
              [("May 1", "10", "0"), ("May 2", "8", "-2")], "FollowerHistory.csv")
    assert lt.linhas[1].valores["seguidores_dif"] == -2


def test_problemas_por_linha_com_coluna_e_valor():
    lt = _ler(("Date", "Video Views", "Likes"),
              [("May 1", "-1", "2"), ("May 2", "1.2K", "x"), ("May 3", "", "1"),
               ("May 4", "3")])
    assert [(p.linha, p.coluna, p.valor) for p in lt.problemas] == [
        (2, "Video Views", "-1"), (3, "Video Views", "1.2K"), (3, "Likes", "x"),
        (4, "Video Views", ""), (5, None, None)]
    assert lt.linhas == []


def test_vazio_em_opcional_vira_sem_dado_e_linha_vazia_ignorada():
    lt = _ler(("Date", "Video Views", "Likes"), [("May 1", "3", ""), ("", "", "")])
    assert lt.problemas == [] and len(lt.linhas) == 1
    assert lt.linhas[0].valores["likes"] is None


def test_dia_repetido_igual_conta_uma_vez_e_diferente_e_erro():
    igual = _ler(("Date", "Video Views"), [("May 1", "3"), ("May 1", "3"), ("May 2", "4")])
    assert igual.problemas == [] and len(igual.linhas) == 2
    diferente = _ler(("Date", "Video Views"), [("May 1", "3"), ("May 1", "5")])
    assert [p.motivo for p in diferente.problemas] == [
        "dia repetido (linha 2) com números diferentes"]


def test_tudo_zero_e_valido():
    lt = _ler(("Date", "Video Views", "Likes"), [("May 1", "0", "0")])
    assert lt.problemas == [] and lt.linhas[0].valores["views"] == 0


# Spec 022 (FR-004): Atividade, Gênero e Territórios saem daqui (passam a ser importados).
@pytest.mark.parametrize(("cab", "secao"), [
    (("Video title", "Video link", "Post time", "Video views"), "Conteúdo")])
def test_secao_nao_importada(cab, secao):
    with pytest.raises(ApiError) as e:
        _ler(cab, [])
    assert e.value.code == "studio_secao_nao_importada"
    assert e.value.details["secaoReconhecida"] == secao


@pytest.mark.parametrize("cab", [("Video Views", "Likes"), ("Date", "Likes"),
                                 ("Datum", "Videovisningar")])
def test_formato_nao_reconhecido(cab):
    with pytest.raises(ApiError) as e:
        _ler(cab, [("1", "2")])
    assert e.value.code == "studio_formato"
    assert e.value.details["encontradas"] == list(cab)
    assert "Video Views" in e.value.details["esperadas"]


def test_vazio_e_codificacao():
    for dados in (b"", "﻿".encode(), csv_bytes(("Date", "Video Views"), [])):
        with pytest.raises(ApiError) as e:
            formato.ler("Overview.csv", dados)
        assert e.value.code == "studio_formato"
    with pytest.raises(ApiError) as e:
        formato.ler("Overview.csv", '"Date","Video Views"\n"Março 1","3"'.encode("latin-1"))
    assert e.value.code == "studio_formato" and e.value.details["motivo"] == "codificacao"


# ---- spec 022: os cabeçalhos reais das 4 seções de público ----

@pytest.mark.parametrize(("cab", "secao"), [
    (("Gender", "Distribution"), "genero"),
    (("Top territories", "Distribution"), "territorios"),
    (("Date", "Hour", "Active followers"), "atividade"),
    (("Date", "Total Viewers", "New Viewers", "Returning Viewers"), "espectadores"),
    (("Gênero", "Distribuição"), "genero"),
    (("Data", "Hora", "Seguidores ativos"), "atividade")])
def test_secoes_de_publico_pelo_cabecalho(cab, secao):
    assert formato.secao_de(list(cab)) == (secao, None)


def test_espectadores_sem_as_opcionais():
    lt = _ler(("Date", "Total Viewers"), [("May 1", "3")], "Viewers.xlsx")
    assert lt.secao == "espectadores"
    assert lt.ausentes == ["New Viewers", "Returning Viewers"]


def test_undefined_na_visao_geral_continua_erro():
    lt = _ler(("Date", "Video Views"), [("May 1", "undefined")])
    assert [p.motivo for p in lt.problemas] == [formato.MOTIVO_NUMERO]
