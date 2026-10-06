"""Cobertura (spec 020, US5, T040): faixas contínuas por seção, a sobreposição com a coleta, os
buracos (dia faltando no arquivo), uma série sem coleta (buracos até ontem) e as desfeitas fora.
Membro também vê."""

from integration.analytics_helpers import cena, local, membro  # noqa: F401
from integration.studio_helpers import (
    DiaOverview,
    csv_overview,
    overview_dias,
    seguidores_dias,
    semear_coleta,
    st,  # noqa: F401
    zip_overview,
    zip_seguidores,
)

H = "atavernanerd"


def _secao(c, nome):
    [s] = [s for s in c["secoes"] if s["secao"] == nome]
    return s


def _d(k):
    return str(local(k).date())


def test_faixas_sobreposicao_e_sem_buraco(st):  # noqa: F811
    semear_coleta(st.db, st.conta_id, local(3, 9), serie_id=st.serie())
    # Studio de D−9 a D−1; coleta desde D−3 (1º dia coberto D−2)
    st.importar(zip_overview(overview_dias(local(1).date(), 9), H))
    c = st.cobertura()
    assert c["coleta"] == {"primeiroDia": _d(3), "primeiroDiaCoberto": _d(2)}
    vg = _secao(c, "visao_geral")
    assert vg["faixas"] == [{"de": _d(9), "ate": _d(1), "fonte": "studio"}]
    assert vg["sobreposicao"] == [{"de": _d(3), "ate": _d(1)}]
    assert vg["buracos"] == []
    assert _secao(c, "seguidores") == {"secao": "seguidores", "faixas": [],
                                       "sobreposicao": [], "buracos": []}
    assert c["importacoesAtivas"] == 1


def test_buraco_de_um_dia_e_serie_sem_coleta(st):  # noqa: F811
    linhas = [DiaOverview(local(k).date(), 5) for k in (8, 7, 5, 4)]
    st.importar(("Overview.csv", csv_overview(linhas)), confirmo=True)
    st.importar(zip_seguidores(seguidores_dias(local(3).date(), 2), H))
    c = st.cobertura()
    assert c["coleta"] is None
    vg = _secao(c, "visao_geral")
    assert vg["faixas"] == [{"de": _d(8), "ate": _d(7), "fonte": "studio"},
                            {"de": _d(5), "ate": _d(4), "fonte": "studio"}]
    # sem coleta, os buracos vão até ontem
    assert vg["buracos"] == [{"de": _d(6), "ate": _d(6)}, {"de": _d(3), "ate": _d(1)}]
    seg = _secao(c, "seguidores")
    assert seg["faixas"] == [{"de": _d(4), "ate": _d(3), "fonte": "studio"}]
    assert seg["buracos"] == [{"de": _d(2), "ate": _d(1)}]


def test_desfeitas_ficam_fora_e_membro_ve(st, membro):  # noqa: F811
    imp = st.importar(zip_overview(overview_dias(n=3), H))
    st.desfazer(imp)
    c = st.cobertura(h=membro[1])
    assert _secao(c, "visao_geral")["faixas"] == [] and c["importacoesAtivas"] == 0
    assert [i["estado"] for i in st.importacoes(h=membro[1])] == ["desfeita"]
