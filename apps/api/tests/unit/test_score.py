"""Pontuação de recomendação (T032, research R3)."""

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sociman_api.canais import score
from sociman_api.canais.models import VideoLive

AGORA = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _entrada(**kw) -> score.Entrada:
    base = {"views": 10_000, "likes": 500, "comments": 40,
            "published_at": AGORA - timedelta(days=10), "duration_s": 24 * 60,
            "live": VideoLive.nenhum, "disponivel": True, "vph_recente": None}
    base.update(kw)
    return score.Entrada(**base)


def test_pesos():
    assert score.PESOS == {"v": 0.45, "e": 0.20, "r": 0.15, "d": 0.20}
    assert sum(score.PESOS.values()) == pytest.approx(1.0)


def test_formula_completa():
    e = _entrada(vph_recente=300.0)
    eng = (500 + 3 * 40) / 10_000
    r = score.calcular(e, mediana_vph=100.0, mediana_eng=eng, agora=AGORA)
    v = min(1, math.log(1 + 3) / math.log(9))
    e_comp = math.log(2) / math.log(5)
    rec = math.exp(-10 / 30)
    esperado = 100 * (0.45 * v + 0.20 * e_comp + 0.15 * rec + 0.20 * 1.0)
    assert r.score == Decimal(str(round(esperado, 1)))
    assert r.recomendavel is True
    assert r.detail["v"] == pytest.approx(v, abs=1e-3)
    assert r.detail["e"] == pytest.approx(e_comp, abs=1e-3)
    assert r.detail["r"] == pytest.approx(rec, abs=1e-3)
    assert r.detail["d"] == 1.0
    assert r.detail["componente"] == "v"
    assert r.detail["valores"]["rV"] == 3.0


def test_velocidade_satura_em_8_vezes_a_mediana():
    r8 = score.calcular(_entrada(vph_recente=800.0), 100.0, None, AGORA)
    r20 = score.calcular(_entrada(vph_recente=2000.0), 100.0, None, AGORA)
    assert r8.detail["v"] == 1.0 == r20.detail["v"]


def test_vph_sem_leituras_usa_views_por_hora_publicada():
    e = _entrada(views=4800, published_at=AGORA - timedelta(hours=48))
    assert score.vph(e, AGORA) == pytest.approx(100.0)
    assert score.vph(_entrada(vph_recente=7.5), AGORA) == 7.5
    assert score.vph(_entrada(views=None), AGORA) is None


def test_engajamento_com_likes_ocultos_conta_zero():
    assert score.engajamento(_entrada(views=1000, likes=None, comments=10)) == 0.03
    assert score.engajamento(_entrada(views=1000, likes=100, comments=10)) == 0.13


def test_recencia_decai_em_30_dias():
    novo = score.calcular(_entrada(published_at=AGORA), None, None, AGORA)
    velho = score.calcular(_entrada(published_at=AGORA - timedelta(days=30)), None, None, AGORA)
    assert novo.detail["r"] == pytest.approx(1.0, abs=1e-3)
    assert velho.detail["r"] == pytest.approx(math.exp(-1), abs=1e-3)


@pytest.mark.parametrize(("segundos", "d"), [
    (60, 0.0), (179, 0.0), (180, 0.6), (7 * 60, 0.6), (8 * 60, 1.0), (60 * 60, 1.0),
    (61 * 60, 0.7), (3 * 3600, 0.7), (None, 0.0),
])
def test_tabela_de_duracao(segundos, d):
    r = score.calcular(_entrada(duration_s=segundos), None, None, AGORA)
    assert r.detail["d"] == d


@pytest.mark.parametrize(("mudanca", "motivo"), [
    ({"disponivel": False}, "Indisponível no YouTube (removido ou privado)"),
    ({"live": VideoLive.ao_vivo}, "Ao vivo agora: não recomendado"),
    ({"live": VideoLive.agendado}, "Transmissão agendada: não recomendado"),
    ({"duration_s": 3 * 3600 + 1}, "Longo demais (> 3 h)"),
    ({"duration_s": 44}, "Curto demais (Shorts)"),
])
def test_zeram_e_saem_da_recomendacao(mudanca, motivo):
    r = score.calcular(_entrada(vph_recente=5000.0, **mudanca), 100.0, 0.01, AGORA)
    assert r.score == Decimal("0.0")
    assert r.recomendavel is False
    assert r.reason == motivo
    assert r.detail["componente"] == "aviso"


def test_45_segundos_ainda_e_recomendavel():
    r = score.calcular(_entrada(duration_s=45), None, None, AGORA)
    assert r.recomendavel is True and r.detail["d"] == 0.0


def test_motivos_pelo_maior_componente():
    rapido = score.calcular(_entrada(vph_recente=12_345.0), 4000.0, 1.0, AGORA)
    assert rapido.detail["componente"] == "v"
    assert rapido.reason == "12 mil views/h recentes (3,1× a média do canal)"

    novo = score.calcular(
        _entrada(published_at=AGORA - timedelta(hours=5), views=0, likes=0, comments=0,
                 duration_s=5 * 60),
        100.0, 1.0, AGORA)
    assert novo.detail["componente"] == "r"
    assert novo.reason == "Novo: publicado há 5 h"

    longo = score.calcular(_entrada(views=0, likes=0, comments=0,
                                   published_at=AGORA - timedelta(days=200)),
                           100.0, 1.0, AGORA)
    assert longo.detail["componente"] == "d"
    assert longo.reason == "Duração boa para cortes (24 min)"

    engajado = score.calcular(
        _entrada(views=1000, likes=300, comments=0, published_at=AGORA - timedelta(days=200),
                 duration_s=5 * 60, vph_recente=0.0), 100.0, 0.125, AGORA)
    assert engajado.detail["componente"] == "e"
    assert engajado.reason == "Engajamento alto: 2,4× o do canal"


def test_direito_nao_entra_na_conta():
    campos = {f.name for f in score.Entrada.__dataclass_fields__.values()}
    assert "direito" not in campos


def test_score_exibido_ja_cortado():
    assert score.score_exibido(Decimal("80.0"), False) == Decimal("80.0")
    assert score.score_exibido(Decimal("80.0"), True) == Decimal("24.0")
    assert score.score_exibido(Decimal("55.5"), True) == Decimal("16.7")


def test_mediana_e_relativo_sem_referencia():
    assert score.mediana([None, 3.0, 1.0, 2.0]) == 2.0
    assert score.mediana([None]) is None
    r = score.calcular(replace(_entrada(), vph_recente=10.0), None, None, AGORA)
    assert r.detail["valores"]["rV"] == 1.0


def test_formatacao():
    assert score.formatar_contagem(12) == "12"
    assert score.formatar_contagem(1234) == "1,2 mil"
    assert score.formatar_contagem(12_345) == "12 mil"
    assert score.formatar_contagem(3_100_000) == "3,1 mi"
    assert score.formatar_duracao(80 * 60) == "1 h 20 min"
