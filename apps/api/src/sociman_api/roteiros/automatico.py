"""A escolha automática da opção 1 do keyframe (research R9, FR-037): o **único** chamador de
`geracao.service.escolher_automatico` (guarda AST).

Roda no gancho `rodando → revisao` do `cena.keyframe` e quando a máquina passa por uma geração
em revisão com o portão KEYFRAMES desligado (ou no modo automático). As três conferências (o
passo, o roteiro e o modo) são do `escolher_automatico`, na mesma transação; aqui só há o
savepoint: uma recusa (ou uma cena `usada` que não aceita a troca) não desfaz a transição que
chamou.
"""

import logging

from sqlalchemy.orm import Session

from sociman_api.errors import ApiError
from sociman_api.geracao.models import Geracao, GeracaoStatus
from sociman_api.geracao.service import EscolhaRecusada, escolher_automatico

log = logging.getLogger("sociman.gerador")


def tentar(db: Session, geracao: Geracao) -> bool:
    """Escolhe a opção 1 se o roteiro pede (devolve se escolheu)."""
    if geracao.status != GeracaoStatus.revisao or geracao.passo != "cena.keyframe":
        return False
    try:
        with db.begin_nested():
            escolher_automatico(db, geracao)
        return True
    except EscolhaRecusada:
        return False
    except ApiError as exc:
        log.info("escolha automática da geração %s recusada: %s", geracao.id, exc.code)
        return False
