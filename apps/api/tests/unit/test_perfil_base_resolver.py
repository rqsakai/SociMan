"""Perfil base de um pedido (spec 029, T007, R4): os 3 estados, arquivado e inexistente."""

import uuid
from types import SimpleNamespace

import pytest

from sociman_api.errors import ApiError
from sociman_api.perfis import base


class _Db:
    def __init__(self, *perfis):
        self.perfis = {p.id: p for p in perfis}

    def get(self, _modelo, pid):
        return self.perfis.get(pid)


A = SimpleNamespace(id=uuid.uuid4(), archived=False)
B = SimpleNamespace(id=uuid.uuid4(), archived=False)
X = SimpleNamespace(id=uuid.uuid4(), archived=True)
DB = _Db(A, B, X)


def test_tres_estados():
    assert base.resolver(DB, A.id) is A  # ausente = o do item
    assert base.resolver(DB, A.id, None) is None  # nenhum
    assert base.resolver(DB, A.id, B.id) is B  # outro, só no pedido
    assert base.resolver(DB, None) is None


def test_arquivado_e_inexistente():
    with pytest.raises(ApiError) as e:
        base.resolver(DB, X.id)
    assert e.value.code == "perfil_base_arquivado" and e.value.status == 409
    with pytest.raises(ApiError) as e:
        base.resolver(DB, None, uuid.uuid4())
    assert e.value.code == "perfil_invalido" and e.value.details == {"field": "perfilBaseId"}
    assert base.perfil_existente(DB, X.id) is X  # o item pode ter perfil arquivado


def test_filtro():
    assert base.filtro_perfil(None) is None and base.filtro_perfil("sem") == "sem"
    assert base.filtro_perfil(str(A.id)) == A.id
    with pytest.raises(ApiError):
        base.filtro_perfil("outro")
