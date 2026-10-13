"""Extensões da 021 para a spec 011 (T012, R2, R3, R5 e R11), com aplicadores de teste no lugar
dos da onda 2: o clipe (bloco de vídeo do ComfyUI) vira candidato de vídeo com miniatura e as
medidas do ffprobe; a montagem roda na `LinhaMontagem` (motor `ffmpeg`) com um job de GPU
rodando; a narração usa o `/v2/tts_paragraph`, aplica o `atempo` e divide os tempos; o link
`geracao_video` serve o mp4 com Range. Nada chama serviço real."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import io
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

import pytest
from PIL import Image as PILImage
from sqlalchemy import func, select

from integration.geracao_helpers import (  # noqa: F401 — fixtures
    _buckets,
    motores,
    owner,
    rodar_gpu,
)
from sociman_api import storage
from sociman_api.geracao import aplicadores, gerador, video
from sociman_api.geracao.models import (
    Audio,
    Geracao,
    GeracaoAlvo,
    GeracaoCandidato,
    GeracaoMotor,
    GeracaoStatus,
)
from sociman_api.perfis.models import Image, ImageKind


class _Clipe(aplicadores.Aplicador):
    aplicados: list[uuid.UUID]

    def __init__(self):
        self.aplicados = []

    def validar_alvo(self, db, perfil_id, alvo_id, *, lock=False):
        return None

    def conferir_referencias(self, db, geracao):
        return None

    def aplicar(self, db, actor, geracao, candidato):
        self.aplicados.append(candidato.id)


class _Montagem(_Clipe):
    """Junta o vídeo de um candidato anterior (baixado pelo `ctx`) num mp4 novo, com ffmpeg."""

    def __init__(self, fonte_key: str):
        super().__init__()
        self.fonte_key = fonte_key
        self.pastas: list[Path] = []

    def executar_video(self, geracao, ctx):
        self.pastas.append(ctx.pasta)
        entrada = ctx.baixar(self.fonte_key, "videos", "../fora/entrada.mp4")
        assert entrada.parent == ctx.pasta  # o nome não sai da pasta de trabalho
        ctx.andamento(50, "Juntando")
        saida = ctx.pasta / "previa.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                        "-i", str(entrada), "-an", "-c:v", "libx264", "-preset", "ultrafast",
                        str(saida)], check=True, timeout=120)
        return saida


class _Narracao(_Clipe):
    def __init__(self, velocidade: float = 1.08):
        super().__init__()
        self.velocidade = velocidade

    def pedido_tts(self, db, geracao):
        return {"op": "paragrafo", "velocidade": self.velocidade,
                "corpo": {"sentences": ["Olha esse vestido.", "Ele é levinho e fresco."],
                          "voice": "animada", "seed": 7, "max_attempts": 5,
                          "min_similarity": 0.95, "language": "Portuguese",
                          "pronuncias": {"levinho": "lévinho"}}}


def _png(w=736, h=1280) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (w, h), (200, 90, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _keyframe(db) -> uuid.UUID:
    iid = uuid.uuid4()
    key = f"agencia/{iid}.png"
    storage.put(key, _png(), "image/png")
    db.add(Image(id=iid, kind=ImageKind.keyframe, object_key=key, content_type="image/png",
                 bytes=1, width=736, height=1280, sha256="x"))
    db.commit()
    return iid


def _geracao(db, user, passo: str, motor: GeracaoMotor, alvo: GeracaoAlvo,
             params: dict, status=GeracaoStatus.na_fila) -> Geracao:
    g = Geracao(alvo_tipo=alvo, alvo_id=uuid.uuid4(), passo=passo, motor=motor,
                params={**params, "seeds": params.get("seeds", [5]), "n": 1}, n_opcoes=1,
                status=status, created_by=user.id)
    db.add(g)
    db.commit()
    return g


def _candidato(db, g: Geracao) -> GeracaoCandidato:
    db.expire_all()
    return db.scalar(select(GeracaoCandidato).where(GeracaoCandidato.geracao_id == g.id))


def _ffprobe(dados: bytes) -> dict:
    import json

    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate:format=duration", "-of",
                        "json", "-"], input=dados, capture_output=True, check=True)
    return json.loads(r.stdout)


def test_clipe_vira_candidato_de_video(client, db, owner, motores, monkeypatch):
    clipe = _Clipe()
    monkeypatch.setitem(aplicadores.APLICADORES, "cena.clipe", clipe)
    kf = _keyframe(db)
    g = _geracao(db, owner[0], "cena.clipe", GeracaoMotor.comfyui, GeracaoAlvo.cena,
                 {"bloco": "clipe_wan", "prompt": "She smiles. The room stays the same.",
                  "largura": 736, "altura": 1280, "extras": {"quadros": 33},
                  "referencias": [str(kf)]})
    assert rodar_gpu(motores)[0] == "ok"
    db.expire_all()
    g = db.get(Geracao, g.id)
    cand = _candidato(db, g)
    assert g.status == GeracaoStatus.escolhido and clipe.aplicados == [cand.id]
    assert cand.video_key == f"geracoes/{g.id}/1.mp4" and cand.image_id is None
    assert cand.video_miniatura_key == f"agencia/geracoes/{g.id}/1.jpg"
    assert (cand.video_largura, cand.video_altura, cand.video_fps) == (736, 1280, 16)
    assert abs(cand.video_duracao_ms - 33 / 16 * 1000) < 100
    assert cand.video_bytes > 0 and len(cand.metricas["sha256"]) == 64
    assert storage.stat(cand.video_key, bucket="videos").size == cand.video_bytes
    assert storage.stat(cand.video_miniatura_key).size > 0
    # O bloco foi preenchido pelo contrato: sem o `end_image`, com os quadros e a resolução.
    import json

    from sociman_api.geracao.comfyui import WORKFLOWS

    contrato = json.loads((WORKFLOWS / "clipe_wan.params.json").read_text())["params"]
    api = next(p for p in motores.comfy.requests if p.caminho == "/prompt").corpo["prompt"]
    assert contrato["end_image"]["node"] not in api
    for nome, valor in (("frames", 33), ("width", 736), ("height", 1280), ("seed", 5)):
        spec = contrato[nome]
        assert api[spec["node"]]["inputs"][spec["input"]] == valor, nome
    # O detalhe da geração traz o vídeo, e o link serve o mp4 com Range.
    r = client.get(f"/api/geracoes/{g.id}", headers=owner[1])
    assert r.status_code == 200, r.text
    v = r.json()["candidatos"][0]["video"]
    assert v["duracaoMs"] == cand.video_duracao_ms and v["miniaturaUrl"]
    r = client.get(v["link"]["url"], headers={"Range": "bytes=0-7"})
    assert r.status_code == 206 and r.content[4:8] == b"ftyp"
    # Nada sobrou na pasta de trabalho.
    assert not (video.raiz_tmp() / str(g.id)).exists()


def test_montagem_roda_fora_da_trava_de_gpu(db, owner, motores, monkeypatch):
    kf = _keyframe(db)
    monkeypatch.setitem(aplicadores.APLICADORES, "cena.clipe", _Clipe())
    clipe = _geracao(db, owner[0], "cena.clipe", GeracaoMotor.comfyui, GeracaoAlvo.cena,
                     {"bloco": "clipe_minimax", "prompt": "Push in.", "largura": 736,
                      "altura": 1280, "extras": {"quadros": 22}, "referencias": [str(kf)]})
    rodar_gpu(motores)
    fonte = _candidato(db, clipe)
    montagem = _Montagem(fonte.video_key)
    monkeypatch.setitem(aplicadores.APLICADORES, "roteiro.montagem", montagem)
    # Um job de GPU "rodando" (com heartbeat recente) não segura a montagem (FR-043).
    gpu = _geracao(db, owner[0], "cena.clipe", GeracaoMotor.comfyui, GeracaoAlvo.cena,
                   {"bloco": "clipe_wan"}, status=GeracaoStatus.rodando)
    gpu.heartbeat_at = func.now()
    db.commit()
    g = _geracao(db, owner[0], "roteiro.montagem", GeracaoMotor.ffmpeg, GeracaoAlvo.roteiro, {})
    linha = gerador.LinhaMontagem(motores.clientes, threading.Event())
    linha.executor.heartbeat_s = 0.05
    assert linha.volta() == "ok"
    db.expire_all()
    g = db.get(Geracao, g.id)
    cand = _candidato(db, g)
    assert g.status == GeracaoStatus.escolhido and montagem.aplicados == [cand.id]
    assert cand.video_key == f"geracoes/{g.id}/1.mp4"
    info = _ffprobe(storage.get(cand.video_key, bucket="videos"))
    assert [s["codec_type"] for s in info["streams"]] == ["video"]  # o áudio saiu (-an)
    assert all(not p.exists() for p in montagem.pastas)
    assert db.get(Geracao, gpu.id).status == GeracaoStatus.rodando
    # A linha GPU não pega o `ffmpeg`, e a de montagem não pega os de GPU.
    assert linha.volta() is None


def test_montagem_sem_executor_falha(db, owner, motores, monkeypatch):
    monkeypatch.setitem(aplicadores.APLICADORES, "roteiro.montagem", _Clipe())
    g = _geracao(db, owner[0], "roteiro.montagem", GeracaoMotor.ffmpeg, GeracaoAlvo.roteiro, {})
    linha = gerador.LinhaMontagem(motores.clientes, threading.Event())
    assert linha.volta() == "falhou"
    db.expire_all()
    assert db.get(Geracao, g.id).status == GeracaoStatus.falhou


def test_narracao_continua_com_atempo_e_tempos(db, owner, motores, monkeypatch):
    if shutil.which("ffmpeg") is None:  # pragma: no cover — a imagem tem ffmpeg
        pytest.skip("sem ffmpeg")
    narracao = _Narracao(1.08)
    monkeypatch.setitem(aplicadores.APLICADORES, "roteiro.narracao", narracao)
    g = _geracao(db, owner[0], "roteiro.narracao", GeracaoMotor.tts, GeracaoAlvo.roteiro, {})
    assert rodar_gpu(motores)[0] == "ok"
    db.expire_all()
    g = db.get(Geracao, g.id)
    cand = _candidato(db, g)
    assert g.status == GeracaoStatus.escolhido and narracao.aplicados == [cand.id]
    assert motores.tts.ultimo_pronuncias == {"levinho": "lévinho"}
    pedido = [p for p in motores.tts.requests if p.caminho == "/v2/tts_paragraph"][-1]
    assert pedido.corpo["sentences"] == ["Olha esse vestido.", "Ele é levinho e fresco."]
    m = cand.metricas
    esperados = motores.tts.tempos_esperados(pedido.corpo["sentences"])
    assert [t["frase"] for t in m["tempos"]] == [0, 1]
    for t, (a, b) in zip(m["tempos"], esperados, strict=True):
        assert t["inicio_s"] == round(a / 1.08, 3) and t["fim_s"] == round(b / 1.08, 3)
    assert m["velocidade"] == 1.08 and m["similaridade"] == motores.tts.similaridade
    audio = db.get(Audio, cand.audio_id)
    # O áudio guardado já está na velocidade final (~ total / 1,08).
    assert abs(audio.duracao_ms / 1000 - m["total_s"]) < 0.1
    assert motores.tts.lotes_apagados  # o lote foi apagado no shop-tts
    assert cand.seed == 7


def test_narracao_que_nao_bateu_falha_com_mensagem(db, owner, motores, monkeypatch):
    monkeypatch.setitem(aplicadores.APLICADORES, "roteiro.narracao", _Narracao())
    motores.tts.narracao_ruim = 1
    g = _geracao(db, owner[0], "roteiro.narracao", GeracaoMotor.tts, GeracaoAlvo.roteiro, {})
    assert rodar_gpu(motores)[0] == "falhou"
    db.expire_all()
    g = db.get(Geracao, g.id)
    assert (g.status, g.error_code) == (GeracaoStatus.falhou, "entrada_invalida")
    assert g.error_message == gerador.NARRACAO_NAO_BATEU


def test_atempo_e_tempos_puros():
    wav = b"RIFF"  # 1,0 devolve como veio, sem chamar o ffmpeg
    assert video.atempo(wav, 1.0) is wav
    tempos, total = video.tempos_na_velocidade(
        [{"index": 1, "start": 0.0, "end": 1.08}, {"index": 2, "start": 1.08, "end": 2.16}],
        2.2, 1.08)
    assert tempos == [{"frase": 0, "inicio_s": 0.0, "fim_s": 1.0},
                      {"frase": 1, "inicio_s": 1.0, "fim_s": 2.0}]
    assert total == round(2.2 / 1.08, 3)
