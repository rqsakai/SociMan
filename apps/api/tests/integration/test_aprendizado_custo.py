"""Custo e controle (spec 023, T058; SC-009; FR-051 a FR-053): o resumo do mês separa as
finalidades; o membro não vê custo; com a classificação automática pausada, o post fica
pendente e conta como "pendente de classificação" na análise."""

import uuid
from decimal import Decimal

from fakes.anthropic_fake import anthropic_fake  # noqa: F401

from integration.analytics_helpers import agora, cena  # noqa: F401
from integration.aprendizado_helpers import ap, estagnados, membro  # noqa: F401
from sociman_api.aprendizado import trilha
from sociman_api.ia.models import IaChamada, IaDesfecho


def _chamada(ap, tipo, usd):  # noqa: F811
    ap.db.add(IaChamada(tipo_campo=tipo, perfil_id=uuid.UUID(ap.perfil_id), entity_type="perfil",
                        model="claude-fake", prompt_version="ia/3", duration_ms=1,
                        custo_usd=Decimal(usd), desfecho=IaDesfecho.sem_acao))
    ap.db.commit()


def test_resumo_separa_as_finalidades_e_membro_sem_custo(ap, membro):  # noqa: F811
    for tipo, usd in (("aprendizado.taxonomia", "0.010"), ("aprendizado.classificacao", "0.002"),
                      ("aprendizado.classificacao", "0.002"), ("aprendizado.analise", "0.050")):
        _chamada(ap, tipo, usd)
    r = ap.client.get("/api/ia/resumo", headers=ap.h)
    assert r.status_code == 200, r.text
    por_tipo = {t["tipoCampo"]: t for t in r.json()["porTipo"]}
    assert por_tipo["aprendizado.classificacao"] == {
        "tipoCampo": "aprendizado.classificacao", "chamadas": 2, "custoUsd": 0.004}
    assert por_tipo["aprendizado.analise"]["custoUsd"] == 0.05
    assert por_tipo["aprendizado.taxonomia"]["chamadas"] == 1
    _, hm = membro
    assert ap.client.get("/api/ia/resumo", headers=hm).status_code == 403


def test_classificacao_pausada_deixa_pendente(ap, estagnados, anthropic_fake):  # noqa: F811
    ap.tema("Marvel")
    for d in range(2, 20):
        ap.post(dias=d, views=100 + d)
    v = ap.get("preferencias")["perfil"]["version"]
    ap.client.patch(f"{ap.url}/preferencias", headers=ap.h,
                    json={"version": v, "classificacaoAuto": False})
    trilha.rodar(ap.db, client=anthropic_fake.ia_client(), agora=agora())
    assert anthropic_fake.requests == []
    an = ap.get("analise")
    assert an["pendentesClassificacao"] == 18 and an["semTema"] == 0
    assert not [e for e in an["efeitos"] if e["fator"] == "tema"]
