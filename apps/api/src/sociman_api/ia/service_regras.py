"""Regras (system prompts) por tipo de campo (spec 008, US2; research R2).

O padrão fica no código (`regras_padrao.py`); a personalização, em `ia_regras`, uma linha por
tipo criada só na primeira edição (como o kit com `version = 0`). Toda mutação trava a linha,
faz `check_version` e grava a versão em `entity_versions` (`entity_type = "ia_regra"`) na mesma
transação, com o autor. "Voltar ao padrão" grava `texto = NULL` (`details = {"padrao": true}`)
e também pode ser revertido. Não há arquivamento. Só o dono muda (as rotas usam `RequireOwner`).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.ia import schemas
from sociman_api.ia.models import IaRegra
from sociman_api.ia.service import tipo_or_404
from sociman_api.ia.tipos import TIPOS, TipoCampo
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import target_state, user_refs, versions_out

ENTITY = "ia_regra"
LABEL = "Esta regra"


def _row(db: Session, tipo_id: str, lock: bool = False) -> IaRegra | None:
    stmt = select(IaRegra).where(IaRegra.tipo_campo == tipo_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _regras_out(tipo: TipoCampo, row: IaRegra | None,
                users: dict) -> schemas.Regras:
    personalizada = row is not None and row.texto is not None
    return schemas.Regras(
        texto=row.texto if personalizada else tipo.padrao,  # type: ignore[union-attr]
        padrao=tipo.padrao, personalizada=personalizada,
        padrao_atualizado=personalizada and tipo.padrao_versao > row.padrao_versao,  # type: ignore[union-attr]
        version=row.version if row is not None else 0,
        updated_at=row.updated_at if row is not None else None,
        updated_by=users.get(row.updated_by) if row is not None and row.updated_by else None,
    )


def _tipo_out(tipo: TipoCampo, row: IaRegra | None, users: dict) -> schemas.TipoCampo:
    lim = tipo.limites
    return schemas.TipoCampo(
        id=tipo.id, rotulo=tipo.rotulo, onde=tipo.onde, entidade=tipo.entidade,
        idioma=tipo.idioma, formato=tipo.formato,
        limites=schemas.Limites(
            max_chars=lim.max_chars, min_chars=lim.min_chars, uma_linha=lim.uma_linha,
            max_itens=lim.max_itens, min_itens=lim.min_itens,
            max_chars_item=lim.max_chars_item, max_sugestoes=lim.max_sugestoes),
        regras=_regras_out(tipo, row, users),
    )


def listar(db: Session) -> list[schemas.TipoCampo]:
    rows = {r.tipo_campo: r for r in db.scalars(select(IaRegra))}
    users = user_refs(db, [r.updated_by for r in rows.values()])
    return [_tipo_out(t, rows.get(t.id), users) for t in TIPOS.values()]


def obter(db: Session, tipo_id: str) -> schemas.TipoCampo:
    tipo = tipo_or_404(tipo_id)
    row = _row(db, tipo.id)
    users = user_refs(db, [row.updated_by] if row is not None else [])
    return _tipo_out(tipo, row, users)


def _saved(db: Session, tipo: TipoCampo, row: IaRegra) -> schemas.TipoCampo:
    db.flush()
    db.refresh(row)  # updated_at vem do banco
    return _tipo_out(tipo, row, user_refs(db, [row.updated_by]))


def _mudar(db: Session, actor: Actor, tipo_id: str, version: int, texto: str | None,
           details: dict | None = None) -> schemas.TipoCampo:
    tipo = tipo_or_404(tipo_id)
    row = _row(db, tipo.id, lock=True)
    if row is None:
        if version != 0:
            raise ApiError(409, "version_conflict", f"{LABEL} foi alterada por outra pessoa; "
                                                    "recarregue")
        if texto is None:
            raise ApiError(400, "validation_error", "Esta regra já usa o padrão")
        row = IaRegra(tipo_campo=tipo.id, texto=texto, padrao_versao=tipo.padrao_versao,
                      created_by=actor.user_id, updated_by=actor.user_id)
        db.add(row)
        db.flush()
        history.record(db, actor, ENTITY, row, "created", None, history.snapshot(row), details)
        return _saved(db, tipo, row)
    history.check_version(row, version, LABEL)
    before = history.snapshot(row)
    row.texto = texto
    after = history.snapshot(row)
    if after == before:
        if texto is None:
            raise ApiError(400, "validation_error", "Esta regra já usa o padrão")
        return _saved(db, tipo, row)
    row.padrao_versao = tipo.padrao_versao
    row.updated_by = actor.user_id
    history.record(db, actor, ENTITY, row, "updated", before, after, details)
    return _saved(db, tipo, row)


def put_regras(db: Session, actor: Actor, tipo_id: str,
               body: schemas.RegrasIn) -> schemas.TipoCampo:
    return _mudar(db, actor, tipo_id, body.version, body.texto)


def voltar_ao_padrao(db: Session, actor: Actor, tipo_id: str, version: int
                     ) -> schemas.TipoCampo:
    return _mudar(db, actor, tipo_id, version, None, {"padrao": True})


def versoes(db: Session, tipo_id: str) -> VersionsList:
    tipo = tipo_or_404(tipo_id)
    row = _row(db, tipo.id)
    if row is None:
        return VersionsList(items=[])
    return versions_out(db, ENTITY, row.id)


def revert(db: Session, actor: Actor, tipo_id: str, version: int,
           to_version: int) -> schemas.TipoCampo:
    """Volta o texto da versão alvo numa versão nova `reverted` (só o dono, princípio VII)."""
    tipo = tipo_or_404(tipo_id)
    row = _row(db, tipo.id, lock=True)
    if row is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    history.check_version(row, version, LABEL)
    state = target_state(db, ENTITY, row, to_version)
    before = history.snapshot(row)
    row.texto = state["texto"]
    after = history.snapshot(row)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    row.padrao_versao = tipo.padrao_versao
    row.updated_by = actor.user_id
    history.record(db, actor, ENTITY, row, "reverted", before, after,
                   {"from_version": to_version})
    return _saved(db, tipo, row)
