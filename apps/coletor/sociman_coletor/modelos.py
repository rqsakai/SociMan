"""Modelos Pydantic do protocolo com a API de ingestão (contracts/http-api.md, rotas C).

Espelham `apps/api/src/sociman_api/coleta/schemas.py`: JSON em camelCase, nomes em snake_case
no código. Só o que o coletor lê ou manda.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Modelo(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore", serialize_by_alias=True
    )


# ---- fila ----


class Janela(Modelo):
    inicio: int
    fim: int
    dentro: bool


class Limites(Modelo):
    paginas_dia: int
    imagens_dia: int
    imagens_por_produto: int
    itens_por_coleta: int
    pausa_min_s: int
    pausa_max_s: int
    lease_min: int


class Orcamento(Modelo):
    paginas_hoje: int
    paginas_restantes: int
    imagens_hoje: int
    imagens_restantes: int


class Tarefa(Modelo):
    tarefa_id: str
    tipo: str
    rede: str = "tiktok"
    mercado: str = "BR"
    fonte: str = "pagina_publica"
    chave: str
    url: str
    nivel: int = 0
    prioridade: int = 0
    turno: str | None = None
    reservada_ate: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


MotivoVazia = Literal[
    "desligada", "fora_da_janela", "pausada", "orcamento", "nada_a_coletar", "aguardando_continuar"
]


class Fila(Modelo):
    habilitada: bool
    desligada_no_servidor: bool = False
    pausada_ate: datetime | None = None
    continuar_em: datetime | None = None
    agora_servidor: datetime
    data_local: date
    fuso: str
    janela: Janela
    limites: Limites
    orcamento: Orcamento
    tarefas: list[Tarefa] = Field(default_factory=list)
    motivo_vazia: MotivoVazia | None = None


# ---- rodada ----


class LimitesLocais(Modelo):
    paginas_dia: int | None = None
    imagens_dia: int | None = None


class AbrirColeta(Modelo):
    versao_coletor: str
    chrome_versao: str | None = None
    protocolo: int = 1
    limites_locais: LimitesLocais | None = None
    iniciada_em: datetime | None = None


class Coleta(Modelo):
    id: str
    estado: str
    iniciada_em: datetime | None = None
    terminada_em: datetime | None = None
    paginas: int = 0
    imagens: int = 0
    itens_ok: int = 0
    itens_erro: int = 0
    itens_repetidos: int = 0


class ColetaResumo(Modelo):
    id: str
    estado: str
    iniciada_em: datetime | None = None
    paginas: int = 0


class ColetasLista(Modelo):
    itens: list[ColetaResumo] = Field(default_factory=list)
    proximo: str | None = None


# ---- itens ----

StatusItem = Literal["ok", "erro", "captcha"]
Fonte = Literal["pagina_publica", "affiliate", "ambas"]


class Item(Modelo):
    """Um resultado de página. `bruto` = gzip + base64 do JSON interceptado, já podado."""

    tarefa_id: str
    status: StatusItem
    coletado_em: datetime
    duracao_ms: int | None = None
    esquema_versao: str | None = None
    fonte: Fonte | None = None
    campos: dict[str, Any] | None = None
    bruto: str | None = None
    imagens: list[str] = Field(default_factory=list)
    erro_codigo: str | None = None
    reprocessado_de: int | None = None


class ResultadoItem(Modelo):
    tarefa_id: str
    status: Literal["gravado", "repetido", "invalido", "erro", "captcha"]
    data_local: date | None = None
    turno: str | None = None
    imagens_pendentes: list[str] = Field(default_factory=list)
    bruto_pendente: bool = False
    ficha_nova: bool = False
    erro_codigo: str | None = None
    erro_campo: str | None = None
    tentativas: int | None = None
    volta_para_fila: bool | None = None


class RespostaItens(Modelo):
    coleta_id: str
    resultados: list[ResultadoItem]
    orcamento: Orcamento | None = None
    pausada_ate: datetime | None = None
    parar: bool = False


# ---- imagens ----


class ManifestoImagem(Modelo):
    sha256: str
    tarefa_id: str | None = None
    origem: Literal["produto", "avaliacao"] = "produto"
    content_type: str | None = None


class ImagemRecusada(Modelo):
    sha256: str
    motivo: str


class OrcamentoImagens(Modelo):
    imagens_hoje: int
    imagens_restantes: int


class RespostaImagens(Modelo):
    aceitas: list[str] = Field(default_factory=list)
    repetidas: list[str] = Field(default_factory=list)
    recusadas: list[ImagemRecusada] = Field(default_factory=list)
    orcamento: OrcamentoImagens | None = None


# ---- batimento, fim, eventos ----


class Batimento(Modelo):
    estado: str | None = None
    tarefa_atual_id: str | None = None
    paginas_hoje: int | None = None
    imagens_hoje: int | None = None
    proxima_acao_em: datetime | None = None
    memoria_mb: int | None = None


class RespostaBatimento(Modelo):
    parar: bool = False
    motivo: str | None = None
    pausada_ate: datetime | None = None
    continuar_em: datetime | None = None
    limites: Limites | None = None
    orcamento: Orcamento | None = None


MotivoFim = Literal[
    "fila_vazia",
    "orcamento",
    "fora_da_janela",
    "parar_local",
    "servico_parado",
    "erro_interno",
    "pausa_vencida",
    "limite",
]


class Fim(Modelo):
    motivo: MotivoFim
    terminada_em: datetime | None = None
    paginas: int | None = None
    imagens: int | None = None
    por_tipo: dict[str, int] = Field(default_factory=dict)


TipoEvento = Literal[
    "captcha",
    "login_perdido",
    "bloqueio_suspeito",
    "layout_mudou",
    "parar_local",
    "retomou",
    "iniciado",
    "parado",
]


class Evento(Modelo):
    tipo: TipoEvento
    coleta_id: str | None = None
    tarefa_id: str | None = None
    ocorreu_em: datetime | None = None
    detalhe: dict[str, Any] = Field(default_factory=dict)


class RespostaEvento(Modelo):
    evento_id: int
    pausada_ate: datetime | None = None
    notificado: bool = False


class Link(Modelo):
    url: str
    expires_at: datetime | None = None


class BrutoLink(Modelo):
    link: Link
    bytes: int | None = None
    esquema_versao: str | None = None
    data_local: date | None = None
    turno: str | None = None


class ItemColeta(Modelo):
    """Um item da rodada, como `GET /api/coleta/coletas/{id}` o devolve (para o `reprocessar`)."""

    id: int
    tarefa_id: str | None = None
    tipo: str
    fonte: str | None = None
    status: str
    bruto_pendente: bool = False


class ColetaDetalhe(Coleta):
    itens: list[ItemColeta] = Field(default_factory=list)
