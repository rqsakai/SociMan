"""Sugestão de textos pela API (T063, R9): plataforma da conta, erros em pt-BR, registro de
cada chamada em `ia_chamadas`, e a sugestão não altera a postagem. Claude falso.

Spec 008 (T043): as rotas da 006 continuam respondendo `{ sugestao }`, agora pelo assistente
(`postagem.textos`), com os códigos de erro novos (`ia_timeout`…)."""

import json

import pytest
from fakes.anthropic_fake import anthropic_fake, fixture, mensagem  # noqa: F401

from integration.postagem_helpers import (  # noqa: F401
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
)
from sociman_api.ia.cliente import get_ia_client
from sociman_api.ia.models import IaChamada
from sociman_api.main import app


@pytest.fixture
def cenario(client, db, dono, anthropic_fake):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], "youtube", "tavernanerd")
    corte = criar_corte(db, perfil["id"], transcript="hoje o atalho é ctrl+shift+t",
                        openshorts_title="Atalho secreto")
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    return {"h": h, "perfil": perfil, "conta": conta, "corte": corte}


def textos_validos() -> dict:
    dados = json.loads(fixture("valida")["content"][0]["text"])
    return mensagem(dados | {"explicacao": "Textos para o clipe.", "avisos": []})


def _sugerir(client, c, **extra):
    return client.post(f"/api/cortes/{c['corte'].id}/sugestoes", headers=c["h"],
                       json={"contaId": c["conta"]["id"], **extra})


def test_sugere_para_a_plataforma_da_conta_e_registra(client, db, cenario, anthropic_fake):  # noqa: F811
    c = cenario
    r = _sugerir(client, c)
    assert r.status_code == 200, r.text
    s = r.json()["sugestao"]
    assert s["plataforma"] == "youtube" and s["model"] == "claude-sonnet-5-5"
    assert 3 <= len(s["hashtags"]) <= 8 and len(s["titulo"]) <= 100
    texto = anthropic_fake.bodies[0]["messages"][0]["content"]
    assert "YouTube Shorts" in texto and "ctrl+shift+t" in texto and "Atalho secreto" in texto
    # base → regras → perfil (spec 008, R5): o perfil fica no último bloco, o do cache
    assert "A Taverna Nerd" in anthropic_fake.bodies[0]["system"][-1]["text"]
    [row] = db.query(IaChamada).all()
    assert row.prompt_version == "ia/1" and row.erro_code is None
    assert row.tipo_campo == "postagem.textos" and row.entity_type == "corte"
    assert row.conta_id is not None and row.sessao_id is None
    assert row.proposta["titulo"] == s["titulo"]
    assert (row.input_tokens, row.output_tokens, row.cache_read_tokens) == (1800, 220, 1200)
    assert row.duration_ms >= 0 and row.created_by is not None


def test_nao_altera_a_postagem(client, cenario):
    c = cenario
    p = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["conta"]["id"], "titulo": "meu título"}).json()["destino"]
    assert _sugerir(client, c).status_code == 200
    atual = client.get(f"/api/destinos/{p['id']}", headers=c["h"]).json()["destino"]
    assert atual["titulo"] == "meu título" and atual["version"] == 1


def test_outra_versao_manda_as_anteriores(client, cenario, anthropic_fake):  # noqa: F811
    c = cenario
    primeira = _sugerir(client, c).json()["sugestao"]
    _sugerir(client, c, outraVersao=True)
    assert primeira["titulo"] not in anthropic_fake.bodies[0]["messages"][0]["content"]
    assert primeira["titulo"] in anthropic_fake.bodies[1]["messages"][0]["content"]


def test_lista_mais_recentes_primeiro_so_com_resultado(client, db, cenario, anthropic_fake):  # noqa: F811
    c = cenario
    anthropic_fake.responder(textos_validos(), "timeout", textos_validos())
    a = _sugerir(client, c).json()["sugestao"]
    assert _sugerir(client, c).status_code == 504
    b = _sugerir(client, c).json()["sugestao"]
    r = client.get(f"/api/cortes/{c['corte'].id}/sugestoes", headers=c["h"])
    assert [s["id"] for s in r.json()["items"]] == [b["id"], a["id"]]
    assert db.query(IaChamada).count() == 3  # o erro também ficou registrado


@pytest.mark.parametrize(("itens", "status", "code", "erro", "trecho"), [
    (["timeout"], 504, "ia_timeout", "timeout", "demorou demais"),
    (["recusa"], 502, "ia_recusa", "refusal", "escreva à mão"),
    (["poucas_hashtags", "poucas_hashtags"], 502, "ia_invalida", "invalid", "fora do formato"),
    ([(500, "erro_api")], 502, "claude_error", "api_error", "não respondeu"),
    ([(401, {"type": "error", "error": {"type": "authentication_error", "message": "x"}})],
     502, "claude_error", "api_error", "ANTHROPIC_API_KEY"),
])
def test_erros_em_pt_br_e_registrados(client, db, cenario, anthropic_fake,  # noqa: F811
                                      itens, status, code, erro, trecho):
    anthropic_fake.responder(*itens)
    r = _sugerir(client, cenario)
    assert r.status_code == status, r.text
    body = r.json()["error"]
    assert body["code"] == code and trecho in body["message"]
    [row] = db.query(IaChamada).all()  # commitado antes do erro
    assert row.erro_code == erro and row.proposta is None


def test_sem_chave_claude_unconfigured(client, db, cenario):
    app.dependency_overrides[get_ia_client] = lambda: None
    r = _sugerir(client, cenario)
    assert r.status_code == 503 and r.json()["error"]["code"] == "claude_unconfigured"
    [row] = db.query(IaChamada).all()  # spec 008: grava sempre, inclusive sem chave
    assert row.erro_code == "unconfigured" and row.proposta is None


def test_conta_de_outro_perfil_e_corte_inexistente(client, cenario):
    c = cenario
    outro = criar_perfil(client, c["h"], "Outro")
    conta = criar_conta(client, c["h"], outro["id"])
    r = _sugerir(client, c, contaId=conta["id"])
    assert r.status_code == 400
    r = client.post("/api/cortes/00000000-0000-0000-0000-000000000000/sugestoes",
                    headers=c["h"], json={"contaId": c["conta"]["id"]})
    assert r.status_code == 404
    r = client.get("/api/cortes/00000000-0000-0000-0000-000000000000/sugestoes", headers=c["h"])
    assert r.status_code == 404
