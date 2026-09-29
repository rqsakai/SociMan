"""Trilha `lembretes` do agendador (research R10): notificação "Hora de postar".

A cada `AGENDADOR_LEMBRETES_S`, o agendador chama `rodar(db)` com uma sessão própria e faz o
commit no fim da volta. Busca `agendado AND planned_at <= now() AND lembrado_em IS NULL` (com
`SKIP LOCKED`), cria **uma** `hora_de_postar` para o autor e os donos e marca `lembrado_em` na
mesma transação. Remarcar zera `lembrado_em` (service), e a `dedupe_key` leva o horário: um
reinício no meio não duplica o aviso.

Nenhum job muda uma postagem para `postado` (princípio I): isto só avisa.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.cortes.models import Corte
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo
from sociman_api.perfis.models import Conta, Platform
from sociman_api.perfis.platforms import PLATFORMS
from sociman_api.postagem.models import EstadoPostagem, Postagem

log = logging.getLogger("sociman.agendador.lembretes")

LOTE = 50


def _plataforma(conta: Conta) -> str:
    if conta.platform == Platform.outra and conta.platform_name:
        return conta.platform_name
    return PLATFORMS[conta.platform].label


def rodar(db: Session) -> int:
    """Uma volta da trilha; devolve quantos lembretes criou (0 = nada a fazer)."""
    agora = datetime.now(UTC)
    rows = db.execute(
        select(Postagem, Conta, Corte)
        .join(Conta, Conta.id == Postagem.conta_id)
        .join(Corte, Corte.id == Postagem.corte_id)
        .where(Postagem.estado == EstadoPostagem.agendado, Postagem.planned_at <= agora,
               Postagem.lembrado_em.is_(None), Postagem.archived_at.is_(None))
        .order_by(Postagem.planned_at, Postagem.id)
        .limit(LOTE)
        .with_for_update(of=Postagem, skip_locked=True)
    ).all()
    for postagem, conta, corte in rows:
        assert postagem.planned_at is not None  # garantido pelo filtro (e pelo check)
        nome = postagem.titulo or corte.openshorts_title or corte.hook_text or "seu corte"
        autor = postagem.updated_by or postagem.created_by
        notificacoes.criar(
            db, NotificacaoTipo.hora_de_postar,
            titulo=f"Hora de postar: {nome} no {_plataforma(conta)}",
            corpo=f"@{conta.handle}: copie os textos e baixe o vídeo",
            link=f"/app/cortes/{postagem.corte_id}",
            entidade=("postagem", postagem.id),
            dedupe_key=f"hora_de_postar:{postagem.id}:{postagem.planned_at.isoformat()}",
            destinatarios=notificacoes.destinatarios_padrao(db, autor),
        )
        postagem.lembrado_em = agora
    if rows:
        log.info("lembretes: %d \"Hora de postar\" criados", len(rows))
    return len(rows)
