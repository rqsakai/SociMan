"""Modelos Pydantic do analytics (spec 019, contracts/http-api.md; data-model "Entidades
calculadas"). JSON em camelCase, como na 016.

Regras de resposta: listas sempre presentes (vazias sem dado); percentuais como fração (0–1);
monetários em USD com 4 casas (número no JSON); datas e horas com o deslocamento de
America/Sao_Paulo. Nenhum identificador de série anônima, token ou link de upload sai daqui: a
conta anônima aparece só pelo `rotulo` ("Conta anônima N"), com `contaId` nulo.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, PlainSerializer

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.models import CanalDireito
from sociman_api.canais.schemas import AprendizadoAfinidade, PerfilRef
from sociman_api.metricas.schemas import VideosList
from sociman_api.perfis.models import Platform

QUATRO_CASAS = Decimal("0.0001")

# Decimal no servidor, número com 4 casas no JSON (e `number` no contrato).
Usd = Annotated[Decimal, PlainSerializer(lambda d: float(d.quantize(QUATRO_CASAS)),
                                         return_type=float, when_used="json")]

MedidaNome = Literal["h1", "h24", "d7"]
ChaveIndicador = Literal["views", "likes", "engajamento", "seguidores", "posts", "mediana_post"]
RegraInsight = Literal["horario", "dia", "duracao", "canal", "hashtag", "destaque"]
ChaveEixo = Literal["views_por_post", "engajamento", "frequencia", "crescimento",
                    "velocidade_1h", "acima_mediana"]
ChaveEtapa = Literal["enviados", "cortes", "aprovados", "publicados", "acima_patamar"]
TipoAlerta = Literal["estagnado", "destaque", "sem_coleta", "vinculo_a_confirmar"]
Severidade = Literal["atencao", "info", "positivo"]
TipoAlvo = Literal["video", "serie", "destino"]
FonteDia = Literal["coletado", "studio"]  # spec 020
FonteCalendario = Literal["coletado", "studio", "misto"]


# ---- comuns ----

class Minimos(CamelModel):
    grupo: int
    correlacao: int
    contas_radar: int


class ContextoStudio(CamelModel):
    """Spec 020: dias distintos do período em que alguma série usou o histórico do Studio."""

    dias: int
    series: int


class Contexto(CamelModel):
    de: date
    ate: date
    anterior_de: date
    anterior_ate: date
    medida: MedidaNome
    fuso: str
    posts_no_periodo: int
    aguardando: int  # idade < marco da medida: fora das comparações
    fora_do_sociman: int  # sem vínculo com um destino
    minimos: Minimos
    studio: ContextoStudio  # spec 020


class Amostra(CamelModel):
    n: int
    minimo: int
    suficiente: bool
    faltam: int


class Medida(CamelModel):
    """A medida do post (marco 1 h/24 h/7 d de views, research R3)."""

    valor: float | None
    estimado: bool  # marco interpolado com folga > 25%
    aguardando: bool  # o vídeo ainda não chegou à idade do marco


class Indicador(CamelModel):
    chave: ChaveIndicador
    valor: float | None
    anterior: float | None
    variacao_pct: float | None  # fração; null = "sem base de comparação"
    n: int
    dias_studio: int  # spec 020: dias do período vindos do Studio (views, curtidas,
    # engajamento e seguidores; 0 nos demais)


class Insight(CamelModel):
    regra: RegraInsight
    frase: str
    valor: float | None
    grupo: str | None  # ex.: "18h–21h"
    amostra: Amostra
    pendente: bool  # true: a frase diz o que falta


class PostResumo(CamelModel):
    """Um post analisado, resumido para listas (principais, alertas)."""

    video_id: UUID
    conta_id: UUID | None  # null se anônima
    rotulo_conta: str
    publicado_em: datetime
    titulo_curto: str
    link: str | None
    thumb_url: str | None
    medida: Medida
    views_atual: int | None
    views_periodo: int  # views ganhas no período
    engajamento: float | None


# ---- Ordem das contas (cor fixa por conta, FR-006) ----

class ContaOrdem(CamelModel):
    conta_id: UUID
    rotulo: str  # "@handle"
    rede: Platform
    perfil_id: UUID


class OrdemContasOut(CamelModel):
    contas: list[ContaOrdem]  # por created_at, id; inclui arquivadas e as de perfis arquivados


# ---- Visão geral (US1) ----

class ViewsConta(CamelModel):
    conta_id: UUID | None
    rotulo: str
    views: int
    # Spec 020: a fonte do dia, as views da outra fonte (comparação) e as visitas ao perfil
    # (só o Studio informa).
    fonte: FonteDia
    comparacao: int | None
    visitas_perfil: int | None


class DiaSerie(CamelModel):
    dia: date
    por_conta: list[ViewsConta]


class VisaoGeralOut(CamelModel):
    contexto: Contexto
    indicadores: list[Indicador]
    serie_diaria: list[DiaSerie]
    principais: list[PostResumo]
    insights: list[Insight]
    ranking: VideosList  # o ranking da 016, 1ª página


# ---- Quando postar (US2) ----

class CelulaMapa(CamelModel):
    dia: int  # 0 = segunda
    hora: int  # 0–23, America/Sao_Paulo
    valor: float | None
    n: int
    amostra_pequena: bool


class Mapa(CamelModel):
    celulas: list[CelulaMapa]


class MapaAudiencia(Mapa):
    sem_hora: int  # views de intervalos > 3 h, sem hora atribuída (R4)


class DiaCalendario(CamelModel):
    dia: date
    posts: int
    views: int
    fonte: FonteCalendario  # spec 020: `misto` com contas de fontes diferentes
    contas_studio: int


class QuandoPostarOut(CamelModel):
    contexto: Contexto
    por_publicacao: Mapa
    audiencia: MapaAudiencia
    calendario: list[DiaCalendario]
    # spec 022: o 3º mapa (aditivo; definido no fim do arquivo)
    atividade_seguidores: "PublicoAtividadeSeguidores" = Field(
        default_factory=lambda: PublicoAtividadeSeguidores())


# ---- O que funciona (US3) ----

class PontoDispersao(CamelModel):
    video_id: UUID
    x: float
    y: float
    estimado: bool
    titulo_curto: str
    conta_id: UUID | None  # null se anônima (a SPA pinta pela cor fixa da conta)
    conta: str | None


class Correlacao(CamelModel):
    rho: float | None
    leitura: str | None
    amostra: Amostra


class Dispersao(CamelModel):
    pontos: list[PontoDispersao]
    correlacao: Correlacao


class Dispersoes(CamelModel):
    duracao: Dispersao
    gancho: Dispersao
    score: Dispersao


class LinhaRanking(CamelModel):
    chave: str
    rotulo: str
    n: int
    mediana: float | None
    lift: float | None  # null = sem base
    amostra: Amostra
    direito: CanalDireito | None = None  # só nos canais-fonte
    engajamento: float | None = None  # mediana; nos modos e padrões (FR-022)


class OQueFuncionaOut(CamelModel):
    contexto: Contexto
    dispersoes: Dispersoes
    canais: list[LinhaRanking]
    hashtags: list[LinhaRanking]
    modos: list[LinhaRanking]
    padroes: list[LinhaRanking]
    excluidos_sem_vinculo: int


# ---- Curvas (US4) ----

class PontoCurva(CamelModel):
    idade_h: float
    views: int


class Curva(CamelModel):
    video_id: UUID
    titulo_curto: str
    conta_id: UUID | None
    conta: str
    pontos: list[PontoCurva]
    meia_vida_h: float | None  # null = "ainda não calculável"


class DistribuicaoConta(CamelModel):
    conta_id: UUID | None
    rotulo: str
    min: float | None
    q1: float | None
    mediana: float | None
    q3: float | None
    max: float | None
    amostra: Amostra


class CurvasOut(CamelModel):
    contexto: Contexto
    curvas: list[Curva]
    distribuicao: list[DistribuicaoConta]


# ---- Contas (US5) ----

class ContaLinha(CamelModel):
    conta_id: UUID
    rotulo: str
    perfil: PerfilRef
    rede: Platform
    indicadores: list[Indicador]


class PerfilLinha(CamelModel):
    perfil: PerfilRef
    indicadores: list[Indicador]


class EixoRadar(CamelModel):
    chave: ChaveEixo
    valor: float | None
    media: float | None
    indice: float | None  # 0–200 (valor ÷ média × 100)
    acima: bool  # cortado em 200


class RadarConta(CamelModel):
    conta_id: UUID
    rotulo: str
    eixos: list[EixoRadar]


class ContasOut(CamelModel):
    contexto: Contexto
    contas: list[ContaLinha]
    perfis: list[PerfilLinha]
    radar: list[RadarConta] | None
    radar_motivo: str | None


# ---- Funil (US6) ----

class Perda(CamelModel):
    motivo: str
    n: int


class EtapaFunil(CamelModel):
    chave: ChaveEtapa
    n: int
    conversao_pct: float | None  # fração da etapa anterior
    perdas: list[Perda]
    tempo_mediano_h: float | None


class FunilOut(CamelModel):
    contexto: Contexto
    etapas: list[EtapaFunil]
    patamar: int
    custo_ia_usd: Usd | None  # null para membro (o servidor não calcula)
    custo_por_mil_views_usd: Usd | None  # idem


# ---- Mercado (US7) ----

class CanalOportunidade(CamelModel):
    id: UUID
    titulo: str
    direito: CanalDireito


class Oportunidade(CamelModel):
    video_fonte_id: UUID
    titulo_curto: str
    canal: CanalOportunidade
    idade_h: float
    views: int | None
    velocidade: float | None  # views/h
    link_gerar_cortes: str
    afinidade: AprendizadoAfinidade | None = None  # spec 023: só com perfil no filtro


class CanalMercado(CamelModel):
    canal_id: UUID
    titulo: str
    direito: CanalDireito
    videos: int
    mediana_velocidade: float | None


class MercadoOut(CamelModel):
    contexto: Contexto
    publicacao: Mapa
    velocidade_por_horario: Mapa
    oportunidades: list[Oportunidade]
    canais: list[CanalMercado]
    ocultos_por_tema: int = 0  # spec 023: oportunidades de tema cortado escondidas


# ---- Alertas (US8) ----

class AlvoAlerta(CamelModel):
    tipo: TipoAlvo
    id: UUID | None  # null quando o alvo é de uma série anônima
    rotulo: str


class Alerta(CamelModel):
    tipo: TipoAlerta
    severidade: Severidade
    alvo: AlvoAlerta
    motivo: str
    numeros: dict[str, float | None]  # ex.: idadeH, views, medianaReferencia
    link: str | None


class ContagemAlertas(CamelModel):
    atencao: int
    info: int
    positivo: int


class AlertasOut(CamelModel):
    contexto: Contexto
    alertas: list[Alerta]
    contagem: ContagemAlertas


# ---- Público (spec 022, contracts/http-api.md): dados importados do TikTok Studio ----

MotivoPublico = Literal["sem_importacao", "veio_vazia", "sem_dado_no_periodo"]
MarcaPublico = Literal["novo", "saiu"]


class PublicoConta(CamelModel):
    """A conta de uma entrada do público, na ordem de `ordem-contas` (019). Numa série anônima,
    `serieId` e `contaId` vêm nulos e o `rotulo` é "Conta anônima N"."""

    serie_id: UUID | None
    conta_id: UUID | None
    rotulo: str
    ordem: int | None  # a posição em `ordem-contas` (a cor fixa); null se anônima


class PublicoItem(CamelModel):
    rotulo: str
    rotulo_exibicao: str
    pct: float | None  # 0–100 (é a % da TikTok, não fração); null = sem dado ou "saiu"
    pct_comparacao: float | None
    dif_pp: float | None  # pontos percentuais; null sem os dois valores
    marca: MarcaPublico | None


class PublicoDistribuicao(CamelModel):
    data_foto: date
    anterior_ao_periodo: bool  # a foto é de antes do início do período (FR-016, resposta A)
    importacao_id: UUID
    data_foto_comparacao: date | None
    seguidores_na_data: int | None  # o total de seguidores da 020 no dia anterior à foto
    itens: list[PublicoItem]
    outros_pct: float | None  # só nos territórios: 100 − Σ


class PublicoAtividade(CamelModel):
    celulas: list[CelulaMapa]  # sempre 7 × 24; `valor` = média dos dias com dado, `n` = dias
    dias_com_dado: int
    ultimo_dia_com_dado: date | None  # em qualquer período (o atalho "ver os últimos dias")


class PublicoDiaEspectadores(CamelModel):
    dia: date
    total: int | None
    novos: int | None
    recorrentes: int | None


class PublicoIndicador(CamelModel):
    valor: float | None
    anterior: float | None
    variacao_pct: float | None  # fração; null = sem base de comparação
    n: int  # dias com valor


class PublicoEspectadores(CamelModel):
    serie: list[PublicoDiaEspectadores]
    novos: PublicoIndicador  # soma
    media_total: PublicoIndicador
    media_recorrentes: PublicoIndicador
    dias_sem_dado: int


class PublicoMotivos(CamelModel):
    genero: MotivoPublico | None
    territorios: MotivoPublico | None
    atividade: MotivoPublico | None
    espectadores: MotivoPublico | None


class PublicoContaOut(CamelModel):
    conta: PublicoConta
    genero: PublicoDistribuicao | None
    territorios: PublicoDistribuicao | None
    atividade: PublicoAtividade | None
    espectadores: PublicoEspectadores | None
    motivos: PublicoMotivos


class PublicoOut(CamelModel):
    contexto: Contexto
    contas: list[PublicoContaOut]


class PublicoAtividadeConta(CamelModel):
    conta: PublicoConta
    atividade: PublicoAtividade | None
    motivo: MotivoPublico | None


class PublicoAtividadeSeguidores(CamelModel):
    """O 3º mapa de Quando postar ("Seguidores on-line", spec 022): o mesmo cálculo da aba
    Público, por conta (nunca somado entre contas)."""

    contas: list[PublicoAtividadeConta] = Field(default_factory=list)


QuandoPostarOut.model_rebuild()
