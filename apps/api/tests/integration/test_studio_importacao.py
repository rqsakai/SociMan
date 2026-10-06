"""Confirmar a importação (spec 020, US1, T015 e T016): tudo ou nada, histórico sem nome de
arquivo nem @, `nomes_arquivos` gravado, 2 cliques (410), base mudou (409), prévia de outro
usuário ou conta (410), fotos da API intactas (SC-004) e a idempotência (mesmo arquivo, re-zipado,
uma seção repetida e outra nova, arquivo sobreposto e diferente)."""

import hashlib
import json
import uuid
import zipfile

import pytest
from sqlalchemy import func, select, text

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.postagem_helpers import PW, criar_conta, criar_perfil
from integration.studio_helpers import (
    DiaOverview,
    csv_overview,
    err,
    overview_dias,
    seguidores_dias,
    semear_coleta,
    st,  # noqa: F401
    zip_bytes,
    zip_overview,
    zip_seguidores,
)
from sociman_api.history import EntityVersion
from sociman_api.metricas.models import FotoConta, FotoVideo
from sociman_api.metricas.studio import service
from sociman_api.metricas.studio.models import DiaStudio, Importacao

H = "atavernanerd"


def _fotos(db) -> tuple:
    """Contagem e hash de todas as fotos da API (SC-004)."""
    db.expire_all()
    linhas = db.execute(text(
        "SELECT 'v', id, video_id::text, coletado_em::text, views, likes, comments, shares "
        "FROM metricas_video_fotos UNION ALL SELECT 'c', id, serie_id::text, "
        "coletado_em::text, seguidores, seguindo, curtidas, videos FROM metricas_conta_fotos "
        "ORDER BY 1, 2")).all()
    return len(linhas), hashlib.sha256(repr(linhas).encode()).hexdigest()


def test_confirmar_grava_dias_importacao_e_historico(st):  # noqa: F811
    serie = st.serie()
    semear_coleta(st.db, st.conta_id, local(1, 9), serie_id=serie)
    antes = _fotos(st.db)
    ate = local(1).date()
    vg, seg = overview_dias(ate, 7), seguidores_dias(ate, 7)
    nomes = [zip_overview(vg, H)[0], zip_seguidores(seg, H)[0]]
    p = st.previa_ok(zip_overview(vg, H), zip_seguidores(seg, H))
    r = st.confirmar(p["previaId"])
    assert r.status_code == 201, r.text
    imp = r.json()
    assert (imp["estado"], imp["version"], imp["gravados"]) == ("ativa", 1, 7)
    assert imp["secoes"] == ["visao_geral", "seguidores"] and imp["anoOrigem"] == "nome_zip"
    assert (imp["periodoDe"], imp["periodoAte"]) == (str(vg[0].dia), str(ate))
    assert imp["contaId"] == st.conta_id and imp["criadaPor"]["name"] == "Dono"
    assert imp["nomesArquivos"] == nomes
    assert imp["contagens"]["visao_geral"]["gravados"] == 7
    assert imp["contagens"]["visao_geral"]["coletados"] == 0  # D−1 é o dia da 1ª coleta
    st.db.expire_all()
    dias = st.db.scalars(select(DiaStudio).order_by(DiaStudio.dia)).all()
    assert [(d.dia, d.views, d.seguidores) for d in dias] == [
        (x.dia, x.views, s[1]) for x, s in zip(vg, seg, strict=True)]
    assert all(d.tem_visao_geral and d.tem_seguidores and d.serie_id == serie for d in dias)
    [v] = st.db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "studio_importacao")).all()
    assert (v.version, v.action, v.actor_user_id) == (1, "created", st.dono.id)
    assert v.details == {"secoes": ["visao_geral", "seguidores"], "gravados": 7}
    bruto = json.dumps([v.after, v.details])
    assert H not in bruto and ".zip" not in bruto and "nomes_arquivos" not in v.after
    assert st.importacoes()[0]["id"] == imp["id"]
    assert _fotos(st.db) == antes  # SC-004


def test_tudo_ou_nada(st, monkeypatch):  # noqa: F811
    p = st.previa_ok(zip_overview(overview_dias(n=5), H))

    def falha(*a, **kw):
        raise RuntimeError("falha no meio")

    monkeypatch.setattr(service.history, "record", falha)
    with pytest.raises(RuntimeError):
        st.confirmar(p["previaId"])
    assert st.contar() == (0, 0)


def test_dois_cliques_e_previa_de_outro(st, make_user, login):  # noqa: F811
    p = st.previa_ok(zip_overview(overview_dias(n=3), H))
    outro = make_user(role="dono", name="Outro Dono")
    h2 = login(st.client, outro.email, PW)
    r = st.confirmar(p["previaId"], h=h2)
    assert (r.status_code, err(r)) == (410, "previa_indisponivel")
    perfil = criar_perfil(st.client, st.h, "Outro")
    conta2 = criar_conta(st.client, st.h, perfil["id"], "tiktok", "outraconta")
    r = st.confirmar(p["previaId"], conta_id=conta2["id"])
    assert (r.status_code, err(r)) == (410, "previa_indisponivel")
    assert st.confirmar(p["previaId"]).status_code == 201  # a do dono continuou valendo
    r = st.confirmar(p["previaId"])
    assert (r.status_code, err(r)) == (410, "previa_indisponivel")
    assert st.contar() == (1, 3)


def test_base_mudou_entre_a_previa_e_o_confirmar(st):  # noqa: F811
    p1 = st.previa_ok(zip_overview(overview_dias(local(10).date(), 3), H))
    st.importar(zip_overview(overview_dias(local(1).date(), 3), H))
    r = st.confirmar(p1["previaId"])
    assert (r.status_code, err(r)) == (409, "previa_desatualizada")
    assert st.contar() == (1, 3)


def test_coleta_nova_tambem_muda_a_base(st):  # noqa: F811
    p = st.previa_ok(zip_overview(overview_dias(n=3), H))
    semear_coleta(st.db, st.conta_id, local(1, 9), serie_id=st.serie())
    r = st.confirmar(p["previaId"])
    assert (r.status_code, err(r)) == (409, "previa_desatualizada")


# ---- idempotência (T016) ----

def test_reenviar_os_mesmos_zips(st):  # noqa: F811
    arquivos = (zip_overview(overview_dias(n=7), H), zip_seguidores(seguidores_dias(n=7), H))
    imp = st.importar(*arquivos)
    p = st.previa_ok(*arquivos)
    assert p["podeConfirmar"] is False
    for s in p["secoes"]:
        assert s["jaImportada"]["importacaoId"] == imp["id"]
        assert s["jaImportada"]["por"] == "Dono"
        assert s["contagens"]["iguais"] == 7
    r = st.confirmar(p["previaId"])
    assert r.status_code == 200 and r.json()["gravados"] == 0 and r.json()["id"] == imp["id"]
    assert st.contar() == (1, 7)
    assert st.db.scalar(select(func.count()).select_from(EntityVersion).where(
        EntityVersion.entity_type == "studio_importacao")) == 1


def test_re_zipar_o_mesmo_csv_e_idempotente(st):  # noqa: F811
    vg = overview_dias(n=4)
    nome, _ = zip_overview(vg, H)
    st.importar((nome, zip_bytes({"Overview.csv": csv_overview(vg)})))
    rezipado = zip_bytes({"Overview.csv": csv_overview(vg)}, zipfile.ZIP_DEFLATED)
    p = st.previa_ok((nome.replace(".zip", " (1).zip"), rezipado))
    assert p["podeConfirmar"] is False
    assert st.confirmar(p["previaId"]).status_code == 200
    assert st.contar() == (1, 4)


def test_uma_secao_repetida_e_outra_nova(st):  # noqa: F811
    vg = zip_overview(overview_dias(n=4), H)
    st.importar(vg)
    p = st.previa_ok(vg, zip_seguidores(seguidores_dias(n=4), H))
    assert p["podeConfirmar"] is True
    r = st.confirmar(p["previaId"])
    assert r.status_code == 201 and r.json()["secoes"] == ["seguidores"]
    assert r.json()["gravados"] == 4
    st.db.expire_all()
    nova = st.db.get(Importacao, uuid.UUID(r.json()["id"]))
    assert nova.sha_visao_geral is None and nova.sha_seguidores
    assert st.contar() == (2, 8)


def test_arquivo_sobreposto_e_diferente_grava_mas_vale_o_anterior(st):  # noqa: F811
    from sociman_api.metricas.studio import efetivo

    ate = local(1).date()
    a = st.importar(zip_overview(overview_dias(ate, 3), H))
    diferente = [DiaOverview(x.dia, x.views + 7) for x in overview_dias(ate, 4)]
    p = st.previa_ok(zip_overview(diferente, H))
    c = p["secoes"][0]["contagens"]
    assert (c["gravados"], c["divergentes"], c["iguais"]) == (4, 3, 0)
    b = st.confirmar(p["previaId"]).json()
    assert b["gravados"] == 4 and st.contar() == (2, 7)
    serie = st.serie()
    dias = efetivo.dias(st.db, [serie])[serie]
    assert dias[ate].visao_geral.importacao_id == uuid.UUID(a["id"])
    assert dias[diferente[0].dia].visao_geral.importacao_id == uuid.UUID(b["id"])


def test_fotos_intactas_ao_importar_e_desfazer(st):  # noqa: F811
    semear_coleta(st.db, st.conta_id, local(3, 9), serie_id=st.serie())
    antes = _fotos(st.db)
    assert antes[0] > 0
    imp = st.importar(zip_overview(overview_dias(n=7), H))
    assert st.desfazer(imp).status_code == 200
    assert _fotos(st.db) == antes
    st.db.expire_all()
    assert st.db.scalar(select(func.count()).select_from(FotoConta)) > 0
    assert st.db.scalar(select(func.count()).select_from(FotoVideo)) > 0
