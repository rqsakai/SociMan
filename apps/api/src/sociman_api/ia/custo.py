"""Custo aproximado das chamadas pelo `usage` do SDK (research R7).

Tabela de preços em código (US$ por milhão de tokens), gravada em cada chamada com
`PRECOS_VERSAO`: o resumo do mês é um `SUM`, e as chamadas antigas ficam com o preço da época.
- Soma de todas as tentativas da chamada (a segunda tentativa de validação também custa).
- Com o fallback do servidor, `usage.iterations` traz uma entrada por tentativa, cada uma com o
  modelo dela; sem `iterations`, vale o `response.model`.
- Modelo fora da tabela: preço do Sonnet 5.5 e um aviso no log (o valor é aproximado mesmo).
"""

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

log = logging.getLogger(__name__)

PRECOS_VERSAO = "2026-09"
MODELO_PADRAO = "claude-sonnet-5-5"
_MILHAO = Decimal(1_000_000)
_SEIS_CASAS = Decimal("0.000001")


@dataclass(frozen=True)
class Preco:
    entrada: Decimal
    saida: Decimal
    cache_escrita: Decimal  # 5 minutos
    cache_leitura: Decimal


def _p(entrada: str, saida: str, escrita: str, leitura: str) -> Preco:
    return Preco(Decimal(entrada), Decimal(saida), Decimal(escrita), Decimal(leitura))


PRECOS: dict[str, Preco] = {
    "claude-sonnet-5-5": _p("2.00", "10.00", "2.50", "0.20"),
    # Para onde o `fallbacks: "default"` pode desviar.
    "claude-opus-5-5": _p("4.00", "20.00", "5.00", "0.20"),
}


def preco(model: str | None) -> Preco:
    p = PRECOS.get(model or "")
    if p is None:
        log.warning("modelo %r fora da tabela de preços; usando o do %s", model, MODELO_PADRAO)
        return PRECOS[MODELO_PADRAO]
    return p


@dataclass
class Uso:
    """Tokens e custo somados de todas as tentativas de uma chamada."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    custo: Decimal | None = None
    model_servido: str | None = None

    @property
    def custo_usd(self) -> Decimal | None:
        if self.custo is None:
            return None
        return self.custo.quantize(_SEIS_CASAS, rounding=ROUND_HALF_UP)


def _int(obj: Any, attr: str) -> int:
    return getattr(obj, attr, None) or 0


def _custo(p: Preco, entrada: int, saida: int, leitura: int, escrita: int) -> Decimal:
    return (entrada * p.entrada + saida * p.saida + leitura * p.cache_leitura
            + escrita * p.cache_escrita) / _MILHAO


def somar(uso: Uso, resposta: Any, model_pedido: str) -> None:
    """Acrescenta a `uso` os tokens e o custo de uma resposta do SDK (sem `usage`, nada)."""
    usage = getattr(resposta, "usage", None)
    if usage is None:
        return
    servido = getattr(resposta, "model", None) or model_pedido
    uso.model_servido = servido
    for campo, attr in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                        ("cache_read_tokens", "cache_read_input_tokens"),
                        ("cache_creation_tokens", "cache_creation_input_tokens")):
        valor = getattr(usage, attr, None)
        if valor is not None:
            setattr(uso, campo, (getattr(uso, campo) or 0) + valor)

    iteracoes = [i for i in getattr(usage, "iterations", None) or ()
                 if getattr(i, "type", None) in ("message", "fallback_message")]
    if iteracoes:
        custo = sum((_custo(preco(getattr(i, "model", None) or model_pedido),
                            _int(i, "input_tokens"), _int(i, "output_tokens"),
                            _int(i, "cache_read_input_tokens"),
                            _int(i, "cache_creation_input_tokens")) for i in iteracoes),
                    Decimal(0))
    else:
        custo = _custo(preco(servido), _int(usage, "input_tokens"),
                       _int(usage, "output_tokens"), _int(usage, "cache_read_input_tokens"),
                       _int(usage, "cache_creation_input_tokens"))
    uso.custo = (uso.custo or Decimal(0)) + custo
