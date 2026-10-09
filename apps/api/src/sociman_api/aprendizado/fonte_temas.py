"""Casamento dos vídeos-fonte com os temas (spec 023, plano B do R9; migration
`0019_aprendizado_fonte_temas`).

O casamento por palavra-chave em título + descrição (sem acento, palavra inteira) custa segundos
sobre dezenas de milhares de vídeos-fonte; feito na leitura, o Descobrir passava da meta de
+300 ms (R14). A trilha `aprendizado` grava o resultado em `aprendizado_fonte_temas`:
- **refaz** o perfil inteiro quando a versão da taxonomia muda (`fonte_temas_versao`);
- **acrescenta** os vídeos-fonte novos (`first_seen_at` depois de `fonte_temas_em`).

É dado derivado (sem `version`/`history`): reconstruível a qualquer momento a partir dos temas e
dos vídeos-fonte, e nunca toca no direito do canal. Não chama a IA.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, PrimaryKeyConstraint, Uuid, delete, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from sociman_api.aprendizado import afinidade
from sociman_api.aprendizado import preferencias as prefs
from sociman_api.aprendizado.models import Tema
from sociman_api.canais.models import CanalPerfil, VideoFonte
from sociman_api.db import Base


class FonteTema(Base):
    __tablename__ = "aprendizado_fonte_temas"
    __table_args__ = (PrimaryKeyConstraint("perfil_id", "video_fonte_id", "tema_id"),)

    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"))
    video_fonte_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("videos_fonte.id"))
    tema_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aprendizado_temas.id"))



def _casar(db: Session, perfil_id: uuid.UUID, desde: datetime | None) -> int:
    """INSERT … SELECT por tema (um passe por tema sobre os vídeos do perfil)."""
    total = 0
    texto = afinidade.texto_sem_acento(VideoFonte.title, VideoFonte.description)
    canais = select(CanalPerfil.canal_id).where(CanalPerfil.perfil_id == perfil_id)
    for t in db.scalars(select(Tema).where(Tema.perfil_id == perfil_id,
                                           Tema.archived_at.is_(None))):
        if not t.palavras_chave:
            continue
        sel = (select(literal(perfil_id), VideoFonte.id, literal(t.id))
               .where(VideoFonte.canal_id.in_(canais),
                      texto.op("~")(afinidade.regex(t.palavras_chave))))
        if desde is not None:
            sel = sel.where(VideoFonte.first_seen_at > desde)
        res = db.execute(insert(FonteTema).from_select(
            ["perfil_id", "video_fonte_id", "tema_id"], sel).on_conflict_do_nothing())
        total += res.rowcount or 0
    return total


def reconstruir(db: Session, perfil_id: uuid.UUID, agora: datetime | None = None) -> int:
    """Refaz o casamento do perfil do zero (idempotente; sem commit). Devolve as linhas."""
    agora = agora or datetime.now(UTC)
    row = prefs.linha(db, perfil_id, None, lock=True)
    db.execute(delete(FonteTema).where(FonteTema.perfil_id == perfil_id))
    total = _casar(db, perfil_id, None)
    if row is not None:
        row.fonte_temas_versao, row.fonte_temas_em = row.taxonomia_versao, agora
    return total


def limpar_tema(db: Session, tema_id: uuid.UUID) -> None:
    """Arquivar ou juntar um tema tira as linhas dele na hora (o resto se refaz na trilha)."""
    db.execute(delete(FonteTema).where(FonteTema.tema_id == tema_id))


def atualizar(db: Session, agora: datetime | None = None) -> None:
    """Uma volta: cada perfil com tema ativo fica em dia (commit por perfil). A taxonomia mudou
    → reconstrói; senão, casa só os vídeos-fonte novos."""
    agora = agora or datetime.now(UTC)
    com_tema = select(Tema.perfil_id).where(Tema.archived_at.is_(None)).distinct()
    for perfil_id in list(db.scalars(com_tema)):
        row = prefs.linha(db, perfil_id, None)
        if row is None:
            continue
        if row.fonte_temas_versao != row.taxonomia_versao:
            reconstruir(db, perfil_id, agora)
        else:
            _casar(db, perfil_id, row.fonte_temas_em)
            row = prefs.linha(db, perfil_id, None, lock=True)
            row.fonte_temas_em = agora
        db.commit()


def em_dia(db: Session, perfil_id: uuid.UUID) -> bool:
    """Casado com a taxonomia atual (senão, a afinidade fica neutra: nunca o regex na leitura)."""
    row = prefs.linha(db, perfil_id, None)
    return row is not None and row.fonte_temas_versao == row.taxonomia_versao
