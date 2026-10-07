"""Aba Público do analytics (spec 022, US3, T030 e T031; SC-006), com cálculo de referência:
- a foto válida (FR-016, resposta A): dentro do período, anterior ao início, sem foto; a
  comparação em p.p. com a foto válida no fim do período anterior; `novo`/`saiu`; `outrosPct`;
  `seguidoresNaData`;
- o mapa (FR-017, resposta A): média e n por célula, amostra pequena, dias fora do período, o
  período sem dado com `ultimoDiaComDado`;
- os espectadores: a série com nulos, os novos somados, as médias e a variação;
- os motivos, várias contas, a conta anonimizada, o desfazer e o membro;
- **T031:** visão geral, quando postar (sem o campo novo), contas e alertas idênticos com e sem
  dados de público."""

from datetime import date

from integration.analytics_helpers import cena, local, membro  # noqa: F401
from integration.studio_helpers import (
    csv_atividade,
    csv_bytes,
    csv_genero,
    csv_seguidores,
    csv_territorios,
    data_en,
    seguidores_dias,
    st,  # noqa: F401
    viewers_dias,
    zip_bytes,
    zip_seguidores,
    zip_viewers,
)
from sociman_api.auth.deps import Actor
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import Serie

H = "atavernanerd"


def _d(k: int) -> date:
    return local(k).date()


def _followers(ate: date, genero=None, territorios=None, handle: str = H):
    """Um ZIP de Seguidores com o histórico até `ate` (a foto fica em `ate + 1`)."""
    entradas = {"FollowerHistory.csv": csv_seguidores(seguidores_dias(ate, 3))}
    if genero is not None:
        entradas["FollowerGender.csv"] = csv_genero(genero)
    if territorios is not None:
        entradas["FollowerTopTerritories.csv"] = csv_territorios(territorios)
    return f"Followers_{handle}.zip", zip_bytes(entradas)


def _conta(corpo: dict, i: int = 0) -> dict:
    return corpo["contas"][i]


def _publico(st, de: date, ate: date, h=None, **kw) -> dict:  # noqa: F811
    return st.ok("publico", h=h, de=str(de), ate=str(ate), **kw)


G1 = (("Female", "60%"), ("Male", "40%"))
G2 = (("Female", "55%"), ("Male", "43%"), ("Other", "2%"))


def test_foto_valida_comparacao_e_seguidores(st):  # noqa: F811
    st.importar(_followers(_d(10), G1, (("BR", "90%"), ("PT", "5%"))))  # foto em D−9
    st.importar(_followers(_d(3), G2, (("BR", "92%"), ("US", "3%"))))  # foto em D−2

    c = _conta(_publico(st, _d(5), _d(1)))
    g = c["genero"]
    assert (g["dataFoto"], g["anteriorAoPeriodo"], g["dataFotoComparacao"]) == (
        str(_d(2)), False, str(_d(9)))
    assert g["seguidoresNaData"] == seguidores_dias(_d(3), 3)[-1][1]
    por = {i["rotulo"]: i for i in g["itens"]}
    assert (por["feminino"]["pct"], por["feminino"]["pctComparacao"],
            por["feminino"]["difPp"]) == (55.0, 60.0, -5.0)
    assert (por["outro"]["marca"], por["outro"]["difPp"]) == ("novo", None)
    assert por["masculino"]["marca"] is None and g["outrosPct"] is None
    t = c["territorios"]
    rot = {i["rotulo"]: i for i in t["itens"]}
    assert (rot["US"]["marca"], rot["PT"]["marca"], rot["PT"]["pct"]) == ("novo", "saiu", None)
    assert t["outrosPct"] == 5.0
    assert c["motivos"]["genero"] is None

    # a foto de antes do início vale, com a data em destaque; a comparação seria a mesma data
    g = _conta(_publico(st, _d(1), _d(0)))["genero"]
    assert (g["dataFoto"], g["anteriorAoPeriodo"], g["dataFotoComparacao"]) == (
        str(_d(2)), True, None)
    assert all(i["marca"] is None for i in g["itens"])

    # sem foto até o fim do período
    c = _conta(_publico(st, _d(20), _d(15)))
    assert c["genero"] is None and c["motivos"]["genero"] == "sem_dado_no_periodo"


def test_mapa_media_n_e_periodo(st):  # noqa: F811
    dias_ = [_d(k) for k in (9, 8, 2, 1)]
    st.importar(("FollowerActivity.csv", csv_atividade(dias_, (20, 21))), confirmo=True)
    c = _conta(_publico(st, _d(8), _d(1)))  # D−9 fica fora
    a = c["atividade"]
    assert len(a["celulas"]) == 168 and a["diasComDado"] == 3
    assert a["ultimoDiaComDado"] == str(_d(1))
    from integration.studio_helpers import ativos
    esperado: dict[tuple[int, int], list[int]] = {}
    for d in dias_[1:]:
        for h in (20, 21):
            esperado.setdefault((d.weekday(), h), []).append(ativos(d, h))
    for cel in a["celulas"]:
        vs = esperado.get((cel["dia"], cel["hora"]), [])
        assert cel["n"] == len(vs)
        assert cel["valor"] == (round(sum(vs) / len(vs), 1) if vs else None)
        assert cel["amostraPequena"] == (0 < len(vs) < 2)
    assert c["motivos"]["atividade"] is None

    vazio = _conta(_publico(st, _d(30), _d(25)))
    assert vazio["motivos"]["atividade"] == "sem_dado_no_periodo"
    assert vazio["atividade"]["ultimoDiaComDado"] == str(_d(1))
    assert all(x["valor"] is None and x["n"] == 0 for x in vazio["atividade"]["celulas"])


def test_espectadores_serie_indicadores_e_variacao(st):  # noqa: F811
    antes = [(d, (10, 8, 2)) for d, _ in viewers_dias(_d(8), [(0, 0, 0)] * 7)]
    agora = viewers_dias(_d(1))
    st.importar(zip_viewers(antes, H))
    st.importar(zip_viewers(agora, H))
    e = _conta(_publico(st, _d(7), _d(1)))["espectadores"]
    assert [x["total"] for x in e["serie"]] == [v[0] for _, v in agora]
    assert e["diasSemDado"] == 1
    novos = sum(v[1] for _, v in agora)
    assert e["novos"] == {"valor": novos, "anterior": 56.0,
                          "variacaoPct": round((novos - 56) / 56, 4), "n": 7}
    media = round(sum(v[0] for _, v in agora[1:]) / 6, 1)
    assert (e["mediaTotal"]["valor"], e["mediaTotal"]["n"], e["mediaTotal"]["anterior"]) == (
        media, 6, 10.0)
    assert e["mediaRecorrentes"]["valor"] == round(41 / 7, 1)
    sem_base = _conta(_publico(st, _d(1), _d(1)))["espectadores"]
    assert sem_base["novos"]["anterior"] is not None  # D−2 tem valor
    longe = _conta(_publico(st, _d(30), _d(20)))
    assert longe["espectadores"] is None
    assert longe["motivos"]["espectadores"] == "sem_dado_no_periodo"


def test_motivos(st):  # noqa: F811
    c = _conta(_publico(st, _d(7), _d(0)))
    assert c["motivos"] == {"genero": "sem_importacao", "territorios": "sem_importacao",
                            "atividade": "sem_importacao", "espectadores": "sem_importacao"}
    st.importar(zip_seguidores(seguidores_dias(_d(1), 3), H))  # as 3 vazias, como o real
    c = _conta(_publico(st, _d(7), _d(0)))
    assert c["motivos"] == {"genero": "veio_vazia", "territorios": "veio_vazia",
                            "atividade": "veio_vazia", "espectadores": "sem_importacao"}
    assert c["conta"]["rotulo"] == f"@{H}" and c["conta"]["ordem"] == 0


def test_varias_contas_sem_misturar(st):  # noqa: F811
    outra = st.segunda_conta("contab", outro_perfil=True)
    st.serie(outra)
    st.importar(("FollowerGender.csv", csv_genero(G1)), confirmo=True)
    p = st.previa_ok(("FollowerGender.csv", csv_genero(G2)), conta_id=outra["id"])
    assert st.confirmar(p["previaId"], confirmo=True, conta_id=outra["id"]).status_code == 201
    corpo = _publico(st, _d(1), _d(0))
    assert [c["conta"]["rotulo"] for c in corpo["contas"]] == [f"@{H}", "@contab"]
    assert [c["conta"]["ordem"] for c in corpo["contas"]] == [0, 1]
    assert [c["genero"]["itens"][0]["pct"] for c in corpo["contas"]] == [60.0, 55.0]
    so_b = _publico(st, _d(1), _d(0), contaId=outra["id"])
    assert [c["conta"]["rotulo"] for c in so_b["contas"]] == ["@contab"]


def test_conta_anonimizada(st):  # noqa: F811
    st.importar(("FollowerGender.csv", csv_genero(G1)), confirmo=True)
    serie = st.db.get(Serie, st.serie())
    anonimizar.serie(st.db, serie, Actor(kind="user", user_id=st.dono.id))
    st.db.commit()
    corpo = _publico(st, _d(1), _d(0))
    [c] = [c for c in corpo["contas"] if c["conta"]["contaId"] is None]
    assert c["conta"]["rotulo"].startswith("Conta anônima")
    assert c["conta"]["serieId"] is None and c["genero"]["itens"][0]["rotulo"] == "feminino"


def test_desfazer_volta_ao_anterior(st):  # noqa: F811
    antes = _publico(st, _d(7), _d(0))
    imp = st.importar(zip_viewers(viewers_dias(_d(1)), H))
    assert _conta(_publico(st, _d(7), _d(0)))["espectadores"] is not None
    st.desfazer(imp)
    assert _publico(st, _d(7), _d(0)) == antes


def test_membro_le(st, membro):  # noqa: F811
    _, h = membro
    st.importar(("FollowerGender.csv", csv_genero(G1)), confirmo=True)
    assert _conta(_publico(st, _d(1), _d(0), h=h))["genero"] is not None


# ---- T031: as rotas da 019/020 não mudam com o público ----

def _sem_campo_novo(corpo: dict) -> dict:
    corpo = dict(corpo)
    corpo.pop("atividadeSeguidores", None)
    return corpo


def test_regressao_das_rotas_com_e_sem_publico(st):  # noqa: F811
    st.semear(videos=3, fotos=40, inicio=local(9, 10), intervalo_h=48, serie_id=st.serie())
    st.importar(zip_seguidores(seguidores_dias(_d(12), 3), H))
    abas = ("visao-geral", "quando-postar", "contas", "alertas")
    periodos = ({}, {"de": str(_d(13)), "ate": str(_d(0))})
    antes = {(a, i): _sem_campo_novo(st.ok(a, **p)) for a in abas
             for i, p in enumerate(periodos)}
    dias_ = [_d(k) for k in range(7, 0, -1)]
    st.importar(("FollowerActivity.csv", csv_atividade(dias_)), confirmo=True)
    st.importar(zip_viewers(viewers_dias(_d(1)), H))
    st.importar(("FollowerGender.csv", csv_genero(G1)), confirmo=True)
    st.importar(("FollowerTopTerritories.csv", csv_territorios((("BR", "90%"),))),
                confirmo=True)
    st.importar(("Espectadores.csv", csv_bytes(
        ("Date", "Total Viewers"), [(data_en(_d(20)), "5")])), confirmo=True)
    depois = {(a, i): _sem_campo_novo(st.ok(a, **p)) for a in abas
              for i, p in enumerate(periodos)}
    assert depois == antes
    qp = st.ok("quando-postar", **periodos[1])["atividadeSeguidores"]
    assert qp["contas"][0]["atividade"]["diasComDado"] == 7
