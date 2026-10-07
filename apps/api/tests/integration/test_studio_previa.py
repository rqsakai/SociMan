"""Pré-visualização (spec 020, US1, T014): os 2 ZIPs (período, ano pelo nome, seções, ignorados,
totais, amostra de 5 + 5), nada gravado, a chave no Redis com TTL ≤ 30 min, só uma seção, e as
contagens `coletados`/`iguais`/`divergentes`/`faltando`/`ignorados`."""

from datetime import timedelta

from integration.analytics_helpers import cena, hoje_sp, local  # noqa: F401
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
from sociman_api.metricas.studio import previa
from sociman_api.redis import get_redis

H = "atavernanerd"


def _secao(p, nome):
    [s] = [s for s in p["secoes"] if s["secao"] == nome]
    return s


def test_previa_com_os_dois_zips_nao_grava(st):  # noqa: F811
    ate = local(1).date()
    vg, seg = overview_dias(ate, 12), seguidores_dias(ate, 12)
    p = st.previa_ok(zip_overview(vg, H), zip_seguidores(seg, H))
    assert p["conta"]["handle"] == H and p["conta"]["perfil"] == st.perfil["name"]
    assert p["periodo"] == {"de": str(vg[0].dia), "ate": str(ate), "anoOrigem": "nome_zip"}
    arquivos = {a["secao"]: a for a in p["arquivos"]}
    assert arquivos["visao_geral"]["tipo"] == "zip" and arquivos["visao_geral"]["handle"] == H
    # spec 022 (FR-004, FR-006): os 3 CSVs de público são lidos; só com o cabeçalho, aparecem
    # como seções vazias em `publico[]`, e não mais em `ignorados`
    assert arquivos["seguidores"]["ignorados"] == []
    assert [(x["secao"], x["vazia"]) for x in p["publico"]] == [
        ("genero", True), ("territorios", True), ("atividade", True)]
    s = _secao(p, "visao_geral")
    assert s["jaImportada"] is None
    assert s["contagens"] == {"gravados": 12, "iguais": 0, "divergentes": 0, "coletados": 0,
                              "faltando": [], "ignorados": []}
    assert s["totais"]["views"] == sum(x.views for x in vg)
    assert s["totais"]["likes"] == sum(x.likes for x in vg)
    assert s["colunas"]["ausentes"] == [] and len(s["colunas"]["reconhecidas"]) == 6
    amostra = [a["dia"] for a in s["amostra"]]
    assert amostra == [str(x.dia) for x in vg[:5] + vg[-5:]]
    assert {a["situacao"] for a in s["amostra"]} == {"novo"}
    t = _secao(p, "seguidores")["totais"]
    assert (t["seguidoresInicio"], t["seguidoresFim"]) == (seg[0][1], seg[-1][1])
    assert t["ganhos"] == seg[-1][1] - seg[0][1]
    assert p["exigeConfirmacaoConta"] is False and p["podeConfirmar"] is True
    assert st.contar() == (0, 0)
    ttl = get_redis().ttl(previa.CHAVE.format(p["previaId"]))
    assert 0 < ttl <= 1800


def test_so_uma_secao(st):  # noqa: F811
    p = st.previa_ok(zip_overview(overview_dias(n=3), H))
    assert [s["secao"] for s in p["secoes"]] == ["visao_geral"]
    p = st.previa_ok(zip_seguidores(seguidores_dias(n=3), H))
    assert [s["secao"] for s in p["secoes"]] == ["seguidores"]
    assert p["periodo"]["anoOrigem"] == "deduzido"  # Seguidores sozinho não tem o ano no nome
    assert "ano_deduzido" in {a["codigo"] for a in p["avisos"]}


def test_contagens_coletados_iguais_divergentes_faltando_e_ignorados(st):  # noqa: F811
    serie = st.serie()
    hoje = hoje_sp()
    # 1ª coleta em D−2 → D−1 é o 1º dia coberto
    semear_coleta(st.db, st.conta_id, local(2, 9), serie_id=serie)
    # já importado: D−6 e D−5
    st.importar(zip_overview([DiaOverview(local(6).date(), 10), DiaOverview(local(5).date(), 20)],
                             H))
    # arquivo novo: D−6 igual, D−5 divergente, D−4 falta, D−3, D−2 (dia da 1ª coleta),
    # D−1 coberto e hoje (incompleto); CSV solto para o nome não precisar bater com hoje
    linhas = [DiaOverview(local(6).date(), 10), DiaOverview(local(5).date(), 99),
              DiaOverview(local(3).date(), 30), DiaOverview(local(2).date(), 40),
              DiaOverview(local(1).date(), 50), DiaOverview(hoje, 60)]
    p = st.previa_ok(("Overview.csv", csv_overview(linhas)))
    c = _secao(p, "visao_geral")["contagens"]
    assert c == {"gravados": 5, "iguais": 1, "divergentes": 1, "coletados": 1,
                 "faltando": [str(local(4).date())], "ignorados": [str(hoje)]}
    situacoes = [a["situacao"] for a in _secao(p, "visao_geral")["amostra"]]
    assert situacoes == ["igual", "divergente", "novo", "novo", "coletado", "ignorado"]
    codigos = {a["codigo"] for a in p["avisos"]}
    assert {"dia_incompleto", "dias_faltando", "ano_deduzido"} <= codigos
    assert p["periodo"]["ate"] == str(local(1).date())  # hoje fica fora do período
    assert p["exigeConfirmacaoConta"] is True


def test_amostra_e_totais_com_coluna_ausente(st):  # noqa: F811
    from integration.studio_helpers import csv_bytes

    ate = local(1).date()
    dias = [ate - timedelta(days=k) for k in (2, 1, 0)]
    dados = csv_bytes(("Date", "Video Views"), [(f"{d:%B} {d.day}", 5) for d in dias])
    p = st.previa_ok(("Overview.csv", dados))
    s = _secao(p, "visao_geral")
    assert s["totais"] == {"views": 15, "visitasPerfil": None, "likes": None, "comments": None,
                           "shares": None}
    assert s["colunas"]["ausentes"] == ["Profile Views", "Likes", "Comments", "Shares"]
    assert "colunas_ausentes" in {a["codigo"] for a in p["avisos"]}
