"""Trilha `lembretes` do agendador (research R10): notificação "Hora de postar".

A cada `AGENDADOR_LEMBRETES_S`, o agendador chama `rodar(db)` com uma sessão própria e faz o
commit no fim da volta. Busca `agendado AND planned_at <= now() AND lembrado_em IS NULL` (com
`SKIP LOCKED`), cria **uma** `hora_de_postar` para o autor e os donos e marca `lembrado_em` na
mesma transação. Remarcar zera `lembrado_em` (service), e a `dedupe_key` leva o horário: um
reinício no meio não duplica o aviso.

Nenhum job muda uma postagem para `postado` (princípio I): isto só avisa.

Spec 014 (R8): só destinos no modo `lembrete` e com a conta em condição (não arquivada, nem
`pausada`, nem `encerrada`: esses ficam em "atenção" e não avisam). O título é o do destino ou,
sem ele, o do conteúdo, e o link abre o conteúdo na aba da conta. Continua sem mudar estado:
`a_postar` e `atrasado` são derivados (`conteudos/consulta.py`).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.conteudos import consulta
from sociman_api.conteudos.models import Conteudo, Modo
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo
from sociman_api.perfis.models import Conta, Platform
from sociman_api.perfis.platforms import PLATFORMS
from sociman_api.postagem.models import DestinoEstado, Postagem

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
        select(Postagem, Conta, Conteudo)
        .join(Conta, Conta.id == Postagem.conta_id)
        .join(Conteudo, Conteudo.id == Postagem.conteudo_id)
        .where(Postagem.estado == DestinoEstado.agendado, Postagem.modo == Modo.lembrete,
               Postagem.planned_at <= agora, Postagem.lembrado_em.is_(None),
               Postagem.archived_at.is_(None), ~consulta.conta_em_atencao())
        .order_by(Postagem.planned_at, Postagem.id)
        .limit(LOTE)
        .with_for_update(of=Postagem, skip_locked=True)
    ).all()
    for postagem, conta, conteudo in rows:
        assert postagem.planned_at is not None  # garantido pelo filtro (e pelo check)
        nome = postagem.titulo or conteudo.titulo or "seu conteúdo"
        autor = postagem.updated_by or postagem.created_by
        notificacoes.criar(
            db, NotificacaoTipo.hora_de_postar,
            titulo=f"Hora de postar: {nome} no {_plataforma(conta)}",
            corpo=f"@{conta.handle}: copie os textos e baixe o vídeo",
            link=f"/app/conteudos/{postagem.conteudo_id}?conta={postagem.conta_id}",
            entidade=("postagem", postagem.id),
            dedupe_key=f"hora_de_postar:{postagem.id}:{postagem.planned_at.isoformat()}",
            destinatarios=notificacoes.destinatarios_padrao(db, autor),
        )
        postagem.lembrado_em = agora
    if rows:
        log.info("lembretes: %d \"Hora de postar\" criados", len(rows))
    return len(rows)
