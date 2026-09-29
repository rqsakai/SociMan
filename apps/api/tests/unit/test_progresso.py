"""Progresso real do OpenShorts (T086, FR-010a): parser puro com amostras de log de jobs reais
(2026-09-29), incluindo o ruído que precisa ser ignorado."""

from types import SimpleNamespace

import pytest

from sociman_api.envios.progresso import (
    Etapa,
    Progresso,
    clipes,
    geral,
    gravar,
    interpretar,
    publico,
    zerar,
)

JOB = "7ee2bef6-65b9-4aa7-97e5-9ef81ec8705d"

# Amostras copiadas de `GET /api/status/{job}` de jobs reais (self-host: saída crua).
RUIDO = [
    "INFO: Created TensorFlow Lite XNNPACK delegate for CPU.",
    "WARNING: All log messages before absl::InitializeLog() is called are written to STDERR",
    ("W0000 00:00:1790697872.126668  657378 inference_feedback_manager.cc:114] Feedback manager "
     "requires a model with a single signature inference. Disabling support for feedback tensors."),
    "[debug] Encodings: locale UTF-8, fs utf-8, pref UTF-8, out utf-8 (No ANSI)",
    "[debug] [youtube] [pot:bgutil:script-node] Node.js version too low.",
    "[youtube] PWMQq7Ba_lU: Downloading webpage",
    "original url = /s/player/fb50cd46/player_es6.vflset/en_US/base.js",
    "WARNING: [youtube] PWMQq7Ba_lU: Some mweb client https formats have been skipped",
    "[info] PWMQq7Ba_lU: Downloading 1 format(s): 299+140",
    "[Merger] Merging formats into \"output/x/PARAMOUNT.mp4\"",
    "Deleting original file output/x/PARAMOUNT.f299.mp4 (pass -k to keep)",
    ("/app/scene_detection.py:109: UserWarning: The given NumPy array is not writable, and "
     "PyTorch does not support non-writable tensors."),
    "tensor = torch.from_numpy(np.ascontiguousarray(frames)).to(model.device)",
    "[h264 @ 0x64395e0c7d00] mmco: unref short failure",
    "🎞️ [Encoder] video encoder: libx264 (FFMPEG_ENCODER=x264)",
    "🚀 Reframe engine v2 (ffmpeg-native render)",
    "⏱️ Reframe v2 total: 224.9s",
]
DOWNLOAD = [
    f"Job {JOB} queued.", "Job started by worker.",
    "🔍 Debug: yt-dlp version: 2026.09.16.232951", "📥 Downloading video from YouTube...",
    "⚠️ YOUTUBE_COOKIES env var not found.", "📥 Download attempt: HD",
    *RUIDO[:11],
    f"[download] Destination: output/{JOB}/PARAMOUNT.f299.mp4",
]
BARRA_DOWNLOAD = ("[download]   0.0% of  293.97MiB at  Unknown B/s ETA Unknown\r[download]  12.5% of"
                  "  293.97MiB at   20.1MiB/s ETA 00:12\r[download]  45.3% of  293.97MiB at   "
                  "21.30MiB/s ETA 00:07")
BAIXADO = ["✅ Download succeeded (HD).",
           f"✅ Video downloaded in 38.24s: output/{JOB}/PARAMOUNT.mp4",
           "🎛️  Choosing a layout for this video…",
           "🎬 Layout: none (confianza 0.95) — The video features a single speaker."]
TRANSCRICAO = ["🎙️  Transcribing video...", "🎙️ Transcribing… 25% (102s)",
               "🎙️ Transcribing… 50% (196s)", "🎙️ Transcribing… 75% (288s)",
               "🎙️ Transcribing… 100% (375s)", "🧹 [ASR] resident models released",
               "Detected language 'pt', 236 segments",
               "[0.00s -> 4.20s]  E aí, 🔥 Found 50 clips! Processing Clip 3: foi o que ele disse",
               "[4.20s -> 9.00s]  ✅ Clip 1 ready — fala do vídeo"]
ESCOLHA = ["🤖  Analyzing with local LLM at https://api.anthropic.com/v1 (2-pass: score → detail)...",
           "🤖  Model: claude-sonnet-4-6 | language: pt", "Built 14 scoring window(s).",
           "Shortlisted 10 window(s) for detail.",
           "💰 Total cost (claude-sonnet-4-6, 2-pass, 6 calls): $0.000000"]
CLIPES = ["🔥 Found 9 clips!", f"Saved metadata to output/{JOB}/PARAMOUNT_metadata.json",
          "🎬 Processing Clip 5: 448.66s - 507.96s",
          "Title: Pagar multa de 30 milhões — ✅ Clip 8 ready no título",
          "🎬 Processing Clip 1: 0.0s - 58.01s", "Title: Tentaram barrar a fusão",
          "🎬 Processing Clip 9: 766.54s - 826.54s", "Title: Duna Parte 3 vs Vingadores",
          *RUIDO[11:]]
CENAS_PARCIAL = ("Analyzing Scenes:   0%|          | 0/27 [00:00<?, ?it/s]\r   Analyzing Scenes: "
                 "  4%|▎         | 1/27 [00:01<00:30,  1.16s/it]\r   Analyzing Scenes:  40%|████  "
                 "    | 11/27 [00:06<00:09,  1.80it/s]")
CENAS_FIM = ("Analyzing Scenes:   0%|          | 0/27 [00:00<?, ?it/s]\r   Analyzing Scenes: 100%|"
             "██████████| 27/27 [00:14<00:00,  1.80it/s]")
CLIPE_9_PRONTO = ["🎬 Scene engine: TransNetV2 — 27 scenes", CENAS_FIM,
                  f"✅ Clip saved to output/{JOB}/PARAMOUNT_clip_9.mp4",
                  f"✅ Clip 9 ready: output/{JOB}/PARAMOUNT_clip_9.mp4",
                  "🎬 Processing Clip 3: 254.16s - 314.02s", "Title: Paramount ameaçou"]


def proc(*logs: list[str], **extra) -> dict:
    return {"status": "processing", "logs": [x for bloco in logs for x in bloco],
            "result": None, "queue": None, "partial": None} | extra


def test_na_fila_com_posicao():
    p = interpretar({"status": "queued", "logs": [f"Job {JOB} queued."],
                     "queue": {"position": 2, "ahead": 1, "eta_seconds": 600}})
    assert p == Progresso(Etapa.fila, posicao_fila=2, mensagem="Na fila do OpenShorts (2º)",
                          progresso_geral=0)
    assert interpretar({"status": "queued", "queue": None}).mensagem == "Na fila do OpenShorts"


def test_processando_sem_marco_e_preparando():
    p = interpretar(proc([f"Job {JOB} queued.", "Job started by worker."]))
    assert (p.etapa, p.mensagem, p.progresso_geral) == (Etapa.baixando, "Preparando o vídeo", 0)


def test_baixando():
    p = interpretar(proc(DOWNLOAD))
    assert (p.etapa, p.etapa_pct, p.mensagem) == (Etapa.baixando, None, "Baixando o vídeo")
    p = interpretar(proc(DOWNLOAD, [BARRA_DOWNLOAD]))
    assert (p.etapa_pct, p.mensagem, p.progresso_geral) == (45, "Baixando o vídeo 45%", 2)
    p = interpretar(proc(DOWNLOAD, [BARRA_DOWNLOAD], BAIXADO))
    assert (p.etapa, p.etapa_pct, p.progresso_geral) == (Etapa.baixando, 100, 5)


def test_transcrevendo_com_pct():
    p = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO[:1]))
    assert (p.etapa, p.etapa_pct, p.mensagem, p.progresso_geral) == (
        Etapa.transcrevendo, 0, "Transcrevendo o vídeo", 5)
    p = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO[:2]))
    assert (p.etapa_pct, p.mensagem, p.progresso_geral) == (25, "Transcrevendo o vídeo 25%", 12)
    p = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO))  # + segmentos com "marcos" falsos
    assert (p.etapa, p.etapa_pct, p.progresso_geral) == (Etapa.transcrevendo, 100, 35)


def test_esperando_vaga_de_transcricao():
    logs = ["🎙️  Transcribing video...", "🎙️ Waiting for a free transcription slot…"]
    p = interpretar(proc(DOWNLOAD, BAIXADO, logs))
    assert (p.etapa, p.mensagem) == (Etapa.transcrevendo, "Aguardando a vez de transcrever")
    p = interpretar(proc(DOWNLOAD, BAIXADO, logs, ["🎙️ Transcribing… 25% (110s)"]))
    assert p.mensagem == "Transcrevendo o vídeo 25%"


def test_escolhendo_momentos():
    p = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO, ESCOLHA[:2]))
    assert (p.etapa, p.etapa_pct, p.mensagem, p.progresso_geral) == (
        Etapa.escolhendo_momentos, None, "Escolhendo os momentos", 35)
    assert interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO, ESCOLHA)).progresso_geral == 38


def test_clipes_em_paralelo():
    p = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO, ESCOLHA, CLIPES))
    assert (p.etapa, p.clipe_atual, p.clipes_previstos, p.etapa_pct, p.mensagem) == (
        Etapa.processando_clipes, 1, 9, 0, "Cortando clipe 1 de 9")
    assert p.progresso_geral == 40
    p = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO, ESCOLHA, CLIPES,
                         ["🎬 Scene engine: TransNetV2 — 27 scenes", CENAS_PARCIAL]))
    assert p.mensagem == "Cortando clipe 1 de 9 (cenas 40%)"
    p = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO, ESCOLHA, CLIPES, CLIPE_9_PRONTO))
    assert (p.clipe_atual, p.etapa_pct, p.mensagem, p.progresso_geral) == (
        2, 11, "Cortando clipe 2 de 9", 45)


def test_result_parcial_conta_e_falha_de_clipe_tambem():
    clips = [{"video_url": f"/videos/{JOB}/a_clip_{i}.mp4"} for i in (1, 5, 9)]
    p = interpretar(proc(DOWNLOAD, CLIPES, ["❌ Clip 5 failed again."]) | {"result": {"clips": clips}})
    assert (p.clipe_atual, p.clipes_previstos) == (5, 9)  # 3 prontos + 1 falho
    # clipe pronto no result sem o "Found" nos logs: já é geração, sem o total
    p = interpretar(proc([f"Job {JOB} queued."]) | {"result": {"clips": clips[:1]}})
    assert (p.etapa, p.clipes_previstos, p.mensagem) == (
        Etapa.processando_clipes, None, "Cortando os clipes: 1 pronto")


def test_parcial_na_mensagem():
    p = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO[:3],
                         partial={"processed_minutes": 30, "source_minutes": 95}))
    assert p.mensagem == "Transcrevendo o vídeo 50% (primeiros 30 min)"


def test_ruido_e_desconhecido_mantem_a_etapa_anterior():
    so_ruido = proc(RUIDO, ["linha que ninguém conhece", "", "   "])
    assert interpretar(so_ruido, Etapa.transcrevendo).etapa == Etapa.transcrevendo
    assert interpretar(so_ruido, Etapa.escolhendo_momentos).mensagem == \
        "Escolhendo os momentos"
    # a anterior de outra fase (importação, erro) não vale para um job `processing`
    assert interpretar(so_ruido, Etapa.importando).etapa == Etapa.baixando
    # ruído depois de um marco não muda nada
    p1 = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO[:3]))
    p2 = interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO[:3], RUIDO))
    assert p1 == p2


@pytest.mark.parametrize("entrada", [
    None, "texto", 42, [], {}, {"status": "processing", "logs": None},
    {"status": "processing", "logs": "não é lista"}, {"status": "processing", "logs": [None, 3, {}]},
    {"status": "queued", "queue": {"position": "2"}}, {"status": "queued", "queue": {"position": True}},
    {"status": "processing", "logs": ["🔥 Found x clips!", "🎙️ Transcribing… abc%"]},
    {"status": "processing", "result": {"clips": "x"}, "partial": {"processed_minutes": "30"}},
    {"status": "algo-novo", "logs": ["?"]},
])
def test_nunca_quebra(entrada):
    p = interpretar(entrada)
    assert isinstance(p, Progresso) and 0 <= p.progresso_geral <= 100


def test_concluido_e_falhou():
    p = interpretar({"status": "completed", "logs": [], "result": {"clips": [{}, {}, {}]}})
    assert (p.etapa, p.clipes_previstos, p.progresso_geral) == (Etapa.importando, 3, 90)
    p = interpretar({"status": "failed", "logs": ["Job x queued.", "Process failed with exit code 1", ""]})
    assert (p.etapa, p.mensagem) == (Etapa.erro, "O OpenShorts falhou: Process failed with exit code 1")


def test_reenfileirado_depois_de_queda():
    p = interpretar(proc(DOWNLOAD, [("🔁 A temporary server problem interrupted your video. "
                                     "It's back in the queue.")]))
    assert p.etapa == Etapa.baixando and p.mensagem == "Preparando o vídeo"


def test_faixas_do_geral():
    assert [geral(e, 1) for e in (Etapa.baixando, Etapa.transcrevendo, Etapa.escolhendo_momentos,
                                  Etapa.processando_clipes, Etapa.importando)] == [5, 35, 40, 90, 100]
    assert geral(Etapa.fila, 1) == 0 and geral(Etapa.concluido, 0) == 100


def test_clipes_da_importacao():
    p = clipes(Etapa.legendas, 1, 9)
    assert (p.clipe_atual, p.clipes_previstos, p.mensagem, p.progresso_geral) == (
        2, 9, "Aplicando legendas do kit 2 de 9", 91)
    assert clipes(Etapa.importando, 8, 9).mensagem == "Importando 9 de 9"


def _envio(**kw):
    base = {"status": "processando", "progress": 0, "openshorts_queue_pos": None,
            "etapa": None, "etapa_pct": None, "clipe_atual": None, "clipes_previstos": None,
            "etapa_mensagem": None, "clips_total": None, "clips_importados": 0,
            "error_message": None}
    return SimpleNamespace(**(base | kw))


def test_gravar_nao_volta_o_geral():
    e = _envio(progress=90)  # estimativa antiga (antes da 0007): a 1ª leitura a substitui
    gravar(e, interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO[:3])))
    assert e.progress == 20
    e = _envio(progress=56, etapa="processando_clipes")
    gravar(e, interpretar(proc(DOWNLOAD, BAIXADO, TRANSCRICAO[:2])))
    assert (e.etapa, e.etapa_mensagem, e.progress) == ("transcrevendo", "Transcrevendo o vídeo 25%", 56)
    gravar(e, interpretar({"status": "queued", "queue": {"position": 1}}))
    assert (e.etapa, e.progress, e.openshorts_queue_pos) == ("fila", 0, 1)
    e.progress = 40
    gravar(e, Progresso(Etapa.erro, mensagem="x"))
    assert e.progress == 40
    zerar(e)
    assert (e.etapa, e.etapa_pct, e.clipe_atual, e.clipes_previstos, e.etapa_mensagem) == (None,) * 5


def test_publico():
    assert publico(_envio(status="pronto", clips_importados=3, clips_total=3)).mensagem == "Pronto: 3 clipes"
    assert publico(_envio(status="falhou", error_message="O OpenShorts falhou")).etapa == Etapa.erro
    assert publico(_envio(status="na_fila")).etapa == Etapa.fila
    assert publico(_envio(status="selecionado")).etapa is None
    assert publico(_envio(openshorts_queue_pos=3)).mensagem == "Na fila do OpenShorts (3º)"
    e = _envio(etapa="processando_clipes", etapa_pct=11, clipe_atual=2, clipes_previstos=9,
               etapa_mensagem="Cortando clipe 2 de 9")
    assert publico(e).mensagem == "Cortando clipe 2 de 9" and publico(e).etapa_pct == 11
    assert publico(_envio(etapa="invalida")).etapa == Etapa.fila
