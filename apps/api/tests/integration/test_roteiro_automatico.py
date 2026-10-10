"""Escolha automática do keyframe (spec 011, R9), parte 1 (T015): `escolher_automatico` só vale
para o `cena.keyframe` pedido por um roteiro não arquivado, numa etapa de keyframes, com a posição
ainda pedindo aquele keyframe e em modo automático ou com o portão KEYFRAMES desligado. Fora
disso, recusa sem mudar nada. O caminho feliz usa um aplicador de teste no lugar do da onda 2
(T027) e confere o ator `system:roteiro` ("sistema (automático)") e o `details.automatico`."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

import pytest
from sqlalchemy import select

from integration.roteiro_helpers import _buckets, motores, owner  # noqa: F401 — fixtures
from sociman_api import history
from sociman_api.auth.deps import ROTEIRO
from sociman_api.cenas import service as cenas_service
from sociman_api.cenas.models import Cena
from sociman_api.geracao import aplicadores
from sociman_api.geracao.models import (
    Geracao,
    GeracaoAlvo,
    GeracaoCandidato,
    GeracaoMotor,
    GeracaoStatus,
)
from sociman_api.geracao.service import EscolhaRecusada, escolher_automatico
from sociman_api.perfis.models import Image, ImageKind, Perfil
from sociman_api.roteiros.models import Roteiro, RoteiroCena, RoteiroModo, RoteiroStatus


class _AplicadorTeste(aplicadores.Aplicador):
    """Só para o teste: leva a opção ao keyframe da cena, como o da onda 2 fará."""

    def validar_alvo(self, db, perfil_id, alvo_id, *, lock=False):
        return db.get(Cena, alvo_id, with_for_update=lock)

    def aplicar(self, db, actor, geracao, candidato):
        cena = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        cenas_service.definir_keyframe(db, actor, cena, candidato.image_id,
                                       geracao_id=geracao.id, details={"automatico": True})


@pytest.fixture
def aplicador_teste(monkeypatch):
    monkeypatch.setitem(aplicadores.APLICADORES, "cena.keyframe", _AplicadorTeste())


def _imagem(db, kind=ImageKind.keyframe) -> uuid.UUID:
    iid = uuid.uuid4()
    db.add(Image(id=iid, kind=kind, object_key=f"agencia/{iid}.png", content_type="image/png",
                 bytes=1, width=736, height=1280, sha256="x"))
    db.flush()
    return iid


def _cenario(db, *, modo=RoteiroModo.revisar, keyframes=True,
             status=RoteiroStatus.gerando_keyframes, passo="cena.keyframe",
             extras: dict | None = None, geracao_status=GeracaoStatus.revisao) -> dict:
    perfil = Perfil(slug=f"p{uuid.uuid4().hex[:8]}", name="P")
    db.add(perfil)
    db.flush()
    cena = Cena(perfil_id=perfil.id, nome="Cena", acao="ela mostra o vestido")
    db.add(cena)
    db.flush()
    portoes = {"texto": True, "narracao": True, "keyframes": keyframes, "clipes": True,
               "final": True}
    roteiro = Roteiro(perfil_id=perfil.id, nome="Vestido", modo=modo, portoes=portoes,
                      status=status, frases=["Olha esse vestido."])
    db.add(roteiro)
    db.flush()
    db.add(RoteiroCena(roteiro_id=roteiro.id, ordem=0, cena_id=cena.id, frases=[0]))
    extras = {"roteiroId": str(roteiro.id), "ordem": 0} if extras is None else extras
    g = Geracao(perfil_id=perfil.id, alvo_tipo=GeracaoAlvo.cena, alvo_id=cena.id, passo=passo,
                motor=GeracaoMotor.comfyui, params={"bloco": "keyframe", "extras": extras},
                n_opcoes=2, status=geracao_status)
    db.add(g)
    db.flush()
    cands = []
    for n in (1, 2):
        c = GeracaoCandidato(geracao_id=g.id, numero=n, image_id=_imagem(db))
        db.add(c)
        cands.append(c)
    db.commit()
    return {"perfil": perfil, "cena": cena, "roteiro": roteiro, "geracao": g, "cands": cands}


def _recusa(db, g: Geracao, motivo: str) -> None:
    antes = g.version
    with pytest.raises(EscolhaRecusada) as exc:
        escolher_automatico(db, db.get(Geracao, g.id, with_for_update=True))
    assert str(exc.value) == motivo
    db.rollback()
    db.expire_all()
    g = db.get(Geracao, g.id)
    assert g.status in (GeracaoStatus.revisao, GeracaoStatus.rodando)
    assert g.escolhido_id is None and g.version == antes


def test_recusa_passo_que_nao_e_keyframe(db, aplicador_teste):
    c = _cenario(db, passo="cenario.variacao", modo=RoteiroModo.automatico)
    _recusa(db, c["geracao"], "passo")


def test_recusa_fora_de_roteiro(db, aplicador_teste):
    c = _cenario(db, modo=RoteiroModo.automatico, extras={})
    _recusa(db, c["geracao"], "fora_de_roteiro")
    c = _cenario(db, modo=RoteiroModo.automatico, extras={"roteiroId": "não é uuid"})
    _recusa(db, c["geracao"], "fora_de_roteiro")
    c = _cenario(db, modo=RoteiroModo.automatico,
                 extras={"roteiroId": str(uuid.uuid4()), "ordem": 0})
    _recusa(db, c["geracao"], "roteiro")


def test_recusa_com_o_portao_ligado_no_revisar(db, aplicador_teste):
    c = _cenario(db, modo=RoteiroModo.revisar, keyframes=True)
    _recusa(db, c["geracao"], "portao")


def test_recusa_roteiro_arquivado_ou_fora_da_etapa(db, aplicador_teste):
    c = _cenario(db, modo=RoteiroModo.automatico)
    r = db.get(Roteiro, c["roteiro"].id)
    r.archived_at = r.created_at
    db.commit()
    _recusa(db, c["geracao"], "roteiro")
    c = _cenario(db, modo=RoteiroModo.automatico, status=RoteiroStatus.gerando_clipes)
    _recusa(db, c["geracao"], "roteiro")


def test_recusa_posicao_de_outra_cena_ou_ja_atendida(db, aplicador_teste):
    c = _cenario(db, modo=RoteiroModo.automatico,
                 extras=None)
    g = c["geracao"]
    g = db.get(Geracao, g.id)
    g.params = {**g.params, "extras": {**g.params["extras"], "ordem": 3}}  # sem essa posição
    db.commit()
    _recusa(db, g, "roteiro")
    c = _cenario(db, modo=RoteiroModo.automatico)
    cena = db.get(Cena, c["cena"].id)
    cena.keyframe_inicial_id = c["cands"][0].image_id
    cena.keyframe_geracao_id = c["geracao"].id  # esta geração já foi aplicada
    db.commit()
    _recusa(db, c["geracao"], "roteiro")


def test_recusa_geracao_fora_de_revisao(db, aplicador_teste):
    c = _cenario(db, modo=RoteiroModo.automatico, geracao_status=GeracaoStatus.rodando)
    _recusa(db, c["geracao"], "status")


@pytest.mark.parametrize("modo,keyframes", [(RoteiroModo.automatico, True),
                                            (RoteiroModo.revisar, False)])
def test_escolhe_a_opcao_1_com_o_ator_do_roteiro(db, aplicador_teste, modo, keyframes):
    c = _cenario(db, modo=modo, keyframes=keyframes)
    g = escolher_automatico(db, db.get(Geracao, c["geracao"].id, with_for_update=True))
    db.commit()
    assert g.status == GeracaoStatus.escolhido and g.escolhido_id == c["cands"][0].id
    cena = db.get(Cena, c["cena"].id)
    assert cena.keyframe_inicial_id == c["cands"][0].image_id
    assert cena.keyframe_geracao_id == g.id
    v_cena = history.list_versions(db, "cena", cena.id)[0]
    assert v_cena.actor_kind == ROTEIRO.kind and v_cena.actor_user_id is None
    assert v_cena.details["automatico"] is True and v_cena.details["acao"] == "keyframe"
    v_g = history.list_versions(db, "geracao", g.id)[0]
    assert v_g.details["automatico"] is True and v_g.details["numero"] == 1
    assert history.autores(db, [v_g])[v_g.id]["nome"] == "sistema (automático)"
    assert db.scalar(select(GeracaoCandidato.numero).where(
        GeracaoCandidato.id == g.escolhido_id)) == 1


# ---- parte 2 (T032): pelo fluxo do roteiro, com os fakes ----

def _keyframes_do(db, roteiro_id: str) -> list[Geracao]:
    db.expire_all()
    return list(db.scalars(select(Geracao).where(
        Geracao.passo == "cena.keyframe",
        Geracao.params["extras"]["roteiroId"].astext == roteiro_id)))


def test_portao_desligado_escolhe_e_ligado_nao(client, db, owner, motores):
    from integration.roteiro_helpers import (
        acao,
        controle,
        criar_roteiro,
        montar,
        rodar_ate,
    )

    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    ligado = criar_roteiro(client, h, b, nome="Ligado")
    ligado = controle(client, h, ligado, texto=False, narracao=False)
    ligado = acao(client, h, ligado, "planejar")
    ligado = rodar_ate(client, h, motores, ligado["id"], "aguardando_keyframes")
    assert all(g.status == GeracaoStatus.revisao for g in _keyframes_do(db, ligado["id"]))

    desligado = criar_roteiro(client, h, b, nome="Desligado")
    desligado = controle(client, h, desligado, texto=False, narracao=False, keyframes=False,
                         clipes=True)
    desligado = acao(client, h, desligado, "planejar")
    desligado = rodar_ate(client, h, motores, desligado["id"], "aguardando_clipes")
    gs = _keyframes_do(db, desligado["id"])
    assert gs and all(g.status == GeracaoStatus.escolhido for g in gs)
    for g in gs:
        assert db.get(GeracaoCandidato, g.escolhido_id).numero == 1
        v = history.list_versions(db, "cena", g.alvo_id)
        kf = next(x for x in v if x.details.get("acao") == "keyframe")
        assert kf.actor_kind == "system:roteiro" and kf.details["automatico"] is True
    # As do roteiro com o portão ligado continuam esperando o humano.
    assert all(g.status == GeracaoStatus.revisao for g in _keyframes_do(db, ligado["id"]))


def test_fora_de_roteiro_e_arquivado_nao_escolhem(client, db, owner, motores):
    from integration.roteiro_helpers import (
        acao,
        controle,
        criar_roteiro,
        montar,
        rodar_ate,
    )
    from sociman_api.auth.deps import Actor as Ator
    from sociman_api.geracao import service as geracao_service
    from sociman_api.geracao.models import GeracaoAlvo

    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    cena = b["cenas"][0]
    img = _imagem(db)
    import io

    from PIL import Image as PILImage

    from sociman_api import storage

    buf = io.BytesIO()
    PILImage.new("RGB", (736, 1280), (10, 20, 30)).save(buf, format="PNG")
    storage.put(f"agencia/{img}.png", buf.getvalue(), "image/png")
    g = geracao_service.criar_para_alvo(
        db, Ator(kind="user", user_id=owner[0].id), None, "cena.keyframe", GeracaoAlvo.cena,
        uuid.UUID(cena["id"]), {"bloco": "keyframe", "prompt": "She smiles",
                                "instrucao": "She smiles", "referencias": [str(img)],
                                "largura": 736, "altura": 1280})
    db.commit()
    from integration.roteiro_helpers import rodar_gpu

    rodar_gpu(motores)
    db.expire_all()
    assert db.get(Geracao, g.id).status == GeracaoStatus.revisao  # ninguém escolheu
    assert db.get(Cena, uuid.UUID(cena["id"])).keyframe_inicial_id is None

    # O roteiro arquivado no meio: as gerações abertas são canceladas e nada é escolhido.
    rot = criar_roteiro(client, h, b, nome="Arquivado")
    rot = controle(client, h, rot, modo="automatico")
    rot = acao(client, h, rot, "planejar")
    rot = rodar_ate(client, h, motores, rot["id"], "gerando_keyframes", voltas=6)
    rot = acao(client, h, rot, "arquivar")
    gs = _keyframes_do(db, rot["id"])
    assert gs and all(x.status == GeracaoStatus.cancelada for x in gs)
    rodar_gpu(motores)
    assert all(x.status == GeracaoStatus.cancelada for x in _keyframes_do(db, rot["id"]))
