"""Rotas do analytics (spec 019, T011; contracts/http-api.md): as 8 abas respondem 200 com o
`contexto` e as listas presentes, os erros comuns do filtro (400 `periodo_invalido`, 400
`conta_fora_do_perfil`, 404, validação) e o membro também lê; o custo do funil é `null` para ele."""

import uuid
from datetime import timedelta

import pytest

from integration.analytics_helpers import cena, err, hoje_sp, local, membro  # noqa: F401

ABAS = ("visao-geral", "quando-postar", "o-que-funciona", "curvas", "contas", "funil",
        "mercado", "alertas")
LISTAS = {
    "visao-geral": ("principais",),
    "quando-postar": (),
    "o-que-funciona": ("canais", "hashtags", "modos", "padroes"),
    "curvas": ("curvas", "distribuicao"),
    "contas": ("contas", "perfis"),
    "funil": ("etapas",),
    "mercado": ("oportunidades", "canais"),
    "alertas": ("alertas",),
}


@pytest.mark.parametrize("aba", ABAS)
def test_aba_responde_com_contexto_padrao(cena, aba):  # noqa: F811
    corpo = cena.ok(aba)
    ctx = corpo["contexto"]
    hoje = hoje_sp()
    assert (ctx["de"], ctx["ate"]) == (str(hoje - timedelta(days=6)), str(hoje))
    assert (ctx["anteriorDe"], ctx["anteriorAte"]) == (str(hoje - timedelta(days=13)),
                                                       str(hoje - timedelta(days=7)))
    assert ctx["medida"] == "h24" and ctx["fuso"] == "America/Sao_Paulo"
    assert ctx["minimos"] == {"grupo": 5, "correlacao": 8, "contasRadar": 2}
    assert (ctx["postsNoPeriodo"], ctx["aguardando"], ctx["foraDoSociman"]) == (0, 0, 0)
    for chave in LISTAS[aba]:
        assert corpo[chave] == [], chave


def test_contexto_conta_os_posts_do_filtro(cena):  # noqa: F811
    s = cena.semear(videos=3, fotos=30, inicio=local(4, 10))
    cena.vincular(s.videos[0])
    ctx = cena.ok("visao-geral", medida="d7")["contexto"]
    assert (ctx["postsNoPeriodo"], ctx["aguardando"], ctx["foraDoSociman"]) == (3, 3, 2)
    assert cena.ok("visao-geral", medida="h1")["contexto"]["aguardando"] == 0
    longe = cena.ok("curvas", de=str(local(60).date()), ate=str(local(50).date()))["contexto"]
    assert longe["postsNoPeriodo"] == 0 and longe["de"] == str(local(60).date())
    assert cena.ok("alertas", rede="youtube")["contexto"]["postsNoPeriodo"] == 0


@pytest.mark.parametrize("aba", ABAS)
def test_periodo_invalido(cena, aba):  # noqa: F811
    hoje = hoje_sp()
    r = cena.get(aba, de=str(hoje), ate=str(hoje - timedelta(days=1)))
    assert r.status_code == 400 and err(r) == "periodo_invalido"
    r = cena.get(aba, de=str(hoje - timedelta(days=400)), ate=str(hoje))
    assert r.status_code == 400 and err(r) == "periodo_invalido"


@pytest.mark.parametrize("aba", ABAS)
def test_conta_fora_do_perfil_e_inexistentes(cena, aba):  # noqa: F811
    outra = cena.segunda_conta("deoutroperfil", outro_perfil=True)
    r = cena.get(aba, perfilId=cena.perfil["id"], contaId=outra["id"])
    assert r.status_code == 400 and err(r) == "conta_fora_do_perfil"
    r = cena.get(aba, perfilId=str(uuid.uuid4()))
    assert r.status_code == 404 and err(r) == "not_found"
    r = cena.get(aba, contaId=str(uuid.uuid4()))
    assert r.status_code == 404 and err(r) == "not_found"
    # a conta certa do perfil passa
    assert cena.get(aba, perfilId=cena.perfil["id"], contaId=cena.conta["id"]).status_code == 200


def test_validacao_dos_parametros(cena):  # noqa: F811
    # O app devolve a validação do FastAPI como 400 `validation_error` (errors.py).
    for aba, params in (("visao-geral", {"medida": "d30"}), ("visao-geral", {"rede": "orkut"}),
                        ("visao-geral", {"de": "ontem"}), ("funil", {"patamar": 0})):
        r = cena.get(aba, **params)
        assert r.status_code == 400 and err(r) == "validation_error", params
    assert cena.ok("funil", patamar=50)["patamar"] == 50
    assert cena.ok("funil")["patamar"] == 100


@pytest.mark.parametrize("aba", ABAS)
def test_membro_le_e_anonimo_nao(cena, membro, aba):  # noqa: F811
    _, h = membro
    assert cena.get(aba, h=h).status_code == 200
    r = cena.client.get(f"/api/analytics/{aba}")
    assert r.status_code == 401


def test_custo_do_funil_e_null_para_o_membro(cena, membro):  # noqa: F811
    _, h = membro
    corpo = cena.ok("funil", h=h)
    assert corpo["custoIaUsd"] is None and corpo["custoPorMilViewsUsd"] is None


def test_so_get_em_analytics(cena):  # noqa: F811
    for aba in ABAS:
        for metodo in ("post", "put", "patch", "delete"):
            r = cena.client.request(metodo.upper(), f"/api/analytics/{aba}", headers=cena.h)
            assert r.status_code == 405, (metodo, aba)
