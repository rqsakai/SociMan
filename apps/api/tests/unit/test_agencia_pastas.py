"""Varredura segura (spec 013, T007, R2): link para fora, limite de entradas, pasta vazia ou
inexistente e a impressão digital; e a origem `importacao` do histórico (T011)."""

import hashlib
import uuid
from types import SimpleNamespace

import pytest

from sociman_api import history
from sociman_api.agencia import pastas
from sociman_api.config import get_settings
from sociman_api.errors import ApiError


@pytest.fixture
def raizes(tmp_path, monkeypatch):
    shared, clipes = tmp_path / "shared", tmp_path / "clipes"
    shared.mkdir()
    clipes.mkdir()
    monkeypatch.setattr(get_settings(), "agencia_shared_dir", str(shared))
    monkeypatch.setattr(get_settings(), "agencia_clipes_dir", str(clipes))
    return shared, clipes


def test_link_dentro_vale_e_para_fora_nao(raizes, tmp_path):
    shared, _ = raizes
    (shared / "a.md").write_text("a")
    (shared / "dentro.md").symlink_to(shared / "a.md")
    (tmp_path / "fora.md").write_text("x")
    (shared / "fora.md").symlink_to(tmp_path / "fora.md")
    (shared / "pasta").symlink_to(tmp_path)
    v = pastas.varrer("shared")
    assert sorted(a.rel for a in v.arquivos) == ["a.md", "dentro.md"]
    assert sorted(v.links_fora) == ["shared:fora.md", "shared:pasta"]


def test_limite_de_entradas(raizes, monkeypatch):
    shared, _ = raizes
    for i in range(3):
        (shared / f"{i}.md").write_text("x")
    monkeypatch.setattr(pastas, "ENTRADAS_MAX", 2)
    with pytest.raises(ApiError) as e:
        pastas.varrer("shared")
    assert (e.value.status, e.value.code) == (413, "agencia_pasta_grande")


def test_vazia_ou_inexistente(raizes, monkeypatch):
    with pytest.raises(ApiError) as e:
        pastas.varrer("shared")  # vazia
    assert (e.value.status, e.value.code) == (503, "agencia_pasta_indisponivel")
    assert pastas.varrer("clipes").arquivos == []  # clipes pode estar vazia
    monkeypatch.setattr(get_settings(), "agencia_clipes_dir", "/nao/existe")
    assert pastas.disponivel("clipes") == (False, "pasta não encontrada")


def test_bytes_com_limite_e_sha(raizes):
    shared, _ = raizes
    (shared / "a.md").write_bytes(b"x" * 10)
    [arq] = pastas.varrer("shared").arquivos
    assert pastas.ler_bytes(arq, 9) is None and pastas.ler_bytes(arq, 10) == b"x" * 10
    assert pastas.sha256_arquivo(arq.path) == hashlib.sha256(b"x" * 10).hexdigest()
    assert arq.id == "shared:a.md"


def test_origem_importacao_no_historico():
    db = SimpleNamespace(added=[], add=lambda r: db.added.append(r))
    ator = SimpleNamespace(kind="user", user_id=uuid.uuid4())
    ent = SimpleNamespace(id=uuid.uuid4(), version=1)
    history.record(db, ator, "perfil", ent, "updated", {}, {}, {"x": 1})
    assert db.added[-1].details == {"x": 1}  # fora do contexto: nada muda
    with history.origem_importacao({"id": "i", "arquivo": "a", "trecho": "t"}):
        history.record(db, ator, "perfil", ent, "updated", {}, {})
    assert db.added[-1].details == {"importacao": {"id": "i", "arquivo": "a", "trecho": "t"}}
    history.record(db, ator, "perfil", ent, "updated", {}, {})
    assert db.added[-1].details == {}
