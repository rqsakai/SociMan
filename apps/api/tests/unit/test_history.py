"""history.py: diff, snapshot serializável, controle otimista e ordem das versões."""

import enum
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from sociman_api import history
from sociman_api.auth.deps import CLI
from sociman_api.errors import ApiError


class _Cor(enum.StrEnum):
    azul = "azul"


def test_diff_creation_lists_all_fields():
    assert history.diff(None, {"name": "A", "bio": ""}) == ["name", "bio"]


def test_diff_only_changed_fields():
    before = {"name": "A", "bio": "x", "status": "ativo"}
    after = {"name": "B", "bio": "x", "status": "pausado"}
    assert history.diff(before, after) == ["name", "status"]


def test_diff_no_change_and_removed_key():
    assert history.diff({"a": 1}, {"a": 1}) == []
    assert history.diff({"a": 1, "b": 2}, {"a": 1}) == ["b"]


def test_snapshot_is_json_serializable_and_only_versioned_fields():
    uid = uuid.uuid4()
    entity = SimpleNamespace(
        __versioned_fields__=("name", "status", "logo_image_id", "when"),
        name="A", status=_Cor.azul, logo_image_id=uid,
        when=datetime(2026, 9, 29, tzinfo=UTC), version=7,
    )
    assert history.snapshot(entity) == {
        "name": "A", "status": "azul", "logo_image_id": str(uid),
        "when": "2026-09-29T00:00:00+00:00",
    }


def test_check_version_conflict_message():
    history.check_version(SimpleNamespace(version=3), 3, "Este perfil")
    with pytest.raises(ApiError) as exc:
        history.check_version(SimpleNamespace(version=3), 2, "Este perfil")
    assert (exc.value.status, exc.value.code) == (409, "version_conflict")
    assert exc.value.message == "Este perfil foi alterado por outra pessoa; recarregue"
    with pytest.raises(ApiError) as exc:
        history.check_version(SimpleNamespace(version=1), 2, "Esta conta")
    assert exc.value.message == "Esta conta foi alterada por outra pessoa; recarregue"


def test_record_rejects_unknown_action(db):
    entity = SimpleNamespace(id=uuid.uuid4(), version=1)
    with pytest.raises(ValueError):
        history.record(db, CLI, "perfil", entity, "deleted", None, {"a": 1})


def test_record_numbers_versions_and_lists_newest_first(db):
    # entity_versions não tem FK para a entidade: um objeto qualquer com id e version basta.
    entity = SimpleNamespace(id=uuid.uuid4(), version=None)
    s1 = {"name": "A", "status": _Cor.azul}
    history.record(db, CLI, "perfil", entity, "created", None, s1)
    assert entity.version == 1
    s2 = {"name": "B", "status": _Cor.azul}
    history.record(db, CLI, "perfil", entity, "updated", s1, s2)
    history.record(db, CLI, "perfil", entity, "reverted", s2, s1, {"from_version": 1})
    db.commit()
    assert entity.version == 3

    versions = history.list_versions(db, "perfil", entity.id)
    assert [v.version for v in versions] == [3, 2, 1]
    assert [v.action for v in versions] == ["reverted", "updated", "created"]
    assert versions[2].before is None and versions[2].changed_fields == ["name", "status"]
    assert versions[1].changed_fields == ["name"]
    assert versions[0].details == {"from_version": 1}
    assert versions[0].actor_kind == "system:cli" and versions[0].actor_user_id is None
    assert history.version_state(db, "perfil", entity.id, 1) == {"name": "A", "status": "azul"}
    assert history.version_state(db, "perfil", entity.id, 9) is None
    assert history.list_versions(db, "conta", entity.id) == []
