"""Filtro comum da leitura do mercado (FR-043; contracts/http-api.md, "Filtro comum").

- **Período:** dias no fuso do mercado; padrão `hoje − 29 … hoje` (`PERIODO_PADRAO_DIAS`); até
  `PERIODO_MAX_DIAS` → 400 `periodo_invalido`. O anterior tem a mesma duração e termina na véspera.
- **Perfil:** só restringe (produtos com interesse do perfil, ou com categoria nas do perfil);
  inexistente → 404.
- `mercado` (padrão `BR`), `rede`, `categoriaId` (e as filhas, pelo `caminho`), `lojaId`,
  `origem` (repetível), `soAcompanhados`, `q`, `ordenar` (campo com sufixo `:asc`), `limite`,
  `cursor` (opaco: a posição).
"""

import base64
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from sociman_api.errors import ApiError
from sociman_api.mercado import mercados
from sociman_api.mercado.constantes import LIMITE_LISTA_MAX, PERIODO_MAX_DIAS, PERIODO_PADRAO_DIAS
from sociman_api.mercado.models import InteresseOrigem
from sociman_api.perfis.models import Perfil, Platform

ORDENS = ("vendasPeriodo", "gmvPeriodo", "crescimento", "vendasTotais", "gmvTotal", "preco",
          "comissaoBp", "comissaoPorVenda", "retornoAfiliado", "nCriadores", "primeiraVezEm",
          "ultimaFotoEm", "titulo")
ORDEM_PADRAO = "vendasPeriodo"


@dataclass(frozen=True)
class Periodo:
    de: date
    ate: date

    @property
    def dias(self) -> int:
        return (self.ate - self.de).days + 1


@dataclass(frozen=True)
class Filtro:
    atual: Periodo
    anterior: Periodo
    mercado: str
    perfil_id: uuid.UUID | None = None
    rede: Platform | None = None
    categoria_id: uuid.UUID | None = None
    loja_id: uuid.UUID | None = None
    origens: tuple[InteresseOrigem, ...] = ()
    so_acompanhados: bool = False
    q: str | None = None
    ordenar: str = ORDEM_PADRAO
    desc: bool = True
    limite: int = 50
    offset: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def fuso(self) -> str:
        return mercados.mercado(self.mercado).tz


def periodos(de: date | None, ate: date | None, hoje: date) -> tuple[Periodo, Periodo]:
    ate = ate or hoje
    if de is None:
        de = ate - timedelta(days=PERIODO_PADRAO_DIAS - 1)
    if de > ate or (ate - de).days + 1 > PERIODO_MAX_DIAS:
        raise ApiError(400, "periodo_invalido",
                       f"Período inválido (até {PERIODO_MAX_DIAS} dias, no fuso do mercado)")
    dias = (ate - de).days + 1
    anterior_ate = de - timedelta(days=1)
    return Periodo(de, ate), Periodo(anterior_ate - timedelta(days=dias - 1), anterior_ate)


def ordenar_de(valor: str | None) -> tuple[str, bool]:
    if not valor:
        return ORDEM_PADRAO, True
    campo, _, sufixo = valor.partition(":")
    if campo not in ORDENS or sufixo not in ("", "asc", "desc"):
        raise ApiError(400, "entrada_invalida", f"ordenar: valor desconhecido ({valor})",
                       details={"field": "ordenar"})
    # Título em ordem alfabética por padrão; os números do maior para o menor.
    padrao_desc = campo != "titulo"
    return campo, (sufixo == "desc") if sufixo else padrao_desc


def cursor_para(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode().rstrip("=")


def offset_de(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        if not raw.startswith("o:"):
            raise ValueError
        return max(0, int(raw[2:]))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(400, "entrada_invalida", "cursor: inválido",
                       details={"field": "cursor"}) from exc


def montar(db: Session, *, de: date | None = None, ate: date | None = None,
           perfil_id: uuid.UUID | None = None, mercado: str | None = None,
           rede: Platform | None = None, categoria_id: uuid.UUID | None = None,
           loja_id: uuid.UUID | None = None, origem: list[InteresseOrigem] | None = None,
           so_acompanhados: bool = False, q: str | None = None, ordenar: str | None = None,
           limite: int = 50, cursor: str | None = None) -> Filtro:
    codigo = mercado or mercados.PADRAO
    mercados.mercado(codigo)
    atual, anterior = periodos(de, ate, mercados.hoje(codigo))
    if perfil_id is not None and db.get(Perfil, perfil_id) is None:
        raise ApiError(404, "not_found", "Perfil não encontrado")
    campo, desc = ordenar_de(ordenar)
    return Filtro(atual=atual, anterior=anterior, mercado=codigo, perfil_id=perfil_id, rede=rede,
                  categoria_id=categoria_id, loja_id=loja_id, origens=tuple(origem or ()),
                  so_acompanhados=so_acompanhados, q=(q or "").strip() or None, ordenar=campo,
                  desc=desc, limite=max(1, min(limite, LIMITE_LISTA_MAX)), offset=offset_de(cursor))
