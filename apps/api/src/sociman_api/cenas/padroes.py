"""Estilo e negative padrão das cenas de um perfil (data-model `cena_padroes`).

Sem linha, vale o padrão do código com `version 0` (como os guias da 017). O `PUT` cria (com a
`version` 0) ou atualiza a linha, com histórico (`entity_type = "cena_padroes"`); a reversão é
só do dono humano (a rota usa `RequireHumanOwner`).
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.cenas import schemas
from sociman_api.cenas.models import ESTILO_PADRAO, NEGATIVE_PADRAO, CenaPadroes
from sociman_api.errors import ApiError
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, target_state, versions_out

ENTITY = "cena_padroes"
LABEL = "O padrão das cenas"


def efetivos(db: Session, perfil_id: uuid.UUID) -> tuple[str, str]:
    """(estilo, negative) em vigor no perfil."""
    row = db.get(CenaPadroes, perfil_id)
    if row is None:
        return ESTILO_PADRAO, NEGATIVE_PADRAO
    return row.estilo, row.negative


def _out(perfil_id: uuid.UUID, row: CenaPadroes | None) -> schemas.CenaPadroes:
    estilo, negative = (row.estilo, row.negative) if row is not None \
        else (ESTILO_PADRAO, NEGATIVE_PADRAO)
    return schemas.CenaPadroes(
        perfil_id=perfil_id, estilo=estilo, negative=negative,
        version=row.version if row is not None else 0,
        padrao_codigo=schemas.CenaPadroesTexto(estilo=ESTILO_PADRAO, negative=NEGATIVE_PADRAO))


def _conflito(versao_atual: int) -> ApiError:
    return ApiError(409, "version_conflict", f"{LABEL} foi alterado por outra pessoa; "
                    "recarregue", details={"versaoAtual": versao_atual})


def obter(db: Session, perfil_id: uuid.UUID) -> schemas.CenaPadroes:
    get_perfil_or_404(db, perfil_id)
    return _out(perfil_id, db.get(CenaPadroes, perfil_id))


def salvar(db: Session, actor: Actor, perfil_id: uuid.UUID,
           body: schemas.PadroesIn) -> schemas.CenaPadroes:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    row = db.get(CenaPadroes, perfil_id, with_for_update=True)
    atual = row.version if row is not None else 0
    if body.version != atual:
        raise _conflito(atual)
    if row is None:
        row = CenaPadroes(perfil_id=perfil_id, estilo=body.estilo, negative=body.negative,
                          created_by=actor.user_id, updated_by=actor.user_id)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:  # outro PUT com `version 0` criou a linha antes
            raise _conflito(1) from None
        history.record(db, actor, ENTITY, row, "created", None, history.snapshot(row))
    else:
        before = history.snapshot(row)
        row.estilo, row.negative = body.estilo, body.negative
        after = history.snapshot(row)
        if after != before:
            row.updated_by = actor.user_id
            history.record(db, actor, ENTITY, row, "updated", before, after)
    db.flush()
    return _out(perfil_id, row)


def versoes(db: Session, perfil_id: uuid.UUID) -> VersionsList:
    get_perfil_or_404(db, perfil_id)
    return versions_out(db, ENTITY, perfil_id)


def reverter(db: Session, actor: Actor, perfil_id: uuid.UUID, version: int,
             to_version: int) -> schemas.CenaPadroes:
    get_perfil_or_404(db, perfil_id)
    row = db.get(CenaPadroes, perfil_id, with_for_update=True)
    if row is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    history.check_version(row, version, LABEL)
    state = target_state(db, ENTITY, row, to_version)
    before = history.snapshot(row)
    row.estilo, row.negative = state["estilo"], state["negative"]
    after = history.snapshot(row)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    row.updated_by = actor.user_id
    history.record(db, actor, ENTITY, row, "reverted", before, after,
                   {"from_version": to_version})
    db.flush()
    return _out(perfil_id, row)
