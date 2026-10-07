"""Confirmar com público (spec 022, US1, T019): tudo ou nada, as colunas novas da importação, o
`gravados` em linhas, o histórico sem rótulo, nome de arquivo nem @, a idempotência por seção
(mesmo SHA, XLSX re-zipado, uma seção repetida e outra nova), a sobreposição diferente
(`divergentes`, vale a anterior) e os dias da 020 e as fotos da 016 intactos."""

import hashlib
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    csv_genero,
    seguidores_dias,
    semear_coleta,
    st,  # noqa: F401
    viewers_dias,
    xlsx_viewers,
    zip_bytes,
    zip_seguidores,
    zip_viewers,
)
from sociman_api.history import EntityVersion
from sociman_api.metricas.studio import efetivo, service
from sociman_api.metricas.studio.models import (
    AtividadeStudio,
    DiaStudio,
    EspectadoresStudio,
    FotoDistribuicao,
    Importacao,
)

H = "atavernanerd"
MODELOS = (Importacao, DiaStudio, FotoDistribuicao, AtividadeStudio, EspectadoresStudio)


def _contar(db) -> tuple[int, ...]:
    db.expire_all()
    return tuple(db.scalar(select(func.count()).select_from(m)) for m in MODELOS)


def _hash(db, sql: str) -> str:
    db.expire_all()
    return hashlib.sha256(repr(db.execute(text(sql)).all()).encode()).hexdigest()


def _fotos_api(db) -> str:
    return _hash(db, "SELECT id, serie_id, coletado_em, seguidores FROM metricas_conta_fotos "
                     "UNION ALL SELECT id, video_id, coletado_em, views FROM "
                     "metricas_video_fotos ORDER BY 1, 2")


def test_confirmar_grava_tudo(st):  # noqa: F811
    serie = st.serie()
    semear_coleta(st.db, st.conta_id, local(1, 9), serie_id=serie)
    api = _fotos_api(st.db)
    ate = local(1).date()
    seg, vw = seguidores_dias(ate, 7), viewers_dias(ate)
    p = st.previa_ok(zip_seguidores(seg, H, publico=True), zip_viewers(vw, H))
    r = st.confirmar(p["previaId"])
    assert r.status_code == 201, r.text
    imp = r.json()
    assert imp["secoes"] == ["seguidores", "genero", "territorios", "atividade", "espectadores"]
    data_foto = min(ate + timedelta(days=1), local(0).date())
    assert (imp["dataFoto"], imp["dataFotoOrigem"], imp["secoesVazias"]) == (
        str(data_foto), "historico", [])
    assert imp["gravados"] == 7 + 3 + 3 + 168 + 7
    assert (imp["periodoDe"], imp["periodoAte"]) == (str(seg[0][0]), str(data_foto))
    assert imp["contagens"]["espectadores"]["semDado"] == 1
    assert imp["contagens"]["genero"]["gravados"] == 3
    assert _contar(st.db) == (1, 7, 6, 168, 7)

    st.db.expire_all()
    row = st.db.scalar(select(Importacao))
    for col in ("sha_seguidores", "sha_genero", "sha_territorios", "sha_atividade",
                "sha_espectadores"):
        assert len(getattr(row, col)) == 64
    assert row.sha_espectadores == hashlib.sha256(xlsx_viewers(vw)).hexdigest()
    esp = st.db.scalars(select(EspectadoresStudio).order_by(EspectadoresStudio.dia)).all()
    assert (esp[0].total, esp[0].novos, esp[0].recorrentes) == (None, 0, 0)

    [v] = st.db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "studio_importacao")).all()
    assert v.details["gravados"] == imp["gravados"] and "vazias" not in v.details
    assert set(v.details["publico"]) == {"genero", "territorios", "atividade", "espectadores"}
    bruto = json.dumps([v.after, v.details])
    for proibido in (H, ".zip", ".xlsx", "BR", "feminino", "nomes_arquivos"):
        assert proibido not in bruto, proibido
    assert v.after["data_foto"] == str(data_foto)
    assert _fotos_api(st.db) == api  # a coleta da 016 intacta


def test_so_vazias_mais_historico_anota(st):  # noqa: F811
    imp = st.importar(zip_seguidores(seguidores_dias(local(1).date(), 5), H))
    assert imp["secoes"] == ["seguidores"]
    assert imp["secoesVazias"] == ["genero", "territorios", "atividade"]
    assert imp["dataFoto"] is None and imp["gravados"] == 5


def test_so_fotos_usa_o_ano_da_foto(st):  # noqa: F811
    p = st.previa_ok(("FollowerGender.csv", csv_genero()))
    r = st.confirmar(p["previaId"], confirmo=True)
    assert r.status_code == 201, r.text
    imp = r.json()
    assert imp["secoes"] == ["genero"] and imp["anoOrigem"] == "deduzido"
    assert imp["periodoDe"] == imp["periodoAte"] == imp["dataFoto"] == str(local(0).date())
    assert imp["dataFotoOrigem"] == "importacao" and imp["gravados"] == 3


def test_tudo_ou_nada(st, monkeypatch):  # noqa: F811
    p = st.previa_ok(zip_seguidores(seguidores_dias(local(1).date(), 3), H, publico=True),
                     zip_viewers(viewers_dias(local(1).date()), H))
    original = service._inserir

    def falha(db, modelo, linhas):
        if modelo is service.EspectadoresStudio:  # a última tabela: as outras já foram
            raise RuntimeError("falha no meio")
        original(db, modelo, linhas)

    monkeypatch.setattr(service, "_inserir", falha)
    with pytest.raises(RuntimeError):
        st.confirmar(p["previaId"])
    monkeypatch.setattr(service, "_inserir", original)
    assert _contar(st.db) == (0, 0, 0, 0, 0)


def test_idempotencia_por_secao(st):  # noqa: F811
    ate = local(1).date()
    seg, vw = seguidores_dias(ate, 7), viewers_dias(ate)
    st.importar(zip_seguidores(seg, H, publico=True), zip_viewers(vw, H))
    antes = _contar(st.db)
    # o mesmo envio: nada novo
    p = st.previa_ok(zip_seguidores(seg, H, publico=True), zip_viewers(vw, H))
    assert all(s["jaImportada"] for s in p["publico"]) and p["podeConfirmar"] is False
    r = st.confirmar(p["previaId"])
    assert (r.status_code, r.json()["gravados"]) == (200, 0)
    # o mesmo XLSX re-zipado (deflate): o SHA é do XLSX, não do ZIP
    import zipfile
    rezip = ("Viewers_atavernanerd.zip",
             zip_bytes({"Viewers.xlsx": xlsx_viewers(vw)}, zipfile.ZIP_DEFLATED))
    r = st.confirmar(st.previa_ok(rezip)["previaId"])
    assert (r.status_code, r.json()["gravados"]) == (200, 0)
    assert _contar(st.db) == antes
    # uma seção repetida (espectadores) e outra nova (gênero solto, outro SHA)
    p = st.previa_ok(zip_viewers(vw, H),
                     ("FollowerGender.csv", csv_genero((("Female", "60%"), ("Male", "40%")))))
    r = st.confirmar(p["previaId"], confirmo=True)
    assert r.status_code == 201 and r.json()["secoes"] == ["genero"]
    assert _contar(st.db)[2] == antes[2] + 2


def test_sobreposicao_diferente_vale_a_anterior(st):  # noqa: F811
    ate = local(1).date()
    vw = viewers_dias(ate)
    st.importar(zip_viewers(vw, H))
    outros = [(d, (t, n, r + 1 if r is not None else None)) for d, (t, n, r) in vw]
    p = st.previa_ok(zip_viewers(outros, H))
    [e] = [s for s in p["publico"] if s["secao"] == "espectadores"]
    assert e["contagens"]["divergentes"] == 7
    assert {a["situacao"] for a in e["amostra"]} == {"divergente"}
    imp = st.confirmar(p["previaId"]).json()
    assert imp["contagens"]["espectadores"]["divergentes"] == 7
    serie = st.serie()
    ef = efetivo.espectadores(st.db, [serie])[serie]
    assert [ef[d].recorrentes for d, _ in vw] == [r for _, (_, _, r) in vw]  # vale o anterior


def test_foto_da_mesma_data_igual_e_divergente(st):  # noqa: F811
    st.importar(("FollowerGender.csv", csv_genero()), confirmo=True)
    p = st.previa_ok(("FollowerGender.csv", csv_genero((("Male", "37.5%"), ("Female", "61%"),
                                                         ("Other", "1.5%")))))
    g = p["publico"][0]
    assert (g["situacao"], g["contagens"]["iguais"]) == ("igual", 3)  # outro SHA, mesmos números
    p = st.previa_ok(("FollowerGender.csv", csv_genero((("Female", "50%"), ("Male", "50%")))))
    assert p["publico"][0]["situacao"] == "divergente"


def test_atividade_no_mesmo_dia_e_hora(st):  # noqa: F811
    from integration.studio_helpers import ativos, csv_atividade, csv_bytes, data_en

    dias_ = [local(2).date(), local(1).date()]
    st.importar(("FollowerActivity.csv", csv_atividade(dias_, (20,))), confirmo=True)
    linhas = [(data_en(d), 20, ativos(d, 20) + 1) for d in dias_]
    p = st.previa_ok(("FollowerActivity.csv",
                      csv_bytes(("Date", "Hour", "Active followers"), linhas)))
    a = p["publico"][0]
    assert a["contagens"]["divergentes"] == 2
    st.confirmar(p["previaId"], confirmo=True)
    serie = st.serie()
    ef = efetivo.atividade(st.db, [serie])[serie]
    assert [ef[(d, 20)].ativos for d in dias_] == [ativos(d, 20) for d in dias_]
