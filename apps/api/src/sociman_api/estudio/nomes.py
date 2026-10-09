"""O nome do perfil base nas listas da biblioteca (spec 029, T009): uma consulta por página,
sem N+1."""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.perfis.models import Perfil


def perfil_nomes(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return dict(db.execute(select(Perfil.id, Perfil.name).where(Perfil.id.in_(wanted))).all())
