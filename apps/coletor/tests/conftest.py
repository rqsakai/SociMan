"""Fixtures comuns: pasta de configuração temporária (token 600), SociMan falso e relógio."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sociman_coletor import config

from .fakes import RelogioFalso, SocimanFalso

TOKEN_TESTE = "scol_teste1234_" + "a" * 43


@pytest.fixture
def dir_config(tmp_path: Path) -> Path:
    pasta = tmp_path / "sociman-coletor"
    pasta.mkdir(mode=0o700)
    (pasta / "config.toml").write_text(
        'api_url = "http://sociman.teste"\n'
        f'perfil_dir = "{pasta / "chrome-profile"}"\n'
        "[log]\n"
        f'arquivo = "{pasta / "coletor.log"}"\n',
        encoding="utf-8",
    )
    token = pasta / "token"
    token.write_text(TOKEN_TESTE + "\n", encoding="utf-8")
    os.chmod(token, 0o600)
    return pasta


@pytest.fixture
def cfg(dir_config: Path) -> config.Config:
    return config.carregar(dir_config)


@pytest.fixture
def token(cfg: config.Config) -> config.Segredo:
    return config.ler_token(cfg)


@pytest.fixture
def relogio() -> RelogioFalso:
    return RelogioFalso()


@pytest.fixture
def sociman(relogio: RelogioFalso) -> SocimanFalso:
    return SocimanFalso(relogio)
