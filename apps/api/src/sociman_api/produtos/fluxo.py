"""Orquestração dos passos do produto (research R8): o único ponto que decide o status e pede
as gerações `produto.*`.

`reavaliar` roda **na mesma transação** de cada evento (as ações do produto e os aplicadores da
021): lê as gerações do produto, aplica `estados.proximo` e cria as que faltam pelo serviço da
021 (`criar_para_alvo`), com o ator da ação (no gerador, quem pediu a geração que terminou). Não
grava a versão do produto: quem chama tira o snapshot antes e grava uma versão só, com o que
mudou (o resultado aplicado e o status). É idempotente: o que já tem geração não é pedido de
novo, então chamar duas vezes não cria nada a mais.

Sem rede e sem motor: criar a próxima geração é só INSERT (regra dos ganchos da 021).

Spec 029 (R4): o perfil base das gerações é o do produto, salvo o `perfil_base` de um pedido
humano (a ficha usa o guia dele; `None` = nenhum). Os passos que o fluxo encadeia sozinho
(recorte e flat, só imagem) voltam ao perfil base do produto.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.auth.deps import Actor
from sociman_api.geracao.models import Geracao, GeracaoAlvo
from sociman_api.perfis import base
from sociman_api.produtos import estados, flat
from sociman_api.produtos.models import Produto, ProdutoVariante


def _variante_id(g: Geracao) -> uuid.UUID | None:
    vid = ((g.params or {}).get("extras") or {}).get("varianteId")
    return uuid.UUID(vid) if vid else None


def geracoes(db: Session, produto_id: uuid.UUID) -> list[Geracao]:
    """Todas as gerações do produto, da mais antiga para a mais nova."""
    return list(db.scalars(
        select(Geracao).where(Geracao.alvo_tipo == GeracaoAlvo.produto,
                              Geracao.alvo_id == produto_id)
        .order_by(Geracao.created_at, Geracao.id)))


def ultimas(gs: list[Geracao]) -> list[estados.Ultima]:
    """A mais recente de cada passo × variante."""
    por_chave: dict[tuple[str, uuid.UUID | None], estados.Ultima] = {}
    for g in gs:
        u = estados.Ultima(g.passo, _variante_id(g), g.status)
        por_chave[(u.passo, u.variante_id)] = u
    return list(por_chave.values())


def abertas(gs: list[Geracao]) -> list[estados.Ultima]:
    return [u for u in (estados.Ultima(g.passo, _variante_id(g), g.status) for g in gs)
            if u.aberta]


# ---- os pedidos (params do data-model, imutáveis depois de criados) ----

def params_ficha(produto: Produto) -> dict[str, Any]:
    return {"instrucao": produto.obs or "", "referencias": [
        str(v.original_image_id) for v in produto.ativas()], "rotulo": None, "texto": None,
        "extras": {"nome": produto.name}}


def params_recorte(variante: ProdutoVariante) -> dict[str, Any]:
    return {"instrucao": "", "referencias": [str(variante.original_image_id)], "rotulo": None,
            "texto": None, "extras": {"varianteId": str(variante.id)}, "bloco": "cutout"}


def params_flat(produto: Produto, variante: ProdutoVariante) -> dict[str, Any]:
    instrucao = flat.instrucao(produto, variante)
    return {"instrucao": instrucao, "prompt": instrucao,
            "referencias": [str(variante.recorte_image_id)], "rotulo": None, "texto": None,
            "extras": {"varianteId": str(variante.id)}, "bloco": "keyframe"}


def pedir(db: Session, actor: Actor, produto: Produto, passo: str,
          variante: ProdutoVariante | None = None,
          perfil_base: base.Pedido = base.AUSENTE) -> Geracao:
    from sociman_api.geracao import service as geracao_service  # a 021 importa os aplicadores

    if passo == estados.FICHA:
        params = params_ficha(produto)
    elif passo == estados.RECORTE:
        assert variante is not None
        params = params_recorte(variante)
    else:
        assert variante is not None
        params = params_flat(produto, variante)
    return geracao_service.criar_para_alvo(db, actor, produto.perfil_id, passo,
                                           GeracaoAlvo.produto, produto.id, params,
                                           perfil_base=perfil_base)


def reavaliar(db: Session, actor: Actor, produto: Produto,
              evento: estados.Evento = "gancho",
              perfil_base: base.Pedido = base.AUSENTE) -> list[Geracao]:
    """Aplica `estados.proximo` (status e pedidos). Devolve as gerações criadas; o
    `perfil_base` vale para as que este evento cria."""
    db.flush()
    ativas = produto.ativas()
    decisao = estados.proximo(produto, ativas, ultimas(geracoes(db, produto.id)), evento)
    produto.status = decisao.status
    criadas = []
    for passo, variante_id in decisao.pedidos:
        variante = produto.variante(variante_id) if variante_id else None
        criadas.append(pedir(db, actor, produto, passo, variante, perfil_base))
    db.flush()
    return criadas
