"""T024 (FR-044..FR-049, SC-001): cada fórmula com séries sintéticas, com os números calculados à
mão aqui no teste."""

from datetime import date, timedelta

from sociman_api.mercado import calculo as c
from sociman_api.mercado import constantes as k

HOJE = date(2026, 10, 9)


def _serie(dias: int, inicio: int = 1000, passo: int = 20, preco: int = 4990,
           preco_max: int | None = None, ate: date = HOJE, affiliate: bool = True,
           comissao: int = 1200, criadores: int = 37, vendas_7d: int | None = None) -> list[c.Foto]:
    fotos = []
    for n in range(dias):
        d = ate - timedelta(days=dias - 1 - n)
        fotos.append(c.Foto(d, "manha", "pagina_publica", vendidos=inicio + n * passo,
                            vendidos_min=inicio + n * passo, vendidos_max=inicio + n * passo,
                            vendidos_exato=True, preco_min_centavos=preco,
                            preco_max_centavos=preco_max or preco))
        if affiliate:
            fotos.append(c.Foto(d, "manha", "affiliate", comissao_bp=comissao,
                                n_criadores=criadores, vendas_7d=vendas_7d,
                                preco_min_centavos=preco))
    return fotos


def test_estado_coletando_amostra_pequena_ok():
    assert c.estado(_serie(1), HOJE) == "coletando"
    assert c.estado(_serie(5), HOJE) == "amostra_pequena"
    assert c.estado(_serie(7), HOJE) == "ok"
    assert c.estado([], HOJE) == "coletando"


def test_vendas_periodo_e_a_diferenca_das_ultimas_fotos():
    fotos = _serie(10)  # 1000, 1020, …, 1180 (hoje)
    n = c.vendas_periodo(fotos, HOJE - timedelta(days=6), HOJE)  # 7 dias
    # v(ate) = 1180; v(de − 1) = foto de hoje − 7 = 1180 − 7×20 = 1040 → 140
    assert n.valor == 140 and n.estimado is True and "fonte_pagina_publica" in n.motivos
    # Sem foto antes do período: a base é a 1ª do período (interpolado).
    n = c.vendas_periodo(fotos, HOJE - timedelta(days=20), HOJE)
    assert n.valor == 180 and "interpolado" in n.motivos
    # Uma foto só → coletando.
    assert c.vendas_periodo(_serie(1), HOJE - timedelta(days=6), HOJE).valor is None


def test_delta_negativo_vira_zero_inconsistente():
    fotos = [c.Foto(HOJE - timedelta(days=1), "manha", "pagina_publica", vendidos=500,
                    vendidos_exato=True, preco_min_centavos=100),
             c.Foto(HOJE, "manha", "pagina_publica", vendidos=450, vendidos_exato=True,
                    preco_min_centavos=100)]
    n = c.vendas_periodo(fotos, HOJE, HOJE)
    assert n.valor == 0 and "inconsistente" in n.motivos
    vd = c.vendas_dia(fotos, HOJE)
    assert vd.valor == 0 and "inconsistente" in vd.motivos


def test_vendas_dia_exige_duas_fotos_com_um_dia_de_distancia():
    assert c.vendas_dia(_serie(1), HOJE).valor is None
    duas_no_mesmo_dia = [c.Foto(HOJE, "manha", "pagina_publica", vendidos=10, vendidos_exato=True),
                         c.Foto(HOJE, "noite", "pagina_publica", vendidos=12, vendidos_exato=True)]
    assert c.vendas_dia(duas_no_mesmo_dia, HOJE).valor is None
    vd = c.vendas_dia(_serie(10), HOJE)  # 7 dias: de 1040 a 1180 em 7 dias de distância → 20/dia
    assert vd.valor == 20 and vd.amostra_pequena is False
    vd = c.vendas_dia(_serie(5), HOJE)  # 4 dias de distância → 20/dia, amostra pequena
    assert vd.valor == 20 and vd.amostra_pequena is True


def test_affiliate_com_vendas_7d_tem_precedencia():
    fotos = _serie(10, vendas_7d=410)
    n = c.vendas_periodo(fotos, HOJE - timedelta(days=6), HOJE)
    assert n.valor == 410 and n.motivos == ["fonte_affiliate"]
    assert c.vendas_dia(fotos, HOJE).valor == 410 / 7
    # Janela que não coincide (10 dias): volta para a página pública.
    n = c.vendas_periodo(fotos, HOJE - timedelta(days=9), HOJE)
    assert "fonte_pagina_publica" in n.motivos


def test_faixa_1_2_mil_carrega_incerteza():
    fotos = [c.Foto(HOJE - timedelta(days=7), "manha", "pagina_publica", vendidos=1000,
                    vendidos_min=1000, vendidos_max=1000, vendidos_exato=True, preco_min_centavos=100),
             c.Foto(HOJE, "manha", "pagina_publica", vendidos=1200, vendidos_min=1150,
                    vendidos_max=1249, vendidos_exato=False, preco_min_centavos=100)]
    n = c.vendas_periodo(fotos, HOJE - timedelta(days=6), HOJE)
    assert n.valor == 200 and "incerteza" in n.motivos and (n.min, n.max) == (150, 249)
    vt = c.vendas_totais(fotos, HOJE)
    assert vt.valor == 1200 and (vt.min, vt.max) == (1150, 1249)


def test_gmv_periodo_e_total():
    fotos = _serie(10, preco=100)  # Δ = 20 por dia × R$ 1,00 → 2000 centavos por par
    n = c.gmv_periodo(fotos, HOJE - timedelta(days=6), HOJE)  # 7 pares (de − 1 … ate)
    assert n.valor == 7 * 20 * 100 and n.min is None
    com_faixa = _serie(10, preco=100, preco_max=200)
    n = c.gmv_periodo(com_faixa, HOJE - timedelta(days=6), HOJE)
    assert (n.min, n.max) == (14000, 28000) and "incerteza" in n.motivos
    gt = c.gmv_total(fotos, HOJE)
    assert gt.valor == 1180 * 100 and "grosseiro" in gt.motivos
    assert c.gmv_total(_serie(1), HOJE).valor == 1000 * 4990


def test_crescimento_7d_vs_7d_anteriores():
    # Primeiros 7 dias a +10/dia, últimos 7 a +20/dia.
    fotos = []
    v = 1000
    for n in range(15):
        d = HOJE - timedelta(days=14 - n)
        fotos.append(c.Foto(d, "manha", "pagina_publica", vendidos=v, vendidos_exato=True,
                            preco_min_centavos=100))
        v += 10 if n < 7 else 20
    cr = c.crescimento(fotos, HOJE)
    assert cr.valor == 1.0  # 20/10 − 1
    # Base menor que 3 vendas/dia → nulo.
    lenta = _serie(15, passo=1)
    assert c.crescimento(lenta, HOJE).valor is None
    assert "base_pequena" in c.crescimento(lenta, HOJE).motivos
    assert c.crescimento(_serie(5), HOJE).valor is None


def test_comissao_retorno_e_saturacao():
    assert c.comissao_por_venda(4990, 1200).valor == 4990 * 0.12
    assert c.comissao_por_venda(4990, None).motivos == ["sem_dado_afiliado"]
    vd = c.vendas_dia(_serie(10), HOJE)  # 20/dia
    cv = c.comissao_por_venda(4990, 1200)
    rd = c.retorno_dia(vd, cv)
    assert rd.valor == 20 * 598.8
    ra = c.retorno_por_afiliado(rd, 37)
    assert ra.valor == rd.valor / (37 + k.K_AFILIADOS)
    assert c.retorno_por_afiliado(rd, None).motivos == ["sem_dado_afiliado"]
    assert c.saturacao(37, vd).valor == 37 / 20
    assert c.saturacao(37, c.Numero(0)).motivos == ["sem_vendas"]


def test_novo_em_alta():
    vd = c.Numero(12)
    sobe = c.Numero(0.6)
    assert c.novo_em_alta(HOJE - timedelta(days=10), HOJE, vd, sobe, False, None, "ok")
    assert not c.novo_em_alta(HOJE - timedelta(days=40), HOJE, vd, sobe, False, None, "ok")
    assert not c.novo_em_alta(HOJE - timedelta(days=10), HOJE, c.Numero(5), sobe, False, None, "ok")
    assert not c.novo_em_alta(HOJE - timedelta(days=10), HOJE, vd, sobe, False, None, "coletando")
    parado = c.Numero(0.1)
    assert not c.novo_em_alta(HOJE - timedelta(days=10), HOJE, vd, parado, False, None, "ok")
    assert c.novo_em_alta(HOJE - timedelta(days=10), HOJE, vd, parado, True, None, "ok")
    assert c.novo_em_alta(HOJE - timedelta(days=10), HOJE, vd, parado, False, 12, "ok")


def test_alto_retorno_com_quartis_e_sem_amostra():
    ra = c.Numero(5000)
    comp = c.Comparaveis(p25_criadores=18, p75_retorno=4210, mediana_retorno_global=1000, n=12)
    assert c.alto_retorno_poucos_afiliados(1200, 1, 10, ra, comp) == (True, True)
    assert c.alto_retorno_poucos_afiliados(1200, 1, 30, ra, comp) == (False, True)  # > P25
    assert c.alto_retorno_poucos_afiliados(1200, 1, 10, c.Numero(100), comp) == (False, True)
    assert c.alto_retorno_poucos_afiliados(400, 1, 10, ra, comp) == (False, True)  # comissão < 5%
    assert c.alto_retorno_poucos_afiliados(1200, 5, 10, ra, comp) == (False, True)  # foto velha
    # 9 produtos: sem quartis → 50 criadores e a mediana global.
    pouca = c.Comparaveis(p25_criadores=18, p75_retorno=4210, mediana_retorno_global=1000, n=9)
    assert c.alto_retorno_poucos_afiliados(1200, 1, 45, ra, pouca) == (True, True)
    assert c.alto_retorno_poucos_afiliados(1200, 1, 60, ra, pouca) == (False, False)
    assert c.alto_retorno_poucos_afiliados(1200, 1, 45, c.Numero(500), pouca) == (False, True)
    assert c.alto_retorno_poucos_afiliados(1200, 1, 45, ra, None) == (True, True)


def test_percentil_e_indicadores():
    assert c.percentil([1, 2, 3, 4], 50) == 2.5
    assert c.percentil([10], 75) == 10
    assert c.percentil([], 50) is None
    loja = c.indicadores_loja([c.Numero(300), c.Numero(100), c.Numero(None)],
                              [HOJE, HOJE - timedelta(days=40)], HOJE, [1200, 800])
    assert loja.gmv_estimado_centavos.valor == 400 and loja.concentracao_top1.valor == 0.75
    assert loja.lancamentos_30d == 1 and loja.comissao_media_bp.valor == 1000
    cat = c.indicadores_categoria([1000] * 12, [4990] * 12, 2, True, [10] * 12, 20)
    assert cat is not None and cat.espaco_em_branco is True and cat.n_novos_em_alta == 2
    assert c.indicadores_categoria([1000] * 9, [4990] * 9, 0, False, [], None) is None


def test_variacao_e_resumo_de_ranking():
    assert c.variacao_posicao(1, 3) == ("subiu", 2)
    assert c.variacao_posicao(5, 2) == ("caiu", -3)
    assert c.variacao_posicao(2, 2) == ("igual", 0)
    assert c.variacao_posicao(4, None) == ("novo", None)
    assert c.variacao_posicao(None, 4) == ("saiu", None)
    pos = {HOJE - timedelta(days=8): 15, HOJE - timedelta(days=7): 12, HOJE - timedelta(days=1): 8,
           HOJE: 3}
    r = c.resumo_ranking(pos, HOJE)
    assert (r.posicao_atual, r.melhor_posicao, r.dias_no_topo) == (3, 3, 2)
    assert r.variacao_7d == 12 - 3 and r.entrou_em == HOJE - timedelta(days=8) and r.saiu_em is None
    r = c.resumo_ranking({HOJE - timedelta(days=2): 4}, HOJE)
    assert r.posicao_atual is None and r.saiu_em == HOJE - timedelta(days=1)
