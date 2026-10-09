"""Todas as constantes nomeadas da 026 num só lugar (FR-050; data-model, "Regras derivadas").

Uma por linha, com o requisito que a justifica. Mudar um limiar é mudar uma linha aqui e o teste
que a cobre; nenhum número destes aparece solto no resto do pacote.
"""

# ---- cálculo na leitura (mercado/calculo.py) ----
MIN_FOTOS_VENDAS = 2  # FR-045: vendas/dia exige duas fotos…
MIN_DIAS_ENTRE_FOTOS = 1  # …com ao menos um dia de distância
AMOSTRA_PEQUENA_DIAS = 7  # US1: menos de 7 dias de fotos → "amostra pequena"
MIN_VENDAS_DIA_BASE = 3  # FR-046: crescimento com base menor que isto é nulo
JANELA_CRESCIMENTO_DIAS = 7  # FR-046: 7 dias contra os 7 anteriores
K_AFILIADOS = 5  # FR-047: retorno por afiliado = retorno/dia ÷ (criadores + K)
COMISSAO_MIN_BP = 500  # FR-047: 5% em pontos-base
AC_FOTO_MAX_DIAS = 3  # FR-047: foto do Affiliate Center com até 3 dias
MIN_PRODUTOS_CATEGORIA = 10  # FR-047: comparáveis para os quartis por categoria
POUCOS_AFILIADOS = 50  # FR-047: sem amostra, criadores ≤ 50 e retorno ≥ mediana global
P_CRIADORES = 25  # FR-047: criadores no quartil inferior (P25)
P_RETORNO = 75  # FR-047: retorno no quartil superior (P75)
NOVO_DIAS = 30  # FR-048 e FR-039: "novo" = visto pela primeira vez há até 30 dias
NOVO_VENDAS_DIA_MIN = 10  # FR-048
NOVO_CRESCIMENTO_MIN = 0.5  # FR-048: crescimento de ao menos 50%
ALTA_POSICOES = 10  # FR-048: subiu 10 posições em 7 dias
RANKING_DIAS_NO_TOPO = 10  # FR-049: "dias no topo" conta posições ≤ 10
LANCAMENTOS_DIAS = 30  # FR-049: ritmo de lançamentos da loja

# ---- cadência e interesse (mercado/cadencia.py, mercado/interesses.py) ----
QUENTE_DIAS = 1  # FR-040: quente = 1 foto por dia
FOTOS_POR_DIA_MAX = 2  # FR-040: 2 por dia (manhã e noite) para novo em alta e manuais
SAI_DO_RANKING_DIAS = 7  # FR-040: fora dos rankings há 7 dias → semanal (`morna`)
MORNA_CADA_DIAS = 7  # FR-040: 1 foto por semana
ESFRIAR_DIAS = 30  # FR-040: 30 dias sem ranking e sem interesse → parada
RANKING_ACOMPANHAR_TOP = 30  # FR-039: os primeiros 30 de cada ranking viram interesses
MAX_RELACIONADOS_DIA = 10  # FR-039: interesses automáticos por perfil por dia
CATEGORIAS_MAX = 5  # FR-037: categorias do nicho por perfil
AVALIACOES_CADA_DIAS = 30  # FR-040a
AVALIACOES_PAGINAS_1A_VISITA = 2  # FR-040a
VIDEOS_CADA_DIAS = 7  # FR-040a
CATEGORIAS_CADA_DIAS = 7  # FR-008: a taxonomia é revisitada toda semana

# ---- operação da coleta (coleta/, mercado/fila.py, mercado/trilha.py) ----
TURNO_CORTE = "15:30"  # data-model: antes disto no fuso do mercado = `manha`, senão `noite`
FILA_LEASE_MIN = 30  # reserva de uma tarefa entregue ao coletor
FILA_TENTATIVAS_MAX = 3  # erros/reservas vencidas até `falhou`
CAPTCHA_ESFRIAR_MIN = 60  # FR-018
CAPTCHA_ESPERA_MAX_H = 2  # FR-018: sem "Continuar" em 2 h a rodada é encerrada
PARSES_VAZIOS_MAX = 5  # FR-017
RECUO_BLOQUEIO_H = 24  # FR-017
COLETA_SEM_BATIMENTO_MIN = 10  # FR-041: rodada sem batimento → interrompida
COLETA_PARADA_H = 48  # FR-041: ligada e sem resultado → aviso "coleta parada"
PAGINAS_DIA_PADRAO = 300  # FR-016
IMAGENS_DIA_PADRAO = 1500  # FR-016
IMAGENS_POR_PRODUTO_PADRAO = 9  # FR-016
IMAGENS_POR_PRODUTO_MAX = 20  # CHECK de `coleta_config`
ITENS_POR_COLETA_PADRAO = 40
ITENS_POR_LOTE_MAX = 50  # FR-032
LOTE_BYTES_MAX = 6 * 1024 * 1024  # FR-032: corpo do lote de itens
BRUTO_BYTES_MAX = 2 * 1024 * 1024  # descomprimido
IMAGEM_BYTES_MAX = 5 * 1024 * 1024  # FR-032
IMAGENS_POR_CHAMADA_MAX = 10
JANELA_INICIO_PADRAO = 8  # FR-016: 08h–23h no fuso do mercado
JANELA_FIM_PADRAO = 23
PAUSA_MIN_S_PADRAO = 5  # FR-016
PAUSA_MAX_S_PADRAO = 40
LIMITE_POR_MINUTO_PADRAO = 120  # portão do coletor (Redis)

# ---- leitura (mercado/filtros.py) ----
PERIODO_PADRAO_DIAS = 30  # FR-043
PERIODO_MAX_DIAS = 400  # FR-043
LIMITE_LISTA_MAX = 100
LIMITE_LISTA_PADRAO = 50
CARDS_COCKPIT = 10  # itens por card do resumo
