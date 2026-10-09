"""Valor efetivo do Studio (spec 020, T012; research R6): o 1º dia coberto (o dia da 1ª coleta
**não** é coberto), a ativa mais antiga vale, uma desfeita não vale e a próxima ativa assume,
seções independentes, série sem coleta e os ganhos diários da coleta."""

from datetime import timedelta

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    DiaOverview,
    overview_dias,
    seguidores_dias,
    semear_coleta,
    st,  # noqa: F401
    zip_overview,
    zip_seguidores,
)
from sociman_api.metricas.studio import efetivo

H = "atavernanerd"


def test_primeiro_dia_coberto_e_o_seguinte_ao_da_1a_coleta(st):  # noqa: F811
    serie = st.serie()
    assert efetivo.primeiro_dia_coberto(st.db, [serie]) == {serie: None}
    semear_coleta(st.db, st.conta_id, local(5, 14, 58), serie_id=serie)
    primeiro = efetivo.primeiro_dia_coberto(st.db, [serie])[serie]
    assert primeiro == local(4).date()
    assert not efetivo.coberto(local(5).date(), primeiro)  # o dia da 1ª coleta
    assert efetivo.coberto(local(4).date(), primeiro)


def test_ativa_mais_antiga_vale_e_desfeita_passa_a_vez(st):  # noqa: F811
    serie = st.serie()
    ate = local(1).date()
    a = st.importar(zip_overview(overview_dias(ate, 3), H))
    outros = [DiaOverview(x.dia, x.views + 1000) for x in overview_dias(ate, 3)]
    b = st.importar(zip_overview(outros, H))
    dias = efetivo.dias(st.db, [serie])[serie]
    assert {d.visao_geral.importacao_id for d in dias.values()} == {_uuid(a["id"])}
    assert st.desfazer(a).status_code == 200
    st.db.expire_all()
    dias = efetivo.dias(st.db, [serie])[serie]
    assert {d.visao_geral.importacao_id for d in dias.values()} == {_uuid(b["id"])}
    assert dias[ate].visao_geral.views == outros[-1].views


def test_secoes_independentes(st):  # noqa: F811
    serie = st.serie()
    ate = local(1).date()
    vg = st.importar(zip_overview(overview_dias(ate, 3), H))
    seg = st.importar(zip_seguidores(seguidores_dias(ate, 5), H))
    dias = efetivo.dias(st.db, [serie], ate - timedelta(days=4), ate)[serie]
    assert len(dias) == 5
    com_vg = [d for d, e in dias.items() if e.visao_geral is not None]
    assert com_vg == [ate - timedelta(days=k) for k in (2, 1, 0)]
    assert all(e.seguidores.importacao_id == _uuid(seg["id"]) for e in dias.values())
    assert all(e.visao_geral.importacao_id == _uuid(vg["id"])
               for e in dias.values() if e.visao_geral)
    # o ganho de seguidores do Studio é a diferença do arquivo
    assert efetivo.ganho_seguidores(ate, dias) == seguidores_dias(ate, 5)[-1][2]


def test_api_por_dia_soma_igual_ao_periodo(st):  # noqa: F811
    serie = st.serie()
    semear_coleta(st.db, st.conta_id, local(3, 10), fotos=30, serie_id=serie)
    de, ate = local(4).date(), local(1).date()
    api = efetivo.api_por_dia(st.db, [serie], de, ate)[serie]
    assert not api[de].tem_dado and api[de].seguidores_dif is None
    # 30 fotos horárias desde D−3 10:00 (k = 1..13 no D−3): views 100·k → 1300 e depois 1700
    assert (api[local(3).date()].views, api[local(2).date()].views) == (1300, 1700)
    assert api[local(1).date()].views == 0 and api[local(1).date()].tem_dado
    assert sum(d.likes for d in api.values()) == 300
    # seguidores: 1000 + d por dia (a 1ª foto do dia é a base no 1º dia)
    assert [api[d].seguidores_dif for d in sorted(api)] == [None, 0, 1, 1]


def _uuid(s):
    import uuid

    return uuid.UUID(s)
