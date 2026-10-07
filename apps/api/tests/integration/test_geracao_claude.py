"""Passos só de texto (spec 021, T048, SC-007, US4), com o Claude falso e um tipo e um aplicador
injetados (os reais `produto.ficha` e `avatar.identidade` chegam com a 012 e a 025, R14)."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

from dataclasses import replace

import pytest
from fakes.anthropic_fake import AnthropicFake, mensagem
from sqlalchemy import select

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    asset,
    detalhe,
    montar,
    motores,
    owner,
    pedir,
    rodar_gpu,
)
from sociman_api import history
from sociman_api.assets import service as assets_service
from sociman_api.assets.models import Asset
from sociman_api.geracao import aplicadores, passos
from sociman_api.geracao.models import GeracaoAlvo
from sociman_api.ia import tipos
from sociman_api.ia.models import IaChamada, IaDesfecho


class _Descricao(aplicadores.CenarioCena):
    """Injetado: o texto do Claude vai para a descrição do cenário."""

    def montar_params(self, db, actor, alvo, pedido):
        return {"instrucao": pedido.instrucao, "referencias": [], "bloco": None}

    def mensagem_claude(self, db, geracao):
        return f"<instrucao>{geracao.params['instrucao']}</instrucao>"

    def aplicar(self, db, actor, geracao, candidato):
        a = db.get(Asset, geracao.alvo_id, with_for_update=True)
        before = history.snapshot(a)
        a.description = candidato.metricas["texto"]
        assets_service._record(db, actor, a, "updated", before,
                               details={"geracao_id": str(geracao.id), "automatico": True})


@pytest.fixture
def passo_texto(monkeypatch):
    monkeypatch.setitem(tipos.TIPOS, "avatar.identidade",
                        replace(tipos.TIPOS["asset.descricao"], id="avatar.identidade",
                                regras_de="asset.descricao"))
    monkeypatch.setitem(aplicadores.APLICADORES, "avatar.identidade", _Descricao())
    with passos.sobrescrever("avatar.identidade", alvo_tipo=GeracaoAlvo.asset):
        yield


def test_texto_vai_direto_ao_alvo_com_registro(client, owner, motores, passo_texto, db):
    h = owner[1]
    b = montar(client, h)
    fake = AnthropicFake()
    motores.ia_client = fake.ia_client()
    g = pedir(client, h, b, passo="avatar.identidade", instrucao="descreva o quarto")
    assert g["semEscolha"] is True
    assert motores.linha_claude().volta() == "ok"
    g = detalhe(client, h, g["id"])
    assert g["status"] == "escolhido" and g["escolhidoId"]
    hist = client.get(f"/api/geracoes/{g['id']}/versoes", headers=h).json()["items"]
    assert [v["action"] for v in hist] == ["created"]  # o resto é estado de job
    alvo = asset(client, h, b["cenario"]["id"])
    assert alvo["description"]
    versoes = client.get(f"/api/assets/{alvo['id']}/versions", headers=h).json()["items"]
    assert versoes[0]["details"]["geracao_id"] == g["id"]
    assert versoes[0]["details"]["automatico"] is True
    assert versoes[0]["actor"]["id"] == str(owner[0].id)  # autor = quem pediu
    row = db.scalar(select(IaChamada).where(IaChamada.geracao_id == g["id"]))
    assert row.tipo_campo == "avatar.identidade" and row.entity_type == "asset"
    assert row.custo_usd is not None and row.desfecho == IaDesfecho.aplicada
    assert row.desfecho_por == owner[0].id
    # A edição manual depois salva como mudança humana.
    r = client.patch(f"/api/assets/{alvo['id']}", headers=h,
                     json={"version": alvo["version"], "description": "editado"})
    assert r.status_code == 200, r.text
    v = client.get(f"/api/assets/{alvo['id']}/versions", headers=h).json()["items"][0]
    assert "geracao_id" not in v["details"]


def test_resposta_fora_do_formato_falha_e_fica_no_registro(client, owner, motores, passo_texto,
                                                           db):
    h = owner[1]
    b = montar(client, h)
    fake = AnthropicFake()
    fake.responder(mensagem({"nada": 1}), mensagem({"nada": 2}))
    motores.ia_client = fake.ia_client()
    g = pedir(client, h, b, passo="avatar.identidade", instrucao="x")
    motores.linha_claude().volta()
    g = detalhe(client, h, g["id"])
    assert g["status"] == "falhou" and g["erro"]["code"] == "entrada_invalida"
    assert asset(client, h, b["cenario"]["id"])["description"] == ""
    row = db.scalar(select(IaChamada).where(IaChamada.geracao_id == g["id"]))
    assert row.desfecho == IaDesfecho.erro and row.erro_code == "invalid"


def test_sem_chave_falha_na_hora(client, owner, motores, passo_texto, db):
    h = owner[1]
    b = montar(client, h)
    motores.ia_client = None
    g = pedir(client, h, b, passo="avatar.identidade", instrucao="x")
    motores.linha_claude().volta()
    g = detalhe(client, h, g["id"])
    assert g["status"] == "falhou" and g["erro"]["message"] == "O Claude não está configurado"
    assert db.scalar(select(IaChamada).where(IaChamada.geracao_id == g["id"])).erro_code == \
        "unconfigured"


def test_nao_espera_a_gpu(client, owner, motores, passo_texto):
    h = owner[1]
    b = montar(client, h)
    motores.ia_client = AnthropicFake().ia_client()
    pedir(client, h, b)  # um job de GPU na frente
    g = pedir(client, h, b, passo="avatar.identidade", instrucao="x")
    assert motores.linha_claude().volta() == "ok"
    assert detalhe(client, h, g["id"])["status"] == "escolhido"


def test_recorte_injetado_vai_direto_e_nenhum_outro_de_imagem(client, owner, motores,
                                                             monkeypatch):
    """FR-031: o `produto.recorte` (sem escolha) vai direto; o `cenario.cena` vai à revisão."""
    h = owner[1]
    b = montar(client, h)
    aplicados = []

    class _Recorte(aplicadores.CenarioCena):
        def montar_params(self, db, actor, alvo, pedido):
            refs = [aplicadores.referencia_de_asset_ativo(db, alvo.perfil_id, r)
                    for r in pedido.referencias]
            return {"instrucao": pedido.instrucao or "recorte", "bloco": "cutout",
                    "referencias": [str(r.id) for r in refs]}

        def preparar_referencia(self, data):
            return data

        def normalizar(self, png):
            return png

        def aplicar(self, db, actor, geracao, candidato):
            aplicados.append((geracao.id, candidato.numero, actor.user_id))

    monkeypatch.setitem(aplicadores.APLICADORES, "produto.recorte", _Recorte())
    with passos.sobrescrever("produto.recorte", alvo_tipo=GeracaoAlvo.asset,
                             image_kind="imagem"):
        g = pedir(client, h, b, passo="produto.recorte", referencias=[b["foto_image_id"]])
        rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "escolhido" and len(aplicados) == 1
    assert aplicados[0][2] == owner[0].id
    cena = pedir(client, h, b)
    rodar_gpu(motores)
    assert detalhe(client, h, cena["id"])["status"] == "revisao"
