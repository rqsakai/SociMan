"""Voltar uma etapa e invalidações em cascata (spec 011, US7, T050; SC-006): nada é apagado, só
o que mudou é refeito, e as gerações abertas que ficaram velhas são canceladas no nome de quem
mudou."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import io
import uuid

from PIL import Image as PILImage
from sqlalchemy import func, select

from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    aprovar,
    controle,
    criar_roteiro,
    editar,
    levar_ate,
    montar,
    motores,
    owner,
    rodar_ate,
    roteiro_planejado,
    ver_roteiro,
)
from sociman_api import history
from sociman_api.cenas.models import CenaTomada
from sociman_api.geracao.models import Geracao, GeracaoCandidato, GeracaoStatus
from sociman_api.roteiros.models import RoteiroNarracao


def _gens(db, rot_id: str, passo: str) -> list[Geracao]:
    db.expire_all()
    return list(db.scalars(select(Geracao).where(
        Geracao.passo == passo, Geracao.params["extras"]["roteiroId"].astext == rot_id)
        .order_by(Geracao.created_at)))


def _ate_final(client, h, m, b, **kw) -> dict:
    rot = criar_roteiro(client, h, b, **kw)
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False, clipes=False)
    rot = acao(client, h, rot, "planejar")
    return levar_ate(client, h, m, rot, "aguardando_final", voltas=20)


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (w, h), (200, 30, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _soma_ok(rot: dict) -> None:
    soma = sum(p["duracaoS"] for p in rot["posicoes"])
    assert abs(rot["previa"]["duracaoMs"] / 1000 - soma) <= len(rot["posicoes"]) / 24 + 0.01


def test_frase_editada_refaz_so_o_que_mudou(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    rot = _ate_final(client, h, motores, b)
    duracoes = [p["duracaoS"] for p in rot["posicoes"]]
    clipes_antes = len(_gens(db, rot["id"], "cena.clipe"))
    narracao_antes = rot["narracao"]["id"]
    previa_antes = rot["previa"]["geracaoId"]
    # A posição 1 cresce bem além da tomada; as outras continuam cabendo.
    frases = list(rot["frases"])
    frases[1] = frases[1] + " E ainda tem bolso, forro e um tecido que não amassa nunca."
    rot = editar(client, h, rot, frases=frases)
    assert rot["status"] == "narrando" and rot["narracao"]["desatualizada"]
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_final", voltas=40)
    novas = [p["duracaoS"] for p in rot["posicoes"]]
    assert novas[1] > duracoes[1] and rot["narracao"]["id"] != narracao_antes
    clipes = _gens(db, rot["id"], "cena.clipe")
    assert len(clipes) == clipes_antes + 1
    assert str(clipes[-1].alvo_id) == rot["posicoes"][1]["cena"]["id"]
    assert rot["previa"]["geracaoId"] != previa_antes and rot["previa"]["atual"]
    _soma_ok(rot)
    # Nada foi apagado: a narração e a prévia antigas continuam, com os arquivos.
    antiga = db.get(RoteiroNarracao, uuid.UUID(narracao_antes))
    assert antiga.audio_id is not None and antiga.desuso_em is not None
    g = db.get(Geracao, uuid.UUID(previa_antes))
    assert db.get(GeracaoCandidato, g.escolhido_id).video_key is not None
    assert g.desuso_em is not None
    # Uma frase menor cabe na tomada: nenhum clipe novo, só a montagem.
    frases = list(rot["frases"])
    frases[3] = "Corre!"
    rot = editar(client, h, rot, frases=frases)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_final", voltas=40)
    assert len(_gens(db, rot["id"], "cena.clipe")) == clipes_antes + 1
    _soma_ok(rot)


def test_geracoes_abertas_canceladas_com_o_autor(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    rot = criar_roteiro(client, h, b)
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False, clipes=False)
    rot = acao(client, h, rot, "planejar")
    claude, gpu = motores.linha_claude(), motores.linha_gpu()
    for _ in range(40):  # sem a linha de montagem: a prévia fica na fila
        rot = ver_roteiro(client, h, rot["id"])
        if rot["status"] == "montando":
            break
        claude.volta()
        gpu.volta()
    [aberta] = [g for g in rot["geracoesAbertas"] if g["passo"] == "roteiro.montagem"]
    frases = [*rot["frases"][:-1], rot["frases"][-1] + " Hoje!"]
    rot = editar(client, h, rot, frases=frases)
    g = db.get(Geracao, uuid.UUID(aberta["id"]))
    db.refresh(g)
    assert g.status == GeracaoStatus.cancelada
    v = history.list_versions(db, "geracao", g.id)[0]
    assert v.details["acao"] == "cancelar" and v.actor_user_id == owner[0].id


def test_keyframe_trocado_volta_os_roteiros_da_cena(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    um = _ate_final(client, h, motores, b, nome="Um")
    dois = roteiro_planejado(client, h, motores, b, nome="Dois")
    dois = editar(client, h, dois, frases=um["frases"], posicoes=[
        {"cenaId": p["cena"]["id"], "frases": p["frases"]} for p in um["posicoes"]])
    dois = controle(client, h, dois, narracao=False, keyframes=False, clipes=False)
    dois = aprovar(client, h, dois, "texto")
    dois = rodar_ate(client, h, motores, dois["id"], "aguardando_final")
    clipes_um = len(_gens(db, um["id"], "cena.clipe"))
    tomada_antiga = um["posicoes"][2]["tomada"]["id"]
    # Troca o keyframe da posição 2 (upload): só aquela cena regera o clipe, nos dois roteiros.
    um = ver_roteiro(client, h, um["id"])
    r = client.post(f"/api/roteiros/{um['id']}/posicoes/2/keyframe", headers=h,
                    data={"version": str(um["version"])},
                    files={"arquivo": ("k.png", _png(736, 1280), "image/png")})
    assert r.status_code == 200, r.text
    um = r.json()
    assert um["status"] == "gerando_clipes"
    dois = ver_roteiro(client, h, dois["id"])
    assert dois["status"] == "gerando_clipes"
    t = db.get(CenaTomada, uuid.UUID(tomada_antiga))
    assert t is not None and t.video_key is not None  # a tomada antiga continua guardada
    um = rodar_ate(client, h, motores, um["id"], "aguardando_final", voltas=40)
    clipes = _gens(db, um["id"], "cena.clipe")
    assert len(clipes) == clipes_um + 1
    assert str(clipes[-1].alvo_id) == um["posicoes"][2]["cena"]["id"]
    dois = rodar_ate(client, h, motores, dois["id"], "aguardando_final", voltas=40)
    assert dois["posicoes"][2]["tomada"]["id"] == um["posicoes"][2]["tomada"]["id"]
    # Depois de entregue, as cenas ficam `usada`: trocar o keyframe é recusado.
    um = aprovar(client, h, um, "final")
    um = rodar_ate(client, h, motores, um["id"], "pronto")
    r = client.post(f"/api/roteiros/{um['id']}/posicoes/2/keyframe", headers=h,
                    data={"version": str(um["version"])},
                    files={"arquivo": ("k.png", _png(736, 1280), "image/png")})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cena_usada"
    assert db.scalar(select(func.count()).select_from(RoteiroNarracao)) >= 2
