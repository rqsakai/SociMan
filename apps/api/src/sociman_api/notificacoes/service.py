"""Notificações (research R11): criar com dedupe, destinatários, listar e marcar como lidas.

As trilhas do agendador e as rotas chamam `criar` na mesma transação da mudança que notifica
(sem commit aqui). A `dedupe_key` (ex.: `hora_de_postar:<postagem>:<planned_at>`) é única por
usuário: repetir a chamada depois de um reinício não duplica o aviso. Nada é apagado.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sociman_api.auth.models import User, UserRole
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo

LIMIT_PADRAO = 30
LIMIT_MAX = 100


def donos_ativos(db: Session) -> list[uuid.UUID]:
    """Os donos ativos, na ordem de criação (spec 014: `aprovacao_pedida`)."""
    return list(db.scalars(
        select(User.id)
        .where(User.role == UserRole.dono, User.is_active.is_(True))
        .order_by(User.created_at, User.id)
    ))


def destinatarios_padrao(db: Session, autor_id: uuid.UUID | None) -> list[uuid.UUID]:
    """O autor da ação (se houver) e os donos ativos, sem repetir, nessa ordem."""
    donos = donos_ativos(db)
    ids = [autor_id] if autor_id is not None else []
    ids += [d for d in donos if d != autor_id]
    return ids


def criar(
    db: Session,
    tipo: NotificacaoTipo,
    titulo: str,
    corpo: str,
    link: str,
    entidade: tuple[str, uuid.UUID | None] | None,
    dedupe_key: str,
    destinatarios: Iterable[uuid.UUID],
) -> int:
    """Uma linha por destinatário; devolve quantas foram criadas (as repetidas são ignoradas)."""
    entity_type, entity_id = entidade if entidade is not None else (None, None)
    rows = [
        {"user_id": user_id, "tipo": tipo, "titulo": titulo, "corpo": corpo, "link": link,
         "entity_type": entity_type, "entity_id": entity_id, "dedupe_key": dedupe_key}
        for user_id in dict.fromkeys(destinatarios)
    ]
    if not rows:
        return 0
    stmt = (
        insert(Notificacao)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
        .returning(Notificacao.id)
    )
    return len(db.execute(stmt).all())


def nao_lidas(db: Session, user_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notificacao)
        .where(Notificacao.user_id == user_id, Notificacao.lida_em.is_(None))
    ) or 0


def listar(
    db: Session,
    user_id: uuid.UUID,
    after: int | None = None,
    limit: int = LIMIT_PADRAO,
    so_nao_lidas: bool = False,
) -> list[Notificacao]:
    """Do usuário, mais recentes primeiro. `after` (id) traz só as posteriores (polling)."""
    stmt = select(Notificacao).where(Notificacao.user_id == user_id)
    if after is not None:
        stmt = stmt.where(Notificacao.id > after)
    if so_nao_lidas:
        stmt = stmt.where(Notificacao.lida_em.is_(None))
    stmt = stmt.order_by(Notificacao.id.desc()).limit(min(max(limit, 1), LIMIT_MAX))
    return list(db.scalars(stmt))


def marcar_lidas(
    db: Session, user_id: uuid.UUID, ids: Iterable[int] | None = None, todas: bool = False
) -> int:
    """Só preenche `lida_em` (nunca apaga), e só nas do próprio usuário. Devolve as não lidas."""
    stmt = (
        update(Notificacao)
        .where(Notificacao.user_id == user_id, Notificacao.lida_em.is_(None))
        .values(lida_em=datetime.now(UTC))
    )
    if not todas:
        stmt = stmt.where(Notificacao.id.in_(list(ids or [])))
    db.execute(stmt)
    return nao_lidas(db, user_id)
