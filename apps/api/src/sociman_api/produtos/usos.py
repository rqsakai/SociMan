"""Onde o produto é usado (data-model "Regras derivadas", T036): as cenas da 010 ligadas ao
catálogo (`cenas.produto_id`). Só informa (`bloqueia = False`): arquivar o produto continua
permitido, e a cena mostra o aviso `produto_fora_de_aprovado`. Cenas arquivadas não contam."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.cenas.models import Cena
from sociman_api.produtos import schemas


def do_produto(db: Session, produto_id: uuid.UUID) -> list[schemas.UsoProduto]:
    cenas = db.execute(select(Cena.id, Cena.nome).where(
        Cena.produto_id == produto_id, Cena.archived_at.is_(None))
        .order_by(Cena.nome, Cena.id)).all()
    return [schemas.UsoProduto(origem="cena", rotulo=f"Cena: {nome}", href=f"/app/cenas/{cid}")
            for cid, nome in cenas]
