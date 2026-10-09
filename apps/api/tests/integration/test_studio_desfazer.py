"""Desfazer (spec 020, US4, T036): estado `desfeita` com autor e data e a versão 2 com
`{acao: "desfeita"}`; os dias continuam; `version` errada → 409 `version_conflict`; de novo → 409
`ja_desfeita`; reimportar o mesmo arquivo cria outra importação; duas ativas sobrepostas (desfazer
a mais antiga faz a outra valer, US4.3); prévia feita antes do desfazer → 409."""

import uuid

from sqlalchemy import select

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    DiaOverview,
    err,
    overview_dias,
    st,  # noqa: F401
    zip_overview,
)
from sociman_api.history import EntityVersion
from sociman_api.metricas.studio import efetivo

H = "atavernanerd"


def test_desfazer_marca_e_guarda_os_dias(st):  # noqa: F811
    imp = st.importar(zip_overview(overview_dias(n=5), H))
    r = st.desfazer(imp)
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["estado"], d["version"]) == ("desfeita", 2)
    assert d["desfeitaPor"]["name"] == "Dono" and d["desfeitaEm"]
    assert st.contar() == (1, 5)  # nada apagado
    versoes = st.db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "studio_importacao").order_by(EntityVersion.version)).all()
    assert [(v.version, v.action, v.details) for v in versoes] == [
        (1, "created", {"secoes": ["visao_geral"], "gravados": 5}),
        (2, "updated", {"acao": "desfeita"})]
    assert versoes[1].changed_fields == ["estado", "desfeita_em", "desfeita_por"]
    [lista] = st.importacoes()
    assert lista["estado"] == "desfeita" and lista["desfeitaPor"]["id"] == str(st.dono.id)
    serie = st.serie()
    assert efetivo.dias(st.db, [serie]) == {}


def test_version_errada_e_desfazer_de_novo(st):  # noqa: F811
    imp = st.importar(zip_overview(overview_dias(n=3), H))
    r = st.desfazer(imp, version=7)
    assert (r.status_code, err(r)) == (409, "version_conflict")
    assert st.desfazer(imp).status_code == 200
    for v in (1, 2):
        r = st.desfazer(imp, version=v)
        assert (r.status_code, err(r)) == (409, "ja_desfeita")
    r = st.client.post(f"/api/studio/importacoes/{uuid.uuid4()}/desfazer", headers=st.h,
                       json={"version": 1})
    assert (r.status_code, err(r)) == (404, "not_found")


def test_reimportar_depois_de_desfazer(st):  # noqa: F811
    arquivo = zip_overview(overview_dias(n=4), H)
    a = st.importar(arquivo)
    st.desfazer(a)
    p = st.previa_ok(arquivo)
    s = p["secoes"][0]
    assert s["jaImportada"] is None and p["podeConfirmar"] is True
    assert {x["situacao"] for x in s["amostra"]} == {"novo"}
    b = st.confirmar(p["previaId"]).json()
    assert b["id"] != a["id"] and b["gravados"] == 4 and st.contar() == (2, 8)


def test_duas_ativas_desfazer_a_mais_antiga(st):  # noqa: F811
    ate = local(1).date()
    a = st.importar(zip_overview(overview_dias(ate, 3), H))
    outros = [DiaOverview(x.dia, x.views + 500) for x in overview_dias(ate, 3)]
    b = st.importar(zip_overview(outros, H))
    serie = st.serie()
    assert efetivo.dias(st.db, [serie])[serie][ate].visao_geral.importacao_id == uuid.UUID(a["id"])
    st.desfazer(a)
    st.db.expire_all()
    assert efetivo.dias(st.db, [serie])[serie][ate].visao_geral.importacao_id == uuid.UUID(b["id"])


def test_previa_feita_antes_do_desfazer(st):  # noqa: F811
    a = st.importar(zip_overview(overview_dias(local(1).date(), 3), H))
    p = st.previa_ok(zip_overview(overview_dias(local(8).date(), 3), H))
    st.desfazer(a)
    r = st.confirmar(p["previaId"])
    assert (r.status_code, err(r)) == (409, "previa_desatualizada")


# ---- spec 022 (T020): desfazer tira de uso todas as seções, as da 020 e as de público ----

def test_desfazer_tira_o_publico_de_uso_e_reimportar_grava_de_novo(st):  # noqa: F811
    from sqlalchemy import func

    from integration.studio_helpers import (
        seguidores_dias,
        viewers_dias,
        zip_seguidores,
        zip_viewers,
    )
    from sociman_api.metricas.studio.models import (
        AtividadeStudio,
        EspectadoresStudio,
        FotoDistribuicao,
    )

    ate = local(1).date()
    arquivos = (zip_seguidores(seguidores_dias(ate, 3), H, publico=True),
                zip_viewers(viewers_dias(ate), H))
    imp = st.importar(*arquivos)
    serie = st.serie()
    assert efetivo.espectadores(st.db, [serie]) and efetivo.fotos(st.db, [serie], "genero")
    assert st.desfazer(imp).status_code == 200
    st.db.expire_all()
    assert efetivo.dias(st.db, [serie]) == {}
    assert efetivo.fotos(st.db, [serie], "genero") == {}
    assert efetivo.atividade(st.db, [serie]) == {}
    assert efetivo.espectadores(st.db, [serie]) == {}
    contagem = [st.db.scalar(select(func.count()).select_from(m))
                for m in (FotoDistribuicao, AtividadeStudio, EspectadoresStudio)]
    assert contagem == [6, 72, 7]  # nada apagado
    de_novo = st.importar(*arquivos)
    assert de_novo["id"] != imp["id"] and de_novo["gravados"] == imp["gravados"]
    st.db.expire_all()
    assert len(efetivo.espectadores(st.db, [serie])[serie]) == 7
