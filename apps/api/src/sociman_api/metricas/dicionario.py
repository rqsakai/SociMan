"""Dicionário do dataset de métricas (research R16): a fonte única dos arquivos, das colunas e da
ordem delas. A exportação escreve os cabeçalhos a partir daqui, e o teste compara o CSV com esta
constante.

Regra de evolução: coluna nova entra **no fim** do arquivo e sobe `DICIONARIO_VERSAO`. Nenhuma
coluna muda de nome nem de posição.
"""

from dataclasses import dataclass
from typing import Literal

DICIONARIO_VERSAO = 2  # 2: studio_dias (spec 020)

Origem = Literal["TikTok", "SociMan", "calculado"]


@dataclass(frozen=True)
class Coluna:
    arquivo: str  # sem extensão: fotos_videos, videos, fotos_conta, studio_dias
    coluna: str
    tipo: str  # texto, inteiro, decimal, booleano, data, data_hora, uuid
    unidade: str
    significado: str
    origem: Origem


def _c(arquivo: str, coluna: str, tipo: str, unidade: str, significado: str,
       origem: Origem) -> Coluna:
    return Coluna(arquivo, coluna, tipo, unidade, significado, origem)


_FV = "fotos_videos"
_V = "videos"
_FC = "fotos_conta"
_SD = "studio_dias"

COLUNAS: tuple[Coluna, ...] = (
    # ---- fotos_videos: uma linha por foto de vídeo ----
    _c(_FV, "video_ref", "uuid", "", "Identificador do vídeo no SociMan (nunca o id da rede)",
       "SociMan"),
    _c(_FV, "coletado_em", "data_hora", "ISO 8601 (America/Sao_Paulo)",
       "Momento exato da resposta da rede", "SociMan"),
    _c(_FV, "idade_h", "decimal", "horas", "Idade do vídeo na foto (coletado_em − publicado_em)",
       "calculado"),
    _c(_FV, "alvo_idade_h", "decimal", "horas", "Janela da agenda a que a foto pertence",
       "SociMan"),
    _c(_FV, "views", "inteiro", "contagem acumulada", "Visualizações (view_count)", "TikTok"),
    _c(_FV, "likes", "inteiro", "contagem acumulada", "Curtidas (like_count)", "TikTok"),
    _c(_FV, "comments", "inteiro", "contagem acumulada", "Comentários (comment_count)",
       "TikTok"),
    _c(_FV, "shares", "inteiro", "contagem acumulada", "Compartilhamentos (share_count)",
       "TikTok"),
    # ---- videos: uma linha por vídeo ----
    _c(_V, "video_ref", "uuid", "", "Identificador do vídeo no SociMan (nunca o id da rede)",
       "SociMan"),
    _c(_V, "serie", "texto", "", "Série da conta: o uuid da série viva ou \"Conta anônima N\"",
       "SociMan"),
    _c(_V, "rede", "texto", "", "Rede do vídeo (tiktok)", "SociMan"),
    _c(_V, "conta", "texto", "", "@ da conta (vazio se anônima)", "SociMan"),
    _c(_V, "perfil", "texto", "", "Perfil da agência dono da conta (vazio se anônima)",
       "SociMan"),
    _c(_V, "origem", "texto", "", "corte, video_proprio ou fora (sem vínculo com o SociMan)",
       "calculado"),
    _c(_V, "vinculo_metodo", "texto", "", "Como o vídeo foi ligado: envio, casamento, link ou "
       "escolha", "SociMan"),
    _c(_V, "publicado_em", "data_hora", "ISO 8601 (America/Sao_Paulo)",
       "Publicação na rede (create_time; truncado para a hora se anônimo)", "TikTok"),
    _c(_V, "hora_local", "inteiro", "hora (0–23)", "Hora da publicação em São Paulo",
       "calculado"),
    _c(_V, "dia_semana", "inteiro", "0 = segunda", "Dia da semana da publicação em São Paulo",
       "calculado"),
    _c(_V, "duracao_s", "inteiro", "segundos", "Duração do vídeo (duration)", "TikTok"),
    _c(_V, "legenda", "texto", "", "Legenda na rede (video_description; vazio se anônimo)",
       "TikTok"),
    _c(_V, "hashtags", "texto", "", "Hashtags da legenda na rede, separadas por espaço",
       "calculado"),
    _c(_V, "url", "texto", "", "Link do post (vazio se anônimo)", "TikTok"),
    _c(_V, "disponivel", "booleano", "", "O vídeo ainda aparece como público", "SociMan"),
    _c(_V, "conteudo_id", "uuid", "", "Conteúdo do SociMan ligado (vazio sem vínculo)",
       "SociMan"),
    _c(_V, "destino_id", "uuid", "", "Destino do SociMan ligado (vazio sem vínculo)", "SociMan"),
    _c(_V, "modo_envio", "texto", "", "lembrete, criar_rascunho ou publicar", "SociMan"),
    _c(_V, "canal_fonte", "texto", "", "Canal de origem do corte (vazio se anônimo)", "SociMan"),
    _c(_V, "canal_status_direito", "texto", "", "proprio, parceiro, programa_de_cortes ou "
       "sem_acordo", "SociMan"),
    _c(_V, "score", "inteiro", "0–100", "Nota do SociShorts para o corte", "SociMan"),
    _c(_V, "gancho", "texto", "", "Texto do gancho do corte (vazio se anônimo)", "SociMan"),
    _c(_V, "gancho_caracteres", "inteiro", "caracteres", "Tamanho do gancho", "calculado"),
    _c(_V, "hashtags_n", "inteiro", "contagem",
       "Número de hashtags (as do destino; sem vínculo, as da legenda na rede)",
       "calculado"),
    _c(_V, "intervalo_post_anterior_h", "decimal", "horas",
       "Horas desde o post anterior da mesma conta", "calculado"),
    _c(_V, "seguidores_na_publicacao", "inteiro", "contagem",
       "Seguidores da conta na última foto antes da publicação", "calculado"),
    _c(_V, "views_1h", "decimal", "contagem", "Visualizações com 1 h de idade (interpolado)",
       "calculado"),
    _c(_V, "views_1h_estimado", "booleano", "", "O marco de 1 h veio de fotos distantes",
       "calculado"),
    _c(_V, "views_24h", "decimal", "contagem", "Visualizações com 24 h de idade (interpolado)",
       "calculado"),
    _c(_V, "views_24h_estimado", "booleano", "", "O marco de 24 h veio de fotos distantes",
       "calculado"),
    _c(_V, "views_7d", "decimal", "contagem", "Visualizações com 7 dias de idade (interpolado)",
       "calculado"),
    _c(_V, "views_7d_estimado", "booleano", "", "O marco de 7 d veio de fotos distantes",
       "calculado"),
    _c(_V, "views_30d", "decimal", "contagem",
       "Visualizações com 30 dias de idade (interpolado)", "calculado"),
    _c(_V, "views_30d_estimado", "booleano", "", "O marco de 30 d veio de fotos distantes",
       "calculado"),
    _c(_V, "engajamento_7d", "decimal", "razão",
       "(likes + comments + shares) ÷ views com 7 dias de idade", "calculado"),
    _c(_V, "engajamento_7d_estimado", "booleano", "", "Algum marco de 7 d veio de fotos "
       "distantes", "calculado"),
    # ---- fotos_conta: uma linha por foto da conta ----
    _c(_FC, "serie", "texto", "", "Série da conta: o uuid da série viva ou \"Conta anônima N\"",
       "SociMan"),
    _c(_FC, "conta", "texto", "", "@ da conta (vazio se anônima)", "SociMan"),
    _c(_FC, "coletado_em", "data_hora", "ISO 8601 (America/Sao_Paulo)",
       "Momento exato da resposta da rede", "SociMan"),
    _c(_FC, "janela", "data_hora", "ISO 8601 (America/Sao_Paulo)",
       "Janela da foto: a hora cheia ou 00:00 do dia", "SociMan"),
    _c(_FC, "seguidores", "inteiro", "contagem", "Seguidores (follower_count)", "TikTok"),
    _c(_FC, "seguindo", "inteiro", "contagem", "Contas seguidas (following_count)", "TikTok"),
    _c(_FC, "curtidas", "inteiro", "contagem acumulada", "Curtidas recebidas (likes_count)",
       "TikTok"),
    _c(_FC, "videos", "inteiro", "contagem", "Vídeos públicos (video_count)", "TikTok"),
    # ---- studio_dias: uma linha por dia importado do TikTok Studio (spec 020; só importações
    # ativas) ----
    _c(_SD, "serie_ref", "texto", "", "Série da conta: o uuid da série viva ou \"Conta anônima "
       "N\"", "SociMan"),
    _c(_SD, "conta", "texto", "", "@ da conta (ou \"Conta anônima N\")", "SociMan"),
    _c(_SD, "dia", "data", "AAAA-MM-DD", "Dia de calendário do arquivo do Studio (pode seguir o "
       "fuso da TikTok, não o de São Paulo)", "TikTok"),
    _c(_SD, "importacao_id", "uuid", "", "Importação do SociMan que trouxe o dia", "SociMan"),
    _c(_SD, "importada_em", "data_hora", "ISO 8601 (America/Sao_Paulo)",
       "Quando o dono confirmou a importação", "SociMan"),
    _c(_SD, "views", "inteiro", "contagem do dia", "Visualizações de vídeo no dia (Video Views)",
       "TikTok"),
    _c(_SD, "visitas_perfil", "inteiro", "contagem do dia",
       "Visitas ao perfil no dia (Profile Views)", "TikTok"),
    _c(_SD, "likes", "inteiro", "contagem do dia", "Curtidas no dia (Likes)", "TikTok"),
    _c(_SD, "comments", "inteiro", "contagem do dia", "Comentários no dia (Comments)", "TikTok"),
    _c(_SD, "shares", "inteiro", "contagem do dia", "Compartilhamentos no dia (Shares)",
       "TikTok"),
    _c(_SD, "seguidores", "inteiro", "contagem", "Seguidores no fim do dia (Followers)",
       "TikTok"),
    _c(_SD, "seguidores_dif", "inteiro", "contagem do dia",
       "Diferença de seguidores para o dia anterior (pode ser negativa)", "TikTok"),
    _c(_SD, "efetivo_visao_geral", "booleano", "",
       "Este valor da Visão geral vale no analytics (importação ativa mais antiga, num dia que a "
       "coleta não cobre inteiro); vazio sem a seção", "calculado"),
    _c(_SD, "efetivo_seguidores", "booleano", "",
       "Este valor de Seguidores vale no analytics (mesma regra); vazio sem a seção",
       "calculado"),
)

ARQUIVOS: tuple[str, ...] = (_FV, _V, _FC, _SD)

AVISOS = (
    "Só vídeos públicos: a rede não devolve privados nem rascunhos.",
    ("As contagens são acumuladas desde a publicação e gravadas como vieram (podem cair quando "
     "a rede corrige)."),
    "video_count conta só os vídeos públicos da conta.",
    "Datas em ISO 8601 com o fuso de São Paulo; CSV em UTF-8 com BOM, vírgula e ponto decimal.",
    "video_ref é o identificador do SociMan: o mesmo antes e depois da anonimização.",
    ("studio_dias traz os dias importados do TikTok Studio (valores do dia, não acumulados); "
     "as importações desfeitas ficam de fora."),
)


def colunas(arquivo: str) -> list[str]:
    """Os nomes das colunas do arquivo, na ordem do cabeçalho."""
    return [c.coluna for c in COLUNAS if c.arquivo == arquivo]
