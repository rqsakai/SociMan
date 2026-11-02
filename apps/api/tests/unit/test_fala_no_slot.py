"""Fala por slot do vídeo guiado (spec 031, T047, research R4): a narração contínua cortada
pelos tempos das frases, um bloco por posição, no início do slot (+0,15 s), com `atempo` por
bloco até a velocidade total 1,20 e o aviso `fala_nao_cabe` acima disso."""

import array
import subprocess
from pathlib import Path

import pytest

from sociman_api.roteiros import montagem as m
from sociman_api.roteiros.tempos import (
    ATRASO_FALA,
    MARGEM_FIM,
    VELOCIDADE_MAX,
    TemposInvalidos,
    fala_por_slot,
)

VEL = 1.08
# Na velocidade do roteiro: posição 0 com as frases 1 e 2 (passa um pouco do slot), posição 1
# com a 3 (cabe) e posição 2 com a 4 (não cabe nem a 1,20×). Slots de 5 s.
TEMPOS = [{"frase": 1, "inicio_s": 0.0, "fim_s": 2.0},
          {"frase": 2, "inicio_s": 2.3, "fim_s": 4.6},
          {"frase": 3, "inicio_s": 5.0, "fim_s": 7.0},
          {"frase": 4, "inicio_s": 7.4, "fim_s": 13.0}]
POSICOES = [[1, 2], [3], [4]]
DURACOES = [5.0, 5.0, 5.0]


def test_corta_pelos_tempos_das_frases_sem_invadir_o_vizinho():
    blocos, _ = fala_por_slot(TEMPOS, POSICOES, DURACOES, VEL)
    assert [b.ordem for b in blocos] == [0, 1, 2]
    assert (blocos[0].inicio_s, blocos[0].fim_s) == (0.0, 4.65)
    # Entre 4,6 e 5,0 o meio é 4,8: o respiro de 0,05 cabe dos dois lados.
    assert (blocos[1].inicio_s, blocos[1].fim_s) == (4.95, 7.05)
    assert (blocos[2].inicio_s, blocos[2].fim_s) == (7.35, 13.05)
    colados = [{"frase": 1, "inicio_s": 0.0, "fim_s": 2.0},
               {"frase": 2, "inicio_s": 2.02, "fim_s": 3.0}]
    b, _ = fala_por_slot(colados, [[1], [2]], [5.0, 5.0], VEL)
    assert b[0].fim_s == b[1].inicio_s == 2.01


def test_adelay_no_inicio_do_slot():
    blocos, _ = fala_por_slot(TEMPOS, POSICOES, [5.0, 10.0, 15.0], VEL)
    assert [b.atraso_s for b in blocos] == [0.15, 5.15, 15.15]
    assert [b.max_s for b in blocos] == [4.85, 9.85, 14.85]
    assert ATRASO_FALA == 0.15


def test_atempo_por_bloco_ate_a_velocidade_total_120():
    blocos, avisos = fala_por_slot(TEMPOS, POSICOES, DURACOES, VEL)
    cabe = 5.0 - ATRASO_FALA - MARGEM_FIM
    # 4,65 s numa vaga de 4,55 s: 1,022× a mais (1,104× no total).
    assert blocos[0].atempo == pytest.approx(4.65 / cabe, abs=0.001)
    assert (blocos[0].fim_s - blocos[0].inicio_s) / blocos[0].atempo <= cabe
    assert blocos[1].atempo == 1.0
    for b in blocos:
        assert b.atempo * VEL <= VELOCIDADE_MAX + 1e-9
    assert [a["ordem"] for a in avisos] == [2]
    # Com uma duração maior, tudo cabe e não há aviso.
    _, sem = fala_por_slot(TEMPOS, POSICOES, [5.0, 5.0, 10.0], VEL)
    assert sem == []


def test_aviso_fala_nao_cabe_com_a_ordem():
    blocos, avisos = fala_por_slot(TEMPOS, POSICOES, DURACOES, VEL, ordens=[3, 4, 5])
    assert avisos == [{"code": "fala_nao_cabe",
                       "message": "A fala da cena 6 não cabe em 5 s nem a 1,20×",
                       "ordem": 5}]
    # O bloco que não cabe vai no teto (1,20 / 1,08) e é cortado no fim do slot.
    assert blocos[2].atempo == pytest.approx(1.111, abs=0.0005)
    assert blocos[2].max_s == 4.85


def test_posicao_sem_fala_e_validacoes():
    blocos, avisos = fala_por_slot(TEMPOS[:2], [[1], [], [2]], [5.0, 5.0, 5.0], VEL)
    assert [(b.ordem, b.atraso_s) for b in blocos] == [(0, 0.15), (2, 10.15)]
    assert avisos == []
    with pytest.raises(TemposInvalidos):
        fala_por_slot(TEMPOS, [[1], [3], [2, 4]], DURACOES, VEL)
    with pytest.raises(TemposInvalidos):
        fala_por_slot(TEMPOS, POSICOES, [5.0, 5.0], VEL)
    with pytest.raises(TemposInvalidos):
        fala_por_slot(TEMPOS, POSICOES, DURACOES, VEL, ordens=[0])
    with pytest.raises(ValueError):
        fala_por_slot(TEMPOS, POSICOES, DURACOES, 0)


def test_cmd_fala_no_slot_puro():
    blocos, _ = fala_por_slot(TEMPOS, POSICOES, DURACOES, VEL)
    cmd = m.cmd_fala_no_slot("voz.wav", "slot.wav", blocos, DURACOES)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.startswith("[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=3"
                         "[s0][s1][s2];")
    # Cada slot: o bloco, `adelay` de 0,15 s e silêncio até o fim do slot (0,15 + 4,85 = 5).
    assert ("[s1]atrim=start=4.950:end=7.050,asetpts=PTS-STARTPTS,atrim=duration=4.850,"
            "apad=whole_dur=4.850,adelay=150:all=1[b1]") in fc
    assert "atempo=1.022" in fc
    assert fc.endswith("[b0][b1][b2]concat=n=3:v=0:a=1[a]")
    assert cmd[cmd.index("-t") + 1] == "15.000"
    assert "loudnorm" not in fc and "amix" not in fc  # a mistura (cmd_mixar) normaliza
    um = m.cmd_fala_no_slot("v", "s", blocos[:1], [5.0])
    assert "asplit" not in um[um.index("-filter_complex") + 1]
    # Posição sem fala: o slot é silêncio.
    sem, _ = fala_por_slot(TEMPOS[:2], [[1], [], [2]], DURACOES, VEL)
    fc2 = m.cmd_fala_no_slot("v", "s", sem, DURACOES)
    fc2 = fc2[fc2.index("-filter_complex") + 1]
    assert "anullsrc=r=48000:cl=stereo:d=5.000[z1]" in fc2
    assert fc2.endswith("[b0][z1][b2]concat=n=3:v=0:a=1[a]")
    mudo = m.cmd_fala_no_slot("v", "s", [], [5.0, 5.0])
    assert "-i" not in mudo and mudo[mudo.index("-t") + 1] == "10.000"
    with pytest.raises(ValueError):
        m.cmd_fala_no_slot("v", "s", blocos, [5.0])


def _tons(dst: Path, trechos: list[tuple[float, float]], total: float) -> Path:
    # As vírgulas da expressão são escapadas (no filtergraph, a vírgula separa filtros).
    janelas = "+".join(rf"between(t\,{a}\,{b})" for a, b in trechos)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"aevalsrc=0.5*sin(2*PI*440*t)*({janelas}):s=48000:d={total}", str(dst)],
                   check=True)
    return dst


def _rms_por_janela(path: Path, janela: float = 0.05) -> list[float]:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    amostras = array.array("h", pcm)
    n = int(8000 * janela)
    return [(sum(x * x for x in amostras[i:i + n]) / n) ** 0.5
            for i in range(0, len(amostras) - n + 1, n)]


def _duracao(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(path)], capture_output=True,
                                check=True).stdout)


def test_fala_no_slot_de_verdade(tmp_path):
    """A narração com tons nas frases vira um WAV de exatamente o alvo, com silêncio antes de
    cada slot + 0,15 s e o tom dentro do slot; a prévia mistura a −14 LUFS."""
    voz = _tons(tmp_path / "voz.wav", [(t["inicio_s"], t["fim_s"]) for t in TEMPOS], 13.2)
    blocos, avisos = fala_por_slot(TEMPOS, POSICOES, DURACOES, VEL)
    slot = m.colocar_fala(tmp_path, voz, blocos, DURACOES)
    assert _duracao(slot) == pytest.approx(15.0, abs=0.01)
    rms = _rms_por_janela(slot)  # janelas de 50 ms
    for inicio in (0.0, 5.0, 10.0):
        k = round(inicio / 0.05)
        assert max(rms[k:k + 2]) < 50, inicio  # 0 a 0,1 s do slot: silêncio
        assert rms[k + 5] > 1000, inicio  # 0,25 s: a fala já entrou
    # A posição 1 (5 a 10 s) cabe: a fala acaba antes da margem do fim do slot.
    assert max(rms[round(9.75 / 0.05):round(10.0 / 0.05)]) < 50
    assert [a["ordem"] for a in avisos] == [2]

    clipe = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=96x160:rate=24", "-frames:v", "124", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(clipe)], check=True)
    posicoes = [m.PosicaoGuiada([clipe], 5.0) for _ in range(3)]
    previa = m.montar_previa_guiada(tmp_path, posicoes, slot, base_s=5, largura=96, altura=160)
    assert _duracao(previa) == pytest.approx(15.0, abs=0.1)
    medida = subprocess.run(["ffmpeg", "-nostats", "-i", str(previa), "-map", "0:a", "-af",
                             "ebur128", "-f", "null", "-"], capture_output=True,
                            check=True).stderr.decode()
    integrada = float(medida.rsplit("I:", 1)[1].split("LUFS")[0])
    assert integrada == pytest.approx(-14, abs=1.5)
