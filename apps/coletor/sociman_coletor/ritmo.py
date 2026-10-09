"""Ritmo humano (contracts/coletor.md, "Ritmo humano"). Puro: sem relógio, sem rede, RNG semeado.

| Constante | Valor |
|---|---|
| `PAUSA_MIN_S`, `PAUSA_MAX_S` | 5, 40 (ou os do servidor, o maior) |
| `PAUSA_CURTA_MS` | 300..1500 |
| `BLOCO_PAGINAS` | 10 → `PAUSA_LONGA_S` 60..180 |
| `ROLAGEM_PASSOS`, `ROLAGEM_PX` | 3..8, 300..900 |
| `JITTER_JANELA_MIN` | 0..20 |
| `DORMIR_FILA_VAZIA_MIN` | 15 |
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from sociman_coletor import janela as _janela

PAUSA_MIN_S = 5
PAUSA_MAX_S = 40
PAUSA_CURTA_MS = (300, 1500)
BLOCO_PAGINAS = 10
PAUSA_LONGA_S = (60, 180)
ROLAGEM_PASSOS = (3, 8)
ROLAGEM_PX = (300, 900)
JITTER_JANELA_MIN = (0, 20)
DORMIR_FILA_VAZIA_MIN = 15
MOUSE_PASSOS = (5, 25)


@dataclass(frozen=True)
class LimitesEfetivos:
    """`min(local, servidor)` para páginas, imagens e teto da rodada; `max` para as pausas;
    interseção para a janela (FR-016)."""

    paginas_dia: int
    imagens_dia: int
    imagens_por_produto: int
    itens_por_coleta: int
    pausa_min_s: int
    pausa_max_s: int
    janela: _janela.Janela | None


def _menor(local: int | None, servidor: int) -> int:
    return servidor if local is None else min(local, servidor)


def _maior(local: int | None, servidor: int) -> int:
    return servidor if local is None else max(local, servidor)


def limites_efetivos(local, servidor, janela_servidor=None) -> LimitesEfetivos:
    """`local` = `config.LimitesLocais` (campos opcionais); `servidor` = `modelos.Limites` da
    fila; `janela_servidor` = `modelos.Janela` (ou qualquer objeto com `inicio` e `fim`)."""
    pausa_min = _maior(local.pausa_min_s, servidor.pausa_min_s)
    pausa_max = _maior(local.pausa_max_s, servidor.pausa_max_s)
    if pausa_max < pausa_min:
        pausa_max = pausa_min
    janela = None
    if janela_servidor is not None:
        janela = _janela.Janela(janela_servidor.inicio, janela_servidor.fim)
        if local.janela_inicio is not None or local.janela_fim is not None:
            local_j = _janela.Janela(
                janela.inicio if local.janela_inicio is None else local.janela_inicio,
                janela.fim if local.janela_fim is None else local.janela_fim,
            )
            janela = _janela.intersecao(janela, local_j)
    return LimitesEfetivos(
        paginas_dia=_menor(local.paginas_dia, servidor.paginas_dia),
        imagens_dia=_menor(local.imagens_dia, servidor.imagens_dia),
        imagens_por_produto=servidor.imagens_por_produto,
        itens_por_coleta=servidor.itens_por_coleta,
        pausa_min_s=pausa_min,
        pausa_max_s=pausa_max,
        janela=janela,
    )


class Ritmo:
    """Gera as esperas e os gestos. Com `semente` fixa a sequência é reprodutível (teste)."""

    def __init__(
        self,
        pausa_min_s: float = PAUSA_MIN_S,
        pausa_max_s: float = PAUSA_MAX_S,
        semente: int | None = None,
    ):
        if pausa_max_s < pausa_min_s:
            raise ValueError("pausa_max_s menor que pausa_min_s")
        self.pausa_min_s = float(pausa_min_s)
        self.pausa_max_s = float(pausa_max_s)
        self.rng = random.Random(semente)

    def _dois_uniformes(self, minimo: float, maximo: float) -> float:
        """Soma de dois uniformes em [min/2, max/2]: fica em [min, max] com viés para o centro."""
        a = self.rng.uniform(minimo / 2, maximo / 2)
        b = self.rng.uniform(minimo / 2, maximo / 2)
        return a + b

    def pausa(self) -> float:
        """Segundos entre páginas e antes de um clique."""
        return self._dois_uniformes(self.pausa_min_s, self.pausa_max_s)

    def pausa_curta_ms(self) -> int:
        """Milissegundos entre passos de rolagem e movimentos de mouse."""
        return self.rng.randint(*PAUSA_CURTA_MS)

    def pausa_longa_s(self) -> float:
        """Segundos de descanso a cada `BLOCO_PAGINAS` páginas."""
        return self._dois_uniformes(*PAUSA_LONGA_S)

    def rolagem(self) -> list[int]:
        """Os deslocamentos (px) de uma rolagem em passos."""
        passos = self.rng.randint(*ROLAGEM_PASSOS)
        return [self.rng.randint(*ROLAGEM_PX) for _ in range(passos)]

    def ponto_mouse(self, largura: int = 1280, altura: int = 900) -> tuple[int, int, int]:
        """(x, y, passos) de um movimento de mouse dentro da janela."""
        x = self.rng.randint(int(largura * 0.1), int(largura * 0.9))
        y = self.rng.randint(int(altura * 0.1), int(altura * 0.9))
        return x, y, self.rng.randint(*MOUSE_PASSOS)

    def jitter_janela_min(self) -> int:
        """Minutos aleatórios depois de `janela_inicio` antes do 1º pedido do dia."""
        return self.rng.randint(*JITTER_JANELA_MIN)

    @staticmethod
    def dormir_fila_vazia_s() -> int:
        return DORMIR_FILA_VAZIA_MIN * 60

    @staticmethod
    def e_fim_de_bloco(paginas: int) -> bool:
        return paginas > 0 and paginas % BLOCO_PAGINAS == 0
