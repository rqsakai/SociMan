"""Ritmo humano: distribuições das pausas (semente fixa) e limites efetivos (T035)."""

import statistics

from sociman_coletor import janela, ritmo
from sociman_coletor.config import LimitesLocais
from sociman_coletor.modelos import Janela, Limites


def test_constantes_do_contrato():
    assert ritmo.PAUSA_MIN_S == 5 and ritmo.PAUSA_MAX_S == 40
    assert ritmo.PAUSA_CURTA_MS == (300, 1500)
    assert ritmo.BLOCO_PAGINAS == 10 and ritmo.PAUSA_LONGA_S == (60, 180)
    assert ritmo.ROLAGEM_PASSOS == (3, 8) and ritmo.ROLAGEM_PX == (300, 900)
    assert ritmo.JITTER_JANELA_MIN == (0, 20)
    assert ritmo.DORMIR_FILA_VAZIA_MIN == 15


def test_dez_mil_pausas_dentro_dos_limites_com_media_no_terco_central():
    r = ritmo.Ritmo(semente=42)
    pausas = [r.pausa() for _ in range(10_000)]
    assert all(5 <= p <= 40 for p in pausas)
    media = statistics.fmean(pausas)
    terco = (40 - 5) / 3
    assert 5 + terco <= media <= 40 - terco
    assert all(a != b for a, b in zip(pausas, pausas[1:], strict=False))


def test_semente_fixa_reproduz():
    assert [ritmo.Ritmo(semente=7).pausa() for _ in range(5)] == [
        ritmo.Ritmo(semente=7).pausa() for _ in range(5)
    ]


def test_pausa_curta_longa_rolagem_e_jitter():
    r = ritmo.Ritmo(semente=1)
    for _ in range(1000):
        assert 300 <= r.pausa_curta_ms() <= 1500
        assert 60 <= r.pausa_longa_s() <= 180
        passos = r.rolagem()
        assert 3 <= len(passos) <= 8 and all(300 <= p <= 900 for p in passos)
        assert 0 <= r.jitter_janela_min() <= 20
        x, y, s = r.ponto_mouse(1280, 900)
        assert 0 < x < 1280 and 0 < y < 900 and s >= 1


def test_fim_de_bloco_a_cada_dez_paginas():
    assert not ritmo.Ritmo.e_fim_de_bloco(0)
    assert ritmo.Ritmo.e_fim_de_bloco(10) and ritmo.Ritmo.e_fim_de_bloco(20)
    assert not ritmo.Ritmo.e_fim_de_bloco(11)


def _servidor(**kw) -> Limites:
    base = dict(
        paginas_dia=300,
        imagens_dia=1500,
        imagens_por_produto=9,
        itens_por_coleta=40,
        pausa_min_s=5,
        pausa_max_s=40,
        lease_min=30,
    )
    base.update(kw)
    return Limites(**base)


def test_limites_efetivos_menor_para_paginas_e_maior_para_pausas():
    local = LimitesLocais(paginas_dia=100, imagens_dia=2000, pausa_min_s=10, pausa_max_s=20)
    ef = ritmo.limites_efetivos(local, _servidor(), Janela(inicio=8, fim=23, dentro=True))
    assert ef.paginas_dia == 100  # min(100, 300)
    assert ef.imagens_dia == 1500  # min(2000, 1500)
    assert ef.pausa_min_s == 10  # max(10, 5)
    assert ef.pausa_max_s == 40  # max(20, 40)
    assert ef.itens_por_coleta == 40 and ef.imagens_por_produto == 9
    assert ef.janela == janela.Janela(8, 23)


def test_limites_efetivos_sem_local_usa_servidor_e_intersecao_da_janela():
    ef = ritmo.limites_efetivos(
        LimitesLocais(), _servidor(pausa_min_s=8), Janela(inicio=8, fim=23, dentro=True)
    )
    assert ef.paginas_dia == 300 and ef.pausa_min_s == 8 and ef.pausa_max_s == 40
    local = LimitesLocais(janela_inicio=10, janela_fim=18)
    ef = ritmo.limites_efetivos(local, _servidor(), Janela(inicio=8, fim=23, dentro=True))
    assert ef.janela == janela.Janela(10, 18)
    local = LimitesLocais(janela_inicio=0, janela_fim=6)
    ef = ritmo.limites_efetivos(local, _servidor(), Janela(inicio=8, fim=23, dentro=True))
    assert ef.janela is None  # não se tocam


def test_ritmo_usa_as_pausas_efetivas():
    r = ritmo.Ritmo(10, 20, semente=3)
    assert all(10 <= r.pausa() <= 20 for _ in range(2000))
