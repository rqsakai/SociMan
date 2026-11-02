"""Montagem por trecho do vídeo guiado (spec 031, T014, research R2): `setpts` para exatamente o
trecho-base, sem o 1º quadro a partir do 2º trecho, e concat por posição e do vídeo.

Os clipes sintéticos têm o 1º quadro azul e o último vermelho (o keyframe de fim), com o
`testsrc2` no meio: dá para conferir pela cor que o fim não foi cortado e que o 1º quadro saiu.
O caminho da 011 (`cmd_cortar`, `montar_previa`) continua coberto por `test_montagem_comandos` e
`test_roteiro_tempos::test_tempos_bia_vo`.
"""

import json
import subprocess
from pathlib import Path

import pytest

from sociman_api.roteiros import montagem as m

W, H = 96, 160
AZUL, VERMELHO = (0, 0, 255), (255, 0, 0)


def _clipe(dst: Path, quadros: int, fps: int = 24) -> Path:
    """`quadros` quadros a `fps`: o 1º azul, o último vermelho e o `testsrc2` no meio."""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", f"color=blue:size={W}x{H}:rate={fps}",
        "-f", "lavfi", "-i", f"testsrc2=size={W}x{H}:rate={fps}",
        "-f", "lavfi", "-i", f"color=red:size={W}x{H}:rate={fps}",
        "-filter_complex",
        (f"[0:v]trim=end_frame=1[a];[1:v]trim=end_frame={quadros - 2}[b];"
         "[2:v]trim=end_frame=1[c];[a][b][c]concat=n=3:v=1[v]"),
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dst)], check=True)
    return dst


def _info(path: Path) -> tuple[int, float, str]:
    out = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
         "stream=nb_read_frames,r_frame_rate:format=duration", "-of", "json", str(path)],
        capture_output=True, check=True).stdout)
    s = out["streams"][0]
    return int(s["nb_read_frames"]), float(out["format"]["duration"]), s["r_frame_rate"]


def _cor(path: Path, quadro: int) -> tuple[int, int, int]:
    """A cor média do quadro de índice `quadro`."""
    rgb = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf",
         rf"select=eq(n\,{quadro}),scale=1:1", "-frames:v", "1", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    assert len(rgb) == 3, f"o quadro {quadro} não existe em {path.name}"
    return rgb[0], rgb[1], rgb[2]


def _perto(cor: tuple[int, int, int], alvo: tuple[int, int, int], tol: int = 40) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(cor, alvo, strict=True))


def test_cmd_trecho_puro():
    cmd = m.cmd_trecho("/w/t.mp4", "/w/o.mp4", base_s=5, quadros=124, primeiro=True,
                       largura=736, altura=1280)
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.startswith("setpts=N*0.040311653/TB,")  # (120 − 1) / 24 / (124 − 1)
    assert "trim" not in vf and "tpad" not in vf and "select" not in vf
    assert cmd[cmd.index("-frames:v") + 1] == "120"
    assert "-an" in cmd and cmd[-1] == "/w/o.mp4"
    seguinte = m.cmd_trecho("a", "b", base_s=5, quadros=124, primeiro=False, largura=736,
                            altura=1280)
    vf2 = seguinte[seguinte.index("-vf") + 1]
    assert vf2.startswith(r"select=gte(n\,1),setpts=N*0.040642077/TB,")  # 119 / 24 / 122
    com_extra = m.cmd_trecho("a", "b", base_s=5, quadros=81, primeiro=True, largura=736,
                             altura=1280, extra_quadros=2)
    assert com_extra[com_extra.index("-frames:v") + 1] == "122"
    with pytest.raises(ValueError):
        m.cmd_trecho("a", "b", base_s=5, quadros=2, primeiro=False, largura=64, altura=64)
    assert m.quadros_saida(5) == 120 and m.quadros_saida(8) == 192


def test_124_quadros_viram_exatamente_5s_com_o_fim(tmp_path):
    src = _clipe(tmp_path / "t.mp4", 124)
    dst = tmp_path / "o.mp4"
    m.executar(m.cmd_trecho(src, dst, base_s=5, quadros=m.contar_quadros(src), primeiro=True,
                            largura=W, altura=H))
    quadros, duracao, fps = _info(dst)
    assert (quadros, fps) == (120, "24/1")
    assert duracao == pytest.approx(5.0, abs=1 / 24)
    assert _perto(_cor(dst, 0), AZUL)
    assert _perto(_cor(dst, 119), VERMELHO)  # o último quadro é o keyframe de fim
    assert not _perto(_cor(dst, 118), VERMELHO)


def test_do_segundo_trecho_em_diante_sai_o_primeiro_quadro(tmp_path):
    src = _clipe(tmp_path / "t.mp4", 124)
    dst = tmp_path / "o.mp4"
    m.executar(m.cmd_trecho(src, dst, base_s=5, quadros=124, primeiro=False, largura=W,
                            altura=H))
    assert _info(dst)[0] == 120
    assert not _perto(_cor(dst, 0), AZUL)
    assert _perto(_cor(dst, 119), VERMELHO)


def test_tres_trechos_dao_15s_e_cada_um_termina_no_quadro_final(tmp_path):
    """MiniMax (124 a 24 fps), Wan (81 a 16 fps) e LTX (121 a 24 fps) na mesma posição."""
    trechos = [_clipe(tmp_path / "mm.mp4", 124), _clipe(tmp_path / "wan.mp4", 81, fps=16),
               _clipe(tmp_path / "ltx.mp4", 121)]
    [pos] = m.montar_posicoes_guiadas(tmp_path, [m.PosicaoGuiada(trechos, 15.0)], base_s=5,
                                      largura=W, altura=H)
    quadros, duracao, fps = _info(pos)
    assert fps == "24/1"
    assert abs(quadros - 360) <= 1
    assert duracao == pytest.approx(15.0, abs=1 / 24)
    for fim in (119, 239, 359):
        assert _perto(_cor(pos, fim), VERMELHO), fim
    assert _perto(_cor(pos, 0), AZUL)
    assert not _perto(_cor(pos, 120), AZUL)  # sem o quadro repetido na emenda


def test_video_inteiro_e_previa_com_a_soma_das_posicoes(tmp_path):
    a = _clipe(tmp_path / "a.mp4", 124)
    b = _clipe(tmp_path / "b.mp4", 124)
    voz = tmp_path / "voz.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=14", str(voz)], check=True)
    posicoes = [m.PosicaoGuiada([a], 5.0), m.PosicaoGuiada([b, a], 10.0)]
    partes = m.montar_posicoes_guiadas(tmp_path, posicoes, base_s=5, largura=W, altura=H)
    assert [round(_info(p)[1], 2) for p in partes] == [5.0, 10.0]
    mudo = m.concatenar(tmp_path, partes, "mudo_guiado.mp4")
    assert abs(_info(mudo)[0] - 360) <= 1
    previa = m.montar_previa_guiada(tmp_path, posicoes, voz, base_s=5, largura=W, altura=H)
    assert _info(previa)[1] == pytest.approx(15.0, abs=0.1)  # a narração mais longa é cortada


def test_crossfade_previsto_mantem_o_total(tmp_path):
    trechos = [_clipe(tmp_path / f"t{i}.mp4", 124) for i in range(3)]
    [pos] = m.montar_posicoes_guiadas(tmp_path, [m.PosicaoGuiada(trechos, 15.0)], base_s=5,
                                      largura=W, altura=H, crossfade_quadros=2)
    quadros, duracao, _ = _info(pos)
    assert abs(quadros - 360) <= 1
    assert duracao == pytest.approx(15.0, abs=1 / 24)
    assert _perto(_cor(pos, quadros - 1), VERMELHO)
    cmd = m.cmd_crossfade(["a", "b"], "c", base_s=5, crossfade_quadros=2)
    assert cmd[cmd.index("-filter_complex") + 1] == (
        "[0:v][1:v]xfade=transition=fade:duration=0.083333:offset=5.000000[v]")
    with pytest.raises(ValueError):
        m.cmd_crossfade(["a"], "c", base_s=5, crossfade_quadros=2)


def test_posicao_que_nao_fecha_com_a_base(tmp_path):
    src = _clipe(tmp_path / "t.mp4", 124)
    with pytest.raises(ValueError, match="não fecha"):
        m.montar_posicoes_guiadas(tmp_path, [m.PosicaoGuiada([src], 10.0)], base_s=5,
                                  largura=W, altura=H)
    with pytest.raises(ValueError):
        m.montar_posicoes_guiadas(tmp_path, [m.PosicaoGuiada([], 0.0)], base_s=5, largura=W,
                                  altura=H)
