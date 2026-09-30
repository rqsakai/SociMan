"""Interface de executor por rede (research R20 da spec 015, FR-013).

A parte genérica de `publicacao/` (trilha, conexões, service) fala **só** com o que está aqui:
o `ExecutorRede` de cada rede vem de `registro.executor_para(platform)`, e nenhum módulo fora de
`registro.py` importa `publicacao.<rede>` (guarda R16.2). Por isso ficam aqui também os tipos que
atravessam a fronteira: resultados, erros tipados do cliente HTTP e o formato do motivo em pt-BR (R19). O
OAuth de cada rede é um módulo (`publicacao/<rede>/oauth.py`), exposto por `executor.oauth`.

A máquina de estados (R7, R8), o interruptor, os vencidos, o histórico e os avisos ficam na
trilha e valem para qualquer rede.
"""

import enum
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from sociman_api.conteudos.models import Modo
from sociman_api.perfis.models import Platform

if TYPE_CHECKING:
    from sociman_api.publicacao.models import Tentativa


# ---- erros tipados do cliente HTTP de uma rede (o texto já passou por `redact`) ----

class RedeErro(Exception):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.status = status


class PedidoProibido(RedeErro):
    """Pedido fora da lista fechada do cliente, ou para host não permitido (princípio I)."""


class ConexaoPerdida(RedeErro):
    """A autorização não vale mais (refresh revogado ou vencido): a conta precisa reconectar."""


class ConexaoIndisponivel(RedeErro):
    """O pedido não chegou à rede, ou ela respondeu 5xx: tentar na próxima volta."""


class SemResposta(RedeErro):
    """O pedido saiu e a resposta não veio: a rede pode ter processado (no init, `incerta`)."""


class RecusaRede(RedeErro):
    """A rede recusou. `codigo` é o código cru (vai para `codigo_rede`)."""

    def __init__(self, codigo: str, mensagem: str = "", status: int | None = None,
                 log_id: str | None = None):
        super().__init__(f"rede recusou ({codigo}): {mensagem}".rstrip(": "), status)
        self.codigo = codigo
        self.log_id = log_id


# ---- motivo em pt-BR e ação possível (R19) ----

class Acao(enum.StrEnum):
    tentar_de_novo = "tentar_de_novo"
    tentar_de_novo_conferido = "tentar_de_novo_conferido"  # incerta: conferir no app antes
    reagendar = "reagendar"
    reconectar = "reconectar"
    trocar_video = "trocar_video"
    deixar_privada = "deixar_privada"
    verificar_app = "verificar_app"
    esperar = "esperar"  # espera automática (sem vaga, taxa)


@dataclass(frozen=True)
class Motivo:
    motivo: str
    acao: Acao


# Situações do próprio SociMan (sem código da rede).
SEM_RESPOSTA = Motivo("A rede pode ter recebido; confira no app antes de tentar de novo",
                      Acao.tentar_de_novo_conferido)
SEM_CONFIRMACAO = Motivo("A rede não confirmou o envio; confira no app antes de tentar de novo",
                         Acao.tentar_de_novo_conferido)
LINK_EXPIRADO = Motivo("O envio parou no meio e o link de envio expirou; tente de novo",
                       Acao.tentar_de_novo)
LINK_EXPIRADO_INTERRUPTOR = Motivo(
    "O envio foi interrompido pelo interruptor e o link de envio expirou; tente de novo",
    Acao.tentar_de_novo)
VIDEO_MUDOU = Motivo("O vídeo mudou durante o envio; tente de novo", Acao.tentar_de_novo)
SEM_DECISAO_HUMANA = Motivo("Agendamento sem decisão humana", Acao.reagendar)


# ---- resultados dos passos do envio ----

@dataclass(frozen=True)
class Iniciado:
    publish_id: str
    upload_url: str = field(repr=False)  # leva o token de upload: cifrar antes de gravar


@dataclass(frozen=True)
class SemVaga:
    """A rede respondeu que não criou nada por falta de vaga (o init pode sair de novo)."""

    codigo: str | None = None
    motivo: str = ""
    proxima_em: datetime | None = None


@dataclass(frozen=True)
class Recusado:
    """`motivo` em pt-BR e `acao` (valor de `Acao`), R19. `adiar_s`: a rede não criou nada e
    pediu para esperar (taxa); a trilha adia sem gastar a tentativa."""

    codigo: str
    motivo: str
    acao: str
    adiar_s: int | None = None


@dataclass(frozen=True)
class EmAndamento:
    status: str
    detalhes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Entregue:
    status: str


@dataclass(frozen=True)
class Publicado:
    status: str
    post_id: str | None = None


@dataclass(frozen=True)
class Problema:
    campo: str
    mensagem: str


@dataclass(frozen=True)
class Contexto:
    """O que um passo precisa: o cliente HTTP da rede (None = o padrão do executor) e o token
    válido (`conexoes.token_valido`, R5)."""

    client: Any
    token: Callable[[], str]


class ExecutorRede(Protocol):
    rede: Platform
    modos: frozenset[Modo]  # camada 2 das capacidades (R12)
    escopos_por_modo: Mapping[Modo, str]
    oauth: Any  # módulo `publicacao/<rede>/oauth.py` (URL, troca, refresh, revogação)

    def novo_cliente(self, transport: Any = None) -> Any: ...

    def iniciar(self, ctx: Contexto, tentativa: "Tentativa",
                snapshot: Mapping[str, Any] | None) -> Iniciado | SemVaga | Recusado: ...

    def enviar_parte(self, ctx: Contexto, tentativa: "Tentativa", upload_url: str,
                     indice: int, inicio: int, dados: bytes) -> Recusado | None: ...

    def consultar(self, ctx: Contexto, tentativa: "Tentativa"
                  ) -> EmAndamento | Entregue | Publicado | Recusado: ...

    def validar_opcoes(self, opcoes: Any, criador: Any) -> Sequence[Any]: ...

    def consultar_criador(self, ctx: Contexto) -> Any: ...

    def traduzir(self, codigo: str | None) -> Motivo: ...
