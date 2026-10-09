"""Avisos da cena (research R4): função pura, calculada em cada leitura. Nenhum bloqueia.

- `fala_longa`: palavras da fala acima de `ceil(15 × duração / 8)`;
- `duracao_modo`: modo `ingredientes` com duração diferente de 8 s;
- `produto_sem_foto`: produto com nome e sem foto;
- `proibida`: palavra proibida do guia efetivo do perfil na fala, na ação ou no texto na tela
  (`ia.guia.achar_proibidas`: palavra inteira, sem acento e sem caixa);
- `assets_mudaram`: prompt congelado com versão do avatar ou do cenário diferente da atual, com o
  texto da parte antes e depois (o serviço monta as duas);
- `asset_arquivado`: avatar, cenário ou foto do produto arquivados.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sociman_api.cenas.models import CenaModo
from sociman_api.ia.guia import achar_proibidas

PALAVRAS_EM_8S = 15
_ROTULOS = {"avatar": "o avatar", "cenario": "o cenário"}
_ARQUIVADO = {"avatar": "O avatar está arquivado", "cenario": "O cenário está arquivado",
              "produto": "A foto do produto está arquivada"}


@dataclass(frozen=True)
class Aviso:
    codigo: str
    mensagem: str
    campo: str | None = None
    detalhe: dict[str, Any] | None = None


@dataclass(frozen=True)
class Mudanca:
    """Uma parte do prompt que mudou desde o congelamento."""

    papel: str  # "avatar" | "cenario"
    antes: str
    depois: str


@dataclass(frozen=True)
class EntradaAvisos:
    acao: str
    duracao_s: int
    modo: CenaModo
    fala: str | None = None
    texto_tela: str | None = None
    produto_nome: str | None = None
    produto_com_foto: bool = False
    proibidas: Sequence[str] = ()
    mudancas: Sequence[Mudanca] = ()
    arquivados: Sequence[str] = field(default_factory=tuple)  # papéis: avatar, cenario, produto


def limite_palavras(duracao_s: int) -> int:
    return math.ceil(PALAVRAS_EM_8S * duracao_s / 8)


def palavras(texto: str | None) -> int:
    return len((texto or "").split())


def calcular(e: EntradaAvisos) -> list[Aviso]:
    avisos: list[Aviso] = []
    n, limite = palavras(e.fala), limite_palavras(e.duracao_s)
    if n > limite:
        avisos.append(Aviso("fala_longa", f"Fala longa para {e.duracao_s} s: {n} palavras "
                            f"(até {limite})", "fala", {"palavras": n, "limite": limite}))
    if e.modo == CenaModo.ingredientes and e.duracao_s != 8:
        avisos.append(Aviso("duracao_modo", "No modo ingredientes o Flow gera 8 s; "
                            f"a cena está com {e.duracao_s} s", "duracaoS"))
    if (e.produto_nome or "").strip() and not e.produto_com_foto:
        avisos.append(Aviso("produto_sem_foto", "Produto sem foto: o Flow pode inventar a "
                            "aparência", "produtoImagemId"))
    for campo, camel, texto in (("fala", "fala", e.fala), ("acao", "acao", e.acao),
                                ("texto_tela", "textoTela", e.texto_tela)):
        achadas = achar_proibidas([texto or ""], e.proibidas)
        if achadas:
            avisos.append(Aviso("proibida", f"Palavra proibida pelo guia: {', '.join(achadas)}",
                                camel, {"palavras": achadas}))
    for m in e.mudancas:
        avisos.append(Aviso("assets_mudaram", f"{_ROTULOS[m.papel].capitalize()} mudou desde que "
                            "o prompt foi congelado; use \"Remontar prompt\"", None,
                            {"parte": m.papel, "antes": m.antes, "depois": m.depois}))
    for papel in e.arquivados:
        avisos.append(Aviso("asset_arquivado", _ARQUIVADO[papel],
                            {"avatar": "avatarId", "cenario": "cenarioId",
                             "produto": "produtoImagemId"}[papel], {"parte": papel}))
    return avisos
