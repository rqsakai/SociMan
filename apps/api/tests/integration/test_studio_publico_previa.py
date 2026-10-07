"""Prévia com público (spec 022, US1, T018): Seguidores (4 CSVs) e Espectadores → `publico[]` com a
data da foto e a origem, a distribuição, o pico, as contagens, os totais e o "sem dado"; nada
gravado; o Redis com `publico` e `vazias` (TTL ≤ 30 min); as vazias e o `studio_sem_dados`; o
gênero solto com o aviso `data_foto_importacao`; o período raiz e o `podeConfirmar`."""

import json
from datetime import timedelta

from sqlalchemy import func, select

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    VIEWERS,
    ativos,
    csv_bytes,
    csv_genero,
    err,
    seguidores_dias,
    st,  # noqa: F401
    viewers_dias,
    zip_bytes,
    zip_seguidores,
    zip_viewers,
)
from sociman_api.metricas.studio import previa
from sociman_api.metricas.studio.models import (
    AtividadeStudio,
    EspectadoresStudio,
    FotoDistribuicao,
    Importacao,
)
from sociman_api.redis import get_redis

H = "atavernanerd"


def _pub(p, secao):
    [s] = [s for s in p["publico"] if s["secao"] == secao]
    return s


def _contar(db) -> tuple[int, ...]:
    db.expire_all()
    return tuple(db.scalar(select(func.count()).select_from(m))
                 for m in (Importacao, FotoDistribuicao, AtividadeStudio, EspectadoresStudio))


def test_previa_com_seguidores_e_espectadores(st):  # noqa: F811
    ate = local(1).date()
    hoje = local(0).date()
    seg, vw = seguidores_dias(ate, 7), viewers_dias(ate)
    p = st.previa_ok(zip_seguidores(seg, H, publico=True), zip_viewers(vw, H))
    assert {a["secao"]: a["ignorados"] for a in p["arquivos"]} == {
        "seguidores": [], "espectadores": []}
    assert [s["secao"] for s in p["secoes"]] == ["seguidores"]
    assert [s["secao"] for s in p["publico"]] == ["genero", "territorios", "atividade",
                                                  "espectadores"]
    g = _pub(p, "genero")
    assert (g["vazia"], g["dataFoto"], g["dataFotoOrigem"], g["situacao"]) == (
        False, str(min(ate + timedelta(days=1), hoje)), "historico", "novo")
    assert [(i["rotulo"], i["rotuloExibicao"], i["pct"]) for i in g["itens"]] == [
        ("feminino", "Feminino", 61.0), ("masculino", "Masculino", 37.5), ("outro", "Outro", 1.5)]
    assert g["contagens"] == {"gravados": 3, "iguais": 0, "divergentes": 0, "semDado": 0,
                              "faltando": [], "ignorados": []}
    t = _pub(p, "territorios")
    assert [i["rotulo"] for i in t["itens"]] == ["BR", "PT", "US"]
    a = _pub(p, "atividade")
    assert a["contagens"]["gravados"] == 168 and a["periodo"]["de"] == str(seg[0][0])
    melhor = max(((d, h) for d, _, _ in seg for h in range(24)),
                 key=lambda x: (ativos(*x), x[0], -x[1]))
    assert a["pico"] == {"dia": str(melhor[0]), "hora": melhor[1], "ativos": ativos(*melhor)}
    assert a["amostra"] is None
    e = _pub(p, "espectadores")
    assert e["contagens"]["gravados"] == 7 and e["contagens"]["semDado"] == 1
    assert e["totais"] == {"novos": sum(v[1] for v in VIEWERS),
                           "mediaTotal": round(sum(v[0] for v in VIEWERS[1:]) / 6, 1),
                           "mediaRecorrentes": round(41 / 7, 1)}
    assert e["amostra"][0] == {"dia": str(vw[0][0]), "total": None, "novos": 0,
                               "recorrentes": 0, "situacao": "novo"}
    codigos = [x["codigo"] for x in p["avisos"]]
    assert "sem_dado" in codigos and "espectadores_soma" not in codigos
    assert "data_foto_importacao" not in codigos
    assert p["periodo"]["de"] == str(min(seg[0][0], vw[0][0]))
    assert p["podeConfirmar"] is True and p["exigeConfirmacaoConta"] is False
    assert _contar(st.db) == (0, 0, 0, 0)  # nada gravado

    chave = previa.CHAVE.format(p["previaId"])
    assert 0 < get_redis().ttl(chave) <= 1800
    estado = json.loads(get_redis().get(chave))
    assert set(estado["publico"]) == {"genero", "territorios", "atividade", "espectadores"}
    assert estado["vazias"] == []
    assert len(estado["publico"]["atividade"]["linhas"]) == 168
    assert estado["publico"]["genero"]["dataFoto"] == g["dataFoto"]


def test_vazias_como_o_real(st):  # noqa: F811
    p = st.previa_ok(zip_seguidores(seguidores_dias(local(1).date(), 7), H))
    assert [(x["secao"], x["vazia"]) for x in p["publico"]] == [
        ("genero", True), ("territorios", True), ("atividade", True)]
    assert set(p["publico"][0]) >= {"secao", "vazia", "mensagem"}
    assert "cerca de 100" in p["publico"][0]["mensagem"]
    assert p["publico"][0]["itens"] is None
    assert [x for x in p["avisos"] if x["codigo"] == "secao_vazia"]
    estado = json.loads(get_redis().get(previa.CHAVE.format(p["previaId"])))
    assert estado["vazias"] == ["genero", "territorios", "atividade"]
    assert estado["publico"] == {}


def test_so_vazias_e_studio_sem_dados(st):  # noqa: F811
    r = st.previa(zip_seguidores(historico=False, handle=H))
    assert (r.status_code, err(r)) == (400, "studio_sem_dados"), r.text
    assert r.json()["error"]["details"]["secoes"] == ["genero", "territorios", "atividade"]
    vazio = ("Viewers_atavernanerd.zip", zip_bytes({"Viewers.xlsx": _xlsx_vazio()}))
    r = st.previa(vazio)
    assert (r.status_code, err(r)) == (400, "studio_sem_dados")
    assert list(get_redis().scan_iter("studio:previa:*")) == []


def _xlsx_vazio() -> bytes:
    from integration.studio_helpers import xlsx_viewers
    return xlsx_viewers([])


def test_genero_solto_usa_o_dia_da_importacao(st):  # noqa: F811
    p = st.previa_ok(("FollowerGender.csv", csv_genero()))
    g = _pub(p, "genero")
    assert (g["dataFoto"], g["dataFotoOrigem"]) == (str(local(0).date()), "importacao")
    assert "data_foto_importacao" in [x["codigo"] for x in p["avisos"]]
    assert p["exigeConfirmacaoConta"] is True  # CSV solto, sem o @
    assert p["periodo"] == {"de": str(local(0).date()), "ate": str(local(0).date()),
                            "anoOrigem": "deduzido"}
    assert p["podeConfirmar"] is True and p["secoes"] == []


def test_so_espectadores_pode_confirmar(st):  # noqa: F811
    p = st.previa_ok(zip_viewers(viewers_dias(local(1).date()), H))
    assert p["secoes"] == [] and p["podeConfirmar"] is True
    assert [a["secao"] for a in p["arquivos"]] == ["espectadores"]


def test_atividade_ordenada_pela_hora(st):  # noqa: F811
    from integration.studio_helpers import csv_atividade

    dias_ = [local(k).date() for k in (3, 2, 1)]
    a = csv_atividade(dias_, (0, 12), por_hora=True)
    p = st.previa_ok(("FollowerActivity.csv", a))
    at = _pub(p, "atividade")
    assert at["contagens"]["gravados"] == 6
    assert at["periodo"]["de"] == str(dias_[0]) and at["periodo"]["ate"] == str(dias_[-1])


def test_espectadores_soma_avisa_sem_bloquear(st):  # noqa: F811
    p = st.previa_ok(zip_viewers(viewers_dias(local(1).date()), H, defeito="soma"))
    [aviso] = [x for x in p["avisos"] if x["codigo"] == "espectadores_soma"]
    assert len(aviso["detalhes"]["dias"]) == 1


def test_csv_de_espectadores_hoje_e_ignorado(st):  # noqa: F811
    hoje = local(0).date()
    cab = ("Date", "Total Viewers", "New Viewers", "Returning Viewers")
    from integration.studio_helpers import data_en
    dados = csv_bytes(cab, [(data_en(hoje - timedelta(days=1)), "5", "5", "0"),
                            (data_en(hoje), "1", "1", "0")])
    p = st.previa_ok(("Viewers.csv", dados))
    e = _pub(p, "espectadores")
    assert e["contagens"]["gravados"] == 1 and e["contagens"]["ignorados"] == [str(hoje)]
    assert "dia_incompleto" in [x["codigo"] for x in p["avisos"]]
