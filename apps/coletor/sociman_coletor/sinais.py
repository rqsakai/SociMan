"""Sinais e paradas (contracts/coletor.md, "Sinais e paradas"). Sem Playwright: recebe só o que a
navegação já leu (URL, título, srcs de iframes, códigos HTTP) e decide. Cada sinal dispara uma vez.

| Sinal | Detecção |
|---|---|
| `captcha` | URL ou título casa `CAPTCHA_PADROES`, ou iframe de desafio |
| `login_perdido` | URL casa `LOGIN_PADROES` ou resposta interceptada com sessão inválida |
| `bloqueio_suspeito` | `BLOQUEIO_SERIE = 3` respostas 429/403 seguidas, ou 5 páginas 4xx seguidas |
| `layout_mudou` | `PARSES_VAZIOS_MAX = 5` páginas seguidas sem campos (interceptação e DOM) |
| `parar_local` | arquivo `PARAR` |
| `servico_parado` | SIGTERM/SIGINT |
| `fora_da_janela`, `orcamento`, `sem_tela` | relógio × janela; `paginasRestantes = 0`; sem tela |
"""

from __future__ import annotations

import enum
import re
import signal
from collections.abc import Iterable
from pathlib import Path

BLOQUEIO_SERIE = 3
PAGINAS_4XX_MAX = 5
PARSES_VAZIOS_MAX = 5
CAPTCHA_ESFRIAR_MIN = 60
CAPTCHA_ESPERA_MAX_H = 2
RECUO_BLOQUEIO_H = 24
CODIGOS_BLOQUEIO = frozenset({429, 403})


class Sinal(enum.StrEnum):
    captcha = "captcha"
    login_perdido = "login_perdido"
    bloqueio_suspeito = "bloqueio_suspeito"
    layout_mudou = "layout_mudou"
    parar_local = "parar_local"
    servico_parado = "servico_parado"
    fora_da_janela = "fora_da_janela"
    orcamento = "orcamento"
    sem_tela = "sem_tela"


def _casa(padroes: Iterable[re.Pattern[str]], *textos: str | None) -> bool:
    for texto in textos:
        if not texto:
            continue
        for p in padroes:
            if p.search(texto):
                return True
    return False


def detectar_captcha(
    url: str | None, titulo: str | None, iframes: Iterable[str], padroes: Iterable[re.Pattern[str]]
) -> bool:
    """URL ou título com os padrões do adaptador, ou um iframe cuja origem casa com eles."""
    padroes = tuple(padroes)
    return _casa(padroes, url, titulo) or _casa(padroes, *iframes)


def detectar_login(
    url: str | None, padroes: Iterable[re.Pattern[str]], sessao_invalida: bool = False
) -> bool:
    """Redirecionamento para a página de login, ou resposta interceptada de sessão inválida."""
    return sessao_invalida or _casa(tuple(padroes), url)


class ContadorBloqueio:
    """Recusas em série: 3 × (429|403) seguidas, ou 5 páginas 4xx seguidas → `bloqueio_suspeito`."""

    def __init__(self) -> None:
        self.recusas_seguidas = 0
        self.erros_4xx_seguidos = 0
        self.disparado = False

    def registrar(self, status_http: int | None) -> bool:
        """Devolve True **uma vez**, no momento em que a série fecha."""
        if status_http is None or status_http < 400 or status_http >= 500:
            self.recusas_seguidas = 0
            self.erros_4xx_seguidos = 0
            return False
        self.erros_4xx_seguidos += 1
        if status_http in CODIGOS_BLOQUEIO:
            self.recusas_seguidas += 1
        else:
            self.recusas_seguidas = 0
        fechou = (
            self.recusas_seguidas >= BLOQUEIO_SERIE or self.erros_4xx_seguidos >= PAGINAS_4XX_MAX
        )
        if fechou and not self.disparado:
            self.disparado = True
            return True
        return False


class ContadorLayout:
    """5 páginas seguidas com interceptação **e** DOM sem campos → `layout_mudou`."""

    def __init__(self) -> None:
        self.vazios_seguidos = 0
        self.disparado = False

    def registrar(self, tem_campos: bool) -> bool:
        if tem_campos:
            self.vazios_seguidos = 0
            return False
        self.vazios_seguidos += 1
        if self.vazios_seguidos >= PARSES_VAZIOS_MAX and not self.disparado:
            self.disparado = True
            return True
        return False


def parar_local(caminho_parar: Path) -> bool:
    return caminho_parar.exists()


class PedidoParada:
    """Guarda o SIGTERM/SIGINT: o laço termina a tarefa atual e fecha a rodada."""

    def __init__(self) -> None:
        self.pedido = False
        self.sinal: int | None = None

    def instalar(self) -> None:
        signal.signal(signal.SIGTERM, self._receber)
        signal.signal(signal.SIGINT, self._receber)

    def _receber(self, numero: int, _frame) -> None:
        self.pedido = True
        self.sinal = numero
