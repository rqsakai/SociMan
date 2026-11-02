"""A cadeia de quadros do wizard (spec 031, US3, T032; R3, R9, P5) com os serviços falsos:
- com 1 opção, cada quadro vira **provisório** pela máquina (`system:roteiro`) e o seguinte nasce
  dele (o `base_image` do pedido é o quadro anterior);
- o portão de keyframes só passa com todas as posições aprovadas por humanos;
- `aprovar_posicao` com quadro faltando → 409 `nada_a_aprovar` (e fora da etapa, `etapa_errada`);
- com 2 opções (o avançado), a cadeia espera a escolha humana;
- mudar um quadro zera a aprovação da sequência e a dos clipes da posição (FR-028).
Nada chama serviço real."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from sqlalchemy import select

from integration.guiado_helpers import (
    aprovar_posicao,
    ate_narracao,
    ate_quadros,
    ativos,
    geracoes,
    guiado,
    versoes,
)
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    aprovar,
    motores,
    owner,
    rodar_ate,
    ver_roteiro,
)
from sociman_api.auth.deps import Actor
from sociman_api.cenas import quadros
from sociman_api.cenas.models import Cena
from sociman_api.geracao import service as geracao_service
from sociman_api.geracao.models import GeracaoCandidato, GeracaoStatus
from sociman_api.history import EntityVersion
from sociman_api.roteiros import maquina, pedidos
from sociman_api.roteiros.models import Roteiro


def test_opcao_unica_vira_provisoria_e_o_portao_espera_todas_as_posicoes(client, db, owner,
                                                                         motores):
    h = owner[1]
    _, rot, (c0, c1) = guiado(client, h, motores, db, owner[0], trechos=[2, 1])
    rot = ate_quadros(client, h, motores, rot)
    assert rot["status"] == "aguardando_keyframes"

    # Cada quadro: 1 opção, aplicada provisoriamente pela máquina; o seguinte nasce dele.
    for cena_id, n in ((c0, 3), (c1, 2)):
        qs, gs = ativos(db, cena_id), geracoes(db, "cena.keyframe", cena_id)
        assert len(qs) == n and all(q.image_id and q.provisorio for q in qs)
        assert [g.params["extras"]["quadro"] for g in gs] == list(range(n))
        assert all(g.n_opcoes == 1 and g.status == GeracaoStatus.escolhido for g in gs)
        for anterior, g in zip(qs, gs[1:], strict=False):
            assert g.params["extras"]["baseImageId"] == str(anterior.image_id)
            assert g.params["referencias"][0] == str(anterior.image_id)
    v = client.get(f"/api/cenas/{c0}/versions", headers=h).json()["items"]
    provisorias = [x for x in v if x["details"].get("acao") == "quadro"]
    assert len(provisorias) == 3
    assert all(x["details"]["provisorio"] and x["actorKind"] == "system:roteiro"
               for x in provisorias)
    g0 = geracoes(db, "cena.keyframe", c0)[0]
    gv = client.get(f"/api/geracoes/{g0.id}/versoes", headers=h).json()["items"]
    assert gv[0]["details"]["automatico"] and gv[0]["details"]["opcaoUnica"]
    assert not geracoes(db, "cena.clipe", c0)  # o provisório não passa do portão
    assert all(p["aprovadoKeyframesEm"] is None for p in rot["posicoes"])

    # Aprovar a posição 0 não passa o portão (a 1 falta); aprovar de novo, 409.
    rot = aprovar_posicao(client, h, rot, 0)
    assert rot["status"] == "aguardando_keyframes"
    assert rot["posicoes"][0]["aprovadoKeyframesEm"] is not None
    assert rot["posicoes"][1]["aprovadoKeyframesEm"] is None
    assert not any(q.provisorio for q in ativos(db, c0))
    assert all(q.provisorio for q in ativos(db, c1))
    err = aprovar_posicao(client, h, rot, 0, status=409)
    assert err["error"]["code"] == "nada_a_aprovar"
    err = aprovar_posicao(client, h, rot, 0, etapa="clipe", status=409)
    assert err["error"]["code"] == "etapa_errada"

    # FR-037: a aprovação é humana, com antes e depois.
    [ultima] = versoes(client, h, rot)[:1]
    assert ultima["details"] == {"acao": "aprovar_posicao", "etapa": "keyframes", "ordem": 0}
    assert ultima["autor"]["tipo"] == "usuario" and ultima["autor"]["id"] == str(owner[0].id)
    assert ultima["before"]["posicoes"][0]["aprovado_keyframes"] is False
    assert ultima["after"]["posicoes"][0]["aprovado_keyframes"] is True

    # A última posição aprovada passa o portão: os clipes são pedidos.
    rot = aprovar_posicao(client, h, rot, 1)
    assert rot["status"] == "gerando_clipes"
    assert versoes(client, h, rot)[0]["details"]["portao"] == "keyframes"
    assert len(geracoes(db, "cena.clipe", c0)) == 2 and len(geracoes(db, "cena.clipe", c1)) == 1

    # Os clipes também por posição; mudar um quadro zera a sequência e os clipes daquela posição.
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    rot = aprovar_posicao(client, h, rot, 0, etapa="clipe")
    rot = aprovar_posicao(client, h, rot, 1, etapa="clipe")
    assert rot["status"] == "montando"
    cena = db.get(Cena, c0, with_for_update=True)
    assert quadros.arquivar_desde(db, Actor(kind="user", user_id=owner[0].id), cena, 2) == [2]
    maquina.keyframe_mudou(db, c0)
    db.commit()
    rot = ver_roteiro(client, h, rot["id"])
    p0, p1 = rot["posicoes"]
    assert p0["aprovadoKeyframesEm"] is None and p0["aprovadoClipeEm"] is None
    assert p1["aprovadoKeyframesEm"] is not None and p1["aprovadoClipeEm"] is not None
    assert rot["status"] in ("gerando_keyframes", "aguardando_keyframes")


def test_aprovar_posicao_com_quadro_faltando(client, db, owner, motores):
    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[1])
    rot = ate_narracao(client, h, motores, rot)
    err = aprovar_posicao(client, h, rot, 0, status=409)
    assert err["error"]["code"] == "etapa_errada"
    rot = aprovar(client, h, rot, "narracao")
    assert rot["status"] == "gerando_keyframes"
    err = aprovar_posicao(client, h, rot, 0, status=409)  # o quadro 0 ainda na fila
    assert err["error"]["code"] == "nada_a_aprovar"
    err = client.post(f"/api/roteiros/{rot['id']}/aprovar", headers=h,
                      json={"version": rot["version"], "portao": "keyframes"})
    assert err.status_code == 409
    assert not ativos(db, c0)[0].image_id


def test_com_duas_opcoes_a_cadeia_espera_a_escolha_humana(client, db, owner, motores):
    """O avançado pede 2 ou mais opções (FR-015): a cadeia não segue sozinha."""
    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[1])
    rot = aprovar(client, h, ate_narracao(client, h, motores, rot), "narracao")
    [g0] = geracoes(db, "cena.keyframe", c0)
    ator = Actor(kind="user", user_id=owner[0].id)
    geracao_service.cancelar(db, ator, g0.id, g0.version)
    r = db.get(Roteiro, uuid.UUID(rot["id"]), with_for_update=True)
    g2 = pedidos.quadro(db, ator, r, r.posicoes_rel[0], 0, n=2)
    db.commit()
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")
    db.expire_all()
    g2 = db.get(type(g2), g2.id)
    assert g2.status == GeracaoStatus.revisao and g2.n_opcoes == 2
    assert ativos(db, c0)[0].image_id is None
    assert len(geracoes(db, "cena.keyframe", c0)) == 2  # o quadro 1 não foi pedido

    cand = db.scalar(select(GeracaoCandidato).where(GeracaoCandidato.geracao_id == g2.id,
                                                    GeracaoCandidato.numero == 2))
    versao = client.get(f"/api/cenas/{c0}", headers=h).json()["version"]
    resp = client.post(f"/api/geracoes/{g2.id}/escolher", headers=h,
                       json={"version": g2.version, "candidatoId": str(cand.id),
                             "alvoVersion": versao})
    assert resp.status_code == 200, resp.text
    q0 = ativos(db, c0)[0]
    assert q0.image_id == cand.image_id and not q0.provisorio  # a escolha humana
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")
    q = ativos(db, c0)
    assert q[1].image_id and q[1].provisorio  # o seguinte (1 opção) segue provisório
    g1 = geracoes(db, "cena.keyframe", c0)[-1]
    assert g1.params["referencias"][0] == str(q0.image_id)
    autores = {v.actor_kind for v in db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "cena", EntityVersion.entity_id == c0,
        EntityVersion.details["acao"].astext == "quadro"))}
    assert autores == {"user", "system:roteiro"}


def _sha(dados: bytes) -> str:
    import hashlib

    return hashlib.sha256(dados).hexdigest()


def test_cena_de_tres_trechos_quatro_quadros_e_refacao_parcial(client, db, owner, motores):
    """US5 (T044; FR-025 a FR-028): 3 trechos = 4 quadros e 3 clipes com os pares vizinhos (o
    `start_image`/`end_image` que o ComfyUI falso recebeu); refazer um quadro refaz ele, os
    seguintes e só os trechos que tocam neles."""
    from sociman_api.cenas.models import CenaTomada

    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[3])
    rot = ate_quadros(client, h, motores, rot)
    qs = ativos(db, c0)
    assert [q.papel.value for q in qs] == ["inicio", "meio1", "meio2", "fim"]
    assert all(q.image_id for q in qs)
    rot = aprovar_posicao(client, h, rot, 0)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    clipes = sorted(geracoes(db, "cena.clipe", c0), key=lambda g: g.params["extras"]["trecho"])
    assert [(g.params["extras"]["trecho"], g.params["referencias"]) for g in clipes] == [
        (t, [str(qs[t].image_id), str(qs[t + 1].image_id)]) for t in range(3)]
    # O ComfyUI falso recebeu os 3 pares (em qualquer ordem: os pedidos nascem juntos), que
    # formam a cadeia de 4 imagens diferentes: o fim de um trecho é o início do seguinte.
    pares = {_sha(i["start_image"]): _sha(i["end_image"])
             for i in motores.comfy.imagens_de("clipe_minimax")}
    [atual] = set(pares) - set(pares.values())
    cadeia = [atual]
    while atual in pares:
        atual = pares[atual]
        cadeia.append(atual)
    assert len(pares) == 3 and len(set(cadeia)) == 4
    assert rot["posicoes"][0]["duracaoS"] == 15.0

    # Refazer o quadro 2 (meio 2): refaz o 2 e o 3, e só os trechos 1 e 2; o trecho 0 fica.
    db.expire_all()
    p = db.get(Roteiro, uuid.UUID(rot["id"])).posicoes_rel[0]
    t0, t1, t2 = (x.tomada_id for x in p.trechos_ordenados())
    cena = db.get(Cena, c0, with_for_update=True)
    assert quadros.arquivar_desde(db, Actor(kind="user", user_id=owner[0].id), cena, 2) == [2, 3]
    maquina.keyframe_mudou(db, c0)
    db.commit()
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")
    novos = ativos(db, c0)
    assert [q.image_id for q in novos[:2]] == [q.image_id for q in qs[:2]]
    assert all(n.image_id != v.image_id for n, v in zip(novos[2:], qs[2:], strict=True))
    rot = aprovar_posicao(client, h, rot, 0)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    db.expire_all()
    p = db.get(Roteiro, uuid.UUID(rot["id"])).posicoes_rel[0]
    agora = [x.tomada_id for x in p.trechos_ordenados()]
    assert agora[0] == t0 and agora[1] not in (t1, None) and agora[2] not in (t2, None)
    assert [g.params["extras"]["trecho"] for g in geracoes(db, "cena.clipe", c0)[3:]] in \
        ([1, 2], [2, 1])
    nova = db.get(CenaTomada, agora[1])
    assert (nova.keyframe_image_id, nova.keyframe_fim_image_id) == (qs[1].image_id,
                                                                    novos[2].image_id)

    # Refazer o quadro 1 (meio 1) toca os três trechos: nenhum serve mais.
    cena = db.get(Cena, c0, with_for_update=True)
    assert quadros.arquivar_desde(db, Actor(kind="user", user_id=owner[0].id), cena, 1) == \
        [1, 2, 3]
    db.commit()
    from sociman_api.roteiros import estado

    q = ativos(db, c0)
    servem = [estado.tomada_serve_trecho(db, db.get(CenaTomada, x), db.get(Cena, c0), t, 5, q)
              for t, x in enumerate(agora)]
    assert servem == [False, False, False]


def test_movimento_de_mais_de_3_trechos_vira_duas_posicoes():
    """FR-029: cada cena ocupa de 1 a 3 trechos; um movimento de 4 trechos não passa no
    `problemas()` do plano e vira duas posições (2 + 2), que passam."""
    from sociman_api.roteiros import plano

    def _pos(trechos: int, n: int) -> dict:
        return {"cena_id": None, "nivel": None, "trechos": trechos, "frases": [n],
                "motivo": "Giro completo.",
                "nova": {"nome": f"Giro {n}", "acao": "She turns around", "plano": "medio",
                         "movimento": "parada", "camera": None, "motor": "minimax",
                         "quadros": [f"state {i}" for i in range(trechos + 1)]}}

    ctx = plano.ContextoV2(base=5, alvo=20)
    longo = plano.PlanoSaidaV2.model_validate(
        {"frases": ["Olha o giro!"], "posicoes": [_pos(4, 1)], "explicacao": "", "avisos": []})
    erros = plano.problemas_v2(longo) + plano.problemas_contexto(longo, ctx)
    assert any("trechos vai de 1 a 3" in e for e in erros)
    dividido = plano.PlanoSaidaV2.model_validate(
        {"frases": ["Olha o giro!", "E a volta!"], "posicoes": [_pos(2, 1), _pos(2, 2)],
         "explicacao": "", "avisos": []})
    assert plano.problemas_v2(dividido) == [] and plano.problemas_contexto(dividido, ctx) == []
