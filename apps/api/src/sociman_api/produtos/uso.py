"""Provedor `produto` do "em uso" da limpeza de 90 dias da 021 (research R12, T025): toda
imagem de `produto_variantes` (a original, o recorte e o flat, de variante ou produto
arquivados) está em uso e nunca é apagada, mesmo sem ter passado pelo `escolhido_id`."""

import uuid

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from sociman_api.geracao.uso import register
from sociman_api.produtos.models import ProdutoVariante


def _variantes(db: Session, image_id: uuid.UUID | None, audio_id: uuid.UUID | None) -> bool:
    return image_id is not None and bool(db.scalar(select(exists().where(or_(
        ProdutoVariante.original_image_id == image_id,
        ProdutoVariante.recorte_image_id == image_id,
        ProdutoVariante.flat_image_id == image_id)))))


register("produto", _variantes)
