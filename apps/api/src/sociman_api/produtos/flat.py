"""Instrução do flat lay (research R7), pura: o `flat_instrucao` do pipeline
(`comfyui-docker/pipeline/produtos.py`), com a cor da variante.

A mesma função monta o pedido do `produto.flat` e confere o aviso `flat_desatualizado` (R10): se
o texto de hoje difere do que foi gravado em `geracoes.params.instrucao`, o flat foi feito com
outra ficha.
"""

from typing import Any


def instrucao(ficha: Any, variante: Any) -> str:
    """`ficha`: o produto (ou qualquer objeto com `material_en`, `formato_corte` e
    `detalhes_visiveis`); `variante`: com `cor_en`. Os campos entram exatamente como estão."""
    detalhes = "; ".join(ficha.detalhes_visiveis or [])
    cor = variante.cor_en or ""
    return ("Turn this product photo into a realistic flat-lay photo: the same item lying "
            "completely flat and relaxed on a plain white surface, seen from directly above, "
            "with soft natural fabric folds and no volume at all, as if simply laid down on a "
            "table; nobody is wearing it, no invisible body or mannequin shape. "
            f"Keep exactly the same item: {cor} {ficha.material_en or ''}, "
            f"{ficha.formato_corte or ''}; {detalhes}. "
            "Same color, texture, cut and logo. Plain white background, soft even light.")
