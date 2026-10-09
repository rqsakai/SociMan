"""Modelos Pydantic da coleta (contracts/http-api.md da 026): protocolo do coletor (rotas C),
gestão (HO) e leitura (U). JSON em camelCase. Nenhuma saída tem o hash do token; o `token` só
aparece em `ColetaClienteComToken` (criar e rotacionar)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.coleta.models import ColetaSituacao, EventoTipo
from sociman_api.mercado.constantes import ITENS_POR_LOTE_MAX
from sociman_api.mercado.models import ColetaEstado, FilaEstado, ItemStatus
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import UserRef

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Descricao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
MercadoCodigo = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
VersionNumber = Annotated[int, Field(ge=0)]


# ---- protocolo do coletor (rotas C) ----

class Janela(CamelModel):
    inicio: int
    fim: int
    dentro: bool


class LimitesColeta(CamelModel):
    paginas_dia: int
    imagens_dia: int
    imagens_por_produto: int
    itens_por_coleta: int
    pausa_min_s: int
    pausa_max_s: int
    lease_min: int


class Orcamento(CamelModel):
    paginas_hoje: int
    paginas_restantes: int
    imagens_hoje: int
    imagens_restantes: int


class TarefaOut(CamelModel):
    tarefa_id: uuid.UUID
    tipo: str
    rede: Platform
    mercado: str
    fonte: str
    chave: str
    url: str
    nivel: int
    prioridade: int
    turno: str | None
    reservada_ate: datetime | None
    extra: dict[str, Any]


MotivoVazia = Literal["desligada", "fora_da_janela", "pausada", "orcamento", "nada_a_coletar",
                      "aguardando_continuar"]


class FilaOut(CamelModel):
    habilitada: bool
    desligada_no_servidor: bool
    pausada_ate: datetime | None
    continuar_em: datetime | None
    agora_servidor: datetime
    data_local: date
    fuso: str
    janela: Janela
    limites: LimitesColeta
    orcamento: Orcamento
    tarefas: list[TarefaOut]
    motivo_vazia: MotivoVazia | None = None


class LimitesLocais(CamelModel):
    paginas_dia: int | None = None
    imagens_dia: int | None = None


class AbrirColetaIn(CamelModel):
    versao_coletor: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    chrome_versao: Annotated[str, StringConstraints(max_length=40)] | None = None
    protocolo: int = 1
    limites_locais: LimitesLocais | None = None
    iniciada_em: datetime | None = None


class ColetaOut(CamelModel):
    id: uuid.UUID
    cliente_id: uuid.UUID
    rede: Platform
    mercado: str
    estado: ColetaEstado
    iniciada_em: datetime
    batimento_em: datetime
    terminada_em: datetime | None
    tarefa_atual_id: uuid.UUID | None
    paginas: int
    imagens: int
    itens_ok: int
    itens_erro: int
    itens_repetidos: int
    versao_coletor: str
    chrome_versao: str | None
    protocolo: int
    resumo: dict[str, Any]


class ItemIn(CamelModel):
    tarefa_id: uuid.UUID
    status: Literal["ok", "erro", "captcha"]
    coletado_em: datetime
    duracao_ms: int | None = Field(default=None, ge=0)
    esquema_versao: str | None = None
    fonte: Literal["pagina_publica", "affiliate", "ambas"] | None = None
    campos: dict[str, Any] | None = None
    bruto: str | None = None  # gzip + base64 do JSON interceptado, já podado
    imagens: list[Sha256] = Field(default_factory=list, max_length=100)
    erro_codigo: str | None = Field(default=None, max_length=60)
    reprocessado_de: int | None = None


class ItensIn(CamelModel):
    itens: list[ItemIn] = Field(min_length=1, max_length=ITENS_POR_LOTE_MAX)


class ResultadoItem(CamelModel):
    tarefa_id: uuid.UUID
    status: ItemStatus
    data_local: date | None = None
    turno: str | None = None
    imagens_pendentes: list[str] = Field(default_factory=list)
    bruto_pendente: bool = False
    ficha_nova: bool = False
    erro_codigo: str | None = None
    erro_campo: str | None = None
    tentativas: int | None = None
    volta_para_fila: bool | None = None


class ItensOut(CamelModel):
    coleta_id: uuid.UUID
    resultados: list[ResultadoItem]
    orcamento: Orcamento
    pausada_ate: datetime | None
    parar: bool


class ManifestoImagem(CamelModel):
    sha256: Sha256
    tarefa_id: uuid.UUID | None = None
    origem: Literal["produto", "avaliacao"] = "produto"
    content_type: str | None = None


class ImagemRecusada(CamelModel):
    sha256: str
    motivo: str


class OrcamentoImagens(CamelModel):
    imagens_hoje: int
    imagens_restantes: int


class ImagensOut(CamelModel):
    aceitas: list[str]
    repetidas: list[str]
    recusadas: list[ImagemRecusada]
    orcamento: OrcamentoImagens


class BatimentoIn(CamelModel):
    estado: str | None = None
    tarefa_atual_id: uuid.UUID | None = None
    paginas_hoje: int | None = Field(default=None, ge=0)
    imagens_hoje: int | None = Field(default=None, ge=0)
    proxima_acao_em: datetime | None = None
    memoria_mb: int | None = Field(default=None, ge=0)


class BatimentoOut(CamelModel):
    parar: bool
    motivo: str | None = None
    pausada_ate: datetime | None
    continuar_em: datetime | None
    limites: LimitesColeta
    orcamento: Orcamento


MotivoFim = Literal["fila_vazia", "orcamento", "fora_da_janela", "parar_local", "servico_parado",
                    "erro_interno", "pausa_vencida", "limite"]


class FimIn(CamelModel):
    motivo: MotivoFim
    terminada_em: datetime | None = None
    paginas: int | None = Field(default=None, ge=0)
    imagens: int | None = Field(default=None, ge=0)
    por_tipo: dict[str, int] = Field(default_factory=dict)


class EventoIn(CamelModel):
    tipo: EventoTipo
    coleta_id: uuid.UUID | None = None
    tarefa_id: uuid.UUID | None = None
    ocorreu_em: datetime | None = None
    detalhe: dict[str, Any] = Field(default_factory=dict)


class EventoOut(CamelModel):
    evento_id: int
    coleta: ColetaOut | None
    pausada_ate: datetime | None
    notificado: bool


class ColetaLinkOut(CamelModel):
    url: str
    expires_at: datetime | None


class BrutoLinkOut(CamelModel):
    link: ColetaLinkOut
    bytes: int | None
    esquema_versao: str | None
    data_local: date
    turno: str | None


# ---- gestão (HO) ----

class ColetaCliente(CamelModel):
    id: uuid.UUID
    nome: str
    descricao: str
    rede: Platform
    mercado: str
    situacao: ColetaSituacao
    token_id: str  # só o prefixo público; nunca o segredo
    token_emitido_em: datetime
    expira_em: datetime | None
    limite_por_minuto: int
    ultimo_contato_em: datetime | None
    versao_coletor: str | None
    chrome_versao: str | None
    revogado_em: datetime | None
    revogado_por: UserRef | None
    created_at: datetime
    created_by: UserRef | None
    version: int


class ColetaClientesList(CamelModel):
    itens: list[ColetaCliente]


class ColetaClienteComToken(CamelModel):
    cliente: ColetaCliente
    token: str  # mostrado uma única vez (`Cache-Control: no-store`)


class CriarClienteIn(CamelModel):
    nome: Nome
    descricao: Descricao = ""
    mercado: MercadoCodigo = "BR"
    rede: Platform = Platform.tiktok
    expira_em: datetime | None = None
    limite_por_minuto: Annotated[int, Field(ge=1, le=600)] = 120


class EditarClienteIn(CamelModel):
    version: Annotated[int, Field(ge=1)]
    nome: Nome | None = None
    descricao: Descricao | None = None
    expira_em: datetime | None = None
    limite_por_minuto: Annotated[int, Field(ge=1, le=600)] | None = None


class ColetaVersionIn(CamelModel):
    version: Annotated[int, Field(ge=1)]


class ColetaConfig(CamelModel):
    habilitada: bool
    servidor_habilitado: bool
    risco_aceito: bool
    risco_aceito_em: datetime | None
    risco_aceito_por: UserRef | None
    risco_texto_versao: str | None  # a versão do texto aceita (nula antes do 1º aceite)
    texto_risco: str
    texto_risco_versao: str  # a versão corrente do texto, a que o aceite deve mandar
    janela_inicio: int
    janela_fim: int
    paginas_dia: int
    imagens_dia: int
    imagens_por_produto: int
    itens_por_coleta: int
    pausa_min_s: int
    pausa_max_s: int
    pausada_ate: datetime | None
    continuar_em: datetime | None
    version: int
    updated_at: datetime | None
    updated_by: UserRef | None


class ColetaConfigIn(CamelModel):
    version: VersionNumber
    habilitada: bool
    janela_inicio: Annotated[int, Field(ge=0, le=23)] = 8
    janela_fim: Annotated[int, Field(ge=0, le=23)] = 23
    paginas_dia: Annotated[int, Field(ge=1, le=2000)] = 300
    imagens_dia: Annotated[int, Field(ge=0, le=20000)] = 1500
    imagens_por_produto: Annotated[int, Field(ge=0, le=20)] = 9
    itens_por_coleta: Annotated[int, Field(ge=1, le=50)] = 40
    pausa_min_s: Annotated[int, Field(ge=1, le=600)] = 5
    pausa_max_s: Annotated[int, Field(ge=1, le=600)] = 40


class AceitarRiscoIn(CamelModel):
    version: VersionNumber
    texto_versao: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    confirmo: bool


class PausarIn(CamelModel):
    version: VersionNumber
    horas: Annotated[int, Field(ge=1, le=168)]


class ContinuarIn(CamelModel):
    version: VersionNumber


class ColetaRevertIn(CamelModel):
    version: VersionNumber
    to_version: Annotated[int, Field(ge=1)]


# ---- leitura (U) ----

class ColetaResumo(CamelModel):
    id: uuid.UUID
    cliente_id: uuid.UUID
    estado: ColetaEstado
    iniciada_em: datetime
    batimento_em: datetime
    terminada_em: datetime | None
    paginas: int
    imagens: int
    itens_ok: int
    itens_erro: int
    itens_repetidos: int
    versao_coletor: str
    resumo: dict[str, Any]


class ColetasList(CamelModel):
    itens: list[ColetaResumo]
    proximo: str | None


class ColetaItemOut(CamelModel):
    id: int
    tarefa_id: uuid.UUID | None
    tipo: str
    fonte: str | None
    status: ItemStatus
    erro_codigo: str | None
    erro_campo: str | None
    duracao_ms: int | None
    recebido_em: datetime
    coletado_em: datetime
    data_local: date
    turno: str | None
    bruto_pendente: bool
    bruto_bytes: int | None


class ColetaEventoOut(CamelModel):
    id: int
    tipo: EventoTipo
    cliente_id: uuid.UUID
    coleta_id: uuid.UUID | None
    tarefa_id: uuid.UUID | None
    detalhe: dict[str, Any]
    ocorreu_em: datetime
    recebido_em: datetime
    notificado: bool


class ColetaDetalhe(ColetaOut):
    itens: list[ColetaItemOut]
    eventos: list[ColetaEventoOut]


class EventosList(CamelModel):
    itens: list[ColetaEventoOut]
    proximo: str | None


class ClienteResumo(CamelModel):
    id: uuid.UUID
    nome: str
    token_id: str
    situacao: ColetaSituacao
    mercado: str
    ultimo_contato_em: datetime | None
    versao_coletor: str | None
    chrome_versao: str | None


class HojeResumo(CamelModel):
    tarefas: int
    pendentes: int
    recebidas: int
    falhadas: int
    expiradas: int
    gravados: int
    repetidos: int
    invalidos: int


Situacao = Literal["desligada_no_servidor", "desligada", "aceite_pendente", "pausada",
                   "aguardando_continuar", "fora_da_janela", "ociosa", "coletando",
                   "pausada_captcha", "pausada_login", "sem_cliente", "parada"]


class EstadoColetaMercado(CamelModel):
    servidor_habilitado: bool
    habilitada: bool
    risco_aceito: bool
    situacao: Situacao
    pausada_ate: datetime | None
    continuar_em: datetime | None
    janela: Janela
    data_local: date
    fuso: str
    orcamento: Orcamento
    hoje: HojeResumo
    clientes: list[ClienteResumo]
    rodada_atual: ColetaResumo | None
    ultimo_resultado_em: datetime | None
    eventos_recentes: list[ColetaEventoOut]


class TarefaFila(TarefaOut):
    estado: FilaEstado
    perfil_id: uuid.UUID | None
    produto_id: uuid.UUID | None
    tentativas: int
    resultado_status: ItemStatus | None
    erro_codigo: str | None
    criada_em: datetime
    recebida_em: datetime | None


class FilaHojeOut(CamelModel):
    itens: list[TarefaFila]
    por_nivel: dict[str, int]
    por_estado: dict[str, int]
