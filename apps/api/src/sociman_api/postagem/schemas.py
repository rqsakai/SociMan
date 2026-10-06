"""Modelos Pydantic de sugestões, postagens, destinos e calendário (contracts/http-api.md da
006, "Postagens", e da 014, "Tipos"). JSON em camelCase.

Aqui ficam formato e limites (data-model.md). A normalização das hashtags, a ligação conta ×
perfil do corte, o `corte_not_ready` e o `planned_in_past` ficam no service.
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.canais.schemas import PerfilRef  # o mesmo nome no OpenAPI (trilha A)
from sociman_api.conteudos.consulta import EstadoEfetivo, Situacao
from sociman_api.conteudos.models import ConteudoOrigem, Modo
from sociman_api.ia.aplicacao import IaAplicacoes
from sociman_api.perfis.models import ContaStatus, Platform
from sociman_api.perfis.schemas import UserRef, VersionNumber
from sociman_api.postagem.models import DestinoEstado
from sociman_api.publicacao.schemas import (  # ModoInfo: um só no OpenAPI (015, `aviso`)
    ConexaoEstadoOut,
    ModoInfo,
    OpcoesTikTok,
    Tentativa,
    TentativaFaseOut,
)

Titulo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Descricao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
# Cada hashtag chega crua (com ou sem #); o service normaliza e confere `^#[\p{L}0-9_]{1,50}$`.
HashtagIn = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Hashtags = Annotated[list[HashtagIn], Field(max_length=8)]
PostedUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500, pattern=r"^https?://\S+$")
]



# ---- saídas ----

class ContaRef(CamelModel):
    id: UUID
    platform: Platform
    platform_name: str
    handle: str
    status: ContaStatus  # spec 014
    conexao: ConexaoEstadoOut = "nao_conectada"  # spec 015 (só TikTok tem conexão)


class Sugestao(CamelModel):
    id: UUID
    plataforma: Platform
    titulo: str
    descricao: str
    hashtags: list[str]
    ajustes: list[str]  # o que foi cortado ou completado na validação
    model: str
    created_at: datetime


class SugestaoOut(CamelModel):
    sugestao: Sugestao


class SugestoesList(CamelModel):
    items: list[Sugestao]  # mais recentes primeiro (só as que deram resultado)


# ---- entradas ----

class SugestaoIn(CamelModel):
    conta_id: UUID  # a plataforma vem da conta
    # "Outra versão": manda ao Claude as sugestões anteriores deste corte na plataforma.
    outra_versao: bool = False


class PostadoIn(CamelModel):
    version: VersionNumber
    posted_url: PostedUrl | None = None


# ---- spec 014: destinos e agendamentos (contracts/http-api.md da 014, "Tipos") ----

class ModosOut(CamelModel):
    modos: list[ModoInfo]  # os quatro, na ordem da spec


class DestinoResumo(CamelModel):
    """O que a linha da lista (e o `Corte`) mostra de cada destino ativo."""

    id: UUID
    conta: ContaRef
    estado: DestinoEstado
    estado_efetivo: EstadoEfetivo
    motivo_atencao: str | None
    modo: Modo
    planned_at: datetime | None
    sem_textos: bool  # título vazio
    video_mudou: bool
    version: int
    ultima_fase: TentativaFaseOut | None = None  # spec 015


class Aprovacao(CamelModel):
    por: UserRef
    em: datetime


class Pedido(CamelModel):
    por: UserRef
    em: datetime
    nota: str | None


class Recusa(CamelModel):
    por: UserRef
    em: datetime
    motivo: str


class EnvioConfirmado(CamelModel):
    """"Confirmar envio" de um agendamento vencido (spec 015, R11)."""

    por: UserRef
    em: datetime


class Destino(CamelModel):
    id: UUID
    conteudo_id: UUID
    conta: ContaRef
    titulo: str
    descricao: str
    hashtags: list[str]
    estado: DestinoEstado
    estado_efetivo: EstadoEfetivo
    motivo_atencao: str | None
    modo: Modo
    antecedencia_min: int | None
    planned_at: datetime | None  # ISO com o offset de APP_TZ
    lembrado: bool
    posted_at: datetime | None
    posted_url: str | None
    falha_motivo: str | None
    aprovacao: Aprovacao | None
    pedido: Pedido | None
    recusa: Recusa | None
    video_mudou: bool
    archived: bool
    version: int
    created_at: datetime
    updated_at: datetime
    updated_by: UserRef | None
    # ---- spec 015 (execução na rede) ----
    opcoes_rede: OpcoesTikTok | None = None  # só `publicar`
    agendado_por: UserRef | None = None
    agendado_em: datetime | None = None
    envio_confirmado: EnvioConfirmado | None = None
    falha_incerta: bool = False  # a rede pode ter recebido: "Conferi no app" antes de voltar
    rede_post_id: str | None = None
    rede_post_url: str | None = None
    ultima_tentativa: Tentativa | None = None
    snapshot_desatualizado: bool = False  # textos mudaram depois do snapshot (publicar)
    legenda_final: str | None = None  # TikTok (T101): descrição + hashtags, para copiar
    avisos_rede: list[str] = Field(default_factory=list)  # vídeo fora das regras (aviso)


class DestinoOut(CamelModel):
    destino: Destino


class Textos(CamelModel):
    titulo: Titulo | None = None
    descricao: Descricao | None = None
    hashtags: Hashtags | None = None


class LoteFalha(CamelModel):
    conteudo_id: UUID | None
    destino_id: UUID | None
    code: str
    message: str


class LoteResultado(CamelModel):
    ok: list[Destino]
    falhas: list[LoteFalha]


class TodasResultado(CamelModel):
    """Aprovar/desaprovar todas as contas do conteúdo (spec 018): os que mudaram e os que
    ficaram como estavam, com o motivo."""

    ok: list[Destino]
    ignorados: list[LoteFalha]


class DesaprovarTodasIn(CamelModel):
    confirmo: bool = False  # obrigatório quando algum destino está agendado


class SlotSequencia(CamelModel):
    conteudo_id: UUID
    planned_at: datetime


class Pulado(CamelModel):
    planned_at: datetime
    motivo: Literal["passado", "conflito"]
    destino_id: UUID | None


class Inelegivel(CamelModel):
    conteudo_id: UUID
    code: str
    message: str


class Previa(CamelModel):
    intervalo_min: int  # o intervalo mínimo da conta (minutos) usado nos conflitos
    slots: list[SlotSequencia]
    pulados: list[Pulado]
    inelegiveis: list[Inelegivel]


class ConflitoIntervalo(CamelModel):
    """Um item de `details.conflitos` do 409 `intervalo_conflito`."""

    destino_id: UUID
    conteudo_id: UUID
    titulo: str
    planned_at: datetime


# ---- calendário (ampliação da 006 pela 014, R11) ----

class ConteudoCalendario(CamelModel):
    id: UUID
    origem: ConteudoOrigem
    titulo: str
    poster_url: str | None
    duration_ms: int | None
    situacao: Situacao


class PerfilCalendario(PerfilRef):
    cor: str | None = None  # 1ª cor da paleta do kit (#RRGGBB); null sem kit salvo (R14)


class CalendarioItem(Destino):
    conteudo: ConteudoCalendario
    perfil: PerfilCalendario


class SemData(CamelModel):
    """Primeiro os destinos aprovados sem data; depois os conteúdos prontos sem destino
    agendado (`destinoId`/`contaId` nulos)."""

    conteudo_id: UUID
    destino_id: UUID | None
    conta_id: UUID | None
    perfil_id: UUID
    poster_url: str | None
    titulo: str
    perfil_cor: str | None = None  # a mesma cor do PerfilCalendario
    aprovado: bool


class CalendarioOut(CamelModel):
    items: list[CalendarioItem]  # por planned_at
    sem_data: list[SemData]


# ---- spec 014: entradas de destinos e agendamentos ----

Nota = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ConteudoIds = Annotated[list[UUID], Field(min_length=1, max_length=100)]
Antecedencia = Annotated[int, Field(ge=0, le=10080)]
Horario = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class CreateDestinoIn(CamelModel):
    conta_id: UUID
    titulo: Titulo | None = None
    descricao: Descricao | None = None
    hashtags: Hashtags | None = None
    ia: IaAplicacoes | None = None


class UpdateDestinoIn(CamelModel):
    """Só os textos (não muda a aprovação, Q2 = A). A conta não muda depois de criado."""

    model_config = ConfigDict(extra="forbid")

    version: VersionNumber
    titulo: Titulo | None = None
    descricao: Descricao | None = None
    hashtags: Hashtags | None = None
    ia: IaAplicacoes | None = None
    # Spec 009 (FR-020): a proposta de texto que este save aplica (só humano).
    proposta_id: UUID | None = None


class PedirAprovacaoIn(CamelModel):
    version: VersionNumber
    nota: Nota | None = None


class RecusarIn(CamelModel):
    version: VersionNumber
    motivo: Motivo


class LoteAprovarIn(CamelModel):
    conta_id: UUID
    conteudo_ids: ConteudoIds


class LotePedirIn(LoteAprovarIn):
    nota: Nota | None = None


class AgendarIn(CamelModel):
    conteudo_id: UUID
    conta_id: UUID
    planned_at: datetime  # sem offset = horário local (APP_TZ)
    modo: Modo
    antecedencia_min: Antecedencia | None = None
    destino_version: VersionNumber | None = None  # controle otimista do destino que já existe
    textos: Textos | None = None
    ia: IaAplicacoes | None = None
    ignorar_intervalo: bool = False  # "Manter mesmo assim" (409 `intervalo_conflito`)
    # 015 (Q4): agendar de novo um `falhou` incerto exige "Conferi no app e não chegou".
    confirmo_que_nao_chegou: bool | None = None
    # 015 (US3): no modo `publicar`, as escolhas da tela obrigatória da rede.
    opcoes: OpcoesTikTok | None = None


class EnviarAgoraIn(CamelModel):
    """"Enviar agora" (015, T099): agenda com `planned_at = agora` num modo automático."""

    version: VersionNumber
    modo: Modo = Modo.criar_rascunho
    conferi_no_app: bool | None = None  # Q4: obrigatório se a última falha foi incerta
    opcoes: OpcoesTikTok | None = None  # modo `publicar` (US3): a tela obrigatória


class EnviarAgoraOut(CamelModel):
    destino: Destino
    aviso: str | None  # ex.: interruptor desligado (fica pausado)


class ReagendarIn(CamelModel):
    version: VersionNumber
    planned_at: datetime | None = None
    modo: Modo | None = None
    antecedencia_min: Antecedencia | None = None
    ignorar_intervalo: bool = False
    confirmo_que_nao_chegou: bool | None = None  # 015 (Q4)
    opcoes: OpcoesTikTok | None = None  # 015 (US3): trocar as escolhas do `publicar`


class LoteReagendarItem(CamelModel):
    destino_id: UUID
    version: VersionNumber
    planned_at: datetime
    confirmo_que_nao_chegou: bool | None = None  # 015 (Q4), por item


class LoteReagendarIn(CamelModel):
    itens: Annotated[list[LoteReagendarItem], Field(min_length=1, max_length=100)]
    ignorar_intervalo: bool = False


class LoteCancelarItem(CamelModel):
    destino_id: UUID
    version: VersionNumber


class LoteCancelarIn(CamelModel):
    itens: Annotated[list[LoteCancelarItem], Field(min_length=1, max_length=100)]


class SequenciaIn(CamelModel):
    conta_id: UUID
    conteudo_ids: ConteudoIds  # na ordem da sequência
    inicio: date  # primeira data (local, APP_TZ)
    horarios: Annotated[list[Horario], Field(min_length=1, max_length=6)]  # "HH:MM"
    modo: Modo
    # T101: a IA escreve os textos depois; sem isso, item TikTok sem descrição é pulado.
    gerar_textos: bool = False


class SequenciaConfirmarIn(SequenciaIn):
    esperado: Annotated[list[SlotSequencia], Field(max_length=100)]  # os slots da prévia
