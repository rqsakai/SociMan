"""Registro dos passos (spec 021, T007, R15): a lista bate com o CHECK da migration 0027 (os 15
da 0020 e os 6 da 011), e as regras de escolha, aplicação e número de opções do FR-003, FR-010 e
FR-031 (e o FR-041 da 011: só o `cena.keyframe` tem escolha no roteiro)."""

import re
from pathlib import Path

import pytest

from sociman_api.geracao import passos

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
PASSOS_011 = ("roteiro.plano", "roteiro.narracao", "cena.keyframe", "cena.clipe",
              "roteiro.montagem", "roteiro.acabamento")


def _passos_da(arquivo: str) -> tuple[str, ...]:
    texto = (VERSIONS / arquivo).read_text()
    bloco = texto[texto.index("PASSOS = ("):texto.index(")\n", texto.index("PASSOS = ("))]
    return tuple(re.findall(r'"([a-z]+\.[a-z0-9_]+)"', bloco))


def test_lista_bate_com_o_check_da_migration():
    assert _passos_da("0027_roteiros_video_local.py") == passos.IDS
    assert len(passos.IDS) == 21
    assert _passos_da("0020_geracao_local.py") == passos.IDS[:15]
    assert passos.IDS[15:] == PASSOS_011


def test_sem_escolha_e_aplica_alvo():
    sem = {p.id for p in passos.PASSOS.values() if p.sem_escolha}
    assert sem == {"produto.ficha", "avatar.identidade", "produto.recorte", "voz.teste",
                   # 011 (FR-041): os de resultado único do roteiro
                   "roteiro.plano", "roteiro.narracao", "cena.clipe", "roteiro.montagem",
                   "roteiro.acabamento"}
    assert {p.id for p in passos.PASSOS.values() if not p.aplica_alvo} == {"voz.teste"}


def test_numero_de_opcoes():
    for p in passos.PASSOS.values():
        assert 1 <= p.n_padrao <= p.n_max <= 4, p.id
        if p.id == "avatar.rosto_origem":
            assert p.n_padrao == 4
        elif p.id == "voz.teste":
            assert p.n_padrao == p.n_max == 1
        elif p.id.startswith("voz."):
            assert p.n_max <= 3
        elif p.sem_escolha:  # resultado único (recorte e os do roteiro)
            assert p.n_padrao == p.n_max == 1, p.id
        else:
            assert p.n_padrao == 2, p.id


def test_motores_blocos_e_par():
    from sociman_api.geracao.comfyui import BLOCOS

    for p in passos.PASSOS.values():
        assert (p.bloco is not None) == (p.motor.value == "comfyui"), p.id
        assert p.bloco is None or p.bloco in BLOCOS, p.id
        assert (p.resultado == "texto") == (p.motor.value == "claude"), p.id
    assert passos.get("avatar.rostos_34").resultado == "par_imagem"
    assert passos.get("cenario.cena").bloco == "cena"
    assert "no people" in passos.REALISMO and "no people" in passos.MANTER


def test_passos_da_011():
    """Alvos, motores e resultados do data-model (tabela dos passos)."""
    esperado = {
        "roteiro.plano": ("claude", "roteiro", "texto"),
        "roteiro.narracao": ("tts", "roteiro", "audio"),
        "cena.keyframe": ("comfyui", "cena", "imagem"),
        "cena.clipe": ("comfyui", "cena", "video"),
        "roteiro.montagem": ("ffmpeg", "roteiro", "video"),
        "roteiro.acabamento": ("comfyui", "roteiro", "video"),
    }
    for pid, (motor, alvo, resultado) in esperado.items():
        p = passos.get(pid)
        assert (p.motor.value, p.alvo_tipo.value, p.resultado) == (motor, alvo, resultado), pid
    assert passos.get("cena.keyframe").image_kind == "keyframe"
    assert passos.get("cena.keyframe").bloco == "keyframe"
    assert passos.get("roteiro.acabamento").bloco == "upscale_video"
    assert set(passos.BLOCOS_CLIPE) == {"minimax", "wan", "wan_qualidade", "ltx"}
    assert passos.BLOCOS_CLIPE["minimax"] == passos.get("cena.clipe").bloco


def test_sobrescrever_so_no_teste_e_volta(monkeypatch):
    original = passos.get("avatar.identidade")
    with passos.sobrescrever("avatar.identidade", n_padrao=1) as p:
        assert passos.get("avatar.identidade") is p
    assert passos.get("avatar.identidade") is original
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    with pytest.raises(RuntimeError), passos.sobrescrever("avatar.identidade"):
        pass
