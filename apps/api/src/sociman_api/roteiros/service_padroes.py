"""Modo e portões padrão dos roteiros de um perfil (FR-010, data-model `roteiro_padroes`).

Sem linha, vale o padrão do código (`revisar`, todos os portões ligados) com `version 0`, como a
`cena_padroes` da 010. O `PUT` cria (com a `version` 0) ou atualiza a linha, com histórico
(`entity_type = "roteiro_padroes"`). Dono e membro editam (FR-010). Vale para os roteiros novos;
os que já existem guardam os seus.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, versions_out
from sociman_api.roteiros import schemas
from sociman_api.roteiros.models import ENTITY_PADROES, PORTOES_PADRAO, RoteiroModo, RoteiroPadroes

LABEL = "O padrão dos roteiros"


def _out(perfil_id: uuid.UUID, row: RoteiroPadroes | None) -> schemas.RoteiroPadroes:
    if row is None:
        return schemas.RoteiroPadroes(perfil_id=perfil_id, modo=RoteiroModo.revisar,
                                      portoes=schemas.portoes_de(PORTOES_PADRAO), version=0)
    return schemas.RoteiroPadroes(perfil_id=perfil_id, modo=row.modo,
                                  portoes=schemas.portoes_de({**PORTOES_PADRAO, **row.portoes}),
                                  version=row.version)


def _conflito(versao_atual: int) -> ApiError:
    return ApiError(409, "version_conflict", f"{LABEL} foi alterado por outra pessoa; "
                    "recarregue", details={"versaoAtual": versao_atual})


def obter(db: Session, perfil_id: uuid.UUID) -> schemas.RoteiroPadroes:
    get_perfil_or_404(db, perfil_id)
    return _out(perfil_id, db.get(RoteiroPadroes, perfil_id))


def salvar(db: Session, actor: Actor, perfil_id: uuid.UUID,
           body: schemas.RoteiroPadroesIn) -> schemas.RoteiroPadroes:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    row = db.get(RoteiroPadroes, perfil_id, with_for_update=True)
    atual = row.version if row is not None else 0
    if body.version != atual:
        raise _conflito(atual)
    portoes = body.portoes.model_dump()
    if row is None:
        row = RoteiroPadroes(perfil_id=perfil_id, modo=body.modo, portoes=portoes,
                             created_by=actor.user_id, updated_by=actor.user_id)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:  # outro PUT com `version 0` criou a linha antes
            raise _conflito(1) from None
        history.record(db, actor, ENTITY_PADROES, row, "created", None, history.snapshot(row))
    else:
        before = history.snapshot(row)
        row.modo, row.portoes = body.modo, portoes
        after = history.snapshot(row)
        if after != before:
            row.updated_by = actor.user_id
            history.record(db, actor, ENTITY_PADROES, row, "updated", before, after)
    db.flush()
    return _out(perfil_id, row)


def versoes(db: Session, perfil_id: uuid.UUID) -> VersionsList:
    get_perfil_or_404(db, perfil_id)
    return versions_out(db, ENTITY_PADROES, perfil_id)
