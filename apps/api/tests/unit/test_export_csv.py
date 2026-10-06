"""CSV da exportação (spec 016; segurança da 019, R10): texto que começa com `=`, `+`, `-`, `@`,
tab ou CR sai com um apóstrofo na frente (injeção de fórmula na planilha); números, mesmo
negativos, continuam números, e o @ de uma conta sai limpo. O JSON Lines não muda."""

import csv
import io
import json
import zipfile

import pytest

from sociman_api.metricas import export


def _escrever(formato, dados: dict) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        e = export._Escritor(zf, "videos", formato)
        e.linha(dados)
        e.fechar()
    with zipfile.ZipFile(buf) as zf:
        return zf.read(f"videos.{formato}").decode("utf-8-sig")


@pytest.mark.parametrize("perigoso", [
    '=HYPERLINK("https://exemplo.com","clique")', "+1+1", "-2+3", "@SUM(A1)", "@SUM(1)", "@x y", "\tx", "\rx"])
def test_texto_que_vira_formula_ganha_apostrofo(perigoso):
    texto = _escrever("csv", {"legenda": perigoso, "gancho": "Você usa isso?"})
    [cabecalho, linha] = list(csv.reader(io.StringIO(texto)))
    valores = dict(zip(cabecalho, linha, strict=True))
    assert valores["legenda"] == "'" + perigoso
    assert valores["gancho"] == "Você usa isso?"


def test_numero_negativo_continua_numero_e_o_jsonl_nao_muda():
    dados = {"legenda": "=1+1", "intervalo_post_anterior_h": -2.5, "score": -3}
    [cabecalho, linha] = list(csv.reader(io.StringIO(_escrever("csv", dados))))
    valores = dict(zip(cabecalho, linha, strict=True))
    assert valores["intervalo_post_anterior_h"] == "-2.5"
    assert valores["score"] == "-3"
    jsonl = json.loads(_escrever("jsonl", dados))
    assert jsonl["legenda"] == "=1+1" and jsonl["score"] == -3


@pytest.mark.parametrize("handle", ["@atavernanerd", "@meus.queridinhos_10"])
def test_handle_simples_sai_limpo(handle):
    [cabecalho, linha] = list(csv.reader(io.StringIO(_escrever("csv", {"conta": handle}))))
    assert dict(zip(cabecalho, linha, strict=True))["conta"] == handle
