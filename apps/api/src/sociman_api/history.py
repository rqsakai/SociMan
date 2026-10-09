"""Histórico genérico de versões (research R1, princípio VII): `entity_versions` e helpers.

Como uma entidade de domínio usa este módulo:
- o modelo tem a coluna `version` (controle otimista, R2) e declara `__versioned_fields__`, os
  campos do snapshot (nunca `version`, timestamps de auditoria nem segredos). Campos só
  informativos, que a reversão ignora, vão em `__immutable_fields__` (ex.: o `slug` do perfil);
- cada mutação faz `check_version`, tira `snapshot` antes e depois e chama `record` na mesma
  sessão (e portanto na mesma transação) da mutação.
"""

import enum
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from sociman_api.db import Base
from sociman_api.errors import ApiError

ACTIONS = ("created", "updated", "archived", "restored", "reverted",
           # Spec 025: o kit padrão, a checagem de identidade, o consentimento e a revogação.
           "kit_escolhido", "identidade", "consentimento", "revoked")
VERSAO_REDIGIDA = ("Esta versão foi redigida pela revogação do consentimento e não pode ser "
                   "restaurada")


class EntityVersion(Base):
    """Imutável: a aplicação só faz INSERT."""

    __tablename__ = "entity_versions"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version",
                         name="uq_entity_versions_entity_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)  # perfil | conta | …
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)  # ver ACTIONS
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)  # user | system:cli
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    # Spec 009 (R6): o cliente MCP autor; a FK para `mcp_clientes` e o CHECK
    # `ck_entity_versions_ator` ficam na migration 0014 (sem FK no ORM: o `history` não importa
    # o pacote `mcp`).
    actor_mcp_client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


Index(
    "ix_entity_versions_entity_version",
    EntityVersion.entity_type,
    EntityVersion.entity_id,
    EntityVersion.version.desc(),
)


# Spec 013 (R8): a origem `importacao` de toda versão gravada dentro de `origem_importacao(...)`
# (o service chamado não muda de assinatura; o `record` soma `{"importacao": …}` aos `details`).
_ORIGEM_IMPORTACAO: ContextVar[dict[str, Any] | None] = ContextVar("origem_importacao",
                                                                  default=None)


@contextmanager
def origem_importacao(origem: Mapping[str, Any]) -> Iterator[None]:
    """`{"id", "arquivo", "trecho"}` da importação da agência que está gravando."""
    token = _ORIGEM_IMPORTACAO.set(dict(origem))
    try:
        yield
    finally:
        _ORIGEM_IMPORTACAO.reset(token)


class ActorLike(Protocol):
    """O `Actor` da auth (ou qualquer objeto com `kind` e `user_id`). O `mcp_client_id` (spec
    009) é lido com `getattr`: atores sem ele valem como `None`."""

    kind: str
    user_id: uuid.UUID | None


def _jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def snapshot(entity: Any) -> dict[str, Any]:
    """Só os campos versionados da entidade (`__versioned_fields__`), já serializáveis em JSON."""
    return {f: _jsonable(getattr(entity, f)) for f in entity.__versioned_fields__}


def diff(before: Mapping[str, Any] | None, after: Mapping[str, Any]) -> list[str]:
    """Campos que mudaram, na ordem do `after`. Sem `before` (criação), todos os do `after`."""
    if before is None:
        return list(after)
    keys = list(after) + [k for k in before if k not in after]
    return [k for k in keys if before.get(k) != after.get(k)]


def record(
    db: Session,
    actor: ActorLike,
    entity_type: str,
    entity: Any,
    action: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    details: Mapping[str, Any] | None = None,
) -> EntityVersion:
    """Grava a próxima versão da entidade e atualiza `entity.version` (sem commit).

    `created` é sempre a versão 1; as demais ações incrementam a versão atual. A entidade
    precisa ter `id` (o chamador faz `flush` antes, se o id vier do banco).
    """
    if action not in ACTIONS:
        raise ValueError(f"ação de histórico desconhecida: {action}")
    if action == "created":
        entity.version = 1
    else:
        entity.version += 1
    origem = _ORIGEM_IMPORTACAO.get()
    if origem is not None:
        details = {**(details or {}), "importacao": origem}
    before_json = _jsonable(before) if before is not None else None
    after_json = _jsonable(after)
    row = EntityVersion(
        entity_type=entity_type,
        entity_id=entity.id,
        version=entity.version,
        action=action,
        actor_kind=actor.kind,
        actor_user_id=actor.user_id,
        actor_mcp_client_id=getattr(actor, "mcp_client_id", None),
        before=before_json,
        after=after_json,
        changed_fields=diff(before_json, after_json),
        details=_jsonable(details or {}),
    )
    db.add(row)
    return row


def list_versions(db: Session, entity_type: str, entity_id: uuid.UUID) -> list[EntityVersion]:
    """Versões da entidade, da mais recente para a mais antiga."""
    stmt = (
        select(EntityVersion)
        .where(EntityVersion.entity_type == entity_type, EntityVersion.entity_id == entity_id)
        .order_by(EntityVersion.version.desc())
    )
    return list(db.scalars(stmt))


def version_state(
    db: Session, entity_type: str, entity_id: uuid.UUID, n: int
) -> dict[str, Any] | None:
    """O snapshot `after` da versão `n`, ou None se ela não existe. Uma versão redigida pela
    revogação LGPD (spec 025, R10b) não volta: 409 `versao_redigida`, para qualquer entidade."""
    stmt = select(EntityVersion.after, EntityVersion.details).where(
        EntityVersion.entity_type == entity_type,
        EntityVersion.entity_id == entity_id,
        EntityVersion.version == n,
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    if (row.details or {}).get("redigida"):
        raise ApiError(409, "versao_redigida", VERSAO_REDIGIDA)
    return row.after


def _redigir(snap: dict[str, Any] | None, campos: Sequence[str]) -> dict[str, Any] | None:
    if snap is None:
        return None
    out = dict(snap)
    for campo in campos:
        raiz, _, sub = campo.partition(".")
        if raiz not in out:
            continue
        if not sub:
            out[raiz] = None
        elif isinstance(out[raiz], dict) and sub in out[raiz]:
            out[raiz] = {**out[raiz], sub: None}
    return out


def redigir_versoes(db: Session, entity_type: str, entity_id: uuid.UUID, campos: Sequence[str],
                    *, motivo: Literal["lgpd_revogacao"], actor: ActorLike) -> int:
    """Exceção 2 da constitution 4.3.0 (spec 025, R10b): troca por `null`, em `before` e `after`
    de **todas** as versões da entidade, os campos que descrevem a pessoa (`campo` ou
    `campo.sub`). Ação, autor, data e `changed_fields` ficam; soma `details.redigida`. Só a
    revogação (`sociman_api/revogacao.py`) chama (guarda AST). Devolve quantas versões mudaram."""
    rows = list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == entity_type, EntityVersion.entity_id == entity_id)))
    marca = {"em": datetime.now(UTC).isoformat(), "por": str(actor.user_id) if actor.user_id
             else None, "motivo": motivo}
    for r in rows:
        r.before = _redigir(r.before, campos)
        r.after = _redigir(r.after, campos)
        r.details = {**(r.details or {}), "redigida": marca}
    db.flush()
    return len(rows)


def check_version(entity: Any, expected: int, label: str) -> None:
    """Controle otimista (R2). `label` é o sujeito da frase: "Este perfil", "Esta conta".

    O particípio concorda com o pronome: "Esta conta foi alterada…".
    """
    if entity.version != expected:
        feminine = label.split(maxsplit=1)[0].lower() in ("esta", "essa")
        verb = "alterada" if feminine else "alterado"
        # Spec 009 (FR-013): a versão atual vai junto, para o agente reler e tentar de novo.
        raise ApiError(409, "version_conflict",
                       f"{label} foi {verb} por outra pessoa; recarregue",
                       details={"versaoAtual": entity.version})


def autores(db: Session, rows: list[EntityVersion]) -> dict[int, dict[str, Any]]:
    """Spec 009 (R6): o `autor` de cada versão (`{tipo, id, nome}`), numa consulta por tipo.

    `tipo` é `usuario`, `mcp_client` (o selo "Agente: <nome>") ou `sistema` (CLI, trilhas).
    """
    from sociman_api.auth.models import User
    from sociman_api.mcp.models import McpCliente

    user_ids = {r.actor_user_id for r in rows if r.actor_user_id is not None}
    mcp_ids = {r.actor_mcp_client_id for r in rows if r.actor_mcp_client_id is not None}
    users = dict(db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
                 ) if user_ids else {}
    clientes = dict(db.execute(select(McpCliente.id, McpCliente.nome).where(
        McpCliente.id.in_(mcp_ids))).all()) if mcp_ids else {}
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        if r.actor_mcp_client_id is not None:
            out[r.id] = {"tipo": "mcp_client", "id": r.actor_mcp_client_id,
                         "nome": clientes.get(r.actor_mcp_client_id, "Agente")}
        elif r.actor_user_id is not None:
            out[r.id] = {"tipo": "usuario", "id": r.actor_user_id,
                         "nome": users.get(r.actor_user_id, "Usuário")}
        else:
            out[r.id] = {"tipo": "sistema", "id": None, "nome": r.actor_kind}
    return out
