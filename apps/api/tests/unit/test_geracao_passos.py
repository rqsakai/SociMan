"""Registro dos passos (spec 021, T007, R15): a lista bate com o CHECK da migration 0020, e as
regras de escolha, aplicação e número de opções do FR-003, FR-010 e FR-031."""

import re
from pathlib import Path

import pytest

from sociman_api.geracao import passos

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions" / \
    "0020_geracao_local.py"


def test_lista_bate_com_o_check_da_migration():
    texto = MIGRATION.read_text()
    bloco = texto[texto.index("PASSOS = ("):texto.index(")\n", texto.index("PASSOS = ("))]
    assert tuple(re.findall(r'"([a-z]+\.[a-z0-9_]+)"', bloco)) == passos.IDS
    assert len(passos.IDS) == 15


def test_sem_escolha_e_aplica_alvo():
    sem = {p.id for p in passos.PASSOS.values() if p.sem_escolha}
    assert sem == {"produto.ficha", "avatar.identidade", "produto.recorte", "voz.teste"}
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
        elif p.resultado != "texto" and p.id != "produto.recorte":
            assert p.n_padrao == 2, p.id


def test_motores_blocos_e_par():
    for p in passos.PASSOS.values():
        assert (p.bloco is not None) == (p.motor.value == "comfyui"), p.id
        assert (p.resultado == "texto") == (p.motor.value == "claude"), p.id
    assert passos.get("avatar.rostos_34").resultado == "par_imagem"
    assert passos.get("cenario.cena").bloco == "cena"
    assert "no people" in passos.REALISMO and "no people" in passos.MANTER


def test_sobrescrever_so_no_teste_e_volta(monkeypatch):
    original = passos.get("avatar.identidade")
    with passos.sobrescrever("avatar.identidade", n_padrao=1) as p:
        assert passos.get("avatar.identidade") is p
    assert passos.get("avatar.identidade") is original
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    with pytest.raises(RuntimeError), passos.sobrescrever("avatar.identidade"):
        pass
