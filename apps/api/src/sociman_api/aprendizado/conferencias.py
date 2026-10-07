"""Conferências do checklist do diagnóstico (spec 023, US5; FR-049; research R10).

O dono marca, por post, o que conferiu no app da rede (`ok`, `problema` ou `nao_sei`, com nota).
Versionado com `history` (`aprendizado_conferencia`); não cria tarefa nem mexe em destino.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.aprendizado import schemas
from sociman_api.aprendizado.diagnostico import CHECKLIST, conferencias_out
from sociman_api.aprendizado.models import Conferencia, ConferenciaResultado
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.metricas.models import Serie, VideoRede

ENTITY = "aprendizado_conferencia"
LABEL = "Esta conferência"


def put(db: Session, actor: Actor, video_id: uuid.UUID, item: str,
        body: schemas.AprendizadoConferenciaPut) -> schemas.AprendizadoConferencia:
    if item not in CHECKLIST:
        raise ApiError(400, "item_invalido", "Item fora do checklist")
    vivo = db.scalar(select(VideoRede.id).join(Serie, Serie.id == VideoRede.serie_id)
                     .where(VideoRede.id == video_id, Serie.anonimizada_em.is_(None)))
    if vivo is None:
        raise ApiError(404, "not_found", "Post não encontrado")
    c = db.scalar(select(Conferencia).where(Conferencia.video_id == video_id,
                                            Conferencia.item == item).with_for_update())
    resultado = ConferenciaResultado(body.resultado)
    if c is None:
        if body.version != 0:
            raise ApiError(409, "version_conflict", f"{LABEL} foi alterada; recarregue",
                           details={"versaoAtual": 0})
        c = Conferencia(video_id=video_id, item=item, resultado=resultado, nota=body.nota or None,
                        created_by=actor.user_id, updated_by=actor.user_id)
        db.add(c)
        db.flush()
        history.record(db, actor, ENTITY, c, "created", None, history.snapshot(c))
    else:
        history.check_version(c, body.version, LABEL)
        before = history.snapshot(c)
        c.resultado, c.nota = resultado, body.nota or None
        after = history.snapshot(c)
        if after != before:
            c.updated_by = actor.user_id
            history.record(db, actor, ENTITY, c, "updated", before, after)
    db.flush()
    db.refresh(c)
    return next(x for x in conferencias_out(db, video_id) if x.item == item)
