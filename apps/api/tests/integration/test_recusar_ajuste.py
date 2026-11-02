"""O "Não aprovo" do wizard (spec 031, US3, T031; R6, FR-016, FR-034, FR-037) com o Claude falso:
- recusar a narração ("mais animada") muda só a velocidade e refaz a narração, sem quadros;
- recusar o quadro 1 refaz o 1 e os seguintes (o 0 e as outras posições ficam);
- um pedido "ambíguo" vira esclarecimento no chat, sem geração; a resposta continua o pedido;
- o autor da mudança é o humano que recusou, com `details.ia`;
- 409 `etapa_errada` e `geracao_em_andamento`;
- `recusar` e `aprovar_posicao` gravam versão com autor, antes e depois.
Nada chama serviço real."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from integration.guiado_helpers import (
    aprovar_posicao,
    ate_narracao,
    ate_quadros,
    ativos,
    geracoes,
    guiado,
    recusar,
    versoes,
)
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    motores,
    owner,
    rodar_ate,
    ver_conversa,
    ver_roteiro,
)


def _ia(client, h, m, rot: dict) -> dict:
    """Roda a linha Claude (o ajuste) uma volta."""
    assert m.linha_claude().volta()
    return ver_roteiro(client, h, rot["id"])


def _mensagens(client, h, rot: dict, tipo: str) -> list[dict]:
    return [x for x in ver_conversa(client, h, rot["id"])["mensagens"] if x["tipo"] == tipo]


def test_recusar_a_narracao_refaz_so_a_narracao(client, db, owner, motores):
    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[1])
    rot = ate_narracao(client, h, motores, rot)
    narracao = rot["narracao"]["id"]
    assert rot["velocidade"] == 1.08

    rot = recusar(client, h, rot, {"tipo": "narracao"}, opcoes=["Mais animada"])
    [pedido] = _mensagens(client, h, rot, "pedido_troca")
    assert pedido["alvo"] == {"tipo": "narracao"} and pedido["conteudo"]["opcoes"] == \
        ["Mais animada"] and pedido["autor"]["tipo"] == "user"
    assert ver_conversa(client, h, rot["id"])["geracaoAberta"]["passo"] == "roteiro.ajuste"
    v = versoes(client, h, rot)[0]
    assert v["details"]["acao"] == "recusar" and v["details"]["alvo"] == {"tipo": "narracao"}
    assert v["autor"] == {"tipo": "usuario", "id": str(owner[0].id), "nome": v["autor"]["nome"]}
    assert v["before"] is not None and v["after"] is not None

    rot = _ia(client, h, motores, rot)
    assert rot["velocidade"] == 1.15 and rot["status"] == "narrando"
    mudanca = versoes(client, h, rot)[0]
    assert mudanca["autor"]["id"] == str(owner[0].id)  # em nome de quem recusou
    assert mudanca["details"]["ia"]["chamadaId"] and \
        mudanca["details"]["ia"]["passo"] == "roteiro.ajuste"
    assert mudanca["before"]["velocidade"] != mudanca["after"]["velocidade"]
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_narracao")
    assert rot["narracao"]["id"] != narracao and rot["narracao"]["velocidade"] == 1.15
    assert not geracoes(db, "cena.keyframe", c0)  # os quadros não são refeitos
    assert not any(q.image_id for q in ativos(db, c0))
    avisos = _mensagens(client, h, rot, "aviso")
    assert avisos[-1]["conteudo"]["code"] == "ajuste_aplicado"


def test_recusar_o_quadro_1_refaz_ele_e_os_seguintes(client, db, owner, motores):
    h = owner[1]
    _, rot, (c0, c1) = guiado(client, h, motores, db, owner[0], trechos=[2, 1])
    rot = ate_quadros(client, h, motores, rot)
    rot = aprovar_posicao(client, h, rot, 1)  # a outra posição já aprovada
    antes0, antes1 = ativos(db, c0), ativos(db, c1)
    ids0 = [(q.id, q.image_id) for q in antes0]
    ids1 = [(q.id, q.image_id) for q in antes1]

    rot = recusar(client, h, rot, {"tipo": "quadros", "ordem": 0, "quadro": 1},
                  texto="mais de lado, mostrando a manga")
    err = recusar(client, h, rot, {"tipo": "quadros", "ordem": 0, "quadro": 1},
                  opcoes=["Outra pose"], status=409)
    assert err["error"]["code"] == "geracao_em_andamento"
    rot = _ia(client, h, motores, rot)
    assert rot["status"] == "gerando_keyframes"
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")

    depois0 = ativos(db, c0)
    assert (depois0[0].id, depois0[0].image_id) == ids0[0]  # o quadro 0 fica
    assert all(depois0[i].id != ids0[i][0] and depois0[i].image_id != ids0[i][1]
               for i in (1, 2))
    assert depois0[1].instrucao == "She stands sideways, showing the sleeve"
    assert depois0[2].instrucao == antes0[2].instrucao
    assert all(q.provisorio for q in depois0[1:])
    novo1 = [g for g in geracoes(db, "cena.keyframe", c0)
             if g.params["extras"]["quadro"] == 1][-1]
    assert novo1.params["referencias"][0] == str(ids0[0][1])  # nasce do quadro mantido
    assert [(q.id, q.image_id) for q in ativos(db, c1)] == ids1  # a outra posição fica
    p0, p1 = rot["posicoes"]
    assert p0["aprovadoKeyframesEm"] is None and p1["aprovadoKeyframesEm"] is not None

    # A mudança é do humano, com o selo da IA, na cena e no roteiro.
    cv = client.get(f"/api/cenas/{c0}/versions", headers=h).json()["items"]
    refazer = next(x for x in cv if x["details"].get("acao") == "quadros_refazer")
    assert refazer["autor"]["id"] == str(owner[0].id) and refazer["details"]["ia"]["chamadaId"]
    assert refazer["details"]["refeitos"] == [1, 2]
    rv = next(x for x in versoes(client, h, rot) if x["details"].get("acao") == "ajuste")
    assert rv["autor"]["id"] == str(owner[0].id) and rv["details"]["ia"]["chamadaId"]

    # O portão passa com a aprovação da posição refeita.
    rot = aprovar_posicao(client, h, rot, 0)
    assert rot["status"] == "gerando_clipes"


def test_pedido_ambiguo_vira_esclarecimento_sem_gerar(client, db, owner, motores):
    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[1])
    rot = ate_quadros(client, h, motores, rot)
    gs = len(geracoes(db, "cena.keyframe", c0))
    imagens = [q.image_id for q in ativos(db, c0)]

    rot = recusar(client, h, rot, {"tipo": "quadros", "ordem": 0, "quadro": 1},
                  texto="sei lá, ambíguo")
    rot = _ia(client, h, motores, rot)
    assert rot["status"] == "aguardando_keyframes"
    [esc] = _mensagens(client, h, rot, "esclarecimento")
    assert esc["alvo"] == {"tipo": "quadros", "ordem": 0, "quadro": 1}
    assert len(esc["conteudo"]["opcoes"]) >= 2 and esc["conteudo"]["texto"]
    assert esc["autor"]["tipo"] == "system:roteiro"
    assert len(geracoes(db, "cena.keyframe", c0)) == gs  # nada gerado
    assert [q.image_id for q in ativos(db, c0)] == imagens
    [pedido] = _mensagens(client, h, rot, "pedido_troca")
    assert esc["conteudo"]["pedido"] == pedido["conteudo"]["pedido"] == pedido["seq"]

    # A resposta (um clique numa opção do esclarecimento) continua o mesmo pedido.
    opcao = esc["conteudo"]["opcoes"][0]
    rot = recusar(client, h, rot, {"tipo": "quadros", "ordem": 0, "quadro": 1},
                  opcoes=[opcao["id"]])
    segundo = _mensagens(client, h, rot, "pedido_troca")[-1]
    assert segundo["conteudo"]["pedido"] == pedido["seq"]
    assert segundo["conteudo"]["opcoes"] == [opcao["rotulo"]]
    rot = _ia(client, h, motores, rot)
    assert rot["status"] == "gerando_keyframes"
    assert ativos(db, c0)[1].instrucao == "She stands sideways, showing the sleeve"


def test_recusar_fora_da_etapa(client, db, owner, motores):
    h = owner[1]
    _, rot, _ = guiado(client, h, motores, db, owner[0], trechos=[1])
    rot = ate_narracao(client, h, motores, rot)
    err = recusar(client, h, rot, {"tipo": "quadros", "ordem": 0, "quadro": 0},
                  opcoes=["Mais de lado"], status=409)
    assert err["error"]["code"] == "etapa_errada"
    err = recusar(client, h, rot, {"tipo": "final"}, opcoes=["Mais curto"], status=409)
    assert err["error"]["code"] == "etapa_errada"
    err = recusar(client, h, rot, {"tipo": "narracao"}, status=422)  # sem opção nem texto
    assert err["error"]["code"] == "opcao_invalida"
    assert not geracoes(db, "roteiro.ajuste", uuid.UUID(rot["id"]))
