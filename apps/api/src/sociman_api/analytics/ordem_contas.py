"""Ordem estável das contas para a cor fixa por conta do analytics (spec 019, FR-006; R11).

Todas as contas da casa, inclusive as arquivadas e as de perfis arquivados, por `created_at` e
depois `id`: a n-ésima conta recebe `--chart-n` na SPA, e um filtro que esconde contas não repinta
as outras. Uma rota só, no lugar de um GET de perfil por perfil (que estourava o limite do edge).
Só leitura.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.analytics import schemas
from sociman_api.perfis.models import Conta


def calcular(db: Session) -> schemas.OrdemContasOut:
    contas = db.scalars(select(Conta).order_by(Conta.created_at, Conta.id)).all()
    return schemas.OrdemContasOut(contas=[
        schemas.ContaOrdem(conta_id=c.id, rotulo=f"@{c.handle.lstrip('@')}", rede=c.platform,
                           perfil_id=c.perfil_id)
        for c in contas])
