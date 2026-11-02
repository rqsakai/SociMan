"""Núcleo do vídeo guiado (spec 031, Fase 2: T008 a T012 e T045) com os serviços falsos: a cadeia
de quadros por posição (R3: o 0 nasce do cenário, os seguintes do anterior), o clipe por trecho
com o par de quadros vizinhos (R2, R8), os espelhos do keyframe da cena e a refação parcial
(FR-028: refazer um quadro só refaz ele, os seguintes e os trechos que tocam neles). O roteiro
guiado é montado à mão (o "Novo vídeo" e o plano v2 são de outras tarefas); a 011 segue igual
(a suíte dela é a regressão). Nada chama serviço real."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from sqlalchemy import select

from integration.padrao_helpers import cenario_com_cena
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    aprovar,
    controle,
    criar_roteiro,
    montar,
    motores,
    owner,
    rodar_ate,
    ver_roteiro,
)
from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.cenas import quadros
from sociman_api.cenas.models import Cena, CenaTomada
from sociman_api.geracao.models import Geracao, GeracaoStatus
from sociman_api.produtos.models import Produto
from sociman_api.roteiros import maquina
from sociman_api.roteiros.estado import S
from sociman_api.roteiros.models import (
    ConversaEstado,
    PosicaoReuso,
    Roteiro,
    RoteiroCena,
    RoteiroTipoVideo,
)


def _guiado(client, h, m, db, dono, trechos: int = 2) -> tuple[dict, dict, uuid.UUID]:
    """Um roteiro guiado em `aguardando_texto`: 1 posição de `trechos` trechos (5 s cada) com a
    cena da biblioteca e a sequência de `trechos + 1` quadros vazios."""
    b = montar(client, h, m, n_cenas=1)
    b["cenario"] = cenario_com_cena(client, h, m, b["perfil_id"])
    rot = criar_roteiro(client, h, b)
    cena_id = uuid.UUID(b["cenas"][0]["id"])
    r = db.get(Roteiro, uuid.UUID(rot["id"]))
    r.tipo_video = RoteiroTipoVideo.avatar_pov
    r.cenario_id = uuid.UUID(b["cenario"]["id"])
    r.duracao_alvo_s, r.trecho_base_s = trechos * 5, 5
    r.conversa_estado = ConversaEstado.respondida
    r.frases = ["Gente, olha o caimento desse vestido!"]
    r.posicoes_rel.append(RoteiroCena(roteiro_id=r.id, ordem=0, cena_id=cena_id, frases=[0],
                                      trechos=trechos, reuso=PosicaoReuso.nova))
    r.status = S.aguardando_texto
    r.comandado_por = dono.id
    cena = db.get(Cena, cena_id)
    quadros.criar(db, Actor(kind="user", user_id=dono.id), cena,
                  [f"She holds the dress, state {i}" for i in range(trechos + 1)])
    db.commit()
    return b, ver_roteiro(client, h, rot["id"]), cena_id


def _ativos(db, cena_id):
    db.expire_all()
    return quadros.ativos(db, cena_id)


def _geracoes(db, passo: str, cena_id) -> list[Geracao]:
    db.expire_all()
    return list(db.scalars(select(Geracao).where(Geracao.passo == passo,
                                                 Geracao.alvo_id == cena_id)
                           .order_by(Geracao.created_at, Geracao.id)))


def _ate_quadros(client, h, m, rot):
    rot = aprovar(client, h, rot, "texto")
    rot = rodar_ate(client, h, m, rot["id"], "aguardando_narracao")
    rot = aprovar(client, h, rot, "narracao")
    assert rot["status"] == "gerando_keyframes"
    return rot


def test_cadeia_de_quadros_trechos_e_refacao_parcial(client, db, owner, motores):
    h = owner[1]
    b, rot, cena_id = _guiado(client, h, motores, db, owner[0], trechos=2)
    rot = _ate_quadros(client, h, motores, rot)
    db.expire_all()
    avatar = db.get(Asset, uuid.UUID(b["avatar"]["id"]))
    cenario = db.get(Asset, uuid.UUID(b["cenario"]["id"]))
    variante = db.get(Produto, uuid.UUID(b["produto"]["id"])).ativas()[0]
    produto_img = variante.flat_image_id or variante.recorte_image_id

    # Quadro 0: 1 opção, do cenário do roteiro, com o corpo-base e o produto (R3); só ele.
    [g0] = _geracoes(db, "cena.keyframe", cena_id)
    assert g0.n_opcoes == 1 and g0.params["extras"]["quadro"] == 0
    assert g0.params["referencias"] == [str(cenario.slot_ativo("cena").image_id),
                                        str(avatar.slot_ativo("corpo_base").image_id),
                                        str(produto_img)]
    assert _ativos(db, cena_id)[0].geracao_id == g0.id
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")

    # US3 (R3): a opção única vira o quadro provisório, e o 1 nasce do 0 (com o produto e o
    # rosto como âncoras), o 2 do 1; a sequência completa espera o portão.
    g0, g1, g2 = _geracoes(db, "cena.keyframe", cena_id)
    q = _ativos(db, cena_id)
    assert all(x.provisorio for x in q)
    assert [g.params["extras"]["quadro"] for g in (g0, g1, g2)] == [0, 1, 2]
    assert g1.params["referencias"] == [str(q[0].image_id), str(produto_img),
                                        str(avatar.slot_ativo("rosto_frontal").image_id)]
    assert g2.params["referencias"][0] == str(q[1].image_id)
    q = _ativos(db, cena_id)
    assert [x.papel.value for x in q] == ["inicio", "meio1", "fim"]
    assert all(x.image_id for x in q)
    cena = db.get(Cena, cena_id)
    assert (cena.keyframe_inicial_id, cena.keyframe_final_id) == (q[0].image_id, q[2].image_id)
    rot = ver_roteiro(client, h, rot["id"])
    assert rot["status"] == "aguardando_keyframes"  # a sequência completa espera o portão
    versoes = client.get(f"/api/cenas/{cena_id}/versions", headers=h).json()["items"]
    assert [v["details"].get("quadro") for v in versoes[:3]] == [2, 1, 0]

    # Os clipes: um por trecho, com o par de quadros vizinhos e o trecho-base. O `aprovar`
    # global aprova a sequência de todas as posições (os provisórios deixam de ser).
    rot = aprovar(client, h, rot, "keyframes")
    assert not any(x.provisorio for x in _ativos(db, cena_id))
    assert rot["posicoes"][0]["aprovadoKeyframesEm"] is not None
    # Os dois nascem na mesma transação (mesmo `created_at`): ordena pelo trecho.
    clipes = sorted(_geracoes(db, "cena.clipe", cena_id), key=lambda g: g.params["extras"]["trecho"])
    assert [(g.params["extras"]["trecho"], g.params["referencias"]) for g in clipes] == [
        (0, [str(q[0].image_id), str(q[1].image_id)]),
        (1, [str(q[1].image_id), str(q[2].image_id)])]
    assert {g.params["extras"]["duracaoS"] for g in clipes} == {5.0}
    assert {g.params["extras"]["quadros"] for g in clipes} == {124}  # MiniMax 17k+5
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    db.expire_all()
    pos = db.get(Roteiro, uuid.UUID(rot["id"])).posicoes_rel[0]
    trechos = pos.trechos_ordenados()
    assert [x.trecho for x in trechos] == [0, 1] and pos.tomada_id is None
    t0, t1 = (db.get(CenaTomada, x.tomada_id) for x in trechos)
    assert (t0.trecho, t0.keyframe_image_id, t0.keyframe_fim_image_id) == \
        (0, q[0].image_id, q[1].image_id)
    assert (t1.trecho, t1.keyframe_image_id, t1.keyframe_fim_image_id) == \
        (1, q[1].image_id, q[2].image_id)
    assert db.get(Cena, cena_id).tomada_escolhida_id is None  # a do trecho fica na posição
    assert [p["duracaoS"] for p in rot["posicoes"]] == [10.0]

    # FR-028: refazer o quadro 2 só refaz ele e o trecho 1; o trecho 0 fica.
    cena = db.get(Cena, cena_id, with_for_update=True)
    assert quadros.arquivar_desde(db, Actor(kind="user", user_id=owner[0].id), cena, 2) == [2]
    maquina.keyframe_mudou(db, cena_id)
    db.commit()
    rot = ver_roteiro(client, h, rot["id"])
    assert rot["status"] == "gerando_keyframes"
    g2b = _geracoes(db, "cena.keyframe", cena_id)[-1]
    assert g2b.params["extras"]["quadro"] == 2
    assert g2b.params["referencias"][0] == str(q[1].image_id)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")
    rot = aprovar(client, h, ver_roteiro(client, h, rot["id"]), "keyframes")
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    clipes = _geracoes(db, "cena.clipe", cena_id)
    assert len(clipes) == 3 and clipes[-1].params["extras"]["trecho"] == 1
    db.expire_all()
    novos = db.get(Roteiro, uuid.UUID(rot["id"])).posicoes_rel[0].trechos_ordenados()
    assert novos[0].tomada_id == t0.id and novos[1].tomada_id != t1.id
    assert db.get(CenaTomada, t1.id).desuso_em is not None
    assert db.get(CenaTomada, t0.id).desuso_em is None


def test_quadro_refeito_cancela_o_pedido_velho_e_recusa_a_escolha(client, db, owner, motores):
    h = owner[1]
    _, rot, cena_id = _guiado(client, h, motores, db, owner[0], trechos=1)
    rot = _ate_quadros(client, h, motores, rot)  # o pedido do quadro 0 ainda na fila
    [velha] = _geracoes(db, "cena.keyframe", cena_id)
    # O quadro 0 refeito com outra instrução (o ajuste) antes da escolha.
    cena = db.get(Cena, cena_id, with_for_update=True)
    assert quadros.arquivar_desde(db, Actor(kind="user", user_id=owner[0].id), cena, 0,
                                  instrucoes={0: "She smiles, state new"}) == [0]
    maquina.keyframe_mudou(db, cena_id)
    db.commit()
    gs = _geracoes(db, "cena.keyframe", cena_id)
    assert gs[0].id == velha.id and gs[0].status == GeracaoStatus.cancelada
    assert gs[-1].params["extras"]["quadro"] == 0 and "state new" in gs[-1].params["prompt"]
    q0 = _ativos(db, cena_id)[0]
    assert q0.geracao_id == gs[-1].id and q0.instrucao == "She smiles, state new"


def test_portao_de_keyframes_desligado_segue_a_cadeia_sozinho(client, db, owner, motores):
    h = owner[1]
    _, rot, cena_id = _guiado(client, h, motores, db, owner[0], trechos=2)
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    q = _ativos(db, cena_id)
    assert len(q) == 3 and all(x.image_id for x in q)
    assert all(x.provisorio for x in q)  # a opção única aplicada pela máquina (R3)
    assert len(_geracoes(db, "cena.clipe", cena_id)) == 2
    v = client.get(f"/api/cenas/{cena_id}/versions", headers=h).json()["items"]
    quadros_v = [x for x in v if x["details"].get("acao") == "quadro"]
    assert len(quadros_v) == 3 and all(x["details"]["provisorio"] for x in quadros_v)
