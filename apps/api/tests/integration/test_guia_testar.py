"""Testar o guia do formulário (spec 017, T041; US3, research R10): 3 variações com as fixas e as
proibidas do guia **em teste**; formulário inválido não chama o Claude; grava só a chamada."""

import uuid

from fakes.anthropic_fake import anthropic_fake, variacoes  # noqa: F401
from sqlalchemy import func, select

from integration.guia_ia_helpers import campos, cena, fake, guia_conta, guia_perfil  # noqa: F401
from integration.postagem_helpers import dono, membro  # noqa: F401
from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaChamada, IaDesfecho
from sociman_api.postagem.models import Postagem


def _testar(client, c, h=None, status=200, nivel="perfil", conta="tiktok", **guia_kw):
    body = {"perfilId": c["perfil"]["id"], "nivel": nivel, "contaId": c[conta]["id"],
            "alvo": {"entityType": "corte", "entityId": str(c["corte"].id)},
            "guia": campos(**guia_kw)}
    r = client.post("/api/ia/guia/testar", headers=h or c["h"], json=body)
    assert r.status_code == status, r.text
    return r.json()["chamada"] if status == 200 else r.json()


def _versoes(db) -> int:
    return db.scalar(select(func.count()).select_from(EntityVersion))


def test_tres_variacoes_com_o_guia_em_teste(client, db, cena, fake):  # noqa: F811
    c = cena
    guia_perfil(client, c, tom="Salvo", hashtagsFixas=["#salva"])
    guia_conta(client, c, tom="Conta salva")
    antes = _versoes(db)
    fake.responder(variacoes(), variacoes())
    ch = _testar(client, c, tom="Rascunho em teste", hashtagsFixas=["#emteste"],
                 proibidas=["versão"])
    vs = ch["proposta"]["variacoes"]
    assert len(vs) == 3 and all(v["hashtags"][0] == "#emteste" for v in vs)
    assert all("#salva" not in v["hashtags"] for v in vs)
    assert ch["proibidas"] == ["versão"] and len(fake.requests) == 2
    assert ch["tipoCampo"] == "guia.testar" and ch["guiaRascunho"] == "perfil"
    assert ch["guiaPerfilVersion"] == 1 and ch["guiaContaVersion"] == 1
    assert ch["entrada"]["guia"]["tom"] == "Rascunho em teste"
    assert ch["desfecho"] == "sem_acao"
    system = fake.systems[0]
    assert '<guia_em_teste nivel="perfil" versao_base="1">' in system
    assert "Rascunho em teste" in system and "Tom de voz: Salvo" not in system
    assert '<guia_conta versao="1">' in system
    # nada muda: nenhuma versão e nenhum destino
    assert _versoes(db) == antes
    assert db.scalar(select(func.count()).select_from(Postagem)) == 0
    assert db.get(IaChamada, uuid.UUID(ch["id"])).desfecho == IaDesfecho.sem_acao


def test_nivel_conta_sem_guia_salvo_tem_base_0(client, cena, fake):  # noqa: F811
    c = cena
    ch = _testar(client, c, nivel="conta", tom="Conta em teste", hashtagsFixas=["#nova"])
    assert ch["guiaRascunho"] == "conta" and ch["guiaContaVersion"] == 0
    assert ch["guiaPerfilVersion"] is None
    assert '<guia_em_teste nivel="conta" versao_base="0">' in fake.systems[0]


def test_formulario_invalido_nao_chama_o_claude(client, cena, fake):  # noqa: F811
    body = _testar(client, cena, status=400, tom="a" * 501)
    assert body["error"]["code"] == "validation_error"
    assert "tom" in body["error"]["details"]["fields"]
    assert not fake.requests


def test_formulario_da_conta_valida_a_soma_das_fixas(client, cena, fake):  # noqa: F811
    c = cena
    guia_perfil(client, c, hashtagsFixas=["#a", "#b", "#c"])
    body = _testar(client, c, status=400, nivel="conta", hashtagsFixas=["#d", "#e", "#f"])
    assert "hashtagsFixas" in body["error"]["details"]["fields"] and not fake.requests


def test_sem_conta_e_recusado(client, cena, fake):  # noqa: F811
    c = cena
    r = client.post("/api/ia/guia/testar", headers=c["h"], json={
        "perfilId": c["perfil"]["id"], "nivel": "perfil",
        "alvo": {"entityType": "corte", "entityId": str(c["corte"].id)}, "guia": campos()})
    assert r.status_code == 400 and not fake.requests


def test_membro_nao_testa(client, cena, membro, fake):  # noqa: F811
    body = _testar(client, cena, h=membro[1], status=403)
    assert body["error"]["code"] == "forbidden" and not fake.requests


def test_chamada_do_testar_nunca_e_aplicada(client, db, cena, fake):  # noqa: F811
    c = cena
    ch = _testar(client, c)
    v = ch["proposta"]["variacoes"][0]
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], "titulo": v["titulo"],
                          "descricao": v["descricao"], "hashtags": v["hashtags"],
                          "ia": [{"tipoCampo": "guia.testar", "chamadaId": ch["id"]}]})
    assert r.status_code == 201, r.text
    db.expire_all()
    assert db.get(IaChamada, uuid.UUID(ch["id"])).desfecho == IaDesfecho.sem_acao
