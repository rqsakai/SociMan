"""Limpeza de 90 dias dos intermediários de roteiro (spec 011, T055, R12; SC-009; exceção 1
ampliada da constitution 4.5.0): o que deixou de ser atual há 91 dias sai (a linha fica, sem a
mídia, com `limpa_em`); o de 89 dias e os protegidos ficam; a segunda rodada não faz nada; o
evento tem as contagens."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from minio.error import S3Error
from sqlalchemy import select, text

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
)
from sociman_api import storage
from sociman_api.auth.models import SecurityEvent
from sociman_api.cenas.models import CenaTomada
from sociman_api.geracao import limpeza
from sociman_api.geracao.models import Audio, Geracao, GeracaoCandidato
from sociman_api.roteiros.models import RoteiroNarracao


def _envelhecer(db, tabela: str, ids: list, dias: int) -> None:
    db.execute(text(f"UPDATE {tabela} SET desuso_em = now() - make_interval(days => :d) "
                    "WHERE id = ANY(:ids)"), {"d": dias, "ids": ids})
    db.commit()


def _existe(key: str, bucket) -> bool:
    try:
        storage.stat(key, bucket=bucket)
        return True
    except S3Error:
        return False


def test_limpa_o_velho_e_protege_o_entregue(client, db, owner, motores, tmp_path):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    rot = criar_roteiro(client, h, b)
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False, clipes=False)
    rot = acao(client, h, rot, "planejar")
    rot = levar_ate(client, h, motores, rot, "aguardando_final", voltas=20)
    n0, g0 = uuid.UUID(rot["narracao"]["id"]), uuid.UUID(rot["previa"]["geracaoId"])
    t0 = uuid.UUID(rot["posicoes"][1]["tomada"]["id"])
    frases = list(rot["frases"])
    frases[1] += " E ainda tem bolso, forro e um tecido que não amassa nunca."
    rot = editar(client, h, rot, frases=frases)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_final", voltas=40)
    t1 = uuid.UUID(rot["posicoes"][1]["tomada"]["id"])
    assert t1 != t0
    rot = aprovar(client, h, rot, "final")
    rot = rodar_ate(client, h, motores, rot["id"], "pronto")
    db.expire_all()
    narr0 = db.get(RoteiroNarracao, n0)
    audio0 = db.get(Audio, narr0.audio_id)
    cand_g0 = db.scalar(select(GeracaoCandidato).where(GeracaoCandidato.geracao_id == g0))
    tom0 = db.get(CenaTomada, t0)
    assert narr0.desuso_em and db.get(Geracao, g0).desuso_em and tom0.desuso_em
    # A tomada do Flow nunca entra (mesmo com `desuso_em` antigo).
    video = mp4_sintetico(tmp_path / "flow.mp4", 8, 360, 640)
    with video.open("rb") as fh:
        flow = client.post(f"/api/cenas/{rot['posicoes'][0]['cena']['id']}/tomadas", headers=h,
                           files={"file": ("flow.mp4", fh, "video/mp4")}).json()
    _envelhecer(db, "roteiro_narracoes", [n0], 91)
    _envelhecer(db, "geracoes", [g0], 91)
    _envelhecer(db, "cena_tomadas", [t0], 89)  # ainda não
    _envelhecer(db, "cena_tomadas", [t1, uuid.UUID(flow["id"])], 200)  # entregue e do Flow
    key_audio, key_previa, key_t0 = audio0.object_key, cand_g0.video_key, tom0.video_key

    r = limpeza.limpar(db)
    assert (r.narracoes, r.tomadas) == (1, 0) and r.candidatos == 1 and r.audios >= 1
    db.expire_all()
    narr0 = db.get(RoteiroNarracao, n0)
    assert narr0.audio_id is None and narr0.limpa_em is not None
    assert db.get(Audio, audio0.id) is None and not _existe(key_audio, "audios")
    cand_g0 = db.get(GeracaoCandidato, cand_g0.id)
    assert cand_g0.video_key is None and not _existe(key_previa, "videos")
    assert db.get(CenaTomada, t0).video_key == key_t0 and _existe(key_t0, "videos")
    assert db.get(CenaTomada, t1).limpa_em is None  # protegida pela entrega
    assert db.get(CenaTomada, uuid.UUID(flow["id"])).limpa_em is None
    ev = db.scalar(select(SecurityEvent).where(SecurityEvent.type == "eliminacao_intermediarios"))
    assert ev.details["excecao"] == "intermediarios_90d" and ev.details["narracoes"] == 1
    # O vídeo final e o que ele usou continuam (SC-009).
    entregue = rot["posicoes"]
    assert all(db.get(CenaTomada, uuid.UUID(p["tomada"]["id"])).video_key for p in entregue)

    # A segunda rodada não faz nada. A escolhida da cena (a 1ª tomada) é protegida: com a nova
    # escolhida, a antiga de 91 dias sai e a tela mostra "arquivo removido".
    r = limpeza.limpar(db)
    assert (r.narracoes, r.tomadas, r.candidatos) == (0, 0, 0)
    _envelhecer(db, "cena_tomadas", [t0], 91)
    assert limpeza.limpar(db).tomadas == 0
    cena1 = rot["posicoes"][1]["cena"]["id"]
    versao = client.get(f"/api/cenas/{cena1}", headers=h).json()["version"]
    r = client.post(f"/api/cenas/{cena1}/tomadas/{t1}/escolher", headers=h,
                    json={"version": versao})
    assert r.status_code == 200, r.text
    r = limpeza.limpar(db)
    assert r.tomadas == 1
    db.expire_all()
    tom0 = db.get(CenaTomada, t0)
    assert tom0.video_key is None and tom0.limpa_em is not None and not _existe(key_t0, "videos")
    clipe = db.scalar(select(GeracaoCandidato).where(GeracaoCandidato.video_key == key_t0))
    assert clipe is None  # o candidato do clipe (o mesmo objeto) também ficou sem o vídeo
    itens = client.get(f"/api/cenas/{rot['posicoes'][1]['cena']['id']}/tomadas", headers=h,
                       params={"arquivadas": True}).json()["items"]
    removida = next(i for i in itens if i["id"] == str(t0))
    assert removida["limpa"] is True and removida["videoUrl"] is None
