"""Reuso de cenas em dois níveis (spec 031, US4, T039; R7, FR-019 a FR-024, FR-037, SC-003 e
SC-008) com os serviços falsos:
- a classificação: `total` (mesmo avatar, cenário e variante, com os quadros aprovados e o clipe
  de cada trecho) e `plano` (outro avatar, ou uma cena da 010 sem a sequência); a cena de outro
  produto fica fora da proposta, mas pode ser escolhida à mão (só no plano, com aviso);
- o reuso total não gera nada (0 keyframes e 0 clipes para a cena) e não muda a cena;
- o reuso do plano cria a derivada (`origem_cena_id`), que copia ação, câmera, movimento, motor,
  trechos e as instruções dos quadros, com histórico nas duas cenas;
- o modal (`PUT …/posicoes/{ordem}/cena`): `total` que não casa → 422 `reuso_invalido`; `nova`
  pede à IA a cena da posição; depois do texto, só no avançado (409 `etapa_errada`); cada troca
  é uma versão com autor, antes e depois;
- "cenas novas" no chat faz o plano propor `nova` em todas;
- a cena nova fica na biblioteca depois da entrega.
Nada chama serviço real."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from sqlalchemy import select

from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    aprovar,
    avatar_com_voz,
    criar_cena,
    criar_guiado,
    guiado_planejado,
    levar_ate,
    montar_guiado,
    motores,
    owner,
    produto_aprovado,
    responder,
    responder_tudo,
    rodar_ate,
    ver_conversa,
    ver_roteiro,
)
from sociman_api import history
from sociman_api.cenas import quadros
from sociman_api.cenas.models import Cena
from sociman_api.geracao.models import Geracao
from sociman_api.roteiros import reuso
from sociman_api.roteiros.models import Roteiro


def _cena(db, cena_id) -> Cena:
    db.expire_all()
    return db.get(Cena, uuid.UUID(str(cena_id)))


def _definir(client, h, rot: dict, ordem: int, reuso_: str, cena_id=None, status: int = 200,
             **kw) -> dict:
    corpo = {"version": rot["version"], "reuso": reuso_, **kw}
    if cena_id is not None:
        corpo["cenaId"] = str(cena_id)
    r = client.put(f"/api/roteiros/{rot['id']}/posicoes/{ordem}/cena", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def _versoes(client, h, entidade: str, eid) -> list[dict]:
    r = client.get(f"/api/{entidade}/{eid}/{'versoes' if entidade == 'roteiros' else 'versions'}",
                   headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _geracoes_da_cena(db, cena_id, roteiro_id) -> list[Geracao]:
    db.expire_all()
    return [g for g in db.scalars(select(Geracao).where(
        Geracao.alvo_id == uuid.UUID(str(cena_id)),
        Geracao.passo.in_(("cena.keyframe", "cena.clipe"))))
        if (g.params.get("extras") or {}).get("roteiroId") == str(roteiro_id)]


def _video_pronto(client, h, m, b) -> tuple[dict, uuid.UUID]:
    """Um vídeo guiado de 5 s inteiro (o reuso total precisa dos quadros aprovados e do clipe)."""
    rot = guiado_planejado(client, h, m, b, duracaoS=5)
    assert [p["reuso"] for p in rot["posicoes"]] == ["nova"]
    rot = levar_ate(client, h, m, rot, "pronto", voltas=20)
    return rot, uuid.UUID(rot["posicoes"][0]["cena"]["id"])


def test_niveis_reuso_total_sem_gpu_e_cena_nova_na_biblioteca(client, db, owner, motores):
    h = owner[1]
    b = montar_guiado(client, h, motores, n_cenas=0)
    _, cena_a = _video_pronto(client, h, motores, b)

    # SC-008: a cena nova da entrega está na biblioteca, com o perfil base do vídeo.
    lista = client.get("/api/cenas", headers=h, params={"perfilId": b["perfil_id"]}).json()
    assert str(cena_a) in [c["id"] for c in lista["items"]]
    assert str(_cena(db, cena_a).perfil_id) == b["perfil_id"]

    # As outras: a da 010 (sem a sequência) e a de outro avatar são `plano`; a de outro produto
    # não entra.
    sem_seq = criar_cena(client, h, b, nome="Da 010")
    outro = avatar_com_voz(client, h, motores, b["perfil_id"], b["voz"], name="Ana")
    outro_avatar = criar_cena(client, h, b, nome="Outro avatar", avatarId=outro["id"])
    p2 = produto_aprovado(client, h, motores, b["perfil_id"])
    outro_produto = criar_cena(client, h, b, nome="Outro produto", produtoId=p2["id"],
                               produtoVarianteId=p2["variantes"][0]["id"])
    rot = criar_guiado(client, h, b, duracaoS=10)
    r = db.get(Roteiro, uuid.UUID(rot["id"]))
    niveis = {str(c.cena.id): (c.nivel, c.diferencas) for c in reuso.candidatas(db, r)}
    assert niveis[str(cena_a)] == ("total", ())
    assert niveis[sem_seq["id"]][0] == "plano"
    assert "sem a sequência de quadros" in niveis[sem_seq["id"]][1]
    assert niveis[outro_avatar["id"]][0] == "plano"
    assert "outro avatar" in niveis[outro_avatar["id"]][1]
    assert outro_produto["id"] not in niveis
    assert reuso.classificar(db, r, _cena(db, outro_produto["id"])) is None

    # O plano (o Claude falso reaproveita a 1ª candidata, a mais recente, no nível dela): com as
    # outras arquivadas, a cena do vídeo anterior entra como está, e a outra posição é nova.
    for c in (sem_seq, outro_avatar):
        resp = client.post(f"/api/cenas/{c['id']}/arquivar", headers=h,
                           json={"version": _cena(db, c["id"]).version})
        assert resp.status_code == 200, resp.text
    antes = history.snapshot(_cena(db, cena_a))
    versao_a = _cena(db, cena_a).version
    conv = responder_tudo(client, h, motores, rot)
    rot = acao(client, h, {"id": rot["id"], "version": conv["version"]}, "planejar")
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_texto")
    p0 = rot["posicoes"][0]
    assert (p0["reuso"], p0["cena"]["id"]) == ("total", str(cena_a))
    assert rot["posicoes"][1]["reuso"] == "nova"

    # SC-003: até os clipes aprovados, nenhum keyframe nem clipe para a cena reaproveitada, e
    # ela não muda.
    rot = levar_ate(client, h, motores, rot, "montando", voltas=20)
    assert _geracoes_da_cena(db, cena_a, rot["id"]) == []
    assert len(_geracoes_da_cena(db, rot["posicoes"][1]["cena"]["id"], rot["id"])) == 3
    depois = _cena(db, cena_a)
    assert depois.version == versao_a and history.snapshot(depois) == antes


def test_modal_de_cenas(client, db, owner, motores):
    h = owner[1]
    b = montar_guiado(client, h, motores, n_cenas=0)
    _, cena_a = _video_pronto(client, h, motores, b)
    outro = avatar_com_voz(client, h, motores, b["perfil_id"], b["voz"], name="Ana")
    outro_avatar = criar_cena(client, h, b, nome="Outro avatar", avatarId=outro["id"],
                              camera="Handheld, slow push", movimento="camera_na_mao")
    p2 = produto_aprovado(client, h, motores, b["perfil_id"])
    outro_produto = criar_cena(client, h, b, nome="Outro produto", produtoId=p2["id"],
                               produtoVarianteId=p2["variantes"][0]["id"])
    rot = guiado_planejado(client, h, motores, b, duracaoS=10)
    assert rot["status"] == "aguardando_texto"
    # O fake reaproveita a 1ª candidata (a de outro avatar, a mais recente): reuso do plano.
    assert [p["reuso"] for p in rot["posicoes"]] == ["plano", "nova"]

    # `total` com uma cena que não casa (outro avatar; outro produto) → 422.
    err = _definir(client, h, rot, 1, "total", outro_avatar["id"], status=422)
    assert err["error"]["code"] == "reuso_invalido"
    assert "outro avatar" in err["error"]["details"]["diferencas"]
    err = _definir(client, h, rot, 1, "total", outro_produto["id"], status=422)
    assert err["error"]["code"] == "reuso_invalido"

    # `total` com a cena do vídeo anterior: a posição a usa como está, com histórico (FR-037).
    anterior = rot["posicoes"][1]["cena"]["id"]
    rot = _definir(client, h, rot, 1, "total", cena_a)
    assert (rot["posicoes"][1]["reuso"], rot["posicoes"][1]["cena"]["id"]) == ("total",
                                                                               str(cena_a))
    [v] = _versoes(client, h, "roteiros", rot["id"])[:1]
    assert v["details"]["acao"] == "definir_cena" and v["details"]["reuso"] == "total"
    assert v["autor"]["tipo"] == "usuario" and v["autor"]["id"] == str(owner[0].id)
    assert v["before"]["posicoes"][1]["cena_id"] == anterior
    assert v["before"]["posicoes"][1]["reuso"] == "nova"
    assert v["after"]["posicoes"][1]["cena_id"] == str(cena_a)
    assert v["after"]["posicoes"][1]["reuso"] == "total"

    # `plano` com a cena do vídeo anterior: a derivada copia ação, câmera, movimento, motor,
    # trechos e as instruções dos quadros; a origem ganha só a versão "derivada".
    origem = _cena(db, cena_a)
    versao_origem, snap_origem = origem.version, history.snapshot(origem)
    rot = _definir(client, h, rot, 1, "plano", cena_a)
    derivada = _cena(db, rot["posicoes"][1]["cena"]["id"])
    origem = _cena(db, cena_a)
    assert rot["posicoes"][1]["reuso"] == "plano" and derivada.origem_cena_id == cena_a
    for campo in ("acao", "camera", "movimento", "motor", "plano", "trechos"):
        assert getattr(derivada, campo) == getattr(origem, campo), campo
    assert [q.instrucao for q in quadros.ativos(db, derivada.id)] == \
        [q.instrucao for q in quadros.ativos(db, origem.id)]
    assert all(q.image_id is None for q in quadros.ativos(db, derivada.id))  # refaz as imagens
    assert derivada.status.value == "rascunho" and str(derivada.perfil_id) == b["perfil_id"]
    assert origem.version == versao_origem + 1
    snap = history.snapshot(origem)
    assert {k: v for k, v in snap.items() if k != "version"} == \
        {k: v for k, v in snap_origem.items() if k != "version"}
    [vo] = _versoes(client, h, "cenas", cena_a)[:1]
    assert vo["details"]["acao"] == "derivada" and vo["details"]["derivadaId"] == str(derivada.id)
    [vd] = _versoes(client, h, "cenas", derivada.id)[-1:]
    assert vd["action"] == "created" and vd["details"]["origemCenaId"] == str(cena_a)

    # `plano` com outro avatar (da 010, sem quadros): as instruções genéricas da ação, com o
    # avatar do vídeo.
    rot = _definir(client, h, rot, 0, "plano", outro_avatar["id"])
    d0 = _cena(db, rot["posicoes"][0]["cena"]["id"])
    assert str(d0.avatar_id) == b["avatar"]["id"] and d0.camera == "Handheld, slow push"
    assert len(quadros.ativos(db, d0.id)) == 2

    # Uma cena de outro produto só à mão, no plano, com aviso; a derivada leva o produto do vídeo.
    rot = _definir(client, h, rot, 0, "plano", outro_produto["id"])
    d1 = _cena(db, rot["posicoes"][0]["cena"]["id"])
    assert str(d1.produto_id) == b["produto"]["id"] and d1.origem_cena_id == \
        uuid.UUID(outro_produto["id"])
    assert any(a["code"] == "cena_outro_produto" for a in rot["avisos"])

    # `nova`: a IA devolve a cena da posição (os trechos da grade não mudam).
    rot = _definir(client, h, rot, 0, "nova")
    motores.linha_claude().volta()
    rot = ver_roteiro(client, h, rot["id"])
    p0 = rot["posicoes"][0]
    nova = _cena(db, p0["cena"]["id"])
    assert p0["reuso"] == "nova" and nova.origem_cena_id is None and p0["trechos"] == 1
    assert nova.acao == "She walks to the mirror and shows the dress"
    assert [q.instrucao for q in quadros.ativos(db, nova.id)] == \
        ["She walks to the mirror, state 0", "She walks to the mirror, state 1"]
    assert str(nova.perfil_id) == b["perfil_id"]
    conv = ver_conversa(client, h, rot["id"])
    assert any(m["tipo"] == "pedido_troca" and (m.get("alvo") or {}).get("tipo") == "posicao"
               for m in conv["mensagens"])

    # Depois do texto, só no avançado.
    rot = aprovar(client, h, rot, "texto")
    err = _definir(client, h, rot, 1, "total", cena_a, status=409)
    assert err["error"]["code"] == "etapa_errada"
    rot = _definir(client, h, rot, 1, "total", cena_a, avancado=True)
    assert rot["posicoes"][1]["reuso"] == "total"


def test_cenas_novas_no_chat_propoem_nova_em_todas(client, db, owner, motores):
    h = owner[1]
    b = montar_guiado(client, h, motores, n_cenas=0)
    criar_cena(client, h, b, nome="Da 010")  # uma candidata `plano` que o plano ignoraria
    rot = criar_guiado(client, h, b, duracaoS=10)
    claude = motores.linha_claude()
    conv = ver_conversa(client, h, rot["id"])
    while conv["estado"] == "sem_perguntas":
        claude.volta()
        conv = ver_conversa(client, h, rot["id"])
    conv = responder(client, h, conv, rot["id"], texto="quero cenas novas")
    while conv["perguntaAtual"] is not None:
        conv = responder(client, h, conv, rot["id"])
    rot = acao(client, h, {"id": rot["id"], "version": conv["version"]}, "planejar")
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_texto")
    assert [p["reuso"] for p in rot["posicoes"]] == ["nova", "nova"]
