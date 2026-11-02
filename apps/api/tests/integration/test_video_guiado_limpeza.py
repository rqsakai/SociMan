"""Limpeza e revogação do vídeo guiado (spec 031, T055; data-model "Limpeza e revogação"; exceção 1
ampliada da constitution 4.5.0, `intermediarios_90d`):
- a imagem do quadro refeito (arquivado) sai 90 dias depois do `archived_at` (89 dias, fica); o
  quadro arquivado e o candidato escolhido ficam com a imagem nula; os quadros atuais ficam;
- a tomada de trecho trocada sai 90 dias depois do `desuso_em`; as do vídeo entregue ficam;
- revogar o avatar: quadro e trecho novos pela ação humana → 409 `consentimento_revogado`; o trecho
  na fila falha no claim; a `roteiro_conversa` (só inserção) fica intacta."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from minio.error import S3Error
from sqlalchemy import func, select, text

from integration.guiado_helpers import aprovar_posicao, ate_quadros, ativos, guiado
from integration.padrao_helpers import consentimento
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    aprovar,
    controle,
    motores,
    owner,
    rodar_ate,
    ver_roteiro,
)
from sociman_api import storage
from sociman_api.auth.models import SecurityEvent
from sociman_api.cenas.models import CenaQuadro, CenaTomada
from sociman_api.geracao import limpeza
from sociman_api.geracao.models import GeracaoCandidato
from sociman_api.perfis.models import Image
from sociman_api.roteiros.models import (
    ConversaTipo,
    Roteiro,
    RoteiroConversa,
    RoteiroEntrega,
)


def _existe(key: str, bucket) -> bool:
    try:
        storage.stat(key, bucket=bucket)
        return True
    except S3Error:
        return False


def _regerar(client, h, rot: dict, ordem: int, etapa: str, status: int = 200, **corpo) -> dict:
    r = client.post(f"/api/roteiros/{rot['id']}/posicoes/{ordem}/{etapa}/regerar", headers=h,
                    json={"version": rot["version"], **corpo})
    assert r.status_code == status, r.text
    return r.json()


def _trechos(db, roteiro_id: str) -> list[uuid.UUID | None]:
    db.expire_all()
    return [x.tomada_id for x in
            db.get(Roteiro, uuid.UUID(roteiro_id)).posicoes_rel[0].trechos_ordenados()]


def _envelhecer(db, sql: str, ids: list, dias: int) -> None:
    db.execute(text(sql), {"d": dias, "ids": ids})
    db.commit()


ARQUIVAR = ("UPDATE cena_quadros SET archived_at = now() - make_interval(days => :d) "
            "WHERE id = ANY(:ids)")
DESUSO = ("UPDATE cena_tomadas SET desuso_em = now() - make_interval(days => :d) "
          "WHERE id = ANY(:ids)")
# As gerações também ficam velhas (o provedor `params` protege o que uma geração recente cita).
GERACOES = "UPDATE geracoes SET finished_at = now() - make_interval(days => :d) WHERE id = ANY(:ids)"


def test_limpeza_do_quadro_refeito_e_da_tomada_de_trecho(client, db, owner, motores):
    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[2])
    rot = ate_quadros(client, h, motores, controle(client, h, rot, final=False))

    # Refaz o quadro 2 antes dos clipes: a imagem velha fica no quadro arquivado.
    velho = ativos(db, c0)[2]
    id_velha, quadro_velho = velho.image_id, velho.id
    key_velha = db.get(Image, id_velha).object_key
    cand_velho = db.scalar(select(GeracaoCandidato.id).where(
        GeracaoCandidato.image_id == id_velha))
    rot = _regerar(client, h, rot, 0, "keyframe", quadro=2)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")
    atuais = ativos(db, c0)
    assert all(q.image_id for q in atuais) and atuais[2].image_id != id_velha
    rot = aprovar_posicao(client, h, ver_roteiro(client, h, rot["id"]), 0)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    t0, t1 = _trechos(db, rot["id"])

    # Refaz o trecho 1: a tomada velha fica em desuso; o vídeo é entregue com a nova.
    rot = _regerar(client, h, rot, 0, "clipe", trecho=1)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    _, t1_nova = _trechos(db, rot["id"])
    assert t1_nova != t1 and db.get(CenaTomada, t1).desuso_em is not None
    rot = aprovar(client, h, rot, "clipes")
    rot = rodar_ate(client, h, motores, rot["id"], "pronto", voltas=60)
    db.expire_all()
    entrega = db.scalar(select(RoteiroEntrega).where(
        RoteiroEntrega.roteiro_id == uuid.UUID(rot["id"])))
    [pos] = entrega.posicoes
    assert [x["tomadaId"] for x in pos["trechos"]] == [str(t0), str(t1_nova)]
    assert pos["quadros"] == [str(q.image_id) for q in atuais]

    ids_geracoes = list(db.scalars(text("SELECT id FROM geracoes")))
    _envelhecer(db, GERACOES, ids_geracoes, 100)
    _envelhecer(db, ARQUIVAR, [quadro_velho], 89)  # ainda não
    _envelhecer(db, DESUSO, [t1], 91)
    _envelhecer(db, DESUSO, [t0, t1_nova], 200)  # do vídeo entregue: protegidas
    key_t1 = db.get(CenaTomada, t1).video_key

    r = limpeza.limpar(db)
    assert (r.tomadas, r.quadros) == (1, 0)
    db.expire_all()
    assert db.get(CenaTomada, t1).limpa_em is not None and not _existe(key_t1, "videos")
    assert all(db.get(CenaTomada, t).video_key for t in (t0, t1_nova))
    assert db.get(Image, id_velha) is not None and _existe(key_velha, "imagens")

    _envelhecer(db, ARQUIVAR, [quadro_velho], 91)
    r = limpeza.limpar(db)
    assert (r.tomadas, r.quadros) == (0, 1)
    db.expire_all()
    assert db.get(Image, id_velha) is None and not _existe(key_velha, "imagens")
    arquivado = db.get(CenaQuadro, quadro_velho)
    assert arquivado.archived_at is not None and arquivado.image_id is None
    assert db.get(GeracaoCandidato, cand_velho).image_id is None
    # O quadro atual nunca é apagado; o que o vídeo entregue usou continua.
    for q in ativos(db, c0):
        assert q.image_id and _existe(db.get(Image, q.image_id).object_key, "imagens")
    ev = db.scalars(select(SecurityEvent).where(SecurityEvent.type == "eliminacao_intermediarios")
                    .order_by(SecurityEvent.id)).all()
    assert [e.details["quadros"] for e in ev] == [0, 1]
    assert ev[-1].details["excecao"] == "intermediarios_90d"

    # A segunda rodada não faz nada.
    r = limpeza.limpar(db)
    assert (r.tomadas, r.quadros) == (0, 0)


def test_cena_derivada_solta_os_trechos_e_tomada_protege_o_quadro(client, db, owner, motores):
    """Refazer um quadro depois da aprovação deriva a cena (FR-022): as tomadas dos trechos da
    cena antiga saem de uso (`trocar_cena`) e, 90 dias depois, saem. A imagem de um quadro
    arquivado que uma tomada referencia (início ou fim) fica (`ck_tomadas_origem_local`)."""
    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[2])
    rot = aprovar_posicao(client, h, ate_quadros(client, h, motores, rot), 0)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    t0, t1 = _trechos(db, rot["id"])
    meio = ativos(db, c0)[1]
    id_meio, quadro_meio = meio.image_id, meio.id
    rot = _regerar(client, h, ver_roteiro(client, h, rot["id"]), 0, "keyframe", quadro=1)
    db.expire_all()
    assert db.get(Roteiro, uuid.UUID(rot["id"])).posicoes_rel[0].cena_id != c0  # derivada
    assert all(db.get(CenaTomada, t).desuso_em is not None for t in (t0, t1))
    assert db.get(CenaQuadro, quadro_meio).archived_at is None  # a cena antiga fica como está

    _envelhecer(db, GERACOES, list(db.scalars(text("SELECT id FROM geracoes"))), 100)
    _envelhecer(db, DESUSO, [t0, t1], 91)
    # Simula o quadro do meio refeito há 200 dias: as tomadas ainda o referenciam.
    _envelhecer(db, ARQUIVAR, [quadro_meio], 200)
    r = limpeza.limpar(db)
    assert (r.tomadas, r.quadros) == (2, 0)
    db.expire_all()
    assert all(db.get(CenaTomada, t).limpa_em is not None for t in (t0, t1))
    assert db.get(Image, id_meio) is not None
    assert db.get(CenaQuadro, quadro_meio).image_id == id_meio
    assert db.get(CenaTomada, t0).keyframe_fim_image_id == id_meio


def _pessoa_real(db, avatar_id: str) -> None:
    db.execute(text("UPDATE assets SET origem = NULL WHERE id = :a"), {"a": uuid.UUID(avatar_id)})
    db.commit()


def test_revogacao_recusa_quadro_e_trecho_e_nao_toca_a_conversa(client, db, owner, motores):
    h = owner[1]
    b, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[1])
    db.add(RoteiroConversa(roteiro_id=uuid.UUID(rot["id"]), seq=1, tipo=ConversaTipo.resposta,
                           conteudo={"texto": "O vestido é verde"}, autor_tipo="user",
                           autor_id=owner[0].id))
    db.commit()
    rot = aprovar_posicao(client, h, ate_quadros(client, h, motores, rot), 0)
    assert rot["status"] == "gerando_clipes"  # o clipe do trecho está na fila

    _pessoa_real(db, b["avatar"]["id"])
    a = client.get(f"/api/assets/{b['avatar']['id']}", headers=h).json()["asset"]
    a = consentimento(client, h, a["id"], a["version"])["asset"]
    r = client.post(f"/api/assets/{a['id']}/consentimento/revogar", headers=h,
                    json={"version": a["version"], "confirmo": True})
    assert r.status_code == 200, r.text

    # Ação humana: quadro e trecho novos → 409.
    rot = ver_roteiro(client, h, rot["id"])
    for etapa, corpo in (("keyframe", {"quadro": 1}), ("clipe", {"trecho": 0})):
        err = _regerar(client, h, rot, 0, etapa, 409, **corpo)
        assert err["error"]["code"] == "consentimento_revogado", etapa
    assert len(ativos(db, c0)) == 2 and all(q.image_id for q in ativos(db, c0))

    # Máquina: o trecho na fila falha no claim.
    rot = rodar_ate(client, h, motores, rot["id"], "falhou")
    assert rot["etapaFalhou"] == "clipes" and "onsentimento revogado" in rot["erro"]["message"]

    # A conversa fica como estava (só inserção, fora da revogação).
    db.expire_all()
    linhas = db.scalars(select(RoteiroConversa).where(
        RoteiroConversa.roteiro_id == uuid.UUID(rot["id"]))).all()
    assert [(c.seq, c.conteudo) for c in linhas] == [(1, {"texto": "O vestido é verde"})]
    assert db.scalar(select(func.count()).select_from(RoteiroConversa)) == 1
