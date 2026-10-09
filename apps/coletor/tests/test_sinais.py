"""Sinais: captcha, login, 429/403 em série, 4xx em série, layout vazio; cada um dispara uma vez."""

from sociman_coletor import sinais
from sociman_coletor.redes.base import Interceptada

from .fakes import rede_teste


def test_captcha_por_url_titulo_ou_iframe():
    rede = rede_teste()
    assert sinais.detectar_captcha("https://h/verify/123", "", [], rede.CAPTCHA_PADROES)
    assert sinais.detectar_captcha(
        "https://h/p", "Verificação de segurança", [], rede.CAPTCHA_PADROES
    )
    assert sinais.detectar_captcha(
        "https://h/p", "Produto", ["https://x/captcha/frame"], rede.CAPTCHA_PADROES
    )
    assert not sinais.detectar_captcha(
        "https://h/product/1", "Shorts", ["https://x/ads"], rede.CAPTCHA_PADROES
    )


def test_login_por_url_ou_sessao_invalida():
    rede = rede_teste()
    assert sinais.detectar_login("https://h/login?next=x", rede.LOGIN_PADROES)
    assert sinais.detectar_login("https://h/passport/web/login", rede.LOGIN_PADROES)
    assert not sinais.detectar_login("https://h/product/1", rede.LOGIN_PADROES)
    assert sinais.detectar_login("https://h/product/1", rede.LOGIN_PADROES, sessao_invalida=True)
    assert rede.sessao_invalida([Interceptada("u", 200, {"status_msg": "user not login"})])
    assert not rede.sessao_invalida([Interceptada("u", 200, {"status_msg": "ok"})])


def test_bloqueio_tres_recusas_seguidas_uma_vez():
    c = sinais.ContadorBloqueio()
    assert [c.registrar(s) for s in (429, 429)] == [False, False]
    assert c.registrar(403) is True
    assert c.registrar(429) is False  # já disparou
    c = sinais.ContadorBloqueio()
    assert [c.registrar(s) for s in (429, 200, 429, 429)] == [False, False, False, False]


def test_bloqueio_cinco_paginas_4xx_seguidas():
    c = sinais.ContadorBloqueio()
    assert [c.registrar(404) for _ in range(4)] == [False] * 4
    assert c.registrar(410) is True
    c = sinais.ContadorBloqueio()
    assert [c.registrar(s) for s in (404, 404, 500, 404, 404, 404)] == [False] * 6


def test_layout_cinco_vazios_seguidos():
    c = sinais.ContadorLayout()
    assert [c.registrar(False) for _ in range(4)] == [False] * 4
    assert c.registrar(False) is True
    assert c.registrar(False) is False
    c = sinais.ContadorLayout()
    assert [c.registrar(v) for v in (False, False, True, False, False, False, False)] == [False] * 7


def test_constantes():
    assert sinais.BLOQUEIO_SERIE == 3 and sinais.PARSES_VAZIOS_MAX == 5
    assert sinais.CAPTCHA_ESFRIAR_MIN == 60 and sinais.CAPTCHA_ESPERA_MAX_H == 2
    assert sinais.RECUO_BLOQUEIO_H == 24


def test_parar_local(tmp_path):
    assert not sinais.parar_local(tmp_path / "PARAR")
    (tmp_path / "PARAR").touch()
    assert sinais.parar_local(tmp_path / "PARAR")
