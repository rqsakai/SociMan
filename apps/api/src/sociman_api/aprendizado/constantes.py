"""Constantes do aprendizado (spec 023). Cada valor aparece na nota de leitura da tela; o ajuste
fino fica para depois de um ciclo real (Assumptions da spec)."""

import math
from datetime import timedelta

# ---- amostra (FR-022, R2) ----
MIN_GRUPO = 5  # posts distintos por grupo (o mesmo da 019)
MIN_DIAS = 2  # dias distintos por grupo
MIN_CONTA = 15  # posts medidos na conta para ela entrar nos efeitos

# ---- efeito (FR-020, R1) ----
K_ENCOLHIMENTO = 5  # pseudo-posts "típicos" misturados em cada grupo
MEIA_VIDA_DIAS = 30  # FR-014: peso 0,5 aos 30 dias
JANELA_DIAS = 180  # FR-014: janela máxima com peso
RECENTE_DIAS = 30  # FR-014: "em alta" / "em queda" comparam os últimos 30 dias com o resto

# ---- intervalo e confiança (FR-021, R2) ----
REAMOSTRAS = 400  # reamostragens com reposição, semente fixa
PERCENTIS = (0.10, 0.90)  # intervalo de 80%
FORTE_N = 10
LIMIAR_FORTE_REND = math.log(1.5)  # rendimento: |θ| ≥ ln 1,5
LIMIAR_FORTE_ENTREGA = 0.15  # entrega: ≥ 15 p.p.
LIMIAR_FRACA_REND = math.log(1.3)
LIMIAR_FRACA_ENTREGA = 0.08
CONFIANCAS = ("forte", "moderada", "fraca", "indicio", "amostra_pequena")

# ---- robustez (FR-023 a FR-027, R2 a R4) ----
CONCENTRACAO = 0.5  # FR-023: um post com mais da metade das views do grupo
MIN_SEPARAVEL = 3  # FR-024: posts do tema com e sem a hashtag
JACCARD_QUASE = 0.8  # R3: "quase sempre juntas" (sem fundir)
CONFUSAO = 0.8  # FR-026: 80% do grupo com o mesmo valor de outro fator
TRAVADA = 0.6  # FR-027: mais de 60% dos posts medidos da conta estagnados
FALSOS_ESPERADOS = 0.1  # R3: "espere ~10% de falsos achados fracos"

# ---- regras das recomendações (FR-035) ----
AMPLIAR_MIN = 1.5  # efeito encolhido ≥ 1,5×
CORTAR_MAX = 0.5  # ≤ 0,5×
CORTAR_MIN_N = 8
FIXAR_MIN = 1.3  # hashtag separável ≥ 1,3×
EVITAR_MAX = 0.7  # hashtag separável ≤ 0,7×
PADRAO_MIN = 1.5  # gancho, duração e horário (mesma régua do ampliar)
CONFIANCAS_RECOMENDAVEIS = ("forte", "moderada")

# ---- afinidade (FR-040, R9) ----
PESO_AFINIDADE = 20  # até ±20 pontos de 100
PESO_CONFIANCA = {"forte": 1.0, "moderada": 0.7, "fraca": 0.3, "indicio": 0.0,
                  "amostra_pequena": 0.0}
PESO_TEMA = 0.7
PESO_CANAL = 0.3
AMPLIAR_SOMA = 0.5  # `ampliar` aceito: max(a + 0,5, 0,5)
MOTIVO_MIN_PONTOS = 10  # o motivo cita o tema com |pontos| ≥ 10

# ---- classificação (FR-051, R5) ----
LIMITE_DIARIO = 50  # chamadas `aprendizado.classificacao` por perfil por dia local
IDADE_CLASSIFICAR = timedelta(hours=24)  # o marco padrão da medida
MAX_TEMAS = 30  # FR-001
TEMA_NOME_MAX = 40
TEMA_DESCRICAO_MAX = 200
PALAVRAS_MAX = 20
PALAVRA_MIN, PALAVRA_MAX = 2, 30
SECUNDARIOS_MAX = 2
JUSTIFICATIVA_MAX = 160
SUGESTAO_MAX = 40
TRANSCRICAO_MAX = 4000  # como `cortes.transcript`
TAXONOMIA_POSTS = 40  # R5: posts recentes na proposta de taxonomia
TAXONOMIA_TRANSCRICAO = 600
TAXONOMIA_MIN, TAXONOMIA_MAX = 3, 15
ESTILOS_GANCHO = ("pergunta", "revelacao", "numero_lista", "polemica", "humor", "voce_sabia",
                  "ordem_direta", "outro")

# ---- análise da IA (FR-030 a FR-033, R5) ----
ANALISE_N_PADRAO = 8
ANALISE_N_MAX = 15
HIPOTESES_MAX = 6
HIPOTESE_MAX = 240
CONTRASTE_MAX = 160
QUADROS_POR_VIDEO = 4
QUADRO_LARGURA = 512
QUADRO_QUALIDADE = 80
PROCESSANDO_MAX = timedelta(minutes=15)  # depois disso, volta a `pendente` uma vez
LEGENDA_ANALISE_MAX = 600

# ---- faixas dos fatores (FR-013) ----
FAIXAS_GANCHO = ((40, "até 40 caracteres"), (80, "41–80 caracteres"), (None, "mais de 80"))
FAIXAS_DURACAO = ((30, "até 30 s"), (60, "31–60 s"), (None, "mais de 60 s"))  # as da 019
HORAS_FAIXA = 3  # faixas de 3 h de publicação

# ---- bloco <desempenho> (FR-044, R8) ----
EXEMPLOS_MAX = 3
EXEMPLOS_DIAS = 90
EXEMPLO_LEGENDA_MAX = 300
EXEMPLO_GANCHO_MAX = 120

# ---- diagnóstico (FR-048, R10) ----
CONTA_NOVA_DIAS = 30
CONTA_NOVA_POSTS = 15
MUITOS_NO_DIA = 3
HORAS_AUDIENCIA = 6
AUDIENCIA_MIN_VIEWS = 500
CURTO_S = 10
HASHTAGS_DEMAIS = 8

# ---- preferências (data-model) ----
EVITAR_MAX_ITENS = 30
PADROES_MAX = 10
PADRAO_TEXTO_MAX = 120
MOTIVO_MAX = 300
NOTA_MAX = 300
