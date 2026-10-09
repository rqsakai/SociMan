"""As únicas ações sobre a página (contracts/coletor.md, "Ações permitidas"; FR-015).

| Ação | Playwright | Limite |
|---|---|---|
| `abrir(url)` | `page.goto` | só a URL da tarefa ou derivada dela (`url_pagina`), FR-023 |
| `rolar()` | `page.mouse.wheel` | 3..8 passos de 300..900 px |
| `mover_mouse()` | `page.mouse.move` | pontos aleatórios na janela |
| `esperar(ms)` | `page.wait_for_timeout` | sempre pelo `ritmo` |
| `clicar(alvo, seletor)` | `locator.click` | só `alvo ∈ CLIQUES_PERMITIDOS`; ≤ 3 por página |
| `voltar()` | `page.go_back` | só depois de um clique de aba/paginação |

Todo `.click(` do pacote está em `clicar` (guarda `test_guardas`). Nada de `fill`, `type`,
`press`, `keyboard`, formulários, `route`, `request` (fora de `imagens.py`), `evaluate` com
`fetch`/`XMLHttpRequest`, novas abas ou contextos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sociman_coletor import log
from sociman_coletor.ritmo import Ritmo

CLIQUES_PERMITIDOS = frozenset(
    {
        "fechar_aviso",  # banner de cookies, tour, "Entendi", modal informativo
        "aba_categoria",  # trocar a aba/categoria de um ranking
        "paginacao",  # próxima página de ranking, avaliações ou vídeos
        "ver_mais",  # expandir descrição ou lista de atributos
        "fechar_modal",  # X de um modal que a própria página abriu
    }
)
ACOES_PROIBIDAS = re.compile(
    r"Adicionar|Promover|Seguir|Comprar|Enviar|Comentar|Curtir|Salvar|Solicitar|Amostra|"
    r"Compartilhar|Denunciar|Favoritar|Pedir|Entrar|Sair|Login|Cadastr",
    re.IGNORECASE,
)
CLIQUES_POR_PAGINA_MAX = 3
TIMEOUT_NAVEGACAO_MS = 45_000
TIMEOUT_CLIQUE_MS = 5_000
CLIQUES_COM_VOLTA = frozenset({"aba_categoria", "paginacao"})
JANELA = (1280, 900)


class UrlForaDaTarefa(Exception):
    """Tentativa de abrir uma URL que não veio da fila nem deriva dela (FR-023)."""


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def acao_proibida(texto: str | None) -> bool:
    """O texto do elemento casa com uma ação que escreve na rede? (sem acento, sem caixa)"""
    return bool(texto) and ACOES_PROIBIDAS.search(sem_acento(texto)) is not None


@dataclass
class Abertura:
    status: int | None
    url_final: str
    titulo: str
    iframes: list[str]
    redirecionada: bool


class Navegacao:
    def __init__(self, pagina: Any, ritmo: Ritmo, rede: Any):
        self._pagina = pagina
        self._ritmo = ritmo
        self._rede = rede
        self._url_tarefa: str | None = None
        self._cliques = 0
        self._ultimo_clique: str | None = None
        self._log = log.obter("navegacao")

    @property
    def pagina(self) -> Any:
        return self._pagina

    def nova_tarefa(self, url_tarefa: str) -> None:
        self._url_tarefa = url_tarefa
        self._cliques = 0
        self._ultimo_clique = None

    def url_permitida(self, url: str) -> bool:
        if self._url_tarefa is None:
            return False
        if self._rede.url_canonica(url) == self._rede.url_canonica(self._url_tarefa):
            return True
        return self._rede.e_derivada(url, self._url_tarefa)

    def abrir(self, url: str) -> Abertura:
        """`page.goto` com `domcontentloaded` e 45 s. Só a URL da tarefa ou derivada dela."""
        if not self.url_permitida(url):
            raise UrlForaDaTarefa(log.url_sem_query(url))
        resposta = self._pagina.goto(
            url, wait_until="domcontentloaded", timeout=TIMEOUT_NAVEGACAO_MS
        )
        status = resposta.status if resposta is not None else None
        url_final = self._pagina.url
        try:
            titulo = self._pagina.title()
        except Exception:  # noqa: BLE001 - página ainda mudando
            titulo = ""
        iframes = []
        try:
            iframes = [f.url for f in self._pagina.frames[1:] if f.url]
        except Exception:  # noqa: BLE001
            iframes = []
        redirecionada = self._rede.url_canonica(url_final) != self._rede.url_canonica(
            url
        ) and not self.url_permitida(url_final)
        self._log.info("abriu status=%s redirecionada=%s", status, redirecionada)
        return Abertura(status, url_final, titulo, iframes, redirecionada)

    def esperar(self, ms: int) -> None:
        self._pagina.wait_for_timeout(ms)

    def mover_mouse(self) -> None:
        x, y, passos = self._ritmo.ponto_mouse(*JANELA)
        self._pagina.mouse.move(x, y, steps=passos)

    def rolar(self) -> None:
        """Rolagem em passos, com pausa curta e um movimento de mouse antes."""
        self.mover_mouse()
        for dy in self._ritmo.rolagem():
            self._pagina.mouse.wheel(0, dy)
            self.esperar(self._ritmo.pausa_curta_ms())

    def clicar(self, alvo: str, seletor: str) -> bool:
        """Clica só em alvo permitido, até 3 vezes por página, e nunca num elemento cujo texto
        case com `ACOES_PROIBIDAS` (casou → `clique_bloqueado`, não clica, segue)."""
        if alvo not in CLIQUES_PERMITIDOS:
            raise ValueError(f"alvo de clique fora da lista: {alvo}")
        if self._cliques >= CLIQUES_POR_PAGINA_MAX:
            self._log.info("clique ignorado: limite por pagina alvo=%s", alvo)
            return False
        elemento = self._pagina.locator(seletor).first
        try:
            if elemento.count() == 0:
                return False
            texto = elemento.inner_text(timeout=TIMEOUT_CLIQUE_MS)
        except Exception:  # noqa: BLE001 - elemento sumiu
            return False
        if acao_proibida(texto):
            self._log.warning("clique_bloqueado alvo=%s", alvo)
            return False
        self.mover_mouse()
        self.esperar(int(self._ritmo.pausa() * 1000))
        try:
            elemento.click(timeout=TIMEOUT_CLIQUE_MS)
        except Exception:  # noqa: BLE001 - não clicou: nada a desfazer
            return False
        self._cliques += 1
        self._ultimo_clique = alvo
        self._log.info("clicou alvo=%s", alvo)
        return True

    def voltar(self) -> bool:
        if self._ultimo_clique not in CLIQUES_COM_VOLTA:
            return False
        self._pagina.go_back(wait_until="domcontentloaded", timeout=TIMEOUT_NAVEGACAO_MS)
        self._ultimo_clique = None
        return True
