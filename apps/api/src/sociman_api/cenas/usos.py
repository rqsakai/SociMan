"""Vínculo cena × conteúdo vídeo próprio (research R7, FR-012, Q2).

`PUT /api/conteudos/{id}/cenas` define o conjunto de cenas do conteúdo (com a `version` do
conteúdo). O conteúdo precisa ser de origem `video_proprio`; cada cena nova no conjunto precisa
estar não arquivada e não `rascunho` (029, FR-014: de qualquer perfil base, ou sem nenhum). O serviço cria e desfaz os usos e recalcula o
status das cenas afetadas: com uso ativo → `usada`; sem nenhum → `pronta`.

Histórico nos dois lados: a cena ganha `updated` com `details.uso = {conteudoId, acao}`; o
conteúdo, `updated` com `details.cenas = {antes, depois}` (sem campo versionado novo, então o
revert do conteúdo não mexe nos usos). Nada aqui aprova, agenda ou publica.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.cenas import schemas
from sociman_api.cenas import service as cenas
from sociman_api.cenas.models import Cena, CenaStatus, CenaUso
from sociman_api.conteudos import service as conteudos_service
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.errors import ApiError

CONTEUDO = "conteudo"


def _invalido(codigo: str, mensagem: str, cena_id: uuid.UUID | None = None) -> ApiError:
    details = {"cenaId": str(cena_id)} if cena_id is not None else None
    return ApiError(422, codigo, mensagem, details=details)


def _ativos(db: Session, conteudo_id: uuid.UUID) -> dict[uuid.UUID, CenaUso]:
    rows = db.scalars(select(CenaUso).where(CenaUso.conteudo_id == conteudo_id,
                                            CenaUso.desfeito_em.is_(None))
                      .order_by(CenaUso.criado_em, CenaUso.id))
    return {u.cena_id: u for u in rows}


def resumos_do_conteudo(db: Session, conteudo_id: uuid.UUID) -> list[schemas.CenaResumo]:
    ids = list(_ativos(db, conteudo_id))
    if not ids:
        return []
    por_id = {c.id: c for c in db.scalars(select(Cena).where(Cena.id.in_(ids)))}
    return cenas.resumos_out(db, [por_id[i] for i in ids if i in por_id])


def listar(db: Session, conteudo_id: uuid.UUID) -> schemas.CenasResumoList:
    conteudos_service.get_conteudo_or_404(db, conteudo_id)
    return schemas.CenasResumoList(items=resumos_do_conteudo(db, conteudo_id))


def _recalcula(db: Session, actor: Actor, cena: Cena, conteudo_id: uuid.UUID,
               acao: str, before: dict) -> None:
    ativo = cenas.tem_uso_ativo(db, cena.id)
    if ativo and cena.status == CenaStatus.pronta:
        cena.status = CenaStatus.usada
    elif not ativo and cena.status == CenaStatus.usada:
        cena.status = CenaStatus.pronta
    cenas._record(db, actor, cena, "updated", before,
                  {"uso": {"conteudoId": str(conteudo_id), "acao": acao}}, sempre=True)


def definir(db: Session, actor: Actor, conteudo_id: uuid.UUID,
            body: schemas.UsosIn) -> schemas.UsosOut:
    conteudo = conteudos_service.get_conteudo_or_404(db, conteudo_id, lock=True)
    history.check_version(conteudo, body.version, "Este conteúdo")
    if conteudo.origem != ConteudoOrigem.video_proprio:
        raise _invalido("origem_invalida", "Só um vídeo próprio indica as cenas que o compõem")
    if conteudo.archived:
        raise ApiError(409, "conflict", "Este conteúdo está arquivado")
    cenas.perfil_ativo(db, conteudo.perfil_id)
    wanted = list(dict.fromkeys(body.cena_ids))
    ativos = _ativos(db, conteudo.id)
    novas = [i for i in wanted if i not in ativos]
    saem = [i for i in ativos if i not in wanted]
    # Ordem estável das travas (evita deadlock entre dois PUTs).
    travadas = {i: cenas.get_cena_or_404(db, i, lock=True) for i in sorted(novas + saem,
                                                                          key=str)}
    for i in novas:
        cena = travadas[i]
        if cena.archived:
            raise _invalido("cena_arquivada", "Esta cena está arquivada", i)
        if cena.status == CenaStatus.rascunho:
            raise _invalido("cena_rascunho", "Marque a cena como pronta antes de usar", i)
    if not novas and not saem:
        return schemas.UsosOut(items=resumos_do_conteudo(db, conteudo.id),
                               version=conteudo.version)

    antes = [str(i) for i in ativos]
    agora = datetime.now(UTC)
    for i in saem:
        cena = travadas[i]
        before = history.snapshot(cena)
        ativos[i].desfeito_em, ativos[i].desfeito_por = agora, actor.user_id
        db.flush()
        _recalcula(db, actor, cena, conteudo.id, "desfeito", before)
    for i in novas:
        cena = travadas[i]
        before = history.snapshot(cena)
        db.add(CenaUso(id=uuid.uuid4(), cena_id=i, conteudo_id=conteudo.id,
                       criado_por=actor.user_id))
        db.flush()
        _recalcula(db, actor, cena, conteudo.id, "ligado", before)

    snap = history.snapshot(conteudo)
    conteudo.updated_by = actor.user_id
    history.record(db, actor, CONTEUDO, conteudo, "updated", snap, snap,
                   {"cenas": {"antes": antes, "depois": [str(i) for i in wanted]}})
    db.flush()
    return schemas.UsosOut(items=resumos_do_conteudo(db, conteudo.id), version=conteudo.version)


def conteudo_tem_cenas(db: Session, conteudo: Conteudo) -> list[schemas.CenaResumo]:
    """Para o `conteudos_get` (só vídeo próprio)."""
    if conteudo.origem != ConteudoOrigem.video_proprio:
        return []
    return resumos_do_conteudo(db, conteudo.id)
