"""Padrões de corte do perfil (research R8; contracts/http-api.md "Padrões de corte").

Preguiçoso como o kit: sem linha em `padroes_corte`, o GET devolve o padrão com `version: 0`, e o
primeiro PUT (com `version: 0`) cria a v1. As faixas são as do próprio OpenShorts
(`_gen_control`), então nada é recusado lá depois. O gancho automático **não é campo**: está
sempre desligado (FR-008). Só o dono reverte (a rota usa `RequireOwner`).
"""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.envios import schemas
from sociman_api.envios.models import FORMATOS, LAYOUTS, LEGENDAS, PadroesCorte
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Conta
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import (
    get_perfil_or_404,
    target_state,
    user_refs,
    versions_out,
)

ENTITY = "padroes_corte"
LABEL = "Estes padrões"

PADRAO: dict[str, Any] = {
    "clip_min_s": 15, "clip_max_s": 60, "quantidade": None, "layout": "auto",
    "formato": "vertical", "legenda": "kit", "marca_automatica": False,
    "conta_padrao_id": None,
}
# Nome do campo no JSON (camelCase), para o `details.field` do erro.
CAMPO = {"clip_min_s": "clipMinS", "clip_max_s": "clipMaxS", "quantidade": "quantidade",
         "layout": "layout", "formato": "formato", "legenda": "legenda",
         "marca_automatica": "marcaAutomatica", "conta_padrao_id": "contaPadraoId"}


class ValoresInvalidos(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def validar(valores: Mapping[str, Any]) -> None:
    """As faixas de R8 (as mesmas do OpenShorts). Levanta `ValoresInvalidos(field, msg)`."""
    def erro(campo: str, msg: str) -> ValoresInvalidos:
        return ValoresInvalidos(CAMPO[campo], msg)

    mn, mx, qt = valores["clip_min_s"], valores["clip_max_s"], valores["quantidade"]
    if not isinstance(mn, int) or not 5 <= mn <= 175:
        raise erro("clip_min_s", "A duração mínima vai de 5 a 175 segundos")
    if not isinstance(mx, int) or not 10 <= mx <= 180:
        raise erro("clip_max_s", "A duração máxima vai de 10 a 180 segundos")
    if mx < mn + 5:
        raise erro("clip_max_s", "A duração máxima precisa ser pelo menos 5 s maior que a mínima")
    if qt is not None and (not isinstance(qt, int) or not 1 <= qt <= 15):
        raise erro("quantidade", "A quantidade de clipes vai de 1 a 15 (ou vazia: a IA decide)")
    if valores["layout"] not in LAYOUTS:
        raise erro("layout", "Layout inválido")
    if valores["formato"] not in FORMATOS:
        raise erro("formato", "Formato inválido")
    if valores["legenda"] not in LEGENDAS:
        raise erro("legenda", "Legenda inválida")
    if not isinstance(valores["marca_automatica"], bool):
        raise erro("marca_automatica", "Valor inválido")


def _invalid(exc: ValoresInvalidos) -> ApiError:
    return ApiError(400, "invalid_padroes", exc.message, details={"field": exc.field})


def _row(db: Session, perfil_id: uuid.UUID, lock: bool = False) -> PadroesCorte | None:
    stmt = select(PadroesCorte).where(PadroesCorte.perfil_id == perfil_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def valores_atuais(db: Session, perfil_id: uuid.UUID) -> dict[str, Any]:
    """Os padrões vigentes (os salvos ou o padrão), como dict com os nomes das colunas.
    Público: o envio copia isto para `envios.config`."""
    row = _row(db, perfil_id)
    if row is None:
        return dict(PADRAO)
    return {k: getattr(row, k) for k in PADRAO}


def _out(db: Session, perfil_id: uuid.UUID, row: PadroesCorte | None) -> schemas.PadroesCorte:
    if row is None:
        return schemas.PadroesCorte(perfil_id=perfil_id, version=0, updated_at=None,
                                    updated_by=None, **PADRAO)
    updated_by = None
    if row.updated_by is not None:
        updated_by = user_refs(db, [row.updated_by]).get(row.updated_by)
    return schemas.PadroesCorte(
        perfil_id=perfil_id, version=row.version, updated_at=row.updated_at,
        updated_by=updated_by, **{k: getattr(row, k) for k in PADRAO},
    )


def _saved_out(db: Session, row: PadroesCorte) -> schemas.PadroesCorte:
    db.flush()
    db.refresh(row)  # updated_at vem do banco
    return _out(db, row.perfil_id, row)


def _check_conta(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None) -> None:
    if conta_id is None:
        return
    conta = db.get(Conta, conta_id)
    if conta is None or conta.perfil_id != perfil_id or conta.archived:
        raise ApiError(400, "invalid_padroes", "A conta padrão precisa ser uma conta ativa do perfil",
                       details={"field": "contaPadraoId"})


def get_padroes(db: Session, perfil_id: uuid.UUID) -> schemas.PadroesCorte:
    get_perfil_or_404(db, perfil_id)
    return _out(db, perfil_id, _row(db, perfil_id))


def padroes_versions(db: Session, perfil_id: uuid.UUID) -> VersionsList:
    get_perfil_or_404(db, perfil_id)
    row = _row(db, perfil_id)
    if row is None:
        return VersionsList(items=[])
    return versions_out(db, ENTITY, row.id)


def put_padroes(db: Session, actor: Actor, perfil_id: uuid.UUID,
                data: schemas.PadroesCorteIn) -> schemas.PadroesCorte:
    """Cria (versão 0 → 1) ou troca os padrões. Sem mudança real, não grava versão."""
    # A trava do perfil serializa o primeiro salvamento (sem linha para travar ainda).
    get_perfil_or_404(db, perfil_id, lock=True)
    valores = data.model_dump(exclude={"version"})
    try:
        validar(valores)
    except ValoresInvalidos as exc:
        raise _invalid(exc) from exc
    _check_conta(db, perfil_id, valores["conta_padrao_id"])

    row = _row(db, perfil_id, lock=True)
    if row is None:
        if data.version != 0:
            raise ApiError(409, "version_conflict",
                           f"{LABEL} foram alterados por outra pessoa; recarregue")
        row = PadroesCorte(perfil_id=perfil_id, created_by=actor.user_id,
                           updated_by=actor.user_id, **valores)
        db.add(row)
        db.flush()
        history.record(db, actor, ENTITY, row, "created", None, history.snapshot(row))
        return _saved_out(db, row)

    _check_version(row, data.version)
    before = history.snapshot(row)
    for k, v in valores.items():
        setattr(row, k, v)
    after = history.snapshot(row)
    if after == before:
        return _saved_out(db, row)
    row.updated_by = actor.user_id
    history.record(db, actor, ENTITY, row, "updated", before, after)
    return _saved_out(db, row)


def _check_version(row: PadroesCorte, expected: int) -> None:
    if row.version != expected:
        raise ApiError(409, "version_conflict",
                       f"{LABEL} foram alterados por outra pessoa; recarregue")


def revert_padroes(db: Session, actor: Actor, perfil_id: uuid.UUID, version: int,
                   to_version: int) -> schemas.PadroesCorte:
    """Volta os campos da versão alvo numa versão nova `reverted` (só o dono)."""
    get_perfil_or_404(db, perfil_id, lock=True)
    row = _row(db, perfil_id, lock=True)
    if row is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    _check_version(row, version)
    state = target_state(db, ENTITY, row, to_version)
    valores = {k: state.get(k, PADRAO[k]) for k in PADRAO}
    if valores["conta_padrao_id"] is not None:
        valores["conta_padrao_id"] = uuid.UUID(valores["conta_padrao_id"])
    try:
        validar(valores)
    except ValoresInvalidos as exc:
        raise ApiError(409, "revert_conflict", f"Essa versão não vale mais ({exc.message})") from exc
    conta_id = valores["conta_padrao_id"]
    if conta_id is not None:
        conta = db.get(Conta, conta_id)
        if conta is None or conta.perfil_id != perfil_id or conta.archived:
            raise ApiError(409, "revert_conflict",
                           "A conta padrão dessa versão não está mais disponível")

    before = history.snapshot(row)
    for k, v in valores.items():
        setattr(row, k, v)
    after = history.snapshot(row)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    row.updated_by = actor.user_id
    history.record(db, actor, ENTITY, row, "reverted", before, after,
                   {"from_version": to_version})
    return _saved_out(db, row)
