"""Schemas do aprendizado (spec 023, contracts/http-api.md), em camelCase. O prefixo
`Aprendizado` evita colisão de nomes no OpenAPI."""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from sociman_api.analytics.schemas import PostResumo
from sociman_api.aprendizado import constantes as K
from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.schemas import (  # noqa: F401 — a afinidade mora lá (sem ciclo)
    AprendizadoAfinidade,
)
from sociman_api.perfis.schemas import UserRef

Medida = Literal["h1", "h24", "d7"]
Parte = Literal["entrega", "rendimento"]
Confianca = Literal["forte", "moderada", "fraca", "indicio", "amostra_pequena"]
EstiloGancho = Literal["pergunta", "revelacao", "numero_lista", "polemica", "humor", "voce_sabia",
                       "ordem_direta", "outro"]
TipoRecomendacao = Literal["tema_ampliar", "tema_cortar", "hashtag_fixar", "hashtag_evitar",
                           "padrao_gancho", "padrao_duracao", "padrao_horario"]
TipoPadrao = Literal["padrao_gancho", "padrao_duracao", "padrao_horario"]
VersionNumber = Annotated[int, Field(ge=0)]
Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                        max_length=K.TEMA_NOME_MAX)]
Descricao = Annotated[str, StringConstraints(strip_whitespace=True,
                                             max_length=K.TEMA_DESCRICAO_MAX)]
Palavra = Annotated[str, StringConstraints(strip_whitespace=True, max_length=K.PALAVRA_MAX)]


# ---- temas ----

class AprendizadoTemaIn(CamelModel):
    nome: Nome
    descricao: Descricao = ""
    palavras_chave: list[Palavra] = Field(default_factory=list, max_length=K.PALAVRAS_MAX)


class AprendizadoTemasLoteIn(CamelModel):
    temas: list[AprendizadoTemaIn] = Field(min_length=1, max_length=K.MAX_TEMAS)
    chamada_id: UUID | None = None


class AprendizadoTemaPatch(CamelModel):
    version: VersionNumber
    nome: Nome | None = None
    descricao: Descricao | None = None
    palavras_chave: list[Palavra] | None = Field(default=None, max_length=K.PALAVRAS_MAX)


class AprendizadoVersionIn(CamelModel):
    version: VersionNumber


class AprendizadoJuntarIn(CamelModel):
    version: VersionNumber
    destino_id: UUID


class AprendizadoTema(CamelModel):
    id: UUID
    perfil_id: UUID
    nome: str
    descricao: str
    palavras_chave: list[str]
    archived: bool
    juntado_em_id: UUID | None
    n_posts: int
    version: int


class AprendizadoTemasList(CamelModel):
    items: list[AprendizadoTema]
    taxonomia_versao: int


class AprendizadoTemasLoteOut(CamelModel):
    items: list[AprendizadoTema]


class AprendizadoJuntarOut(CamelModel):
    origem: AprendizadoTema
    destino: AprendizadoTema
    movidas: int


class AprendizadoProporIn(CamelModel):
    instrucao: Annotated[str, StringConstraints(max_length=1000)] = ""


class AprendizadoProporOut(CamelModel):
    chamada_id: UUID
    temas: list[AprendizadoTemaIn]
    custo_usd: float | None


# ---- classificações ----

class AprendizadoClassificacao(CamelModel):
    video_id: UUID
    post: PostResumo | None
    tema_id: UUID | None
    tema_nome: str | None
    secundarios: list[UUID]
    estilo_gancho: EstiloGancho | None
    justificativa: str | None
    sugestao_tema: str | None
    origem: Literal["ia", "dono"] | None  # null = ainda sem classificação (pendente)
    evidencia_parcial: bool
    reclassificar: bool
    taxonomia_versao: int | None
    chamada_id: UUID | None
    version: int  # 0 = ainda sem linha


class AprendizadoLimiteHoje(CamelModel):
    usadas: int
    limite: int


class AprendizadoClassificacoesList(CamelModel):
    items: list[AprendizadoClassificacao]
    next_cursor: str | None
    pendentes: int
    limite_hoje: AprendizadoLimiteHoje


class AprendizadoClassificacaoPut(CamelModel):
    version: VersionNumber
    tema_id: UUID | None
    secundarios: list[UUID] = Field(default_factory=list, max_length=K.SECUNDARIOS_MAX)
    estilo_gancho: EstiloGancho | None = None


class AprendizadoClassificarOut(CamelModel):
    pendentes: int
    restantes_hoje: int


# ---- análise estatística ----

class AprendizadoAviso(CamelModel):
    tipo: Literal["puxado_por_1", "nao_separavel", "quase_so_com", "travada", "em_alta",
                  "em_queda"]
    sem_maior: float | None = None
    tema_id: str | None = None
    tema_nome: str | None = None
    fator: str | None = None
    valor: str | None = None
    rotulo: str | None = None


class AprendizadoEfeito(CamelModel):
    fator: str
    valor: str
    rotulo: str
    parte: Parte
    efeito: float | None  # entrega em p.p.; rendimento como fator (≈ 2,4×)
    intervalo: list[float] | None  # [baixo, alto], na mesma unidade
    n_posts: int
    n_dias: int
    confianca: Confianca
    faltam: int | None
    mediana_bruta: float | None  # as views no marco (abaixo da amostra, só os números brutos)
    avisos: list[AprendizadoAviso]


class AprendizadoContaContexto(CamelModel):
    conta_id: UUID
    rotulo: str
    medidos: int
    estagnados: int
    travada: bool
    suficiente: bool


class AprendizadoConstantes(CamelModel):
    """As constantes que a nota de leitura mostra (FR-013, FR-014, FR-022, FR-035)."""

    min_grupo: int
    min_dias: int
    min_conta: int
    k_encolhimento: int
    meia_vida_dias: int
    janela_dias: int
    reamostras: int
    concentracao: float
    travada: float
    ampliar_min: float
    cortar_max: float
    cortar_min_n: int
    fixar_min: float
    evitar_max: float
    limite_diario: int
    peso_afinidade: int


class AprendizadoAnaliseContexto(CamelModel):
    de: date
    ate: date
    medida: Medida
    fuso: str
    aguardando: int
    posts_no_periodo: int
    comparacoes: int
    falsos_esperados: int
    contas: list[AprendizadoContaContexto]
    travadas: list[UUID]
    constantes: AprendizadoConstantes


class AprendizadoBloco(CamelModel):
    valor: str
    hashtags: list[str]
    n_posts: int
    quase_sempre_com: list[str]


class AprendizadoCelulaMatriz(CamelModel):
    bloco: str
    tema_id: UUID
    tema_nome: str
    n: int


class AprendizadoAnalise(CamelModel):
    contexto: AprendizadoAnaliseContexto
    efeitos: list[AprendizadoEfeito]
    blocos: list[AprendizadoBloco]
    matriz: list[AprendizadoCelulaMatriz]
    sem_tema: int
    pendentes_classificacao: int


# ---- recomendações e decisões ----

class AprendizadoEscopo(CamelModel):
    tipo: Literal["perfil", "conta"]
    conta_id: UUID | None = None


class AprendizadoAlvo(CamelModel):
    tema_id: UUID | None = None
    tema_nome: str | None = None
    hashtag: str | None = None
    padrao: str | None = None  # o valor do fator (estilo, faixa) ou o texto da hipótese


class AprendizadoBloqueio(CamelModel):
    code: Literal["fixas_no_maximo"]
    fixas: list[str]
    maximo: int


class AprendizadoRecomendacao(CamelModel):
    chave: str
    tipo: TipoRecomendacao
    escopo: AprendizadoEscopo
    alvo: AprendizadoAlvo
    motivo: str
    evidencia: AprendizadoEfeito | None
    o_que_muda: str
    origem: Literal["regra", "hipotese"]
    decisao_id: UUID | None = None  # a aberta de hipótese
    ja_rejeitada_em: datetime | None = None
    bloqueio: AprendizadoBloqueio | None = None


class AprendizadoDecisao(CamelModel):
    id: UUID
    chave: str
    tipo: TipoRecomendacao
    escopo: AprendizadoEscopo
    estado: Literal["aberta", "aceita", "rejeitada"]
    origem: Literal["regra", "hipotese"]
    analise_id: UUID | None
    evidencia: dict[str, Any]
    texto: str | None
    motivo: str | None
    decidido_por: UserRef | None
    decidido_em: datetime | None
    revertida_em: datetime | None
    superada: bool
    version: int


class AprendizadoRecomendacoesOut(CamelModel):
    abertas: list[AprendizadoRecomendacao]
    decididas: list[AprendizadoDecisao]


class AprendizadoDecidirIn(CamelModel):
    chave: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    decisao: Literal["aceita", "rejeitada"]
    motivo: Annotated[str, StringConstraints(strip_whitespace=True,
                                             max_length=K.MOTIVO_MAX)] | None = None
    substituir: str | None = None  # a fixa a trocar quando o guia está no máximo
    medida: Medida = "h24"
    conta_id: UUID | None = None  # o escopo da análise em que a recomendação apareceu


class AprendizadoGuiaRef(CamelModel):
    nivel: Literal["perfil", "conta"]
    version: int


class AprendizadoPadrao(CamelModel):
    tipo: Literal["gancho", "duracao", "horario"]
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                            max_length=K.PADRAO_TEXTO_MAX)]
    valor: dict[str, Any] | str | None = None


class AprendizadoPreferencias(CamelModel):
    id: UUID | None
    perfil_id: UUID
    conta_id: UUID | None
    temas: dict[str, Literal["ampliar", "cortar"]]
    hashtags_evitar: list[str]
    padroes: list[AprendizadoPadrao]
    classificacao_auto: bool
    usar_desempenho: bool
    taxonomia_versao: int
    version: int


class AprendizadoDecidirOut(CamelModel):
    decisao: AprendizadoDecisao
    preferencias: AprendizadoPreferencias | None = None
    guia: AprendizadoGuiaRef | None = None


class AprendizadoRevertOut(CamelModel):
    decisao: AprendizadoDecisao
    preferencias: AprendizadoPreferencias | None = None
    aviso: str | None = None  # "fixar": a hashtag sai pelo revert do guia
    link_guia: str | None = None


class AprendizadoPreferenciasEfetivas(CamelModel):
    temas: dict[str, Literal["ampliar", "cortar"]]
    hashtags_evitar: list[str]
    padroes: list[AprendizadoPadrao]
    usar_desempenho: bool
    janela_preferida: str | None  # a dica do agendamento (só leitura)


class AprendizadoPreferenciasOut(CamelModel):
    perfil: AprendizadoPreferencias
    conta: AprendizadoPreferencias | None
    efetivas: AprendizadoPreferenciasEfetivas


class AprendizadoPreferenciasPatch(CamelModel):
    version: VersionNumber
    temas: dict[str, Literal["ampliar", "cortar"]] | None = None
    hashtags_evitar: list[str] | None = Field(default=None, max_length=K.EVITAR_MAX_ITENS)
    padroes: list[AprendizadoPadrao] | None = Field(default=None, max_length=K.PADROES_MAX)
    classificacao_auto: bool | None = None
    usar_desempenho: bool | None = None


# ---- análises da IA ----

class AprendizadoEstimativaIn(CamelModel):
    conta_id: UUID | None = None
    n: Annotated[int, Field(ge=1, le=K.ANALISE_N_MAX)] = K.ANALISE_N_PADRAO
    medida: Medida = "h24"


class AprendizadoEstimativa(CamelModel):
    melhores: list[PostResumo]
    comparaveis: list[PostResumo]
    sem_arquivo: int
    custo_sem_quadros_usd: float
    custo_com_quadros_usd: float


class AprendizadoAnaliseIaIn(AprendizadoEstimativaIn):
    com_quadros: bool = False
    confirmo_custo: bool = False


class AprendizadoHipotese(CamelModel):
    texto: str
    posts_ids: list[UUID]
    contraste: str
    n: int
    grau: Literal["a_conferir"]


class AprendizadoAnaliseIa(CamelModel):
    id: UUID
    estado: Literal["pendente", "processando", "pronta", "erro"]
    conta_id: UUID | None
    n: int
    medida: Medida
    com_quadros: bool
    videos_sem_arquivo: int
    melhores: list[UUID]
    comparaveis: list[UUID]
    posts: list[PostResumo] = Field(default_factory=list)  # os do conjunto (sem anônimas)
    hipoteses: list[AprendizadoHipotese]
    custo_estimado_usd: float | None  # null para membro
    custo_usd: float | None  # null para membro
    chamada_id: UUID | None
    erro_code: str | None
    taxonomia_versao: int
    pedido_por: UserRef | None
    created_at: datetime
    concluida_em: datetime | None


class AprendizadoAnalisesList(CamelModel):
    items: list[AprendizadoAnaliseIa]
    next_cursor: str | None


class AprendizadoHipoteseRecomendarIn(CamelModel):
    tipo: TipoPadrao
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                            max_length=K.PADRAO_TEXTO_MAX)]


# ---- diagnóstico ----

class AprendizadoSinal(CamelModel):
    tipo: Literal["conta_nova", "muitos_no_dia", "intervalo_curto", "fora_da_audiencia",
                  "repostagem", "curto", "legenda_vazia", "hashtags_demais", "travada"]
    alvo: Literal["conta", "post"]
    alvo_id: UUID
    numero: float | None
    texto: str


class AprendizadoItemChecklist(CamelModel):
    item: str
    titulo: str
    texto: str


class AprendizadoContaRef(CamelModel):
    id: UUID
    handle: str
    rotulo: str


class AprendizadoDiagnosticoConta(CamelModel):
    conta: AprendizadoContaRef
    travada: bool
    estagnados: int
    medidos: int
    sinais: list[AprendizadoSinal]
    posts_com_sinais: int


class AprendizadoDiagnostico(CamelModel):
    contas: list[AprendizadoDiagnosticoConta]
    checklist: list[AprendizadoItemChecklist]


class AprendizadoConferencia(CamelModel):
    id: UUID | None
    video_id: UUID
    item: str
    resultado: Literal["ok", "problema", "nao_sei"] | None
    nota: str | None
    updated_at: datetime | None
    updated_by: UserRef | None
    version: int


class AprendizadoPostDiagnostico(CamelModel):
    post: PostResumo
    estagnado: bool
    sinais: list[AprendizadoSinal]
    conferencias: list[AprendizadoConferencia]
    checklist: list[AprendizadoItemChecklist]


class AprendizadoConferenciaPut(CamelModel):
    version: VersionNumber
    resultado: Literal["ok", "problema", "nao_sei"]
    nota: Annotated[str, StringConstraints(strip_whitespace=True,
                                           max_length=K.NOTA_MAX)] | None = None
