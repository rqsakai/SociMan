"""Clipe por cena com reuso sem GPU (spec 011, US4, T037; SC-003): a cena reaproveitada com
tomada útil não gera job; os clipes saem no motor da cena e com os quadros da fórmula; a tomada
aponta o objeto do candidato; regerar com `wan` cria só aquela geração; escolher outra tomada não
gera nada; a tomada do Flow só entra pela escolha manual."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from sqlalchemy import select

from integration.cenas_helpers import mp4_sintetico
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
from sociman_api.cenas.models import CenaTomada
from sociman_api.geracao.models import Geracao, GeracaoCandidato
from sociman_api.roteiros import tempos


def _gens(db, rot_id: str, passo: str) -> list[Geracao]:
    db.expire_all()
    return list(db.scalars(select(Geracao).where(
        Geracao.passo == passo, Geracao.params["extras"]["roteiroId"].astext == rot_id)
        .order_by(Geracao.created_at)))


def test_reuso_motor_e_tomadas(client, db, owner, motores, tmp_path):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    a = criar_roteiro(client, h, b, nome="Primeiro")
    a = controle(client, h, a, texto=False, narracao=False, keyframes=False, clipes=False)
    a = acao(client, h, a, "planejar")
    a = levar_ate(client, h, motores, a, "aguardando_final", voltas=20)
    clipes = _gens(db, a["id"], "cena.clipe")
    assert len(clipes) == len({p["cena"]["id"] for p in a["posicoes"]})
    for g in clipes:  # o motor da cena e os quadros da fórmula (R4)
        ex = g.params["extras"]
        assert g.params["bloco"] == f"clipe_{ex['motor']}"
        assert ex["quadros"] == tempos.quadros(ex["motor"], ex["duracaoS"])
        cand = db.scalar(select(GeracaoCandidato).where(GeracaoCandidato.geracao_id == g.id))
        t = db.scalar(select(CenaTomada).where(CenaTomada.geracao_id == g.id))
        assert t.video_key == cand.video_key and t.miniatura_key == cand.video_miniatura_key

    # O 2º roteiro reaproveita as mesmas cenas, com as mesmas frases: nenhum job de GPU.
    bb = roteiro_planejado(client, h, motores, b, nome="Segundo")
    bb = editar(client, h, bb, frases=a["frases"], posicoes=[
        {"cenaId": p["cena"]["id"], "frases": p["frases"]} for p in a["posicoes"]])
    bb = controle(client, h, bb, narracao=False, keyframes=False, clipes=False)
    bb = aprovar(client, h, bb, "texto")
    bb = rodar_ate(client, h, motores, bb["id"], "aguardando_final")
    assert _gens(db, bb["id"], "cena.keyframe") == [] and _gens(db, bb["id"], "cena.clipe") == []
    assert [p["tomada"]["id"] for p in bb["posicoes"]] == \
        [p["tomada"]["id"] for p in a["posicoes"]]

    # Regerar a posição 0 com `wan`: só aquela geração, com o motor gravado na cena.
    bb = controle(client, h, bb, narracao=False, keyframes=False)
    r = client.post(f"/api/roteiros/{bb['id']}/posicoes/0/clipe/regerar", headers=h,
                    json={"version": bb["version"], "motor": "wan"})
    assert r.status_code == 200, r.text
    novas = _gens(db, bb["id"], "cena.clipe")
    assert len(novas) == 1 and novas[0].params["bloco"] == "clipe_wan"
    cena0 = bb["posicoes"][0]["cena"]["id"]
    assert client.get(f"/api/cenas/{cena0}", headers=h).json()["motor"] == "wan"
    bb = rodar_ate(client, h, motores, bb["id"], "aguardando_clipes")
    nova = bb["posicoes"][0]["tomada"]
    assert nova["motor"] == "wan" and nova["id"] != a["posicoes"][0]["tomada"]["id"]

    # Escolher outra tomada existente (a antiga) não gera nada.
    antes = len(_gens(db, bb["id"], "cena.clipe"))
    r = client.put(f"/api/roteiros/{bb['id']}/posicoes/0/tomada", headers=h,
                   json={"version": bb["version"], "tomadaId": a["posicoes"][0]["tomada"]["id"]})
    assert r.status_code == 200, r.text
    bb = r.json()
    assert bb["posicoes"][0]["tomada"]["id"] == a["posicoes"][0]["tomada"]["id"]
    assert len(_gens(db, bb["id"], "cena.clipe")) == antes

    # A tomada do Flow: não entra sozinha; pela escolha manual, entra (se tiver duração).
    video = mp4_sintetico(tmp_path / "flow.mp4", 8, 360, 640)
    with video.open("rb") as fh:
        r = client.post(f"/api/cenas/{cena0}/tomadas", headers=h,
                        files={"file": ("flow.mp4", fh, "video/mp4")})
    assert r.status_code == 201, r.text
    flow = r.json()
    bb = ver_roteiro(client, h, bb["id"])
    assert bb["posicoes"][0]["tomada"]["id"] != flow["id"]
    r = client.put(f"/api/roteiros/{bb['id']}/posicoes/0/tomada", headers=h,
                   json={"version": bb["version"], "tomadaId": flow["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["posicoes"][0]["tomada"]["origem"] == "flow_manual"
    curta = mp4_sintetico(tmp_path / "curta.mp4", 1, 360, 640)
    with curta.open("rb") as fh:
        flow2 = client.post(f"/api/cenas/{cena0}/tomadas", headers=h,
                            files={"file": ("curta.mp4", fh, "video/mp4")}).json()
    bb = ver_roteiro(client, h, bb["id"])
    if bb["posicoes"][0]["duracaoS"] > 1:
        r = client.put(f"/api/roteiros/{bb['id']}/posicoes/0/tomada", headers=h,
                       json={"version": bb["version"], "tomadaId": flow2["id"]})
        assert r.status_code == 400 and r.json()["error"]["code"] == "tomada_curta"
    assert uuid.UUID(flow["id"])
