"""Comandos ffmpeg da montagem e do acabamento (spec 011, T011, research R2, R5 e R11).

Os construtores são puros; um teste roda a montagem de verdade (o ffmpeg está na imagem) com
clipes sintéticos pequenos.
"""

import json
import subprocess
import uuid
from pathlib import Path

import pytest

from sociman_api.geracao.erros import MotorErro
from sociman_api.roteiros import montagem as m


def _vf(cmd: list[str]) -> str:
    return cmd[cmd.index("-vf") + 1]


def _fc(cmd: list[str]) -> str:
    return cmd[cmd.index("-filter_complex") + 1]


def test_cortar_por_posicao():
    cmd = m.cmd_cortar("/w/t.mp4", "/w/p.mp4", duracao_s=3.327, largura=736, altura=1280)
    assert cmd[:5] == ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    assert _vf(cmd) == ("scale=736:1280:force_original_aspect_ratio=decrease,"
                        "pad=736:1280:(ow-iw)/2:(oh-ih)/2,fps=24,trim=duration=3.327,"
                        "setpts=PTS-STARTPTS,format=yuv420p,setsar=1")
    assert "-an" in cmd and "-ss" not in cmd
    assert cmd[-1] == "/w/p.mp4"
    com_inicio = m.cmd_cortar("a", "b", duracao_s=2, largura=720, altura=1248, inicio_s=1.5)
    assert com_inicio[com_inicio.index("-ss") + 1] == "1.500"


def test_concat_sem_recodificar_e_lista_escapada(tmp_path):
    cmd = m.cmd_concat("/w/lista.txt", "/w/mudo.mp4")
    assert cmd[5:] == ["-f", "concat", "-safe", "0", "-i", "/w/lista.txt", "-c", "copy",
                       "/w/mudo.mp4"]
    lista = m.lista_concat([tmp_path / "a.mp4", tmp_path / "it's.mp4"])
    assert lista == f"file '{tmp_path}/a.mp4'\nfile '{tmp_path}/it'\\''s.mp4'\n"


def test_atempo():
    cmd = m.cmd_atempo("in.wav", "out.wav", 1.08)
    assert cmd[cmd.index("-af") + 1] == "atempo=1.08"
    assert cmd[-3:] == ["-c:a", "pcm_s16le", "out.wav"]
    with pytest.raises(ValueError):
        m.cmd_atempo("in.wav", "out.wav", 3)


def test_mistura_a_menos_14_lufs():
    cmd = m.cmd_mixar("mudo.mp4", "voz.wav", "previa.mp4")
    assert _fc(cmd) == ("[1:a]aresample=48000,aformat=channel_layouts=stereo,apad,"
                        "loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "-shortest" in cmd and "+faststart" in cmd


def test_acabamento_receita_do_finalizar_hd():
    cmd = m.cmd_acabamento("junto.mp4", "voz.wav", "final.mp4", largura=736, altura=1280)
    assert _fc(cmd) == (
        "[0:v]scale=1104:1920:flags=lanczos,crop=1080:1920,unsharp=3:3:0.3,fps=24[v];"
        "[1:a]aresample=48000,aformat=channel_layouts=stereo,apad,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    assert cmd[cmd.index("-crf") + 1] == "16"
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-b:a") + 1] == "192k"
    # 720×1248 (o padrão do script) também dá 1080 de largura depois do crop.
    assert "scale=1108:1920" in _fc(m.cmd_acabamento("a", "b", "c", largura=720, altura=1248))
    with pytest.raises(ValueError):
        m.cmd_acabamento("a", "b", "c", largura=512, altura=1280)
    assert _vf(m.cmd_denoise("up.mp4", "hd.mp4")) == "hqdn3d=0:0:3:3"


def test_nunca_estica_a_tomada():
    todos = [m.cmd_cortar("a", "b", duracao_s=3, largura=736, altura=1280),
             m.cmd_concat("l", "d"), m.cmd_mixar("a", "b", "c"), m.cmd_denoise("a", "b"),
             m.cmd_acabamento("a", "b", "c", largura=736, altura=1280)]
    for cmd in todos:
        assert not any("tpad" in p or "clone" in p for p in cmd)
    assert m.tomada_curta(3326, 3.327)
    assert not m.tomada_curta(3327, 3.327)
    assert not m.tomada_curta(8000, 3.327)


def test_executar_traduz_falha(tmp_path):
    with pytest.raises(MotorErro) as exc:
        m.executar(m.cmd_cortar(tmp_path / "nao_existe.mp4", tmp_path / "x.mp4", duracao_s=1,
                                largura=64, altura=112))
    assert exc.value.codigo == "internal"
    assert "nao_existe" in exc.value.detalhe


def test_pasta_temporaria_some_no_fim(monkeypatch, tmp_path):
    class S:
        data_dir = str(tmp_path)

    monkeypatch.setattr(m, "get_settings", lambda: S())
    gid = uuid.uuid4()
    with pytest.raises(RuntimeError), m.pasta_temporaria(gid) as p:
        assert p == tmp_path / "work" / "tmp" / "roteiros" / str(gid)
        (p / "x").write_text("x")
        raise RuntimeError
    assert not m.pasta(gid).exists()


def _clipe(dst: Path, segundos: float, w: int = 96, h: int = 160, fps: int = 16) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size={w}x{h}:rate={fps}:duration={segundos}", "-f", "lavfi",
                    "-i", f"sine=frequency=300:duration={segundos}", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(dst)],
                   check=True)
    return dst


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,width,height,r_frame_rate",
                          "-of", "json", str(path)], capture_output=True, check=True).stdout
    return json.loads(out)


def test_montagem_de_verdade(tmp_path):
    """Duas tomadas com áudio do modelo (Wan a 16 fps e MiniMax a 24) + a narração: a prévia
    tem a resolução da cena, 24 fps, a soma das posições e só o áudio da narração."""
    t1 = _clipe(tmp_path / "t1.mp4", 2.0, fps=16)
    t2 = _clipe(tmp_path / "t2.mp4", 2.0, w=80, h=160, fps=24)
    voz = tmp_path / "voz.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2.4", str(voz)], check=True)
    rapida = m.aplicar_atempo(voz, tmp_path / "voz_rapida.wav", 1.2)
    assert float(_probe(rapida)["format"]["duration"]) == pytest.approx(2.0, abs=0.05)

    previa = m.montar_previa(tmp_path, [(t1, 1.25), (t2, 1.0)], rapida, largura=96, altura=160)
    info = _probe(previa)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"], video["r_frame_rate"]) == (96, 160, "24/1")
    assert [s["codec_type"] for s in info["streams"]].count("audio") == 1
    assert float(info["format"]["duration"]) == pytest.approx(2.25, abs=0.1)

    hd = m.tirar_cintilacao(tmp_path, m.cortar_posicoes(tmp_path, [(t1, 1.0)], largura=96,
                                                        altura=160))
    final = m.acabar(tmp_path, hd, rapida, largura=96, altura=160)
    vf = next(s for s in _probe(final)["streams"] if s["codec_type"] == "video")
    assert (vf["width"], vf["height"], vf["r_frame_rate"]) == (1080, 1920, "24/1")
