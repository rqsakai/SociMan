"""Fumaça dos fakes da spec 011 (T013, research R18): os blocos de vídeo do ComfyUI falso e o
`/v2/tts_paragraph` do shop-tts falso, chamados pelo transporte dos clientes de verdade."""

import copy
import json
import subprocess

import pytest
from fakes import comfyui_fake as _cf
from fakes import shoptts_fake as _sf
from fakes.comfyui_fake import BLOCOS_VIDEO, ComfyFake
from fakes.shoptts_fake import ShopTtsFake

from sociman_api.geracao.comfyui import WORKFLOWS
from sociman_api.geracao.erros import MotorErro
from sociman_api.roteiros.tempos import na_velocidade, quadros

comfy_fake = _cf.comfy_fake
shoptts_fake = _sf.shoptts_fake


def _workflow(bloco: str, valores: dict, sem: tuple[str, ...] = ()) -> dict:
    """O workflow do bloco com os valores (como o `comfyui.preencher`, sem depender do `BLOCOS`):
    os opcionais em `sem` saem com o `drop`/`consumers`/`rewire` do contrato."""
    api = json.loads((WORKFLOWS / f"{bloco}.api.json").read_text())
    contrato = json.loads((WORKFLOWS / f"{bloco}.params.json").read_text())
    api = copy.deepcopy(api)
    for nome, spec in contrato["params"].items():
        if nome in sem:
            api.pop(spec["node"], None)
            for nid in spec.get("drop", []):
                api.pop(nid, None)
            for nid, inp in spec.get("consumers", []):
                api.get(nid, {}).get("inputs", {}).pop(inp, None)
            rw = spec.get("rewire", {})
            for no in api.values():
                for k, v in no["inputs"].items():
                    if isinstance(v, list) and len(v) == 2 and v[0] in rw:
                        no["inputs"][k] = [rw[v[0]], v[1]]
        elif nome in valores:
            api[spec["node"]]["inputs"][spec["input"]] = valores[nome]
    return api


def _rodar(fake: ComfyFake, bloco: str, valores: dict, sem: tuple[str, ...] = ()) -> tuple:
    cli = fake.cliente()
    pid = cli.prompt(_workflow(bloco, valores, sem))
    h = None
    while h is None:
        h = cli.history(pid)
    return cli, h


def _baixar_video(fake: ComfyFake, bloco: str, cli, h) -> bytes:
    contrato = json.loads((WORKFLOWS / f"{bloco}.params.json").read_text())
    no = contrato["outputs"]["video"]["node"]
    f = h["outputs"][no]["images"][0]
    assert f["filename"].endswith(".mp4")
    return cli.view(f["filename"], f["subfolder"], f["type"])


@pytest.mark.parametrize("bloco, motor, fps, audio", [
    ("clipe_minimax", "minimax", 24, True),
    ("clipe_wan", "wan", 16, False),
    ("clipe_wan_qualidade", "wan_qualidade", 16, False),
    ("clipe_ltx", "ltx", 24, True),
])
def test_clipes_devolvem_mp4_no_tamanho_pedido(comfy_fake, bloco, motor, fps, audio) -> None:
    cli = comfy_fake.cliente()
    inicio = cli.upload_image("g1_start_image.png", b"png")
    n = quadros(motor, 1.0)
    cli, h = _rodar(comfy_fake, bloco, {"start_image": inicio, "prompt": "she smiles",
                                        "width": 160, "height": 288, "frames": n, "seed": 9},
                    sem=("end_image",))
    assert h["status"]["status_str"] == "success"
    meta = ComfyFake.meta_do_mp4(_baixar_video(comfy_fake, bloco, cli, h))
    assert (meta["bloco"], meta["seed"]) == (bloco, 9)
    assert (meta["width"], meta["height"], meta["fps"], meta["frames"]) == (160, 288, fps, n)
    assert meta["audio"] is audio
    # O `last_frame` (que o SociMan ignora) vem como PNG.
    contrato = json.loads((WORKFLOWS / f"{bloco}.params.json").read_text())
    quadro = h["outputs"][contrato["outputs"]["last_frame"]["node"]]["images"][0]
    assert cli.view(quadro["filename"], quadro["subfolder"], quadro["type"])[:4] == b"\x89PNG"
    assert comfy_fake.recusados == []


def test_clipe_ltx_com_quadro_final_e_cache(comfy_fake) -> None:
    cli = comfy_fake.cliente()
    ini = cli.upload_image("a.png", b"1")
    fim = cli.upload_image("b.png", b"2")
    valores = {"start_image": ini, "end_image": fim, "prompt": "x", "width": 160,
               "height": 288, "frames": 25, "seed": 3}
    antes = comfy_fake.videos_gerados
    _rodar(comfy_fake, "clipe_ltx", valores)
    _rodar(comfy_fake, "clipe_ltx", valores)
    # Mesmos parâmetros: o ffmpeg rodou no máximo uma vez (o cache vale na sessão do pytest).
    assert comfy_fake.videos_gerados - antes <= 1
    assert comfy_fake.recusados == []
    # Sem o `end_image` enviado, o nó tem de sair (senão o ComfyUI recusa).
    with pytest.raises(MotorErro):
        cli.prompt(_workflow("clipe_ltx", {**valores, "end_image": "nao_enviada.png"}))
    assert comfy_fake.recusados


def test_upscale_devolve_a_entrada_no_tamanho_pedido(comfy_fake, tmp_path) -> None:
    src = tmp_path / "pos.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=96x160:rate=24:duration=1", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", str(src)], check=True)
    cli = comfy_fake.cliente()
    nome = cli.upload_image("g1_video.mp4", src.read_bytes())
    cli, h = _rodar(comfy_fake, "upscale_video", {"video": nome, "width": 192, "height": 320,
                                                  "seed": 42, "prefix": "rot/pos0"})
    meta = ComfyFake.meta_do_mp4(_baixar_video(comfy_fake, "upscale_video", cli, h))
    assert (meta["width"], meta["height"], meta["fps"], meta["frames"]) == (192, 320, 24, 24)
    assert meta["bloco"] == "upscale_video"


def test_video_falhas_como_na_021(comfy_fake) -> None:
    cli = comfy_fake.cliente()
    inicio = cli.upload_image("s.png", b"x")
    valores = {"start_image": inicio, "prompt": "x", "width": 64, "height": 112, "frames": 9,
               "seed": 1}
    comfy_fake.falhar_proximo("oom")
    _, h = _rodar(comfy_fake, "clipe_wan", valores, sem=("end_image",))
    assert h["status"]["status_str"] == "error"
    comfy_fake.falhar_proximo("vazia")
    _, h = _rodar(comfy_fake, "clipe_wan", valores, sem=("end_image",))
    assert h["status"]["status_str"] == "success" and h["outputs"] == {}
    # Vídeo de entrada ilegível no upscale: termina sem saída.
    lixo = cli.upload_image("lixo.mp4", b"nao e video")
    _, h = _rodar(comfy_fake, "upscale_video", {"video": lixo, "width": 64, "height": 112,
                                                "seed": 1})
    assert h["outputs"] == {}
    assert set(BLOCOS_VIDEO) == {"clipe_minimax", "clipe_wan", "clipe_wan_qualidade",
                                 "clipe_ltx", "upscale_video"}


# ---- shop-tts ----

FRASES = ["Gente, achei o vestido perfeito!", "Olha esse caimento.", "Corre no link!"]


def test_tts_paragraph_tempos_proporcionais_e_pronuncias(shoptts_fake) -> None:
    cli = shoptts_fake.cliente()
    r = cli.tts_paragraph({"sentences": FRASES, "voice": "animada", "seed": 7,
                           "max_attempts": 5, "min_similarity": 0.95, "language": "Portuguese",
                           "pronuncias": {"levinho": "lévinho"}})
    assert r["ok"] is True and r["arquivo"] == "narracao.wav"
    assert r["sentences"] == r["frases"]
    assert [(s["start"], s["end"]) for s in r["sentences"]] == ShopTtsFake.tempos_esperados(FRASES)
    duracoes = [s["end"] - s["start"] for s in r["sentences"]]
    assert duracoes[0] > duracoes[1]  # a frase maior dura mais
    assert r["seconds"] == pytest.approx(r["sentences"][-1]["end"] + 0.02)
    assert r["attempts"] == [{"seed": 7, "similarity": 0.97, "seconds": r["seconds"]}]
    assert shoptts_fake.ultimo_pronuncias == {"levinho": "lévinho"}
    # O wav tem a duração do `seconds`, e os tempos passam pelo `na_velocidade` da 011.
    assert len(cli.baixar(r["lote_id"], "narracao.wav")) > 44
    tempos, total = na_velocidade(r["sentences"], r["seconds"], 1.08)
    assert total == pytest.approx(r["seconds"] / 1.08, abs=1e-6)
    assert [t["frase"] for t in tempos] == [1, 2, 3]
    # Sem o campo: `None` (vale o arquivo do serviço); `{}` é diferente de ausente.
    cli.tts_paragraph({"sentences": FRASES, "voice": "animada"})
    assert shoptts_fake.ultimo_pronuncias is None
    cli.tts_paragraph({"sentences": FRASES, "voice": "animada", "pronuncias": {}})
    assert shoptts_fake.pronuncias_recebidas == [{"levinho": "lévinho"}, None, {}]


def test_tts_paragraph_ok_falso_e_503(shoptts_fake) -> None:
    cli = shoptts_fake.cliente()
    shoptts_fake.narracao_ruim = 1
    r = cli.tts_paragraph({"sentences": FRASES, "voice": "animada", "seed": 3,
                           "max_attempts": 5})
    assert r["ok"] is False and r["similarity"] < 0.95
    assert [a["seed"] for a in r["attempts"]] == [3, 4, 5, 6, 7]
    assert cli.tts_paragraph({"sentences": FRASES, "voice": "animada"})["ok"] is True
    shoptts_fake.sem_memoria = 1
    with pytest.raises(MotorErro) as exc:
        cli.tts_paragraph({"sentences": FRASES, "voice": "animada"})
    assert exc.value.codigo == "sem_memoria"


@pytest.mark.parametrize("corpo", [
    {"pronuncias": {"": "x"}},
    {"pronuncias": {"a" * 61: "x"}},
    {"pronuncias": {f"p{i}": "x" for i in range(501)}},
    {"pronuncias": ["levinho"]},
    {"velocidade": 1.08},   # a velocidade não vai ao serviço (R5)
    {"out_dir": "tts/x"},
])
def test_tts_paragraph_recusa_como_o_servico(shoptts_fake, corpo) -> None:
    with pytest.raises(MotorErro):
        shoptts_fake.cliente().tts_paragraph({"sentences": FRASES, "voice": "animada", **corpo})
    assert shoptts_fake.pronuncias_recebidas == []
