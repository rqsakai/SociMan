"""XLSX do Studio, inclusive malicioso (spec 022, T012; research R2): o real sintético, os outros
tipos de célula, a escolha da aba (a outra nunca aberta), as recusas (fórmula, macro, link,
protegido, DOCTYPE/ENTITY, bomb, entradas demais, `..`, link simbólico, cifrado, `.xls`, XLSX
dentro do XLSX) e o `Viewers_x.zip`. Tudo em memória."""

import io
import zipfile
from datetime import date
from zoneinfo import ZoneInfo

import pytest
from integration.studio_helpers import (
    data_en,
    viewers_dias,
    xlsx_viewers,
    zip_bytes,
    zip_viewers,
)

from sociman_api.errors import ApiError
from sociman_api.metricas.studio import arquivos, formato, planilha

TZ = ZoneInfo("America/Sao_Paulo")
ATE = date(2026, 10, 1)
LINHAS = viewers_dias(ATE)


def _recusa(dados: bytes, codigo: str = "studio_planilha", nome: str = "Viewers.xlsx"
            ) -> ApiError:
    with pytest.raises(ApiError) as e:
        planilha.ler(nome, dados)
    assert e.value.code == codigo, e.value.message
    return e.value


def test_real_sintetico():
    p = planilha.ler("Viewers.xlsx", xlsx_viewers(LINHAS))
    assert p.cabecalho == ["Date", "Total Viewers", "New Viewers", "Returning Viewers"]
    assert p.inicio == 2 and len(p.linhas) == 7
    assert p.linhas[0] == [data_en(LINHAS[0][0]), "undefined", "0", "0"]
    assert p.celulas[2][1] == "B4"
    lt = formato.ler_linhas("Viewers.xlsx", p.cabecalho, p.linhas, p.celulas, p.inicio)
    assert lt.secao == "espectadores" and lt.sem_dado == 1 and lt.problemas == []
    assert [ln.valores["espectadores"] for ln in lt.linhas] == [None, 104, 181, 1, 2, 3, 663]
    assert lt.linhas[0].celulas["dia"] == "A2"


@pytest.mark.parametrize("defeito", ["compartilhado", "inline"])
def test_outros_tipos_de_texto(defeito):
    p = planilha.ler("Viewers.xlsx", xlsx_viewers(LINHAS, defeito=defeito))
    assert [ln[0] for ln in p.linhas] == [data_en(d) for d, _ in LINHAS]


def test_numero_e_data_por_numero_de_serie():
    p = planilha.ler("Viewers.xlsx", xlsx_viewers(LINHAS, defeito="serie"))
    assert [ln[0] for ln in p.linhas] == [d.isoformat() for d, _ in LINHAS]


def test_aba_viewers_e_outra_nunca_aberta(monkeypatch):
    dados = xlsx_viewers(LINHAS, defeito="abas_com_viewers")
    abertos: list[str] = []
    original = zipfile.ZipFile.open

    def espiao(self, nome, *a, **kw):
        abertos.append(getattr(nome, "filename", nome))
        return original(self, nome, *a, **kw)

    monkeypatch.setattr(zipfile.ZipFile, "open", espiao)
    p = planilha.ler("Viewers.xlsx", dados)
    assert len(p.linhas) == 7
    assert "xl/worksheets/sheet2.xml" not in abertos
    assert set(abertos) <= {"[Content_Types].xml", "xl/workbook.xml",
                            "xl/_rels/workbook.xml.rels", "xl/worksheets/sheet1.xml",
                            "xl/sharedStrings.xml"}


def test_duas_abas_sem_viewers():
    e = _recusa(xlsx_viewers(LINHAS, defeito="abas"))
    assert e.details["motivo"] == "a planilha não tem a aba Viewers"


def test_uma_aba_com_outro_nome_vale():
    assert len(planilha.ler("x.xlsx", xlsx_viewers(LINHAS, aba="Planilha1")).linhas) == 7


@pytest.mark.parametrize(("defeito", "motivo"), [
    ("macro", "macro"), ("externo", "link externo"), ("protegido", "planilha protegida"),
    ("doctype", "DOCTYPE ou ENTITY no XML"), ("entity", "DOCTYPE ou ENTITY no XML")])
def test_recusas_de_conteudo(defeito, motivo):
    assert _recusa(xlsx_viewers(LINHAS, defeito=defeito)).details["motivo"] == motivo


def test_formula_cita_a_celula():
    e = _recusa(xlsx_viewers(LINHAS, defeito="formula"))
    assert e.details == {"arquivo": "Viewers.xlsx", "motivo": "fórmula", "celula": "B3"}
    assert "célula B3" in e.message


def test_letras_em_b4_e_problema_com_celula():
    p = planilha.ler("Viewers.xlsx", xlsx_viewers(LINHAS, defeito="letras"))
    lt = formato.ler_linhas("Viewers.xlsx", p.cabecalho, p.linhas, p.celulas, p.inicio)
    [prob] = lt.problemas
    assert (prob.celula, prob.valor, prob.linha) == ("B4", "abc", 4)
    assert prob.json()["celula"] == "B4"


def _xlsx_cru(entradas: list[tuple[zipfile.ZipInfo | str, bytes]], metodo=zipfile.ZIP_STORED
              ) -> bytes:
    base = zipfile.ZipFile(io.BytesIO(xlsx_viewers(LINHAS)))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", metodo) as zf:
        for nome in base.namelist():
            zf.writestr(nome, base.read(nome))
        for info, dados in entradas:
            zf.writestr(info, dados)
    return buf.getvalue()


def test_recusas_do_conteiner():
    _recusa(_xlsx_cru([("xl/media/x.bin", b"0" * 200_000)], zipfile.ZIP_DEFLATED),
            "studio_zip_inseguro")  # razão > 100
    _recusa(_xlsx_cru([(f"xl/f{i}.xml", b"") for i in range(16)]), "studio_zip_inseguro")
    _recusa(_xlsx_cru([("../x", b"1")]), "studio_zip_inseguro")
    _recusa(_xlsx_cru([("/abs.xml", b"1")]), "studio_zip_inseguro")
    link = zipfile.ZipInfo("xl/link.xml")
    link.external_attr = 0o120777 << 16
    _recusa(_xlsx_cru([(link, b"/etc/passwd")]), "studio_zip_inseguro")
    _recusa(xlsx_viewers(LINHAS, defeito="zip_dentro"), "studio_zip_inseguro")
    _recusa(_xlsx_cru([("xl/embeddings/outro.xlsx", xlsx_viewers(LINHAS))]),
            "studio_zip_inseguro")


def test_billion_laughs_nao_chega_ao_parser(monkeypatch):
    chamado = []
    original = planilha.ET.fromstring

    def espiao(d):
        chamado.append(d)
        return original(d)

    monkeypatch.setattr(planilha.ET, "fromstring", espiao)
    _recusa(xlsx_viewers(LINHAS, defeito="doctype"))
    assert all(b"<!DOCTYPE" not in d for d in chamado)


def test_cifrado():
    dados = bytearray(xlsx_viewers(LINHAS))
    local, central = dados.find(b"PK\x03\x04"), dados.find(b"PK\x01\x02")
    dados[local + 6] |= 0x1
    dados[central + 8] |= 0x1
    _recusa(bytes(dados), "studio_zip_inseguro")


def test_xls_antigo_e_xlsx_que_nao_e_zip():
    assert _recusa(b"\xd0\xcf\x11\xe0" + b"0" * 10).details["motivo"].startswith(
        "planilha antiga")
    for nome, dados in (("antigo.xls", b"\xd0\xcf\x11\xe0" + b"0" * 10),
                        ("planilha.xlsx", b"qualquer coisa"),
                        ("Viewers.xlsx", zip_bytes({"[Content_Types].xml": b"<x/>",
                                                    "xl_workbook.xml": b""}))):
        with pytest.raises(ApiError) as e:
            arquivos.ler_arquivo(arquivos.Enviado(nome, dados), TZ)
        assert e.value.code == "studio_planilha", (nome, e.value.message)


def test_viewers_zip_com_o_xlsx_dentro_e_aceito():
    nome, dados = zip_viewers(LINHAS)
    a = arquivos.ler_arquivo(arquivos.Enviado(nome, dados), TZ)
    assert (a.tipo, a.handle, a.nome_zip.secao) == ("zip", "contateste", "espectadores")
    [c] = a.csvs
    assert c.entrada == "Viewers.xlsx" and c.lida is not None and len(c.lida.linhas) == 7
    assert c.sha == arquivos.hashlib.sha256(xlsx_viewers(LINHAS)).hexdigest()


def test_viewers_zip_com_xlsx_que_tem_outro_zip_e_recusado():
    with pytest.raises(ApiError) as e:
        arquivos.ler_arquivo(arquivos.Enviado(
            "Viewers_contateste.zip",
            zip_bytes({"Viewers.xlsx": xlsx_viewers(LINHAS, defeito="zip_dentro")})), TZ)
    assert e.value.code == "studio_zip_inseguro"


def test_xlsx_solto_vira_arquivo_xlsx():
    a = arquivos.ler_arquivo(arquivos.Enviado("Viewers.xlsx", xlsx_viewers(LINHAS)), TZ)
    assert (a.tipo, a.handle) == ("xlsx", None) and a.csvs[0].lida is not None
