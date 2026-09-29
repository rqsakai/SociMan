"""HD de dados (R5, FR-018): sentinela e piso de espaço, com `tmp_path` no papel do HD."""

import os
import tempfile
from types import SimpleNamespace

import pytest

from sociman_api import datadir
from sociman_api.config import Settings
from sociman_api.errors import ApiError

GB = 1024**3


@pytest.fixture
def hd(tmp_path, monkeypatch):
    settings = Settings(jwt_secret="x" * 32, data_dir=str(tmp_path), data_min_free_gb=20)
    monkeypatch.setattr(datadir, "get_settings", lambda: settings)
    return tmp_path


def _free(monkeypatch, free_gb: float, total_gb: float = 4000) -> None:
    frsize = 4096
    fake = SimpleNamespace(f_frsize=frsize, f_bavail=int(free_gb * GB) // frsize,
                           f_blocks=int(total_gb * GB) // frsize)
    monkeypatch.setattr(datadir.os, "statvfs", lambda _: fake)


def test_sem_sentinela_fica_indisponivel_e_recusa_gravar(hd):
    s = datadir.status()
    assert (s.available, s.reason, s.free_bytes, s.total_bytes) == (
        False, "sem_sentinela", None, None)
    assert s.min_free_bytes == 20 * GB
    with pytest.raises(ApiError) as e:
        datadir.ensure_writable()
    assert (e.value.status, e.value.code) == (503, "storage_unavailable")
    assert e.value.message == "O HD de dados não está disponível"


def test_pasta_inexistente_conta_como_sem_sentinela(hd, monkeypatch):
    settings = Settings(jwt_secret="x" * 32, data_dir=str(hd / "nao-existe"))
    monkeypatch.setattr(datadir, "get_settings", lambda: settings)
    assert datadir.status().reason == "sem_sentinela"
    assert not (hd / "nao-existe").exists()  # nunca cria a pasta de dados


def test_sentinela_que_e_pasta_nao_vale(hd):
    (hd / datadir.SENTINEL).mkdir()
    assert datadir.status().reason == "sem_sentinela"


def test_com_sentinela_e_espaco_fica_ok(hd, monkeypatch):
    (hd / datadir.SENTINEL).write_text("teste")
    _free(monkeypatch, free_gb=500)
    s = datadir.status()
    assert (s.available, s.reason) == (True, "ok")
    assert s.free_bytes == 500 * GB and s.total_bytes == 4000 * GB
    datadir.ensure_writable(10 * GB)


def test_statvfs_real_do_tmp_path(hd):
    (hd / datadir.SENTINEL).write_text("teste")
    s = datadir.status(min_free_gb=0)
    assert s.available and s.free_bytes > 0 and s.total_bytes >= s.free_bytes


def test_abaixo_do_piso_fica_pouco_espaco(hd, monkeypatch):
    (hd / datadir.SENTINEL).write_text("teste")
    _free(monkeypatch, free_gb=19)
    s = datadir.status()
    assert (s.available, s.reason) == (False, "pouco_espaco")
    with pytest.raises(ApiError) as e:
        datadir.ensure_writable()
    assert (e.value.status, e.value.code) == (507, "storage_full")
    assert e.value.message == "Pouco espaço no HD de dados"


def test_piso_desconta_o_tamanho_da_gravacao(hd, monkeypatch):
    (hd / datadir.SENTINEL).write_text("teste")
    _free(monkeypatch, free_gb=21)
    datadir.ensure_writable(GB)  # sobram 20: ok
    with pytest.raises(ApiError) as e:
        datadir.ensure_writable(GB + 1)
    assert e.value.status == 507


def test_piso_configuravel(hd, monkeypatch):
    (hd / datadir.SENTINEL).write_text("teste")
    _free(monkeypatch, free_gb=5)
    datadir.ensure_writable(min_free_gb=1)
    with pytest.raises(ApiError):
        datadir.ensure_writable(min_free_gb=10)


def test_pin_tempdir_nao_recua_para_tmp(tmp_path, monkeypatch):
    missing = str(tmp_path / "hd-fora" / "work" / "tmp")
    monkeypatch.setenv("TMPDIR", missing)
    monkeypatch.setattr(tempfile, "tempdir", None)
    datadir.pin_tempdir()
    assert tempfile.gettempdir() == missing
    with pytest.raises(FileNotFoundError):
        tempfile.TemporaryFile().close()
    assert not os.path.exists(missing)
