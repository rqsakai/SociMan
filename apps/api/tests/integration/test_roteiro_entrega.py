"""Prévia, acabamento e entrega na 014 (spec 011, US5, T044): a montagem roda fora da trava de
GPU; a prévia tem a duração da soma e a narração; o acabamento sai em 1080×1920 a 24 fps com
−14 LUFS (±1); o conteúdo nasce `gerado_ia`, sem destino; as cenas viram `usada`; a entrega fica
registrada. Tomada curta não monta. Serviços falsos, ffmpeg real."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import json
import os
import re
import subprocess
import tempfile
import uuid

from sqlalchemy import func, select

from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    controle,
    criar_roteiro,
    levar_ate,
    linha_montagem,
    montar,
    motores,
    owner,
    rodar_ate,
    ver_roteiro,
)
from sociman_api import storage
from sociman_api.cenas.models import Cena, CenaStatus
from sociman_api.conteudos.models import Conteudo
from sociman_api.geracao.models import Geracao, GeracaoCandidato, GeracaoStatus
from sociman_api.postagem.models import Postagem
from sociman_api.roteiros.models import RoteiroEntrega


def _baixar(key: str) -> str:
    fd, nome = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    storage.get_to_file(key, nome, bucket="videos")
    return nome


def _probe(path: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate:format=duration",
                        "-of", "json", path], capture_output=True, check=True)
    return json.loads(r.stdout)


def _lufs(path: str) -> float:
    r = subprocess.run(["ffmpeg", "-nostdin", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, check=False)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])


def test_do_plano_ao_conteudo(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    rot = criar_roteiro(client, h, b)
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False, clipes=False)
    rot = acao(client, h, rot, "planejar")
    rot = levar_ate(client, h, motores, rot, "aguardando_final", voltas=20)
    soma = sum(p["duracaoS"] for p in rot["posicoes"])
    previa = rot["previa"]
    # No máximo 1 quadro (24 fps) por cena de diferença (SC-006).
    assert previa["atual"] and abs(previa["duracaoMs"] / 1000 - soma) <= \
        len(rot["posicoes"]) / 24 + 0.01
    g = db.get(Geracao, uuid.UUID(previa["geracaoId"]))
    assert g.motor.value == "ffmpeg" and g.status == GeracaoStatus.escolhido
    cand = db.get(GeracaoCandidato, g.escolhido_id)
    info = _probe(_baixar(cand.video_key))
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio"}

    rot = acao(client, h, rot, "aprovar", portao="final")
    assert rot["status"] == "finalizando"
    rot = rodar_ate(client, h, motores, rot["id"], "pronto")
    assert rot["conteudoId"]
    conteudo = db.get(Conteudo, uuid.UUID(rot["conteudoId"]))
    assert conteudo.gerado_ia is True and conteudo.titulo == rot["nome"]
    assert db.scalar(select(func.count()).select_from(Postagem)
                     .where(Postagem.conteudo_id == conteudo.id)) == 0  # sem destino (SC-005)
    final = _baixar(conteudo.video_key)
    info = _probe(final)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"], video["r_frame_rate"]) == (1080, 1920, "24/1")
    assert abs(_lufs(final) + 14) <= 1
    # As cenas viraram `usada` e a entrega ficou registrada (com os motores).
    for p in rot["posicoes"]:
        assert db.get(Cena, uuid.UUID(p["cena"]["id"])).status == CenaStatus.usada
    entrega = db.scalar(select(RoteiroEntrega).where(
        RoteiroEntrega.roteiro_id == uuid.UUID(rot["id"])))
    assert entrega.conteudo_id == conteudo.id and entrega.motores == ["minimax"]
    assert len(entrega.posicoes) == len(rot["posicoes"])
    r = client.get(f"/api/conteudos/{conteudo.id}", headers=h)
    assert r.status_code == 200, r.text
    corpo = r.json()["conteudo"]
    assert corpo["geradoIa"] is True and corpo["roteiro"]["id"] == rot["id"]
    assert "MiniMax H3" in corpo["roteiro"]["avisoAtribuicao"]


def test_montagem_nao_espera_a_gpu(client, db, owner, motores):
    """FR-043: com um job de GPU rodando, a linha de montagem pega a prévia e termina."""
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    rot = criar_roteiro(client, h, b)
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False, clipes=False)
    rot = acao(client, h, rot, "planejar")
    claude, gpu = motores.linha_claude(), motores.linha_gpu()
    for _ in range(40):  # só as linhas Claude e GPU: a montagem fica na fila
        rot = ver_roteiro(client, h, rot["id"])
        if rot["status"] == "montando":
            break
        if rot["status"] == "aguardando_final":
            raise AssertionError("a montagem não deveria ter rodado")
        claude.volta()
        gpu.volta()
    assert rot["status"] == "montando"
    trava = Geracao(alvo_tipo="cena", alvo_id=uuid.uuid4(), passo="cena.clipe",
                    motor="comfyui", params={}, n_opcoes=1, status=GeracaoStatus.rodando,
                    heartbeat_at=func.now())
    db.add(trava)
    db.commit()
    assert linha_montagem(motores).volta() == "ok"
    rot = ver_roteiro(client, h, rot["id"])
    assert rot["status"] == "aguardando_final" and rot["previa"]["atual"]


def test_tomada_curta_volta_aos_clipes(client, db, owner, motores):
    """FR-032: a tomada mais curta que a posição não monta (nem congela quadro): a posição fica
    com `tomada_curta` e o roteiro volta aos clipes daquela cena."""
    from sqlalchemy import text

    from integration.roteiro_helpers import editar

    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    rot = criar_roteiro(client, h, b)
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False, clipes=False)
    rot = acao(client, h, rot, "planejar")
    rot = levar_ate(client, h, motores, rot, "aguardando_final", voltas=20)
    p = rot["posicoes"][1]
    db.execute(text("UPDATE cena_tomadas SET duracao_ms = 1000 WHERE id = :t"),
               {"t": uuid.UUID(p["tomada"]["id"])})
    db.commit()
    rot = editar(client, h, rot, nome="Vestido verde (2)")
    assert rot["status"] == "gerando_clipes"
    assert rot["posicoes"][1]["aviso"] == "tomada_curta"
    abertas = rot["posicoes"][1]["geracoesAbertas"]
    assert [g["passo"] for g in abertas] == ["cena.clipe"]
