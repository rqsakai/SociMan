"""Configuração local: token 644 recusado, `Segredo` mascarado, padrões e TOML inválido."""

import os
from pathlib import Path

import pytest

from sociman_coletor import config

from .conftest import TOKEN_TESTE


def test_token_600_passa_e_mais_aberto_recusa(dir_config: Path):
    cfg = config.carregar(dir_config)
    assert config.ler_token(cfg).revelar() == TOKEN_TESTE
    os.chmod(cfg.caminho_token, 0o644)
    with pytest.raises(config.ErroConfig) as exc:
        config.ler_token(cfg)
    assert exc.value.codigo == "token_permissao"
    os.chmod(cfg.caminho_token, 0o640)
    with pytest.raises(config.ErroConfig) as exc:
        config.ler_token(cfg)
    assert exc.value.codigo == "token_permissao"
    os.chmod(cfg.caminho_token, 0o400)
    assert config.ler_token(cfg).revelar() == TOKEN_TESTE


def test_token_ausente_ou_sem_prefixo(dir_config: Path):
    cfg = config.carregar(dir_config)
    cfg.caminho_token.write_text("abc\n")
    with pytest.raises(config.ErroConfig) as exc:
        config.ler_token(cfg)
    assert exc.value.codigo == "token_formato"
    cfg.caminho_token.unlink()
    with pytest.raises(config.ErroConfig) as exc:
        config.ler_token(cfg)
    assert exc.value.codigo == "token_ausente"


def test_segredo_nunca_se_mostra():
    s = config.Segredo(TOKEN_TESTE)
    assert TOKEN_TESTE not in repr(s)
    assert TOKEN_TESTE not in str(s)
    assert TOKEN_TESTE not in f"{s}"
    assert TOKEN_TESTE not in f"{s!r}"
    assert repr(s) == "Segredo('scol_****')"
    assert s.revelar() == TOKEN_TESTE
    assert TOKEN_TESTE not in str({"token": s})


def test_padroes_sem_config(tmp_path: Path):
    cfg = config.carregar(tmp_path / "vazia")
    assert cfg.api_url == "https://192.168.86.47:8543"
    assert cfg.ca_cert is None and cfg.chrome_bin is None
    assert cfg.perfil_dir == tmp_path / "vazia" / "chrome-profile"
    assert cfg.screenshots is False
    assert cfg.limites.paginas_dia is None
    assert cfg.caminho_parar == tmp_path / "vazia" / "PARAR"


def test_config_invalida(tmp_path: Path):
    pasta = tmp_path / "c"
    pasta.mkdir()
    (pasta / "config.toml").write_text("api_url = 'ftp://x'\n")
    with pytest.raises(config.ErroConfig) as exc:
        config.carregar(pasta)
    assert exc.value.codigo == "config_invalida"
    (pasta / "config.toml").write_text("isto nao é toml =\n")
    with pytest.raises(config.ErroConfig):
        config.carregar(pasta)
    (pasta / "config.toml").write_text("campo_desconhecido = 1\n")
    with pytest.raises(config.ErroConfig):
        config.carregar(pasta)


def test_limites_locais_e_expansao(tmp_path: Path):
    pasta = tmp_path / "c"
    pasta.mkdir()
    (pasta / "config.toml").write_text(
        'ca_cert = "~/ca.crt"\n[limites]\npaginas_dia = 50\npausa_min_s = 9\n[log]\narquivo = ""\n'
    )
    cfg = config.carregar(pasta)
    assert cfg.ca_cert == Path("~/ca.crt").expanduser()
    assert cfg.limites.paginas_dia == 50 and cfg.limites.pausa_min_s == 9
    assert cfg.log.arquivo is None


def test_tem_tela():
    assert config.tem_tela({"DISPLAY": ":1"})
    assert config.tem_tela({"WAYLAND_DISPLAY": "wayland-0"})
    assert not config.tem_tela({})
