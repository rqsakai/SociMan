"""Modelos Pydantic do Studio (contracts/http-api.md da spec 020). JSON em camelCase.

Nenhum campo tem `tiktok` no nome. `nomesArquivos` vem `null` numa série anonimizada.
"""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from sociman_api.auth.schemas import CamelModel
from sociman_api.perfis.schemas import UserRef, VersionNumber

Secao = Literal["visao_geral", "seguidores"]
AnoOrigem = Literal["nome_zip", "deduzido", "misto"]
Situacao = Literal["novo", "igual", "divergente", "coletado", "ignorado"]
EstadoImportacao = Literal["ativa", "desfeita"]
CodigoAviso = Literal["diverge_da_coleta", "dia_incompleto", "dias_faltando", "periodo_longo",
                      "ano_deduzido", "colunas_ausentes", "cabecalho_provisorio"]


# ---- prévia ----

class ContaPrevia(CamelModel):
    id: UUID
    handle: str
    perfil: str


class ArquivoPrevia(CamelModel):
    nome: str
    tipo: Literal["zip", "csv"]
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
    coletados: int
    faltando: int
    ignorados: int


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


class Cobertura(CamelModel):
    conta_id: UUID
    hoje: date
    coleta: ColetaCobertura | None
    secoes: list[SecaoCobertura]
    importacoes_ativas: int
