"""Modelos Pydantic do Studio (contracts/http-api.md da spec 020). JSON em camelCase.

Nenhum campo tem `tiktok` no nome. `nomesArquivos` vem `null` numa série anonimizada.

Spec 022 (contracts/http-api.md): só acréscimos. `Secao` ganha as 4 seções de público, a prévia
ganha `publico[]`, a importação ganha `dataFoto`, `dataFotoOrigem` e `secoesVazias`, e a
cobertura ganha `publico`.
"""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from sociman_api.auth.schemas import CamelModel
from sociman_api.perfis.schemas import UserRef, VersionNumber

Secao = Literal["visao_geral", "seguidores", "genero", "territorios", "atividade",
                "espectadores"]
SecaoPublico = Literal["genero", "territorios", "atividade", "espectadores"]
DataFotoOrigem = Literal["historico", "importacao"]
SituacaoFoto = Literal["novo", "igual", "divergente"]
AnoOrigem = Literal["nome_zip", "deduzido", "misto"]
Situacao = Literal["novo", "igual", "divergente", "coletado", "ignorado"]
EstadoImportacao = Literal["ativa", "desfeita"]
CodigoAviso = Literal["diverge_da_coleta", "dia_incompleto", "dias_faltando", "periodo_longo",
                      "ano_deduzido", "colunas_ausentes", "cabecalho_provisorio",
                      "data_foto_importacao", "espectadores_soma", "sem_dado", "secao_vazia"]


# ---- prévia ----

class ContaPrevia(CamelModel):
    id: UUID
    handle: str
    perfil: str


class ArquivoPrevia(CamelModel):
    nome: str
    tipo: Literal["zip", "csv", "xlsx"]
    secao: Secao
    handle: str | None
    ignorados: list[str]


class PeriodoPrevia(CamelModel):
    de: date
    ate: date
    ano_origem: AnoOrigem


class JaImportada(CamelModel):
    importacao_id: UUID
    em: datetime
    por: str  # nome do dono


class ContagensPrevia(CamelModel):
    gravados: int
    iguais: int
    divergentes: int
    coletados: int
    faltando: list[date]
    ignorados: list[date]


class Colunas(CamelModel):
    reconhecidas: list[str]
    ausentes: list[str]
    ignoradas: list[str]


class TotaisVisaoGeral(CamelModel):
    views: int
    visitas_perfil: int | None
    likes: int | None
    comments: int | None
    shares: int | None


class TotaisSeguidores(CamelModel):
    seguidores_inicio: int
    seguidores_fim: int
    ganhos: int


class LinhaAmostra(CamelModel):
    dia: date
    situacao: Situacao
    views: int | None = None
    visitas_perfil: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    seguidores: int | None = None
    seguidores_dif: int | None = None


class SecaoPrevia(CamelModel):
    secao: Secao
    ja_importada: JaImportada | None
    contagens: ContagensPrevia
    totais: TotaisVisaoGeral | TotaisSeguidores
    colunas: Colunas
    amostra: list[LinhaAmostra]


class Aviso(CamelModel):
    codigo: CodigoAviso
    mensagem: str
    detalhes: dict[str, Any] | None = None


# ---- prévia: público (spec 022) ----

class PublicoItemPrevia(CamelModel):
    rotulo: str  # gênero normalizado (masculino, feminino, outro) ou o território como veio
    rotulo_exibicao: str
    pct: float | None  # 0–100; null = sem dado


class PublicoPeriodoSecao(CamelModel):
    de: date
    ate: date
    ano_origem: AnoOrigem


class PublicoPico(CamelModel):
    dia: date
    hora: int  # como veio no arquivo
    ativos: int


class PublicoTotaisEspectadores(CamelModel):
    novos: int | None  # soma dos dias com valor
    media_total: float | None  # média diária dos dias com valor
    media_recorrentes: float | None


class PublicoContagensPrevia(CamelModel):
    gravados: int
    iguais: int
    divergentes: int
    sem_dado: int
    faltando: list[date] = Field(default_factory=list)
    ignorados: list[date] = Field(default_factory=list)


class PublicoLinhaEspectadores(CamelModel):
    dia: date
    total: int | None
    novos: int | None
    recorrentes: int | None
    situacao: Situacao


class SecaoPublicoPrevia(CamelModel):
    """Uma seção de público da prévia. Com `vazia`, vem só `secao`, `vazia` e `mensagem`."""

    secao: SecaoPublico
    vazia: bool
    mensagem: str | None = None
    ja_importada: JaImportada | None = None
    # gênero e territórios
    data_foto: date | None = None
    data_foto_origem: DataFotoOrigem | None = None
    situacao: SituacaoFoto | None = None
    itens: list[PublicoItemPrevia] | None = None
    # atividade e espectadores
    periodo: PublicoPeriodoSecao | None = None
    pico: PublicoPico | None = None  # só na atividade (a amostra dela)
    totais: PublicoTotaisEspectadores | None = None  # só nos espectadores
    amostra: list[PublicoLinhaEspectadores] | None = None  # só nos espectadores (até 10)
    colunas: Colunas | None = None
    contagens: PublicoContagensPrevia | None = None


class PreviaStudio(CamelModel):
    previa_id: UUID
    expira_em: datetime
    conta: ContaPrevia
    arquivos: list[ArquivoPrevia]
    periodo: PeriodoPrevia
    secoes: list[SecaoPrevia]
    avisos: list[Aviso]
    exige_confirmacao_conta: bool
    pode_confirmar: bool
    publico: list[SecaoPublicoPrevia] = Field(default_factory=list)  # spec 022


# ---- importação ----

class ConfirmarIn(CamelModel):
    previa_id: UUID
    confirmo_conta: bool = False


class DesfazerIn(CamelModel):
    version: VersionNumber


class ContagensImportacao(CamelModel):
    gravados: int
    iguais: int
    divergentes: int
    coletados: int = 0  # as seções de público não têm coleta da API (022)
    faltando: int = 0
    ignorados: int = 0
    sem_dado: int = 0  # spec 022


class Importacao(CamelModel):
    id: UUID
    conta_id: UUID | None  # null numa série anonimizada
    serie_id: UUID
    version: int
    estado: EstadoImportacao
    secoes: list[Secao]
    periodo_de: date
    periodo_ate: date
    ano_origem: AnoOrigem
    contagens: dict[Secao, ContagensImportacao]
    nomes_arquivos: list[str] | None
    criada_em: datetime
    criada_por: UserRef
    desfeita_em: datetime | None
    desfeita_por: UserRef | None
    gravados: int  # linhas gravadas por esta confirmação (0 no idempotente)
    # spec 022
    data_foto: date | None = None
    data_foto_origem: DataFotoOrigem | None = None
    secoes_vazias: list[SecaoPublico] = Field(default_factory=list)


class ImportacoesList(CamelModel):
    items: list[Importacao]


# ---- cobertura ----

class Faixa(CamelModel):
    de: date
    ate: date


class FaixaFonte(Faixa):
    fonte: Literal["studio"]


class ColetaCobertura(CamelModel):
    primeiro_dia: date
    primeiro_dia_coberto: date


class SecaoCobertura(CamelModel):
    secao: Secao
    faixas: list[FaixaFonte]
    sobreposicao: list[Faixa]
    buracos: list[Faixa]


class PublicoFotoCobertura(CamelModel):
    tipo: Literal["genero", "territorio"]
    data_foto: date
    importacao_id: UUID


class PublicoDiasCobertura(CamelModel):
    faixas: list[Faixa] = Field(default_factory=list)
    buracos: list[Faixa] = Field(default_factory=list)  # dias sem dado efetivo entre o 1º e o último


class PublicoVaziaCobertura(CamelModel):
    secao: SecaoPublico
    em: datetime  # a importação ativa que trouxe a seção vazia (regra "veio vazia")


class CoberturaPublico(CamelModel):
    fotos: list[PublicoFotoCobertura] = Field(default_factory=list)
    atividade: PublicoDiasCobertura = Field(default_factory=PublicoDiasCobertura)
    espectadores: PublicoDiasCobertura = Field(default_factory=PublicoDiasCobertura)
    vazias: list[PublicoVaziaCobertura] = Field(default_factory=list)


class Cobertura(CamelModel):
    conta_id: UUID
    hoje: date
    coleta: ColetaCobertura | None
    secoes: list[SecaoCobertura]
    importacoes_ativas: int
    publico: CoberturaPublico = Field(default_factory=CoberturaPublico)  # spec 022
