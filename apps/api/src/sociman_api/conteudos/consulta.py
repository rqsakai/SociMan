"""A **única** definição dos campos derivados do conteúdo e do estado efetivo do destino
(data-model.md da spec 014, "Campos derivados" e "Estado efetivo"; research R1 e R3).

Nada aqui é gravado: a lista, o filtro, os atalhos, o detalhe, o calendário e o corte usam
estas expressões no `WHERE` e no `SELECT`, e por isso o chip e o filtro nunca divergem.

Spec 015 (data-model, "Estado efetivo"): `pausado`, `vencido` e `aguardando_vaga` são
derivados (relógio, interruptor e última tentativa); `enviando` vem do estado gravado; `atencao`
ganha "Conta não conectada" e "Conta precisa reconectar" nos modos automáticos. O nível do
servidor do interruptor (`PUBLICACAO_HABILITADA`) entra como parâmetro, lido do `Settings`.

As expressões pressupõem, na consulta de quem chama:
- `Conteudo` com `LEFT JOIN cortes ON cortes.id = conteudos.corte_id` (`join_corte`);
- para as do destino, também `Postagem` (destino) e `Conta` (`JOIN contas`).
"""

import enum
from datetime import datetime, timedelta

from sqlalchemy import (
    ColumnElement,
    Select,
    Text,
    and_,
    case,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
)

from sociman_api.config import get_settings
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem, Modo
from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.perfis.models import Conta, ContaStatus
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao.models import (
    Conexao,
    ConexaoEstado,
    PublicacaoConfig,
    Tentativa,
    TentativaFase,
)

ATRASO = timedelta(hours=24)  # `a_postar` vira `atrasado` depois de 24 h
JANELA_ENVIO = timedelta(hours=1)  # automático vencido há mais que isso pede confirmação (R11)
AUTOMATICOS = (Modo.criar_rascunho, Modo.publicar, Modo.rascunho_e_publicar)
FASES_ABERTAS = (TentativaFase.iniciando, TentativaFase.enviando_partes,
                 TentativaFase.processando)
FASES_PAUSAVEIS = (TentativaFase.iniciando, TentativaFase.enviando_partes)


class Situacao(enum.StrEnum):
    em_revisao = "em_revisao"
    processando = "processando"
    pronto = "pronto"
    erro_marca = "erro_marca"


class EstadoEfetivo(enum.StrEnum):
    pronto = "pronto"  # `pendente` com o conteúdo pronto
    aprovacao_pedida = "aprovacao_pedida"
    aprovado = "aprovado"
    agendado = "agendado"
    a_postar = "a_postar"
    atrasado = "atrasado"
    atencao = "atencao"
    postado = "postado"
    rascunho_criado = "rascunho_criado"
    publicado = "publicado"
    falhou = "falhou"
    em_revisao = "em_revisao"
    arquivado = "arquivado"
    # spec 015
    enviando = "enviando"
    pausado = "pausado"
    vencido = "vencido"
    aguardando_vaga = "aguardando_vaga"


SEM_CONTA = "sem_conta"  # estado do conteúdo sem destino ativo (filtro `estado=sem_conta`)

MOTIVOS_ATENCAO = {
    "arquivada": "Conta arquivada",
    ContaStatus.pausada: "Conta pausada",
    ContaStatus.encerrada: "Conta encerrada",
    "nao_conectada": "Conta não conectada",
    ConexaoEstado.precisa_reconectar: "Conta precisa reconectar",
}


def join_corte(query: Select) -> Select:
    """`LEFT JOIN cortes` (vazio no vídeo próprio)."""
    return query.outerjoin(Corte, Corte.id == Conteudo.corte_id)


# ---- conteúdo ----

def situacao() -> ColumnElement[str]:
    return case(
        (Conteudo.origem == ConteudoOrigem.video_proprio, literal(Situacao.pronto.value)),
        (Corte.status == CorteStatus.revisao, literal(Situacao.em_revisao.value)),
        (Corte.status.in_([CorteStatus.na_fila, CorteStatus.processando]),
         literal(Situacao.processando.value)),
        (Corte.status == CorteStatus.pronto, literal(Situacao.pronto.value)),
        else_=literal(Situacao.erro_marca.value),
    )


def pronto() -> ColumnElement[bool]:
    return or_(Conteudo.origem == ConteudoOrigem.video_proprio,
               Corte.status == CorteStatus.pronto)


def arquivado() -> ColumnElement[bool]:
    """Na origem corte vale o do corte (o do conteúdo fica null, `ck_conteudos_origem`)."""
    return or_(Corte.archived_at.is_not(None), Conteudo.archived_at.is_not(None))


def poster_key() -> ColumnElement[str | None]:
    return func.coalesce(Corte.poster_key, Conteudo.poster_key)


def duration_ms() -> ColumnElement[int | None]:
    return func.coalesce(Corte.duration_ms, Conteudo.duration_ms)


def video_ref() -> ColumnElement[str | None]:
    """O vídeo final: `cortes.result_key` ou `conteudos.video_key`."""
    return func.coalesce(Corte.result_key, Conteudo.video_key)


def sem_conta() -> ColumnElement[bool]:
    """Nenhum destino ativo (não arquivado)."""
    return ~exists().where(Postagem.conteudo_id == Conteudo.id,
                           Postagem.archived_at.is_(None))


# ---- destino ----

def conta_em_atencao() -> ColumnElement[bool]:
    return or_(Conta.archived_at.is_not(None),
               Conta.status.in_([ContaStatus.pausada, ContaStatus.encerrada]))


def automatico() -> ColumnElement[bool]:
    return Postagem.modo.in_(AUTOMATICOS)


def conexao_estado() -> ColumnElement[str | None]:
    """O estado da conexão viva da conta do destino (null = não conectada)."""
    return (
        select(cast(Conexao.estado, Text))
        .where(Conexao.conta_id == Postagem.conta_id,
               Conexao.estado != ConexaoEstado.desconectada)
        .correlate(Postagem)
        .limit(1)
        .scalar_subquery()
    )


def sem_conexao() -> ColumnElement[bool]:
    """Modo automático sem conexão `conectada` (não conectada ou precisa reconectar)."""
    return or_(conexao_estado().is_(None),
               conexao_estado() != ConexaoEstado.conectada.value)


def motivo_atencao() -> ColumnElement[str | None]:
    """A conta primeiro; nos modos automáticos, depois, a conexão."""
    return case(
        (Conta.archived_at.is_not(None), literal(MOTIVOS_ATENCAO["arquivada"])),
        (Conta.status == ContaStatus.pausada, literal(MOTIVOS_ATENCAO[ContaStatus.pausada])),
        (Conta.status == ContaStatus.encerrada,
         literal(MOTIVOS_ATENCAO[ContaStatus.encerrada])),
        (and_(automatico(), conexao_estado() == ConexaoEstado.precisa_reconectar.value),
         literal(MOTIVOS_ATENCAO[ConexaoEstado.precisa_reconectar])),
        (and_(automatico(), sem_conexao()), literal(MOTIVOS_ATENCAO["nao_conectada"])),
        else_=None,
    )


# ---- execução (spec 015) ----

def ultima_fase() -> ColumnElement[str | None]:
    return (
        select(cast(Tentativa.fase, Text))
        .where(Tentativa.destino_id == Postagem.id)
        .correlate(Postagem)
        .order_by(Tentativa.numero.desc())
        .limit(1)
        .scalar_subquery()
    )


def _vaga_em() -> ColumnElement[datetime | None]:
    """`proxima_em` da última tentativa, se ela terminou `sem_vaga` (a espera da rede)."""
    return (
        select(case((Tentativa.fase == TentativaFase.sem_vaga, Tentativa.proxima_em),
                    else_=None))
        .where(Tentativa.destino_id == Postagem.id)
        .correlate(Postagem)
        .order_by(Tentativa.numero.desc())
        .limit(1)
        .scalar_subquery()
    )


def horario_envio() -> ColumnElement[datetime]:
    """O horário que vale para a trilha: o agendado, ou o fim da espera por vaga (a espera do
    próprio sistema não faz o destino "vencer")."""
    return func.greatest(Postagem.planned_at, func.coalesce(_vaga_em(), Postagem.planned_at))


def aguardando_vaga(agora: datetime | None = None) -> ColumnElement[bool]:
    now = func.now() if agora is None else literal(agora)
    # coalesce: sem tentativa `sem_vaga` a comparação é NULL, e `NOT NULL` sumiria da trilha.
    return and_(Postagem.estado == DestinoEstado.agendado,
                func.coalesce(_vaga_em() > now, literal(False)))


def tem_tentativa_aberta(fases=FASES_ABERTAS) -> ColumnElement[bool]:
    return exists().where(Tentativa.destino_id == Postagem.id, Tentativa.fase.in_(fases))


def interruptor_desligado() -> ColumnElement[bool]:
    """Qualquer nível desligado: o do servidor (parâmetro) ou o botão (`publicacao_config`)."""
    if not get_settings().publicacao_habilitada:
        return literal(True)
    botao = select(PublicacaoConfig.envios_habilitados).where(PublicacaoConfig.id == 1) \
        .scalar_subquery()
    return func.coalesce(botao, literal(False)).is_(False)


def vencido(agora: datetime | None = None) -> ColumnElement[bool]:
    now = func.now() if agora is None else literal(agora)
    return and_(Postagem.estado == DestinoEstado.agendado, automatico(),
                horario_envio() <= now - JANELA_ENVIO,
                or_(Postagem.envio_confirmado_em.is_(None),
                    Postagem.envio_confirmado_em < Postagem.planned_at),
                ~tem_tentativa_aberta())


def pausado(agora: datetime | None = None) -> ColumnElement[bool]:
    now = func.now() if agora is None else literal(agora)
    return and_(interruptor_desligado(), or_(
        and_(Postagem.estado == DestinoEstado.agendado, automatico(),
             horario_envio() <= now),
        and_(Postagem.estado == DestinoEstado.enviando,
             tem_tentativa_aberta(FASES_PAUSAVEIS)),
    ))


def estado_efetivo(agora: datetime | None = None) -> ColumnElement[str]:
    """Na ordem: `arquivado` → `em_revisao` → `atencao` → `pausado` → `vencido` →
    `aguardando_vaga` → `atrasado` → `a_postar` → estado gravado (`pendente` aparece como
    `pronto`; `enviando` como está). `agora` fixa o relógio (padrão: `now()`)."""
    now = func.now() if agora is None else literal(agora)
    agendado = Postagem.estado == DestinoEstado.agendado
    lembrete = Postagem.modo == Modo.lembrete
    return case(
        (or_(Postagem.archived_at.is_not(None), arquivado()),
         literal(EstadoEfetivo.arquivado.value)),
        (~pronto(), literal(EstadoEfetivo.em_revisao.value)),
        (and_(agendado, or_(conta_em_atencao(), and_(automatico(), sem_conexao()))),
         literal(EstadoEfetivo.atencao.value)),
        (pausado(agora), literal(EstadoEfetivo.pausado.value)),
        (vencido(agora), literal(EstadoEfetivo.vencido.value)),
        (aguardando_vaga(agora), literal(EstadoEfetivo.aguardando_vaga.value)),
        (and_(agendado, lembrete, Postagem.planned_at <= now - ATRASO),
         literal(EstadoEfetivo.atrasado.value)),
        (and_(agendado, lembrete, Postagem.planned_at <= now),
         literal(EstadoEfetivo.a_postar.value)),
        (Postagem.estado == DestinoEstado.pendente, literal(EstadoEfetivo.pronto.value)),
        else_=cast(Postagem.estado, Text),
    )


def motivo_atencao_efetivo(agora: datetime | None = None) -> ColumnElement[str | None]:
    """O motivo só quando o estado efetivo é `atencao`."""
    return case((estado_efetivo(agora) == EstadoEfetivo.atencao.value, motivo_atencao()),
                else_=None)


def video_mudou() -> ColumnElement[bool]:
    """O vídeo final mudou depois da aprovação (research R5)."""
    return and_(Postagem.aprovado_video_ref.is_not(None),
                Postagem.aprovado_video_ref.is_distinct_from(video_ref()))


def destinos_do_conteudo() -> Select:
    """`SELECT` dos destinos com o conteúdo, o corte e a conta (base das expressões acima)."""
    return join_corte(
        select(Postagem)
        .join(Conteudo, Conteudo.id == Postagem.conteudo_id)
        .join(Conta, Conta.id == Postagem.conta_id)
    )


def algum_destino(*condicoes: ColumnElement[bool]) -> ColumnElement[bool]:
    """`EXISTS` de um destino do conteúdo (da consulta externa) com as condições; correlaciona
    `Conteudo` e `Corte` com a consulta de fora."""
    return exists(
        select(Postagem.id)
        .join(Conta, Conta.id == Postagem.conta_id)
        .where(Postagem.conteudo_id == Conteudo.id, *condicoes)
        .correlate(Conteudo, Corte)
    )
