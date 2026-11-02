"""O "Novo vídeo" guiado (spec 031, US1, T016): `POST /api/roteiros` com os 6 blocos e a grade
(`GET /api/roteiros/grade`). A grade é copiada no roteiro, a voz vazia vira a voz padrão do
avatar, só itens utilizáveis passam e as perguntas do chat já saem pedidas. Serviços falsos."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import json
import uuid

from sqlalchemy import select, text

from integration.padrao_helpers import avatar_com_slots
from integration.produtos_helpers import criar as criar_produto
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    criar_guiado,
    montar_guiado,
    motores,
    owner,
    perfil,
    ver_conversa,
    ver_roteiro,
)
from sociman_api.geracao.models import Geracao
from sociman_api.history import EntityVersion


def _erro(r) -> str:
    return r.json()["error"]["code"]


def test_criar_com_a_grade_e_a_voz_padrao(client, db, owner, motores):
    h = owner[1]
    r = client.get("/api/roteiros/grade", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"trechoBaseS": 5, "opcoes": [5, 10, 15, 20, 25, 30],
                        "maxTrechosPorCena": 3}
    b = montar_guiado(client, h, motores)
    rot = criar_guiado(client, h, b, duracaoS=20)
    assert rot["status"] == "rascunho" and rot["tipoVideo"] == "avatar_pov"
    assert (rot["duracaoAlvoS"], rot["trechoBaseS"]) == (20, 5)
    assert rot["cenarioId"] == b["cenario"]["id"] and rot["conversaEstado"] == "sem_perguntas"
    assert rot["voz"]["id"] == b["voz"]["id"]  # a voz padrão do avatar
    assert rot["produtos"][0]["varianteId"] == b["produto"]["variantes"][0]["id"]
    assert rot["nome"].startswith(rot["produtos"][0]["nomeComercial"] or rot["produtos"][0]["nome"])
    assert rot["posicoes"] == [] and rot["brief"] == ""

    # As perguntas já foram pedidas, no nome do humano, com o perfil base do vídeo.
    [g] = db.scalars(select(Geracao).where(Geracao.alvo_id == uuid.UUID(rot["id"]))).all()
    assert g.passo == "roteiro.perguntas" and g.created_by == owner[0].id
    assert g.perfil_id == uuid.UUID(b["perfil_id"])
    conv = ver_conversa(client, h, rot["id"])
    assert conv["geracaoAberta"]["passo"] == "roteiro.perguntas" and conv["mensagens"] == []

    # O histórico: a versão `created` com as escolhas e a marca do guiado.
    [v] = db.scalars(select(EntityVersion).where(EntityVersion.entity_type == "roteiro",
                                                 EntityVersion.entity_id == uuid.UUID(rot["id"])))
    assert v.version == 1 and v.details["guiado"] is True and v.actor_user_id == owner[0].id
    assert v.after["duracao_alvo_s"] == 20 and v.after["trecho_base_s"] == 5
    assert v.after["cenario_id"] == b["cenario"]["id"]

    # A linha Claude traz as perguntas (o fake devolve 3, a 1ª múltipla).
    motores.linha_claude().volta()
    conv = ver_conversa(client, h, rot["id"])
    assert conv["estado"] == "perguntando" and conv["total"] == 3 and conv["rodada"] == 1
    assert conv["perguntaAtual"]["id"] == "foco" and conv["perguntaAtual"]["multipla"]
    assert 2 <= len(conv["perguntaAtual"]["opcoes"]) <= 6
    assert all(m["autor"]["tipo"] == "system:roteiro" for m in conv["mensagens"])
    assert ver_roteiro(client, h, rot["id"])["conversaEstado"] == "perguntando"


def test_criar_recusa_o_que_nao_e_utilizavel(client, db, owner, motores):
    h = owner[1]
    b = montar_guiado(client, h, motores)

    # Duração fora da grade.
    r = client.post("/api/roteiros", headers=h, json=_corpo(b, duracaoS=7))
    assert r.status_code == 422 and _erro(r) == "duracao_fora_da_grade"
    assert r.json()["error"]["details"]["opcoes"] == [5, 10, 15, 20, 25, 30]
    r = client.post("/api/roteiros", headers=h, json=_corpo(b, duracaoS=35))
    assert r.status_code == 422 and _erro(r) == "duracao_fora_da_grade"

    # Produto em revisão (não aprovado) e cenário sem a imagem da cena.
    em_revisao = criar_produto(client, h, b["perfil_id"], name="saia_plissada")
    r = client.post("/api/roteiros", headers=h, json=_corpo(b, produtoId=em_revisao["id"]))
    assert r.status_code == 422 and _erro(r) == "cena_invalida"
    assert r.json()["error"]["details"]["field"] == "produtoId"
    r = client.post("/api/roteiros", headers=h, json=_corpo(b, cenarioId=b["avatar"]["id"]))
    assert r.status_code == 422 and r.json()["error"]["details"]["field"] == "cenarioId"

    # Perfil inexistente e arquivado.
    r = client.post("/api/roteiros", headers=h, json=_corpo(b, perfilId=str(uuid.uuid4())))
    assert r.status_code == 400 and _erro(r) == "perfil_invalido"
    arquivado = perfil(client, h, "velho")
    db.execute(text("UPDATE perfis SET archived_at = now() WHERE id = :p"),
               {"p": uuid.UUID(arquivado)})
    db.commit()
    r = client.post("/api/roteiros", headers=h, json=_corpo(b, perfilId=arquivado))
    assert r.status_code == 409 and _erro(r) == "perfil_base_arquivado"

    # Avatar sem voz padrão: a voz é obrigatória; com a voz escolhida, passa.
    sem_voz = avatar_com_slots(client, h, motores, b["perfil_id"], n=5, name="Lia")
    r = client.post("/api/roteiros", headers=h, json=_corpo(b, avatarId=sem_voz["id"]))
    assert r.status_code == 400 and _erro(r) == "voz_invalida"
    criar_guiado(client, h, b, avatarId=sem_voz["id"], vozId=b["voz"]["id"])

    # Avatar com o consentimento revogado.
    db.execute(text("UPDATE assets SET consentimento = CAST(:c AS jsonb) WHERE id = :a"),
               {"c": json.dumps({"revogado_em": "2026-10-13T10:00:00+00:00"}),
                "a": uuid.UUID(sem_voz["id"])})
    db.commit()
    r = client.post("/api/roteiros", headers=h,
                    json=_corpo(b, avatarId=sem_voz["id"], vozId=b["voz"]["id"]))
    assert r.status_code == 409 and _erro(r) == "consentimento_revogado"

    # Só humano: o MCP nem chega (a rota está em PROIBIDAS, `test_mcp_mapa`).
    from sociman_api.mcp import mapa

    assert mapa.classificar("roteiros_criar_guiado") == "proibida"
    assert mapa.classificar("roteiros_grade") == "fora"


def _corpo(b: dict, **kw) -> dict:
    return {"perfilId": b["perfil_id"], "tipoVideo": "avatar_pov",
            "avatarId": b["avatar"]["id"], "cenarioId": b["cenario"]["id"],
            "produtoId": b["produto"]["id"], "duracaoS": 10} | kw


def test_grade_nova_nao_mexe_no_roteiro_existente(client, db, owner, motores, monkeypatch):
    """FR-033: o roteiro guarda a base com que nasceu; a duração muda dentro dela."""
    from sociman_api.config import get_settings

    h = owner[1]
    b = montar_guiado(client, h, motores)
    rot = criar_guiado(client, h, b, duracaoS=15)
    monkeypatch.setattr(get_settings(), "roteiro_trecho_base_s", 8)
    assert client.get("/api/roteiros/grade", headers=h).json()["opcoes"][:2] == [8, 16]
    rot = ver_roteiro(client, h, rot["id"])
    assert (rot["trechoBaseS"], rot["duracaoAlvoS"]) == (5, 15)
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h,
                     json={"version": rot["version"], "duracaoS": 16})
    assert r.status_code == 422 and _erro(r) == "duracao_fora_da_grade"
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h,
                     json={"version": rot["version"], "duracaoS": 25})
    assert r.status_code == 200, r.text
    assert r.json()["duracaoAlvoS"] == 25 and r.json()["status"] == "rascunho"
