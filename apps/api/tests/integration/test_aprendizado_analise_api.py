"""Análise na leitura pela API (spec 023, T028; US2): o GET não grava nada; o bloco de hashtags e
o "não separável" sobre os dados semeados; a conta travada; os filtros (conta, medida, período)
e os aguardando."""

from datetime import timedelta

from sqlalchemy import func, select

from integration.analytics_helpers import agora, cena, hoje_sp  # noqa: F401
from integration.aprendizado_helpers import (  # noqa: F401
    ap,
    estagnados,
    membro,
    semear_aprendizado,
)
from sociman_api.aprendizado import models as m
from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaChamada

TABELAS = (EntityVersion, m.Tema, m.Classificacao, m.Preferencias, m.Analise, m.Decisao,
           m.Conferencia, IaChamada)


def _contagens(db) -> tuple[int, ...]:
    db.expire_all()
    return tuple(db.scalar(select(func.count()).select_from(t)) for t in TABELAS)


def test_get_nao_grava_e_mostra_bloco_e_nao_separavel(ap, estagnados, membro):  # noqa: F811
    semear_aprendizado(ap)
    estagnados |= set(ap.posts["b_baixos"])
    antes = _contagens(ap.db)
    _, hm = membro
    an = ap.get("analise", h=hm)
    ap.get("recomendacoes")
    ap.get("diagnostico")
    ap.get("preferencias")
    ap.get("classificacoes")
    assert _contagens(ap.db) == antes

    [bloco] = [b for b in an["blocos"] if len(b["hashtags"]) == 3]
    assert bloco["hashtags"] == ["multiversomarvel", "vingadoresdoomsday", "geek"]
    assert bloco["nPosts"] == 8
    e = ap.efeito(an, "hashtag", bloco["valor"])
    assert e["efeito"] is None and e["avisos"][0]["tipo"] == "nao_separavel"
    assert e["avisos"][0]["temaNome"] == "Marvel"
    marvel = ap.temas["Marvel"]["id"]
    assert {"bloco": bloco["valor"], "temaId": marvel, "temaNome": "Marvel", "n": 8} in an["matriz"]
    tema = ap.efeito(an, "tema", marvel)
    assert tema["nPosts"] == 8 and tema["nDias"] == 8 and tema["efeito"] > 1
    ctx = an["contexto"]
    contas = {c["rotulo"]: c for c in ctx["contas"]}
    assert contas["@segundaconta"]["travada"] and not contas["@atavernanerd"]["travada"]
    assert ctx["travadas"] == [ap.conta_b["id"]]
    assert ctx["comparacoes"] > 0 and ctx["constantes"]["minGrupo"] == 5
    anime = ap.efeito(an, "tema", ap.temas["Anime"]["id"])
    assert anime["confianca"] == "amostra_pequena" and anime["faltam"] == 1
    assert anime["medianaBruta"] == 300


def test_filtros_conta_medida_periodo_e_aguardando(ap, estagnados):  # noqa: F811
    semear_aprendizado(ap, conta_b=True)
    so_a = ap.get("analise", contaId=ap.c.conta["id"])
    assert [c["rotulo"] for c in so_a["contexto"]["contas"]] == ["@atavernanerd"]
    curto = ap.get("analise", de=str(hoje_sp() - timedelta(days=5)), ate=str(hoje_sp()))
    assert curto["contexto"]["de"] == str(hoje_sp() - timedelta(days=5))
    assert all(not c["suficiente"] for c in curto["contexto"]["contas"])
    ap.post(publicado=agora() - timedelta(hours=3))
    assert ap.get("analise")["contexto"]["aguardando"] == 1
    assert ap.get("analise", medida="h1")["contexto"]["medida"] == "h1"
    ap.get("analise", status=400, medida="h48")
    r = ap.client.get(f"{ap.url}/analise", headers=ap.h,
                      params={"contaId": "00000000-0000-4000-8000-000000000000"})
    assert r.status_code == 404
