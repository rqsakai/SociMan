"""A anonimização da 016 cobre a 023 (research R11), na mesma transação do `desconectar`.

Os textos que derivam da legenda e da transcrição saem; o que é categórico fica:
- classificação: `justificativa` e `sugestao_tema` → NULL (tema e estilo ficam);
- conferência: `nota` → NULL;
- análises que usaram posts da série: o `texto` e o `contraste` de cada hipótese viram
  "[removido: conta anonimizada]", mantendo `n` e os ids.

Nada é apagado. As séries anônimas nunca viram exemplo (R8) nem entram na análise da IA (R5).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from sociman_api.aprendizado.models import Analise, Classificacao, Conferencia

REMOVIDO = "[removido: conta anonimizada]"


def limpar(db: Session, video_ids: Sequence[uuid.UUID]) -> None:
    ids = list(video_ids)
    if not ids:
        return
    db.execute(update(Classificacao).where(Classificacao.video_id.in_(ids))
               .values(justificativa=None, sugestao_tema=None)
               .execution_options(synchronize_session=False))
    db.execute(update(Conferencia).where(Conferencia.video_id.in_(ids)).values(nota=None)
               .execution_options(synchronize_session=False))
    analises = db.scalars(select(Analise).where(
        Analise.hipoteses.is_not(None),
        or_(Analise.melhores.overlap(ids), Analise.comparaveis.overlap(ids))))
    for a in analises:
        a.hipoteses = [{**h, "texto": REMOVIDO, "contraste": REMOVIDO} for h in a.hipoteses or []]
