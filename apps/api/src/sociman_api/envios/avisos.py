"""Notificações dos envios (research R11): pronto, sem clipes, falhou, confirmar qualidade e
OpenShorts fora. Vão para o autor do envio e os donos ativos, com `dedupe_key` por rodada de
envio (`sent_at`): um reinício do agendador no meio não duplica o aviso, e um "tentar de novo"
gera um aviso novo.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy.orm import Session

from sociman_api.envios.models import Envio
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo


def link(envio: Envio) -> str:
    return f"/app/envios/{envio.id}"


def autor(envio: Envio) -> uuid.UUID | None:
    """Quem fez a última ação humana (enviar, confirmar, tentar de novo) ou quem selecionou."""
    return envio.updated_by or envio.created_by


def _rodada(envio: Envio) -> str:
    sent = envio.sent_at
    return sent.isoformat() if isinstance(sent, datetime) else "sem-data"


def _titulo(envio: Envio) -> str:
    return envio.source_title if len(envio.source_title) <= 80 else envio.source_title[:79] + "…"


def notificar(db: Session, envio: Envio, tipo: NotificacaoTipo, titulo: str,
              corpo: str = "") -> int:
    return notificacoes.criar(
        db, tipo, titulo, corpo, link(envio), ("envio", envio.id),
        f"{tipo.value}:{envio.id}:{_rodada(envio)}",
        notificacoes.destinatarios_padrao(db, autor(envio)),
    )


def pronto(db: Session, envio: Envio) -> int:
    n = envio.clips_importados
    return notificar(db, envio, NotificacaoTipo.envio_pronto,
                     f"Clipes prontos: {_titulo(envio)}",
                     f"{n} clipe{'s' if n != 1 else ''} para revisar")


def sem_clipes(db: Session, envio: Envio) -> int:
    return notificar(db, envio, NotificacaoTipo.envio_sem_clipes,
                     f"Sem clipes: {_titulo(envio)}", envio.error_message or "")


def falhou(db: Session, envio: Envio) -> int:
    return notificar(db, envio, NotificacaoTipo.envio_falhou,
                     f"O envio falhou: {_titulo(envio)}", envio.error_message or "")


def confirmar_qualidade(db: Session, envio: Envio) -> int:
    return notificar(db, envio, NotificacaoTipo.envio_confirmar_qualidade,
                     f"Confirme a qualidade: {_titulo(envio)}", envio.error_message or "")


def openshorts_fora(db: Session, desde: datetime, envios: Iterable[Envio]) -> int:
    """Uma por período fora do ar (a chave é o início do período), para os autores e donos."""
    destinatarios: list[uuid.UUID] = []
    for envio in envios:
        destinatarios += notificacoes.destinatarios_padrao(db, autor(envio))
    return notificacoes.criar(
        db, NotificacaoTipo.openshorts_fora, "O OpenShorts está fora do ar",
        "Os envios continuam na fila e voltam sozinhos quando ele responder.", "/app/envios",
        None, f"openshorts_fora:{desde.isoformat()}", destinatarios,
    )
