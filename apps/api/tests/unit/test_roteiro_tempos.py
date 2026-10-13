"""Durações das posições e quadros por motor (spec 011, T008, research R4 e R6): funções puras."""

import json
from pathlib import Path

import pytest

from sociman_api.roteiros.tempos import (
    DURACAO_MAX_S,
    FPS,
    LEAD,
    TAIL,
    TemposInvalidos,
    duracao_clipe_s,
    limites,
    na_velocidade,
    quadros,
    teto_quadros,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bia_vo_timings.json"


def _tempos(*inicios: float) -> list[dict]:
    return [{"frase": i, "inicio_s": t, "fim_s": t + 1.0} for i, t in enumerate(inicios, 1)]


def test_tempos_bia_vo():
    """Regressão da referência aprovada (`runs/bia_vo`): narração a 1,08x, uma frase por
    posição, as durações do `plano.json`."""
    ref = json.loads(FIXTURE.read_text())
    tempos, total = na_velocidade(ref["sentences"], ref["seconds"], ref["velocidade"])
    lim = limites(tempos, [[1], [2], [3], [4]], total)
    assert [x.duracao_s for x in lim] == ref["esperado"] == [3.327, 6.722, 5.315, 1.826]
    assert lim[0].inicio_s == 0.0
    assert lim[1].inicio_s == round(3.68 / 1.08 - LEAD, 3)
    assert sum(x.duracao_s for x in lim) == pytest.approx(total + TAIL, abs=0.002)


def test_na_velocidade_divide_os_tempos():
    tempos, total = na_velocidade([{"index": 1, "text": "x", "start": 0.0, "end": 2.16},
                                   {"index": 2, "text": "y", "start": 2.7, "end": 5.4}],
                                  5.4, 1.08)
    assert tempos == [{"frase": 1, "inicio_s": 0.0, "fim_s": 2.0},
                      {"frase": 2, "inicio_s": 2.5, "fim_s": 5.0}]
    assert total == 5.0
    with pytest.raises(ValueError):
        na_velocidade([], 1.0, 0)


def test_posicao_com_varias_frases_e_minimo():
    lim = limites(_tempos(0.0, 2.0, 2.5, 6.0), [[1, 2], [3], [4]], 7.0)
    assert [x.inicio_s for x in lim] == [0.0, 2.42, 5.92]
    # 2ª posição: 5,92 − 2,42 = 3,5; a última vai até 7,0 + 0,45.
    assert [x.duracao_s for x in lim] == [2.42, 3.5, 1.53]
    # Uma posição curtíssima fica com o mínimo de 1 s.
    curto = limites(_tempos(0.0, 3.0, 3.3), [[1], [2], [3]], 4.0)
    assert curto[1].duracao_s == 1.0


@pytest.mark.parametrize("posicoes", [
    [[1], [3], [2]],        # fora de ordem
    [[1, 3], [2]],          # não contígua
    [[1], [2]],             # frase sem posição
    [[1], [2], [2, 3]],     # frase repetida
    [[1], [], [2, 3]],      # posição vazia
    [],
])
def test_posicoes_nao_contiguas_dao_erro(posicoes):
    with pytest.raises(TemposInvalidos):
        limites(_tempos(0.0, 1.0, 2.0), posicoes, 3.0)


def test_quadros_dos_4_motores():
    # MiniMax 17k+5 a 24 fps: 3,0 s (+0,1) → ⌈(74,4 − 5)/17⌉ = 5 → 90.
    assert quadros("minimax", 3.0) == 90
    assert quadros("minimax", 6.722) == 175  # S2 da bia_vo
    # Wan 4k+1 a 16 fps: 3,0 s (+0,1) → ⌈(49,6 − 1)/4⌉ = 13 → 53 (para cima, não 49).
    assert quadros("wan", 3.0) == 53
    assert quadros("wan_qualidade", 1.826) == 33
    # LTX 8k+1 a 24 fps: 3,0 s (+0,1) → ⌈(74,4 − 1)/8⌉ = 10 → 81.
    assert quadros("ltx", 3.0) == 81
    for motor in FPS:
        n = quadros(motor, 2.0)
        passo, resto = {"minimax": (17, 5), "ltx": (8, 1)}.get(motor, (4, 1))
        assert (n - resto) % passo == 0
        assert duracao_clipe_s(motor, n) >= 2.0 + 0.1


def test_quadros_param_no_teto_do_motor():
    assert {m: teto_quadros(m) for m in FPS} == {"minimax": 192, "wan": 81,
                                                 "wan_qualidade": 113, "ltx": 121}
    for motor, maximo in DURACAO_MAX_S.items():
        assert quadros(motor, maximo) == teto_quadros(motor)
        assert quadros(motor, maximo + 10) == teto_quadros(motor)
        assert duracao_clipe_s(motor, teto_quadros(motor)) >= maximo
    with pytest.raises(ValueError):
        quadros("veo", 3.0)
