"""Modelos Pydantic da importação da agência (contracts/http-api.md da spec 013). JSON em
camelCase. Sem "youtube" nem "tiktok" nos nomes.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.models import CanalDireito
from sociman_api.perfis.schemas import UserRef, VersionNumber

Tipo = Literal["perfil", "conta", "guia", "anotacao", "canal", "vinculo_canal", "imagem_logo",
               "asset", "arquivo_asset", "clipe", "sugestao_bordao", "arquivo"]
Situacao = Literal["novo", "igual", "diverge", "fora", "aguardando_cota", "sugestao"]
Resultado = Literal["criado", "atualizado", "mantido", "igual", "fora", "nao_gravado",
                    "sugestao"]
EstadoImportacao = Literal["processando", "concluida", "falhou", "desfeita"]
Usar = Literal["sociman", "markdown"]


# ---- estado ----

class AgenciaRaiz(CamelModel):
    disponivel: bool
    motivo: str | None = None


class AgenciaRaizes(CamelModel):
    shared: AgenciaRaiz
    clipes: AgenciaRaiz


class AgenciaPerfilEstado(CamelModel):
    slug: str
    ultima_importacao_em: datetime
    arquivos_mudaram: bool


class AgenciaImportacaoRef(CamelModel):
    id: UUID
    estado: EstadoImportacao
    criada_em: datetime
    criada_por: UserRef | None


class AgenciaEstado(CamelModel):
    raizes: AgenciaRaizes
    ultima: AgenciaImportacaoRef | None
    perfis: list[AgenciaPerfilEstado]
    em_andamento: AgenciaImportacaoRef | None


# ---- prévia ----

class AgenciaOrigem(CamelModel):
    arquivo: str  # `shared:perfis/x/fontes.md` ou `clipes:x/2026-09-25/x-1.mp4`
    trecho: str
    linha: int | None = None


class AgenciaEscolhaPadrao(CamelModel):
    marcado: bool | None = None  # itens `novo`
    usar: Usar | None = None  # itens `diverge`
    direito: CanalDireito | None = None  # canal novo ou `diverge(direito)`


class AgenciaItemPrevia(CamelModel):
    n: int
    tipo: Tipo
    perfil_slug: str | None
    origem: AgenciaOrigem
    origens: list[AgenciaOrigem] = Field(default_factory=list)  # outras linhas (canal em 2 fontes)
    situacao: Situacao
    motivo: str | None = None
    motivo_texto: str | None = None
    atual: dict[str, Any] | None = None
    proposto: dict[str, Any] | None = None
    bytes: int | None = None
    escolha_padrao: AgenciaEscolhaPadrao | None = None
    direitos_aceitos: list[CanalDireito] | None = None
    exige_perfil: bool = False  # persona sem perfil padrão: `personaPerfil` no confirmar


class AgenciaContagens(CamelModel):
    novo: int = 0
    igual: int = 0
    diverge: int = 0
    fora: int = 0
    aguardando_cota: int = 0
    sugestao: int = 0
    nao_reconhecido: int = 0


class AgenciaNaoReconhecido(CamelModel):
    arquivo: str
    faltou: list[str]


class AgenciaPersona(CamelModel):
    perfil_padrao: str | None  # slug do perfil que já tem uma imagem da persona
    exige_perfil: bool


class AgenciaPrevia(CamelModel):
    previa_id: UUID
    expira_em: datetime
    contagens: AgenciaContagens
    bytes_novos: int
    arquivos_nao_reconhecidos: list[AgenciaNaoReconhecido]
    persona: AgenciaPersona | None
    itens: list[AgenciaItemPrevia]


# ---- confirmar ----

class AgenciaEscolha(CamelModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    marcado: bool | None = None
    usar: Usar | None = None
    direito: CanalDireito | None = None


class AgenciaConfirmar(CamelModel):
    model_config = ConfigDict(extra="forbid")

    previa_id: UUID
    escolhas: list[AgenciaEscolha] = Field(default_factory=list, max_length=5000)
    persona_perfil: str | None = None  # slug; obrigatório quando a persona `exigePerfil`


class AgenciaDesfazerIn(CamelModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionNumber


# ---- importação ----

class AgenciaProgresso(CamelModel):
    etapa: Literal["conferindo", "gravando", "fim"] | None = None
    feitos: int = 0
    total: int = 0
    bytes: int = 0


class AgenciaContagensImportacao(CamelModel):
    criado: int = 0
    atualizado: int = 0
    mantido: int = 0
    igual: int = 0
    fora: int = 0
    nao_gravado: int = 0
    sugestao: int = 0


class AgenciaEntidade(CamelModel):
    tipo: str
    id: UUID
    version: int | None


class AgenciaItemImportacao(CamelModel):
    n: int
    tipo: Tipo
    perfil_slug: str | None
    origem: AgenciaOrigem
    situacao: Situacao
    motivo: str | None
    motivo_texto: str | None
    escolha: dict[str, Any]
    resultado: Resultado
    resultado_motivo: str | None
    resultado_texto: str | None
    entidade: AgenciaEntidade | None
    desfeito_em: datetime | None
    desfazer_motivo: str | None
    desfazer_texto: str | None


class AgenciaImportacaoResumo(CamelModel):
    id: UUID
    version: int
    estado: EstadoImportacao
    criada_em: datetime
    criada_por: UserRef | None
    concluida_em: datetime | None
    desfeita_em: datetime | None
    desfeita_por: UserRef | None
    erro: str | None
    progresso: AgenciaProgresso
    contagens: AgenciaContagensImportacao
    arquivos: int  # quantos arquivos foram usados (com a impressão digital)


class AgenciaImportacao(AgenciaImportacaoResumo):
    itens: list[AgenciaItemImportacao]


class AgenciaImportacoesList(CamelModel):
    items: list[AgenciaImportacaoResumo]
