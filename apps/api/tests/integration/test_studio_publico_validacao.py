"""Arquivos de público íntegros (spec 022, US2, T027; SC-004), pela rota: cada defeito de FR-008
recusado com `problemas[]` (e a `celula` na planilha), o XLSX malicioso (`studio_planilha` ou
`studio_zip_inseguro`), o @ do ZIP de Espectadores, o XLSX solto pedindo a confirmação, o aviso
de soma e o 4º arquivo. Em todos, 0 linhas gravadas e nenhuma chave no Redis."""

import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    CAB_ATIVIDADE,
    CAB_VIEWERS,
    csv_bytes,
    csv_genero,
    csv_territorios,
    data_en,
    err,
    seguidores_dias,
    st,  # noqa: F401
    viewers_dias,
    xlsx_viewers,
    zip_bytes,
    zip_overview,
    zip_seguidores,
    zip_viewers,
)
from sociman_api.metricas.studio.models import (
    AtividadeStudio,
    EspectadoresStudio,
    FotoDistribuicao,
    Importacao,
)
from sociman_api.redis import get_redis

H = "atavernanerd"


def _nada(st):  # noqa: F811
    st.db.expire_all()
    for m in (Importacao, FotoDistribuicao, AtividadeStudio, EspectadoresStudio):
        assert st.db.scalar(select(func.count()).select_from(m)) == 0
    assert list(get_redis().scan_iter("studio:previa:*")) == []


def _recusa(st, codigo, *arquivos):  # noqa: F811
    r = st.previa(*arquivos)
    assert (r.status_code, err(r)) == (400, codigo), r.text
    _nada(st)
    return r.json()["error"]


def _ontem():
    return local(1).date()


@pytest.mark.parametrize(("arquivo", "motivo"), [
    (("FollowerGender.csv", csv_genero((("Female", "40%"), ("Male", "40%")))),
     "soma do gênero dá 80%"),
    (("FollowerTopTerritories.csv", csv_territorios((("BR", "95%"), ("PT", "8%")))),
     "mais de 100%"),
    (("FollowerGender.csv", csv_genero((("Female", "-5%"), ("Male", "105%")))),
     "porcentagem negativa"),
    (("FollowerGender.csv", csv_genero((("Female", "60%"), ("Male", "40")))), "misturados"),
    (("FollowerGender.csv", csv_genero((("Female", "60%"), ("Robô", "40%")))),
     "gênero desconhecido"),
])
def test_distribuicao_invalida(st, arquivo, motivo):  # noqa: F811
    e = _recusa(st, "studio_invalido", arquivo)
    assert motivo in e["details"]["problemas"][0]["motivo"]


def test_atividade_invalida(st):  # noqa: F811
    d = data_en(_ontem())
    e = _recusa(st, "studio_invalido", ("FollowerActivity.csv", csv_bytes(
        CAB_ATIVIDADE, [(d, "24", "3"), (d, "5", "3"), (d, "5", "4"), (d, "6", "-1")])))
    motivos = [p["motivo"] for p in e["details"]["problemas"]]
    assert "hora fora de 0 a 23" in motivos and "negativo" in motivos
    assert any("dia e hora repetidos" in m for m in motivos)


def test_letras_no_xlsx_citam_a_celula(st):  # noqa: F811
    e = _recusa(st, "studio_invalido", zip_viewers(viewers_dias(_ontem()), H, defeito="letras"))
    [p] = e["details"]["problemas"]
    assert (p["celula"], p["valor"], p["coluna"]) == ("B4", "abc", "Total Viewers")
    assert "célula B4" in e["message"]


@pytest.mark.parametrize(("defeito", "codigo"), [
    ("macro", "studio_planilha"), ("formula", "studio_planilha"),
    ("externo", "studio_planilha"), ("protegido", "studio_planilha"),
    ("doctype", "studio_planilha"), ("abas", "studio_planilha"),
    ("zip_dentro", "studio_zip_inseguro")])
def test_xlsx_malicioso(st, defeito, codigo):  # noqa: F811
    e = _recusa(st, codigo, zip_viewers(viewers_dias(_ontem()), H, defeito=defeito))
    assert e["details"]["motivo"]
    if defeito == "formula":
        assert e["details"]["celula"] == "B3"


def test_bomb_e_slip(st):  # noqa: F811
    e = _recusa(st, "studio_zip_inseguro", ("Viewers_atavernanerd.zip", zip_bytes(
        {"Viewers.xlsx": xlsx_viewers(viewers_dias(_ontem())), "../x": b"1"})))
    assert "'..'" in e["details"]["motivo"]
    bomba = zip_bytes({"Viewers.xlsx": b"0" * 300_000}, zipfile.ZIP_DEFLATED)
    _recusa(st, "studio_zip_inseguro", ("Viewers_atavernanerd.zip", bomba))


def test_viewers_de_outra_conta(st):  # noqa: F811
    e = _recusa(st, "studio_conta_diferente", zip_viewers(viewers_dias(_ontem()), "outraconta"))
    assert e["details"]["handleArquivo"] == "outraconta"


def test_xlsx_solto_exige_confirmar_a_conta(st):  # noqa: F811
    p = st.previa_ok(("Viewers.xlsx", xlsx_viewers(viewers_dias(_ontem()))))
    assert p["exigeConfirmacaoConta"] is True
    assert p["arquivos"][0]["tipo"] == "xlsx"
    r = st.confirmar(p["previaId"])
    assert (r.status_code, err(r)) == (400, "confirmar_conta")
    assert st.confirmar(p["previaId"], confirmo=True).status_code == 201


def test_soma_diferente_so_avisa(st):  # noqa: F811
    p = st.previa_ok(zip_viewers(viewers_dias(_ontem()), H, defeito="soma"))
    assert "espectadores_soma" in [a["codigo"] for a in p["avisos"]]


def test_quatro_arquivos(st):  # noqa: F811
    ate = _ontem()
    _recusa(st, "studio_arquivos", zip_overview(handle=H), zip_seguidores(
        seguidores_dias(ate, 3), H), zip_viewers(viewers_dias(ate), H),
        ("FollowerGender.csv", csv_genero()))


def test_tres_arquivos_aceitos(st):  # noqa: F811
    ate = _ontem()
    p = st.previa_ok(zip_overview(handle=H), zip_seguidores(seguidores_dias(ate, 3), H),
                     zip_viewers(viewers_dias(ate), H))
    assert [s["secao"] for s in p["secoes"]] == ["visao_geral", "seguidores"]
    assert [a["secao"] for a in p["arquivos"]] == ["visao_geral", "seguidores", "espectadores"]


def test_viewers_com_data_futura(st):  # noqa: F811
    futuro = local(0).date() + timedelta(days=1)
    dados = csv_bytes(CAB_VIEWERS, [("2026-01-01", "1", "1", "0"),
                                    (futuro.isoformat(), "1", "1", "0")])
    e = _recusa(st, "studio_invalido", ("Viewers.csv", dados))
    assert "data futura" in e["details"]["problemas"][0]["motivo"]
