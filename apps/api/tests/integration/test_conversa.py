"""O chat do vídeo guiado e o plano v2 (spec 031, US2, T024 e T027; FR-008 a FR-013, FR-019,
FR-022, FR-031, FR-033 e FR-037): as perguntas fechadas numa chamada só, responder só por
cliques, a palavra proibida do guia fora do plano, retomar a conversa, a IA fora sem perder as
respostas, o plano v2 dentro da grade (a soma fecha, a fala cabe, cenas novas com os quadros e a
derivada no reuso do plano) e o revert/PATCH das posições sem perder os trechos. Serviços
falsos."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from sqlalchemy import select

from integration.guia_ia_helpers import campos
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    criar_guiado,
    editar,
    guiado_planejado,
    montar_guiado,
    motores,
    owner,
    rodar_ate,
    ver_conversa,
    ver_roteiro,
)
from sociman_api.cenas import quadros
from sociman_api.cenas.models import Cena
from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaChamada


def _erro(r) -> str:
    return r.json()["error"]["code"]


def _guia(client, h, perfil_id: str, **kw) -> dict:
    url = f"/api/perfis/{perfil_id}/guia"
    versao = client.get(url, headers=h).json()["guia"]["version"]
    r = client.put(url, headers=h, json={"version": versao, "campos": campos(**kw)})
    assert r.status_code == 200, r.text
    return r.json()["guia"]


def _responder(client, h, rid: str, conv: dict, status: int = 200, **kw):
    corpo = {"version": conv["version"], "perguntaId": conv["perguntaAtual"]["id"]} | kw
    r = client.post(f"/api/roteiros/{rid}/conversa/respostas", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def _planos_v2(fake) -> list[str]:
    from fakes.anthropic_fake import _texto_user

    return [_texto_user(b) for b in fake.bodies if "<grade " in _texto_user(b)]


def test_chat_so_cliques_proibida_e_plano_na_grade(client, db, owner, motores):
    h = owner[1]
    b = montar_guiado(client, h, motores)
    _guia(client, h, b["perfil_id"], tom="Animado e direto", proibidas=["barato"])
    rot = criar_guiado(client, h, b, duracaoS=15)
    rid = rot["id"]
    motores.linha_claude().volta()
    pedido = b["claude"].bodies[-1]["messages"][0]["content"]
    assert "<guia_perfil>" in pedido and "barato" in pedido and "<produto>" in pedido
    chamada = db.scalar(select(IaChamada).where(IaChamada.tipo_campo == "roteiro.perguntas"))
    assert chamada.guia_perfil_version is not None and chamada.entity_id == uuid.UUID(rid)

    conv = ver_conversa(client, h, rid)
    assert conv["estado"] == "perguntando" and 1 <= conv["total"] <= 5
    foco = conv["perguntaAtual"]
    # Opção que não existe e duas opções numa pergunta de escolha única: 422.
    r = client.post(f"/api/roteiros/{rid}/conversa/respostas", headers=h,
                    json={"version": conv["version"], "perguntaId": foco["id"],
                          "opcoes": ["inventada"]})
    assert r.status_code == 422 and _erro(r) == "opcao_invalida"
    conv = _responder(client, h, rid, conv, opcoes=[o["id"] for o in foco["opcoes"][:2]])
    assert conv["respondidas"] == 1
    r = client.post(f"/api/roteiros/{rid}/conversa/respostas", headers=h,
                    json={"version": conv["version"], "perguntaId": foco["id"],
                          "opcoes": [foco["opcoes"][0]["id"]]})
    assert r.status_code == 409 and _erro(r) == "pergunta_respondida"
    unica = conv["perguntaAtual"]
    assert not unica["multipla"]
    r = client.post(f"/api/roteiros/{rid}/conversa/respostas", headers=h,
                    json={"version": conv["version"], "perguntaId": unica["id"],
                          "opcoes": [o["id"] for o in unica["opcoes"][:2]]})
    assert r.status_code == 422 and _erro(r) == "opcao_invalida"

    # Planejar antes de responder tudo: 409.
    r = client.post(f"/api/roteiros/{rid}/planejar", headers=h,
                    json={"version": conv["version"]})
    assert r.status_code == 409 and _erro(r) == "conversa_incompleta"

    # A 2ª com um texto curto que tem a proibida: vira aviso no chat.
    conv = _responder(client, h, rid, conv, opcoes=[unica["opcoes"][0]["id"]],
                      texto="Quero algo barato e lindo")
    aviso = [m for m in conv["mensagens"] if m["tipo"] == "aviso"]
    assert len(aviso) == 1 and aviso[0]["conteudo"]["palavras"] == ["barato"]

    # Fechar e reabrir: a conversa continua de onde parou.
    reaberta = ver_conversa(client, h, rid)
    assert reaberta["perguntaAtual"]["id"] == conv["perguntaAtual"]["id"]
    assert len(reaberta["mensagens"]) == len(conv["mensagens"])
    while conv["perguntaAtual"] is not None:
        conv = _responder(client, h, rid, conv, opcoes=[conv["perguntaAtual"]["opcoes"][0]["id"]])
    assert conv["estado"] == "respondida"

    # Cada resposta é uma versão do roteiro, com o humano como autor (FR-037).
    vs = db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "roteiro", EntityVersion.entity_id == uuid.UUID(rid),
        EntityVersion.details["acao"].astext == "responder")).all()
    assert len(vs) == conv["total"] and all(v.actor_user_id == owner[0].id for v in vs)
    assert vs[1].details["proibidas"] == ["barato"]

    # O plano v2: as respostas sem a proibida, e a soma fecha na duração.
    rot = acao(client, h, {"id": rid, "version": conv["version"]}, "planejar")
    rot = rodar_ate(client, h, motores, rid, "aguardando_texto")
    [msg] = _planos_v2(b["claude"])
    respostas = msg.split("<respostas>")[1].split("</respostas>")[0]
    assert "lindo" in respostas and "barato" not in respostas.lower()
    assert '<grade base="5" alvo="15">' in msg
    pos = rot["posicoes"]
    assert sum(p["trechos"] for p in pos) * 5 == 15 == rot["duracaoAlvoS"]
    assert all(p["reuso"] == "nova" and p["motivo"] and p["orcamentoChars"] == 59 for p in pos)
    assert [p["duracaoS"] for p in pos] == [5.0] * len(pos)
    for p in pos:
        assert [q["papel"] for q in p["quadros"]] == ["inicio", "fim"]
        assert all(q["imageId"] is None and q["instrucao"] for q in p["quadros"])
        assert len(p["tomadasTrechos"]) == p["trechos"]
        cena = db.get(Cena, uuid.UUID(p["cena"]["id"]))
        assert cena.cenario_id == uuid.UUID(b["cenario"]["id"]) and cena.trechos == 1
        assert cena.perfil_id == uuid.UUID(b["perfil_id"])
    plano = db.scalar(select(IaChamada).where(IaChamada.tipo_campo == "roteiro.plano_guiado"))
    assert plano is not None and plano.guia_perfil_version is not None


def test_ia_fora_nao_perde_respostas_e_fala_que_nao_cabe(client, db, owner, motores):
    h = owner[1]
    b = montar_guiado(client, h, motores)
    rot = criar_guiado(client, h, b, duracaoS=10)
    rid = rot["id"]
    b["claude"].responder("recusa")
    motores.linha_claude().volta()
    conv = ver_conversa(client, h, rid)
    assert conv["estado"] == "sem_perguntas" and conv["erro"] is not None
    assert conv["erro"]["message"] == "A IA não respondeu; tente de novo"

    # "Tentar de novo" = refazer as perguntas.
    r = client.post(f"/api/roteiros/{rid}/conversa/refazer-perguntas", headers=h,
                    json={"version": conv["version"]})
    assert r.status_code == 200, r.text
    conv = r.json()
    assert conv["geracaoAberta"] is not None and conv["erro"] is None
    r = client.post(f"/api/roteiros/{rid}/conversa/refazer-perguntas", headers=h,
                    json={"version": conv["version"]})
    assert r.status_code == 409 and _erro(r) == "geracao_em_andamento"
    motores.linha_claude().volta()
    conv = ver_conversa(client, h, rid)
    conv = _responder(client, h, rid, conv, opcoes=[], texto="Não cabe tanta coisa")
    while conv["perguntaAtual"] is not None:
        conv = _responder(client, h, rid, conv, opcoes=[conv["perguntaAtual"]["opcoes"][0]["id"]])

    # O plano falha (IA fora): o roteiro volta a pedir, e as respostas ficam.
    b["claude"].responder("recusa")
    rot = acao(client, h, {"id": rid, "version": conv["version"]}, "planejar")
    rot = rodar_ate(client, h, motores, rid, "falhou")
    assert rot["etapaFalhou"] == "plano"
    assert ver_conversa(client, h, rid)["estado"] == "respondida"
    rot = acao(client, h, rot, "tentar-de-novo")
    rot = rodar_ate(client, h, motores, rid, "aguardando_texto")

    # "Não cabe": a 1ª tentativa estoura o orçamento, a 2ª (com o erro) vem certa.
    *_, primeira, segunda = _planos_v2(b["claude"])
    assert "<erro_anterior>" not in primeira
    assert "<erro_anterior>" in segunda and "a fala tem" in segunda
    assert sum(p["trechos"] for p in rot["posicoes"]) * 5 == 10
    assert not [a for a in rot["avisos"] if a["code"] == "fala_nao_cabe"]


def test_reuso_do_plano_cria_a_derivada(client, db, owner, motores):
    """Uma cena da 011 com o mesmo avatar e produto (sem cenário nem quadros) é candidata
    `plano`: a posição usa uma cena derivada (com a origem registrada), e a origem não muda (só
    a versão que registra a derivação)."""
    h = owner[1]
    b = montar_guiado(client, h, motores, n_cenas=1)
    origem_id = uuid.UUID(b["cenas"][0]["id"])
    versao_origem = db.get(Cena, origem_id).version
    rot = guiado_planejado(client, h, motores, b, duracaoS=10)
    assert rot["status"] == "aguardando_texto"
    p0 = rot["posicoes"][0]
    assert p0["reuso"] == "plano" and p0["cena"]["id"] != str(origem_id)
    db.expire_all()
    derivada = db.get(Cena, uuid.UUID(p0["cena"]["id"]))
    origem = db.get(Cena, origem_id)
    # A origem não muda: só ganha a versão "derivada" (histórico nas duas cenas, FR-037).
    assert derivada.origem_cena_id == origem_id and origem.version == versao_origem + 1
    assert derivada.acao == origem.acao and derivada.cenario_id == uuid.UUID(b["cenario"]["id"])
    assert [q.instrucao.startswith(("Beginning", "End")) for q in
            quadros.ativos(db, derivada.id)] == [True, True]
    assert all(p["reuso"] == "nova" for p in rot["posicoes"][1:])


def test_patch_e_revert_das_posicoes_guardam_os_trechos(client, db, owner, motores):
    h = owner[1]
    b = montar_guiado(client, h, motores)
    rot = guiado_planejado(client, h, motores, b, duracaoS=10)
    planejada = rot["version"]
    pos = rot["posicoes"]
    assert len(pos) == 2

    # Mudar o texto com as mesmas cenas: a posição guarda os trechos, o reuso e o motivo.
    corpo = [{"cenaId": p["cena"]["id"], "frases": p["frases"]} for p in pos]
    rot = editar(client, h, rot, frases=["Olha esse vestido!", "Corre no link!"],
                 posicoes=corpo)
    assert [(p["trechos"], p["reuso"], p["motivo"]) for p in rot["posicoes"]] == \
        [(p["trechos"], p["reuso"], p["motivo"]) for p in pos]

    # Trocar a ordem (sem mandar os trechos): cada posição leva os trechos da cena.
    trocada = [{"cenaId": corpo[1]["cenaId"], "frases": [0]},
               {"cenaId": corpo[0]["cenaId"], "frases": [1]}]
    rot = editar(client, h, rot, posicoes=trocada)
    assert [p["cena"]["id"] for p in rot["posicoes"]] == [corpo[1]["cenaId"], corpo[0]["cenaId"]]
    assert all(p["trechos"] == 1 and p["orcamentoChars"] == 59 for p in rot["posicoes"])

    assert all(p["reuso"] is None for p in rot["posicoes"])  # trocadas: a decisão é nova

    # Trechos que não batem com a cena, e a soma que não fecha.
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h,
                     json={"version": rot["version"],
                           "posicoes": [{**trocada[0], "trechos": 2}, trocada[1]]})
    assert r.status_code == 400 and r.json()["error"]["details"]["field"] == "posicoes.0.trechos"
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h,
                     json={"version": rot["version"], "posicoes": [trocada[0]],
                           "frases": [rot["frases"][0]]})
    assert r.status_code == 422 and _erro(r) == "duracao_nao_fecha"

    # Reverter ao plano: as posições voltam com os trechos, o reuso e o motivo.
    r = client.post(f"/api/roteiros/{rot['id']}/versoes/{planejada}/reverter", headers=h,
                    json={"version": rot["version"]})
    assert r.status_code == 200, r.text
    rot = r.json()
    assert [p["cena"]["id"] for p in rot["posicoes"]] == [c["cenaId"] for c in corpo]
    assert [(p["trechos"], p["reuso"], p["motivo"]) for p in rot["posicoes"]] == \
        [(p["trechos"], p["reuso"], p["motivo"]) for p in pos]

    # A duração muda dentro da grade e refaz o plano (FR-033).
    rot = editar(client, h, rot, duracaoS=15)
    assert rot["status"] == "planejando" and rot["duracaoAlvoS"] == 15
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_texto")
    assert sum(p["trechos"] for p in rot["posicoes"]) * 5 == 15
