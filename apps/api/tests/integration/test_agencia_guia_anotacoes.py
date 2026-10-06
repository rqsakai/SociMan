"""Guia, anotações e sugestões de bordão (spec 013, US5, T038)."""

from sqlalchemy import select

from integration.agencia_helpers import (  # noqa: F401
    _buckets,
    agencia,
    confirmar,
    dono,
    importar,
    itens,
    previa,
    um,
    yt,
)
from sociman_api.anotacoes.models import Anotacao, AnotacaoAlvo, AnotacaoSituacao
from sociman_api.ia.models import IaGuia


def test_guia_vazio_vira_versao_1(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil(proibido="NSFW, política (já cobre o essencial)")
    importar(client, h)
    guia = db.scalars(select(IaGuia)).one()
    assert guia.version == 1
    assert guia.tom == "Humor descontraído"
    assert guia.vocabulario == ["Senta que tem lugar", "Essa foi crit 1"]
    assert guia.nao_faca == ["NSFW", "política (já cobre o essencial)"]
    assert guia.proibidas == []
    assert um(previa(client, h), "guia")["situacao"] == "igual"


def test_guia_editado_diverge_e_so_troca_com_escolha(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    r = client.post("/api/perfis", headers=h, json={"name": "Taverna Teste",
                                                     "slug": "taverna-teste", "status": "ativo",
                                                     "niche": "RPG e colecionáveis"})
    perfil = r.json()["perfil"]
    r = client.put(f"/api/perfis/{perfil['id']}/guia", headers=h, json={
        "version": 0, "campos": {"tom": "Sério", "faca": ["Citar a fonte"]}})
    assert r.status_code == 200, r.text
    agencia.perfil()
    p = previa(client, h)
    g = um(p, "guia")
    assert (g["situacao"], g["motivo"]) == ("diverge", "editado")
    assert g["atual"]["tom"] == "Sério" and g["proposto"]["tom"] == "Humor descontraído"
    confirmar(client, h, p)
    guia = db.scalars(select(IaGuia)).one()
    assert guia.tom == "Sério" and guia.version == 1

    p = previa(client, h)
    confirmar(client, h, p, [{"n": um(p, "guia")["n"], "usar": "markdown"}])
    db.refresh(guia)
    assert guia.tom == "Humor descontraído" and guia.faca == ["Citar a fonte"]
    assert guia.version == 2


def test_anotacoes_por_secao_e_decisao(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil(decisoes="\n".join(f"| 2026-09-{d:02d} | Decisão {d} | Motivo {d} |"
                                      for d in range(1, 14)))
    agencia.pesquisa("taverna-teste", {"1. Termos de busca": "- PT: rpg",
                                       "2. Hashtags": "",
                                       "3. Grande": "texto longo " * 500})
    importar(client, h)
    anot = db.scalars(select(Anotacao).where(Anotacao.alvo_tipo == AnotacaoAlvo.perfil)).all()
    textos = [a.texto for a in anot]
    decisoes = [t for t in textos if t.startswith("perfil.md §8.")]
    assert len(decisoes) == 13
    assert any("Decisão: Decisão 7\nPor quê: Motivo 7" in t for t in decisoes)
    assert sum(t.startswith("perfil.md §3. Público") for t in textos) == 1
    assert sum(t.startswith("perfil.md §6. Monetização") for t in textos) == 1
    assert not any(t.startswith("perfil.md §7.") for t in textos)  # só molde
    assert not any("Hashtags" in t.split("\n")[0] for t in textos)  # seção vazia
    grandes = [t for t in textos if t.startswith("pesquisa.md §3. Grande")]
    assert len(grandes) == 2 and "(1/2)" in grandes[0].split("\n")[0]
    assert all(len(t) <= 4000 for t in textos)
    assert previa(client, h)["contagens"]["novo"] == 0  # reimportar: igual


def test_secao_alterada_diverge_e_edita_a_anotacao(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil()
    agencia.pesquisa("taverna-teste", {"1. Termos de busca": "- PT: rpg"})
    importar(client, h)
    agencia.pesquisa("taverna-teste", {"1. Termos de busca": "- PT: rpg, d&d"})
    p = previa(client, h)
    a = um(p, "anotacao", situacao="diverge")
    assert "rpg, d&d" in a["proposto"]["texto"] and "d&d" not in a["atual"]["texto"]
    confirmar(client, h, p, [{"n": a["n"], "usar": "markdown"}])
    pesq = [x for x in db.scalars(select(Anotacao)) if x.texto.startswith("pesquisa.md")]
    assert len(pesq) == 1 and "rpg, d&d" in pesq[0].texto and pesq[0].version == 2
    assert pesq[0].situacao == AnotacaoSituacao.aberta
    assert previa(client, h)["contagens"]["diverge"] == 0


def test_sugestoes_de_bordao_sem_mudar_o_kit(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil()
    p, _ = importar(client, h)
    sug = itens(p, "sugestao_bordao")
    assert sorted(s["proposto"]["bordao"] for s in sug) == ["Essa foi crit 1",
                                                          "Senta que tem lugar"]
    perfil_id = client.get("/api/perfis", headers=h).json()["items"][0]["id"]
    kit = client.get(f"/api/perfis/{perfil_id}/kit", headers=h).json()
    assert "Essa foi crit 1" not in str(kit)
