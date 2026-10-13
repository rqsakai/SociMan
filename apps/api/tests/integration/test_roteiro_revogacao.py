"""Revogação de pessoa real e os roteiros (spec 011, T056, FR-048, R16; 029: entre perfis): revogar
a voz e o avatar (pela `revogacao.py` da 025) não toca tomadas, narrações, entregas nem
conteúdos; narração, keyframe e clipe novos levam 409 `consentimento_revogado` (ação humana) ou
falham (máquina); montar e finalizar com o que existe continuam; as referências apagadas
aparecem como "referência removida". O roteiro é do perfil B e usa a voz e o avatar do A."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from sqlalchemy import func, select, text

from integration.padrao_helpers import consentimento
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    arquivo_do_slot,
    controle,
    criar_roteiro,
    editar,
    levar_ate,
    montar,
    motores,
    owner,
    perfil,
    rodar_ate,
    ver_roteiro,
)
from sociman_api.cenas.models import CenaTomada
from sociman_api.conteudos.models import Conteudo
from sociman_api.roteiros.models import RoteiroEntrega, RoteiroNarracao


def _contagens(db) -> tuple:
    db.expire_all()
    return (db.scalar(select(func.count()).select_from(CenaTomada)
                      .where(CenaTomada.video_key.is_not(None))),
            db.scalar(select(func.count()).select_from(RoteiroNarracao)
                      .where(RoteiroNarracao.audio_id.is_not(None))),
            db.scalar(select(func.count()).select_from(RoteiroEntrega)),
            db.scalar(select(func.count()).select_from(Conteudo)))


def _pessoa_real(db, avatar_id: str) -> None:
    """O avatar sintético dos helpers vira de pessoa real (só no teste) para registrar e revogar
    o consentimento."""
    db.execute(text("UPDATE assets SET origem = NULL WHERE id = :a"), {"a": uuid.UUID(avatar_id)})
    db.commit()


def _err(r) -> str:
    return r.json()["error"]["code"]


def test_revogar_voz_e_avatar_de_outro_perfil(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)  # perfil A: voz, avatar e produto
    outro = perfil(client, h, "outro")
    rot = criar_roteiro(client, h, b | {"perfil_id": outro})
    assert rot["perfilId"] == outro and rot["voz"]["id"] == b["voz"]["id"]
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False, clipes=False)
    rot = acao(client, h, rot, "planejar")
    rot = levar_ate(client, h, motores, rot, "aguardando_final", voltas=20)
    cena0 = rot["posicoes"][0]["cena"]["id"]
    kit = arquivo_do_slot(b["avatar"])["imageId"] if "imageId" in arquivo_do_slot(b["avatar"]) \
        else arquivo_do_slot(b["avatar"])["image"]["id"]
    c = client.get(f"/api/cenas/{cena0}", headers=h).json()
    r = client.patch(f"/api/cenas/{cena0}", headers=h,
                     json={"version": c["version"], "keyframeRefs": [kit]})
    assert r.status_code == 200, r.text
    antes = _contagens(db)

    # Revoga a voz e o avatar (o avatar precisa do consentimento registrado).
    v = client.get(f"/api/vozes/{b['voz']['id']}", headers=h).json()
    r = client.post(f"/api/vozes/{v['id']}/consentimento/revogar", headers=h,
                    json={"version": v["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    _pessoa_real(db, b["avatar"]["id"])
    a = client.get(f"/api/assets/{b['avatar']['id']}", headers=h).json()["asset"]
    a = consentimento(client, h, a["id"], a["version"])["asset"]
    r = client.post(f"/api/assets/{a['id']}/consentimento/revogar", headers=h,
                    json={"version": a["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    assert _contagens(db) == antes  # nada do roteiro foi apagado

    rot = ver_roteiro(client, h, rot["id"])
    assert rot["voz"]["revogada"] and rot["avatar"]["revogado"]
    assert rot["narracao"]["audioUrl"] and all(p["tomada"]["videoUrl"] for p in rot["posicoes"])
    r = client.get(f"/api/cenas/{cena0}", headers=h)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["keyframeRefs"] == [{"imageId": kit, "removida": True, "thumbUrl": None}]
    # Geração nova pela ação humana: 409 `consentimento_revogado`.
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h,
                     json={"version": rot["version"], "velocidade": "1.00"})
    assert r.status_code == 409 and _err(r) == "consentimento_revogado"
    r = client.post(f"/api/roteiros/{rot['id']}/posicoes/0/keyframe/regerar", headers=h,
                    json={"version": rot["version"]})
    assert r.status_code == 409 and _err(r) == "consentimento_revogado"
    r = client.post(f"/api/roteiros/{rot['id']}/posicoes/0/clipe/regerar", headers=h,
                    json={"version": rot["version"]})
    assert r.status_code == 409 and _err(r) == "consentimento_revogado"
    # Finalizar com o que existe continua: o vídeo é entregue.
    rot = acao(client, h, rot, "aprovar", portao="final")
    rot = rodar_ate(client, h, motores, rot["id"], "pronto")
    assert rot["conteudoId"]


def test_geracao_na_fila_falha_com_o_avatar_revogado(client, db, owner, motores):
    """Na máquina (R16): o clipe pedido antes da revogação falha no claim, e o roteiro vai a
    `falhou` com "consentimento revogado"."""
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    rot = criar_roteiro(client, h, b)
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False)
    rot = acao(client, h, rot, "planejar")
    claude, gpu = motores.linha_claude(), motores.linha_gpu()
    for _ in range(40):  # até os clipes entrarem na fila
        rot = ver_roteiro(client, h, rot["id"])
        if rot["status"] == "gerando_clipes" and any(
                g["passo"] == "cena.clipe" for p in rot["posicoes"]
                for g in p["geracoesAbertas"]):
            break
        claude.volta()
        gpu.volta()
    assert rot["status"] == "gerando_clipes"
    _pessoa_real(db, b["avatar"]["id"])
    a = client.get(f"/api/assets/{b['avatar']['id']}", headers=h).json()["asset"]
    a = consentimento(client, h, a["id"], a["version"])["asset"]
    r = client.post(f"/api/assets/{a['id']}/consentimento/revogar", headers=h,
                    json={"version": a["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    rot = rodar_ate(client, h, motores, rot["id"], "falhou")
    assert rot["etapaFalhou"] == "clipes" and "onsentimento revogado" in rot["erro"]["message"]
    assert uuid.UUID(rot["id"])
