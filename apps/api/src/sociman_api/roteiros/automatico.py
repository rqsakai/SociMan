"""A escolha automática da opção 1 do keyframe (research R9, FR-037): o **único** chamador de
`geracao.service.escolher_automatico` (guarda AST).

Roda no gancho `rodando → revisao` do `cena.keyframe` e quando a máquina passa por uma geração
em revisão com o portão KEYFRAMES desligado (ou no modo automático). As três conferências (o
passo, o roteiro e o modo) são do `escolher_automatico`, na mesma transação; aqui só há o
savepoint: uma recusa (ou uma cena `usada` que não aceita a troca) não desfaz a transição que
chamou.

Spec 031 (R3, P5): a **opção única de quadro de roteiro guiado** (o pedido de um quadro da
sequência com 1 opção, o do wizard e o da cadeia) também é aplicada pela máquina, com o ator
`system:roteiro`, como **provisória**: a cadeia segue (o quadro seguinte nasce dela), e o portão
de keyframes continua esperando a aprovação humana da sequência (`guiado.aprovar_posicao`). Nada
aqui aprova portão nem posição. Com 2 ou mais opções (o avançado), a cadeia espera a escolha
humana.
"""

import logging

from sqlalchemy.orm import Session

from sociman_api.errors import ApiError
from sociman_api.geracao.models import Geracao, GeracaoStatus
from sociman_api.geracao.service import EscolhaRecusada, escolher_automatico
from sociman_api.roteiros import estado

log = logging.getLogger("sociman.gerador")


def opcao_unica_de_quadro(geracao: Geracao) -> bool:
    """O pedido de um quadro da sequência do guiado com 1 opção (R3)."""
    return estado.extras(geracao).get("quadro") is not None and geracao.n_opcoes == 1


def tentar(db: Session, geracao: Geracao) -> bool:
    """Escolhe a opção 1 se o roteiro pede (devolve se escolheu)."""
    if geracao.status != GeracaoStatus.revisao or geracao.passo != "cena.keyframe":
        return False
    try:
        with db.begin_nested():
            escolher_automatico(db, geracao, opcao_unica=opcao_unica_de_quadro(geracao))
        return True
    except EscolhaRecusada:
        return False
    except ApiError as exc:
        log.info("escolha automática da geração %s recusada: %s", geracao.id, exc.code)
        return False
