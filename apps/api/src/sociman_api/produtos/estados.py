"""Regras do cadastro do produto (research R8, R9 e R11), puras: sem banco e sem rede.

`proximo` decide o status do produto e as gerações a pedir a partir de:
- o produto e as variantes **ativas** (qualquer objeto com os atributos do modelo);
- `ultimas`: a geração mais recente de cada passo × variante (`Ultima`), com o status. Uma
  geração aberta (fila, rodando, revisão) não é pedida de novo; uma que falhou ou foi cancelada
  **não** é recriada sozinha (o passo fica pendente, com "Tentar de novo" na tela);
- `evento`: `edicao` (uma mudança humana que tira o `aprovado`, FR-019) ou `gancho` (uma
  transição de geração, ou uma ação que não mexe na ficha).

A ordem é a do pipeline: a ficha (Claude) antes da GPU (SC-002), o recorte de cada variante, e
o flat (só com `precisa_flat`) depois do recorte e com a ficha completa (a instrução usa a cor, o
material, o corte e os detalhes). `aprovado` só vem da ação Aprovar.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sociman_api.geracao.models import TERMINADOS, GeracaoStatus
from sociman_api.produtos.models import ProdutoStatus

FICHA, RECORTE, FLAT = "produto.ficha", "produto.recorte", "produto.flat"
PASSOS = (FICHA, RECORTE, FLAT)
Evento = Literal["edicao", "gancho"]
Motivo = Literal["ficha_incompleta", "sem_variante", "sem_recorte", "sem_flat", "sem_cor",
                 "geracao_em_andamento"]
_TEXTOS = ("nome_comercial", "categoria", "material_en", "material_pt", "formato_corte",
           "tamanho_relativo", "descricao_prompt", "descricao_venda")


@dataclass(frozen=True)
class Ultima:
    passo: str
    variante_id: uuid.UUID | None
    status: GeracaoStatus

    @property
    def aberta(self) -> bool:
        return self.status not in TERMINADOS


@dataclass(frozen=True)
class Pendencia:
    motivo: Motivo
    variante_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Decisao:
    status: ProdutoStatus
    pedidos: tuple[tuple[str, uuid.UUID | None], ...]  # (passo, variante_id)


def _cheio(valor: Any) -> bool:
    return valor is not None and str(valor).strip() != ""


def campos_completos(produto: Any) -> bool:
    """Todos os textos, as duas listas com ≥ 1 item e `precisa_flat` definido."""
    return (all(_cheio(getattr(produto, c)) for c in _TEXTOS)
            and bool(produto.detalhes_visiveis) and bool(produto.cuidados)
            and produto.precisa_flat is not None)


def tem_cor(variante: Any) -> bool:
    return _cheio(variante.cor_en) and _cheio(variante.cor_pt)


def ficha_completa(produto: Any, variantes: Sequence[Any]) -> bool:
    """R9: os campos e a cor (en e pt) de toda variante ativa."""
    return campos_completos(produto) and all(tem_cor(v) for v in variantes)


def _indice(ultimas: Iterable[Ultima]) -> dict[tuple[str, uuid.UUID | None], Ultima]:
    return {(u.passo, u.variante_id): u for u in ultimas}


def pendencias(produto: Any, variantes: Sequence[Any], abertas: Iterable[Ultima]
               ) -> list[Pendencia]:
    """O que falta para aprovar (FR-018), na ordem da tela. `abertas`: as gerações do produto
    ainda não terminadas (qualquer passo)."""
    out: list[Pendencia] = []
    if not campos_completos(produto) or produto.ficha_por is None:
        out.append(Pendencia("ficha_incompleta"))
    if not variantes:
        out.append(Pendencia("sem_variante"))
    for v in variantes:
        if not tem_cor(v):
            out.append(Pendencia("sem_cor", v.id))
        if v.recorte_image_id is None:
            out.append(Pendencia("sem_recorte", v.id))
        if produto.precisa_flat and v.flat_image_id is None:
            out.append(Pendencia("sem_flat", v.id))
    vistas: set[uuid.UUID | None] = set()
    for a in abertas:
        if a.aberta and a.variante_id not in vistas:
            vistas.add(a.variante_id)
            out.append(Pendencia("geracao_em_andamento", a.variante_id))
    return out


def proximo(produto: Any, variantes: Sequence[Any], ultimas: Iterable[Ultima],
            evento: Evento) -> Decisao:
    """O status e as gerações a pedir (R8). Idempotente: o que já tem geração (aberta, ou
    terminada sem sucesso) não é pedido de novo."""
    if not variantes:
        return Decisao(ProdutoStatus.rascunho, ())
    idx = _indice(ultimas)
    pedidos: list[tuple[str, uuid.UUID | None]] = []
    falta = False

    if produto.ficha_por is None:
        falta = True
        if (FICHA, None) not in idx:
            pedidos.append((FICHA, None))
    else:
        flat_liberado = bool(produto.precisa_flat) and campos_completos(produto)
        for v in variantes:
            if v.recorte_image_id is None:
                falta = True
                if (RECORTE, v.id) not in idx:
                    pedidos.append((RECORTE, v.id))
                continue
            if produto.precisa_flat and v.flat_image_id is None:
                falta = True
                if flat_liberado and tem_cor(v) and (FLAT, v.id) not in idx:
                    pedidos.append((FLAT, v.id))

    if falta:
        status = ProdutoStatus.gerando
    elif produto.status == ProdutoStatus.aprovado and evento != "edicao":
        status = ProdutoStatus.aprovado
    else:
        status = ProdutoStatus.revisao
    return Decisao(status, tuple(pedidos))
