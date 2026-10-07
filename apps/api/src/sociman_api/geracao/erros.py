"""Erros dos motores, espera e tentativas (research R8, FR-017 e FR-018).

Cada falha vira um dos 5 códigos, com a mensagem curta em pt-BR de `MENSAGENS` (nunca o texto
cru do serviço, que vai só para o log):
- `gpu_ocupada`: volta à fila em +30 s **sem** contar tentativa e nunca vira falha;
- `sem_memoria` e `servico_fora`: volta à fila com espera crescente (30 s, 1, 2, 4, 8 e 15 min,
  o teto) e conta a tentativa; são 6 esperas, e a 7ª falha leva a `falhou`;
- `entrada_invalida` e `internal`: `falhou` na hora.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

Codigo = Literal["gpu_ocupada", "servico_fora", "sem_memoria", "entrada_invalida", "internal"]

CODIGOS: tuple[Codigo, ...] = ("gpu_ocupada", "servico_fora", "sem_memoria", "entrada_invalida",
                               "internal")
MENSAGENS: dict[str, str] = {
    "gpu_ocupada": "Aguardando a GPU ficar livre",
    "servico_fora": "O serviço de geração está fora do ar; tentando de novo",
    "sem_memoria": "A GPU ficou sem memória; tentando de novo",
    "entrada_invalida": "A entrada da geração não é válida",
    "internal": "Erro interno na geração; tente de novo",
}
# Esgotadas as tentativas, a mensagem final não promete outra volta.
MENSAGENS_FINAIS: dict[str, str] = {
    "servico_fora": "O serviço de geração ficou fora do ar em todas as tentativas",
    "sem_memoria": "A GPU ficou sem memória em todas as tentativas",
}
MAX_TENTATIVAS = 6
ESPERA_GPU = timedelta(seconds=30)
ESPERA_BASE = timedelta(seconds=30)
ESPERA_TETO = timedelta(minutes=15)
_COM_ESPERA = frozenset({"servico_fora", "sem_memoria"})


class MotorErro(Exception):
    """Falha de um motor já traduzida. `mensagem` (opcional) é um texto **nosso** em pt-BR que
    detalha a entrada inválida ("A foto de referência foi arquivada"); `detalhe` vai só para o
    log."""

    def __init__(self, codigo: Codigo, mensagem: str | None = None, detalhe: str = ""):
        super().__init__(f"{codigo}: {detalhe}" if detalhe else codigo)
        self.codigo = codigo
        self.mensagem = mensagem or MENSAGENS[codigo]
        self.detalhe = detalhe


def espera(tentativa: int) -> timedelta:
    """A espera depois da tentativa `tentativa` (1 = a 1ª): 30 s, 1, 2, 4, 8 min; teto 15 min."""
    return min(ESPERA_BASE * (2 ** max(0, tentativa - 1)), ESPERA_TETO)


@dataclass(frozen=True)
class Efeito:
    """O que fazer com a geração depois da falha."""

    acao: Literal["esperar", "falhar"]
    codigo: Codigo
    mensagem: str
    depois: timedelta | None = None  # só em "esperar"
    conta_tentativa: bool = True


def decidir(erro: MotorErro, tentativas: int) -> Efeito:
    """`tentativas` = as já contadas, incluindo a que acabou de falhar."""
    if erro.codigo == "gpu_ocupada":
        return Efeito("esperar", "gpu_ocupada", MENSAGENS["gpu_ocupada"], ESPERA_GPU,
                      conta_tentativa=False)
    if erro.codigo in _COM_ESPERA:
        if tentativas > MAX_TENTATIVAS:
            return Efeito("falhar", erro.codigo, MENSAGENS_FINAIS[erro.codigo])
        return Efeito("esperar", erro.codigo, erro.mensagem, espera(tentativas))
    return Efeito("falhar", erro.codigo, erro.mensagem)
