"""Fumaça dos fakes da spec 021 (T012, T013 e T014) contra os clientes de verdade
(`geracao/comfyui.py`, `geracao/shoptts.py` e `geracao/memoria.py`): o que um chama o outro
atende, com o mesmo formato."""

import io
import json
import shutil
import subprocess
import wave

import pytest
from fakes import comfyui_fake as _cf
from fakes import dockerctl_fake as _df
from fakes import shoptts_fake as _sf
from fakes.comfyui_fake import ComfyFake
from fakes.dockerctl_fake import JOB, NORMAL
from fakes.shoptts_fake import ShopTtsFake, wav_sintetico
from PIL import Image

from sociman_api.geracao.comfyui import Cancelada, normalizar_9x16, run_bloco
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.memoria import MemoriaErro

comfy_fake = _cf.comfy_fake
dockerctl_fake = _df.dockerctl_fake
shoptts_fake = _sf.shoptts_fake


def _png(w: int = 64, h: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _rodar(fake: ComfyFake, bloco: str, params: dict, heartbeat=lambda: True) -> bytes:
    return run_bloco(fake.cliente(), bloco, params, heartbeat, nome_base="g1_1", teto_s=60,
                     sleep=lambda _s: None)


# ---- ComfyUI ----

def test_comfy_cena(comfy_fake) -> None:
    comfy_fake.voltas = 3
    dados = _rodar(comfy_fake, "cena", {"prompt": "quarto claro", "seed": 1234})
    with Image.open(io.BytesIO(dados)) as im:
        assert im.size == (768, 1344)
    assert ComfyFake.seed_do_png(dados) == 1234
    p = comfy_fake.ultimo()
    assert p.bloco == "cena" and p.workflow["1"]["inputs"]["value"] == "quarto claro"
    assert comfy_fake.pedidos().count(("GET", f"/history/{p.id}")) == 4
    assert comfy_fake.frees == [{"unload_models": False, "free_memory": True}]
    assert comfy_fake.recusados == []
    assert len(normalizar_9x16(dados)) > 0


def test_comfy_cena_tamanho_do_workflow(comfy_fake) -> None:
    dados = _rodar(comfy_fake, "cena", {"prompt": "x", "seed": 7, "width": 512, "height": 640})
    with Image.open(io.BytesIO(dados)) as im:
        assert im.size == (512, 640)


def test_comfy_keyframe_sem_refs_opcionais(comfy_fake) -> None:
    dados = _rodar(comfy_fake, "keyframe",
                   {"base_image": _png(), "instruction": "add a lamp", "seed": 5})
    assert ComfyFake.seed_do_png(dados) == 5
    p = comfy_fake.ultimo()
    assert p.bloco == "keyframe"
    assert "2" not in p.workflow and "3" not in p.workflow
    assert "image2" not in p.workflow["14"]["inputs"]
    assert p.workflow["1"]["inputs"]["image"] == "sociman/g1_1_base_image.png"
    assert list(comfy_fake.uploads) == ["sociman/g1_1_base_image.png"]


def test_comfy_keyframe_com_ref(comfy_fake) -> None:
    _rodar(comfy_fake, "keyframe",
           {"base_image": _png(), "ref1": _png(), "instruction": "x", "seed": 1})
    p = comfy_fake.ultimo()
    assert "2" in p.workflow and "3" not in p.workflow
    assert set(comfy_fake.uploads) == {"sociman/g1_1_base_image.png", "sociman/g1_1_ref1.png"}


def test_comfy_prompt_mal_preenchido_e_recusado(comfy_fake) -> None:
    cli = comfy_fake.cliente()
    api = {"1": {"class_type": "LoadImage", "inputs": {"image": "nao-enviada.png"}}}
    with pytest.raises(MotorErro) as exc:
        cli.prompt(api)
    assert exc.value.codigo == "internal"
    assert comfy_fake.recusados


def test_comfy_oom_vira_sem_memoria(comfy_fake) -> None:
    comfy_fake.falhar_proximo("oom")
    with pytest.raises(MotorErro) as exc:
        _rodar(comfy_fake, "cena", {"prompt": "x", "seed": 1})
    assert exc.value.codigo == "sem_memoria"
    assert "OutOfMemoryError" in exc.value.detalhe


def test_comfy_saida_vazia_vira_internal(comfy_fake) -> None:
    comfy_fake.falhar_sempre = "vazia"
    with pytest.raises(MotorErro) as exc:
        _rodar(comfy_fake, "cena", {"prompt": "x", "seed": 1})
    assert exc.value.codigo == "internal"


def test_comfy_fora_do_ar(comfy_fake) -> None:
    comfy_fake.fora = True
    with pytest.raises(MotorErro) as exc:
        comfy_fake.cliente().vram_disponivel_gb()
    assert exc.value.codigo == "servico_fora"


def test_comfy_vram(comfy_fake) -> None:
    comfy_fake.vram_free = 6 * 1024**3
    comfy_fake.torch_vram_total = 2 * 1024**3
    assert comfy_fake.cliente().vram_disponivel_gb() == pytest.approx(8.0)


def test_comfy_cancelada_interrompe_e_tira_da_fila(comfy_fake) -> None:
    comfy_fake.voltas = 5
    chamadas = iter([True, True, False])
    with pytest.raises(Cancelada):
        _rodar(comfy_fake, "cena", {"prompt": "x", "seed": 1}, heartbeat=lambda: next(chamadas))
    p = comfy_fake.ultimo()
    assert comfy_fake.interrupcoes == 1
    assert comfy_fake.apagados == [p.id]
    assert p.estado == "interrompido"


# ---- shop-tts ----

def test_shoptts_register_baixar_apagar(shoptts_fake) -> None:
    cli = shoptts_fake.cliente()
    lote = cli.register(b"audio-qualquer", "gravacao.ogg", nome="v_abc", tom="animada", n=2)
    assert [c["arquivo"] for c in lote["candidatos"]] == ["candidato_1.wav", "candidato_2.wav"]
    assert lote["analise"]["avisos"]  # .ogg = comprimido
    wav = cli.baixar(lote["lote_id"], lote["candidatos"][0]["teste"])
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 24000, 2)
        assert w.getnframes() == 24000
    cli.apagar_lote(lote["lote_id"])
    assert shoptts_fake.lotes_apagados == [lote["lote_id"]]
    with pytest.raises(MotorErro):
        cli.baixar(lote["lote_id"], "candidato_1.wav")
    assert shoptts_fake.requests[0].corpo == {"arquivo": "gravacao.ogg", "nome": "v_abc",
                                              "tom": "animada", "n": "2"}


def test_shoptts_design_tts_import_e_apagar_voz(shoptts_fake) -> None:
    cli = shoptts_fake.cliente()
    lote = cli.design(nome="v_def", descricao="warm female voice", n=1, seed=3)
    assert len(lote["candidatos"]) == 1
    r = cli.importar(nome="v_def", ref=wav_sintetico(2.0), ref_texto="Olá.",
                     meta={"origem": "design", "tom": "calma"})
    assert cli.voices()["v_def"]["sha256"] == r["sha256"]
    frases = cli.tts({"sentences": ["Oi.", "Tudo bem?"], "voice": "v_def"})
    assert [f["arquivo"] for f in frases["frases"]] == ["frase_01.wav", "frase_02.wav"]
    par = cli.tts_paragraph({"sentences": ["Oi.", "Tudo bem?"], "voice": "v_def"})
    assert par["arquivo"] == "narracao.wav" and len(par["frases"]) == 2
    assert cli.baixar(par["lote_id"], "narracao.wav")[:4] == b"RIFF"
    cli.apagar_voz("v_def")
    assert shoptts_fake.vozes_apagadas == ["v_def"]
    assert cli.health()["status"] == "ok"
    cli.unload()
    assert shoptts_fake.unloads == 1


def test_shoptts_503_vira_sem_memoria(shoptts_fake) -> None:
    shoptts_fake.sem_memoria = 1
    cli = shoptts_fake.cliente()
    with pytest.raises(MotorErro) as exc:
        cli.register(b"x", "g.wav", nome="v_abc", tom="calma", n=1)
    assert exc.value.codigo == "sem_memoria"
    assert cli.register(b"x", "g.wav", nome="v_abc", tom="calma", n=1)["lote_id"]


def test_shoptts_fora_e_out_dir(shoptts_fake: ShopTtsFake) -> None:
    cli = shoptts_fake.cliente()
    with pytest.raises(MotorErro) as exc:
        cli.tts({"sentences": ["a"], "out_dir": "tts/x"})
    assert exc.value.codigo == "entrada_invalida"  # 422 do serviço
    shoptts_fake.fora = True
    with pytest.raises(MotorErro) as exc:
        cli.health()
    assert exc.value.codigo == "servico_fora"


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="sem ffprobe")
def test_shoptts_wav_passa_no_ffprobe(tmp_path) -> None:
    arq = tmp_path / "t.wav"
    arq.write_bytes(wav_sintetico(1.0))
    saida = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(arq)],
                           capture_output=True, check=True, timeout=30).stdout
    (s,) = json.loads(saida)["streams"]
    assert (s["codec_name"], s["sample_rate"], s["channels"]) == ("pcm_s16le", "24000", 1)


# ---- dockerctl ----

def test_memoria_subir_e_devolver(dockerctl_fake) -> None:
    cli = dockerctl_fake.cliente()
    assert cli.ler().estado == "normal"
    assert cli.subir().memoria_bytes == JOB
    assert cli.devolver().memoria_bytes == NORMAL
    assert dockerctl_fake.historico == [NORMAL, JOB, NORMAL]
    assert dockerctl_fake.acoes() == ["ler", "subir", "devolver"]


def test_memoria_nao_volta(dockerctl_fake) -> None:
    cli = dockerctl_fake.cliente()
    cli.subir()
    dockerctl_fake.nao_volta = True
    with pytest.raises(MemoriaErro) as exc:
        cli.devolver()
    assert exc.value.motivo == "nao_conferiu"
    assert dockerctl_fake.memoria == JOB


def test_memoria_nao_coube_depois_coube(dockerctl_fake) -> None:
    cli = dockerctl_fake.cliente()
    cli.subir()
    dockerctl_fake.nao_coube = 2
    for _ in range(2):
        with pytest.raises(MemoriaErro) as exc:
            cli.devolver()
        assert exc.value.motivo == "nao_coube"
    assert cli.devolver().estado == "normal"


def test_memoria_fora_e_token(dockerctl_fake) -> None:
    with pytest.raises(MemoriaErro) as exc:
        dockerctl_fake.cliente(token="errado").subir()
    assert exc.value.motivo == "token"
    assert dockerctl_fake.memoria == NORMAL
    dockerctl_fake.fora = True
    with pytest.raises(MemoriaErro) as exc:
        dockerctl_fake.cliente().ler()
    assert exc.value.motivo == "fora"


def test_normalizar_9x16_e_imagem_invalida() -> None:
    """R6: o resultado vira 768×1344 (corte no centro, como o `fit_9x16`); lixo → entrada."""
    import io

    import pytest
    from PIL import Image

    from sociman_api.geracao.comfyui import normalizar_9x16
    from sociman_api.geracao.erros import MotorErro

    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), (10, 20, 30)).save(buf, format="PNG")
    with Image.open(io.BytesIO(normalizar_9x16(buf.getvalue()))) as im:
        assert im.size == (768, 1344) and im.format == "PNG"
    with pytest.raises(MotorErro) as exc:
        normalizar_9x16(b"nao e imagem")
    assert exc.value.codigo == "entrada_invalida"


# ---- correções dos clientes (relatório dos fakes) ----

def test_comfy_interrompido_por_fora_vira_servico_fora(comfy_fake) -> None:
    """Interrompido por outro processo (a UI do ComfyUI, o pipeline do host): volta à fila."""
    comfy_fake.voltas = 5
    cli = comfy_fake.cliente()
    estado = {"n": 0}

    def heartbeat() -> bool:
        estado["n"] += 1
        if estado["n"] == 2:
            cli.interrupt()  # alguém de fora
        return True
    with pytest.raises(MotorErro) as exc:
        run_bloco(cli, "cena", {"prompt": "x", "seed": 1}, heartbeat, nome_base="g1_1",
                  teto_s=60, sleep=lambda _s: None)
    assert exc.value.codigo == "servico_fora"


def test_shoptts_nome_de_voz_e_422(shoptts_fake) -> None:
    cli = shoptts_fake.cliente()
    for ruim in ("Voz", "a", "voz-com-hifen", "v" * 41):
        with pytest.raises(MotorErro) as exc:
            cli.design(nome=ruim, descricao="calm", n=1, seed=1)
        assert exc.value.codigo == "entrada_invalida"
    with pytest.raises(MotorErro) as exc:  # o serviço recusa n > 3 com 422
        cli.design(nome="voz_ok", descricao="calm", n=5, seed=1)
    assert exc.value.codigo == "entrada_invalida"


def test_shoptts_apagar_voz_inexistente_e_idempotente(shoptts_fake) -> None:
    cli = shoptts_fake.cliente()
    cli.apagar_voz("calma")
    cli.apagar_voz("calma")  # 404 no serviço = já removida
    assert "calma" not in shoptts_fake.vozes


@pytest.mark.parametrize("corpo", [b"nao e json", b'{"estado": "normal"}',
                                   b'{"memoria_bytes": 1, "memoria_swap_bytes": 1, "estado": "x"}'])
def test_memoria_corpo_invalido_vira_memoria_erro(corpo) -> None:
    import httpx

    from sociman_api.geracao.memoria import MemoriaClient

    cli = MemoriaClient("http://dockerctl:8080", "t",
                        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=corpo)))
    with pytest.raises(MemoriaErro) as exc:
        cli.ler()
    assert exc.value.motivo == "fora"
