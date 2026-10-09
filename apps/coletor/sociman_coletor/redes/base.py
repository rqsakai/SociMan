"""Protocol `ColetorRede` (contracts/coletor.md, "Adaptador") e os tipos que ele devolve.

Um adaptador conhece a rede: os padrões de URL a interceptar, os hosts de imagem, os padrões de
captcha e de login, a URL canônica e a paginação, e os parsers por tipo de tarefa. Ele **não**
navega nem clica: recebe a página (só leitura) e as respostas já interceptadas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from sociman_coletor import modelos

Origem = Literal["produto", "avaliacao"]


@dataclass(frozen=True)
class Interceptada:
    """Uma resposta da API interna que a própria página chamou (interceptação passiva)."""

    url: str
    status: int
    json: Any


@dataclass(frozen=True)
class ImagemRef:
    """Uma imagem que a página carregou e o parser quer: o `imagens.py` baixa e calcula o sha."""

    url: str
    origem: Origem = "produto"
    # Para onde o sha vai nos `campos` quando chegar: ("ficha.imagensSha", None) para listas,
    # ("ficha.variantes", 2) para um índice. O parser preenche; `coletar` resolve depois.
    destino: tuple[str, int | None] | None = None


@dataclass
class Resultado:
    """O que uma página rendeu. `campos` = payload normalizado (camelCase); `bruto` = o JSON
    interceptado (antes da poda; quem poda é o laço); `imagens` = referências a baixar."""

    campos: dict[str, Any] | None = None
    bruto: Any = None
    imagens: list[ImagemRef] = field(default_factory=list)
    erro_codigo: str | None = None
    fonte: str | None = None
    via_dom: bool = False

    @property
    def tem_campos(self) -> bool:
        return bool(self.campos)


@runtime_checkable
class ColetorRede(Protocol):
    esquema: str
    rede: str
    INTERCEPTAR: tuple[re.Pattern[str], ...]
    IMAGENS_HOSTS: frozenset[str]
    CAPTCHA_PADROES: tuple[re.Pattern[str], ...]
    LOGIN_PADROES: tuple[re.Pattern[str], ...]
    TIPOS: tuple[str, ...]
    URL_LOGIN: str

    def url_canonica(self, url: str) -> str: ...

    def url_pagina(self, url: str, n: int) -> str: ...

    def e_derivada(self, url: str, base: str) -> bool: ...

    def intercepta(self, url: str) -> bool: ...

    def host_de_imagem(self, url: str) -> bool: ...

    def sessao_invalida(self, interceptadas: list[Interceptada]) -> bool: ...

    def coletar(
        self, pagina: Any, tarefa: modelos.Tarefa, interceptadas: list[Interceptada]
    ) -> Resultado: ...

    def reprocessar(self, tarefa_tipo: str, bruto: Any, fonte: str | None) -> Resultado: ...
