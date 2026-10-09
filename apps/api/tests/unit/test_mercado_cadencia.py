"""T049: as transições do estado "Produto (calor)" do data-model e SC-005 (volta a quente no mesmo
dia), num módulo puro."""

from datetime import date, timedelta

from sociman_api.mercado import constantes as k
from sociman_api.mercado.cadencia import Entrada, calcular
from sociman_api.mercado.models import Calor

HOJE = date(2026, 10, 9)


def ent(**kw) -> Entrada:
    base = {"primeira_vez_em": HOJE - timedelta(days=60), "ultima_foto_em": None, "fotos_hoje": 0,
            "ultimo_ranking_em": None, "ultimo_interesse_em": None, "manual_ativo": False,
            "vitrine_ativa": False, "outro_interesse_ativo": False, "novo_em_alta": False}
    base.update(kw)
    return Entrada(**base)


def test_novo_no_lago_e_quente_com_1_ou_2_fotos():
    s = calcular(ent(primeira_vez_em=HOJE), HOJE)
    assert s.calor == Calor.quente and s.fotos_por_dia == 1 and s.proxima_coleta == HOJE
    assert calcular(ent(primeira_vez_em=HOJE, manual_ativo=True), HOJE).fotos_por_dia == 2
    assert calcular(ent(primeira_vez_em=HOJE, novo_em_alta=True), HOJE).fotos_por_dia == 2
    # Vitrine é quente, mas 1 por dia (FR-040: 2/dia só para manual e "novo em alta").
    s = calcular(ent(primeira_vez_em=HOJE, vitrine_ativa=True), HOJE)
    assert s.calor == Calor.quente and s.fotos_por_dia == 1


def test_sem_ranking_ha_7_dias_e_sem_manual_vira_morna_semanal():
    e = ent(ultimo_ranking_em=HOJE - timedelta(days=k.SAI_DO_RANKING_DIAS),
            ultima_foto_em=HOJE - timedelta(days=1))
    s = calcular(e, HOJE)
    assert s.calor == Calor.morna and s.fotos_por_dia == 1
    assert s.proxima_coleta == HOJE - timedelta(days=1) + timedelta(days=k.MORNA_CADA_DIAS)
    # Com 6 dias ainda é quente.
    e6 = ent(ultimo_ranking_em=HOJE - timedelta(days=k.SAI_DO_RANKING_DIAS - 1))
    assert calcular(e6, HOJE).calor == Calor.quente
    # Manual ou vitrine ativos nunca esfriam.
    assert calcular(ent(ultimo_ranking_em=HOJE - timedelta(days=20), manual_ativo=True),
                    HOJE).calor == Calor.quente
    assert calcular(ent(ultimo_ranking_em=HOJE - timedelta(days=20), vitrine_ativa=True),
                    HOJE).calor == Calor.quente
    # As fotos antigas não entram na decisão: nada é apagado, só a cadência muda.


def test_30_dias_sem_sinal_vira_parada_e_reaparecer_volta_a_quente_no_mesmo_dia():
    e = ent(ultimo_ranking_em=HOJE - timedelta(days=k.ESFRIAR_DIAS),
            ultima_foto_em=HOJE - timedelta(days=7))
    s = calcular(e, HOJE)
    assert s.calor == Calor.parada and s.proxima_coleta is None
    assert s.coletar_avaliacoes is False and s.coletar_videos is False
    # SC-005: reaparece no ranking hoje → quente, próxima coleta hoje.
    s = calcular(ent(ultimo_ranking_em=HOJE, ultima_foto_em=HOJE - timedelta(days=7)), HOJE)
    assert s.calor == Calor.quente and s.proxima_coleta == HOJE
    # Ou ganha um interesse ativo (ex.: alguém acompanhou por link).
    s = calcular(ent(ultimo_ranking_em=HOJE - timedelta(days=40), ultimo_interesse_em=HOJE,
                     outro_interesse_ativo=True), HOJE)
    assert s.calor == Calor.quente
    # Um interesse encerrado hoje conta como sinal (fica morna, não parada), mas não segura quente.
    s = calcular(ent(ultimo_ranking_em=HOJE - timedelta(days=40),
                     ultimo_interesse_em=HOJE - timedelta(days=10)), HOJE)
    assert s.calor == Calor.morna


def test_segundo_turno_e_dia_seguinte():
    # 2 por dia e só 1 foto hoje → de novo hoje (o turno da noite).
    s = calcular(ent(manual_ativo=True, ultima_foto_em=HOJE, fotos_hoje=1), HOJE)
    assert s.proxima_coleta == HOJE
    s = calcular(ent(manual_ativo=True, ultima_foto_em=HOJE, fotos_hoje=2), HOJE)
    assert s.proxima_coleta == HOJE + timedelta(days=1)
    # 1 por dia e já tem foto hoje → amanhã.
    s = calcular(ent(vitrine_ativa=True, ultima_foto_em=HOJE, fotos_hoje=1), HOJE)
    assert s.proxima_coleta == HOJE + timedelta(days=1)
    # Morna com foto hoje → daqui a uma semana.
    s = calcular(ent(ultimo_ranking_em=HOJE - timedelta(days=10), ultima_foto_em=HOJE, fotos_hoje=1),
                 HOJE)
    assert s.calor == Calor.morna and s.proxima_coleta == HOJE + timedelta(days=k.MORNA_CADA_DIAS)


def test_avaliacoes_e_videos_so_em_quente():
    s = calcular(ent(manual_ativo=True), HOJE)
    assert s.coletar_avaliacoes is True and s.avaliacoes_paginas == k.AVALIACOES_PAGINAS_1A_VISITA
    assert s.coletar_videos is True
    s = calcular(ent(manual_ativo=True, ultimas_avaliacoes_em=HOJE - timedelta(days=5),
                     ultimos_videos_em=HOJE - timedelta(days=6)), HOJE)
    assert s.coletar_avaliacoes is False and s.coletar_videos is False
    s = calcular(ent(manual_ativo=True,
                     ultimas_avaliacoes_em=HOJE - timedelta(days=k.AVALIACOES_CADA_DIAS),
                     ultimos_videos_em=HOJE - timedelta(days=k.VIDEOS_CADA_DIAS)), HOJE)
    assert s.coletar_avaliacoes is True and s.avaliacoes_paginas == 1 and s.coletar_videos is True
    s = calcular(ent(ultimo_ranking_em=HOJE - timedelta(days=10)), HOJE)
    assert s.calor == Calor.morna and s.coletar_avaliacoes is False and s.coletar_videos is False
