"""O que a limpeza de 90 dias pode apagar dos roteiros (research R12; exceção 1 ampliada da
constitution 4.5.0, FR-049 e FR-050). Só **seleciona**: quem apaga é o `geracao/limpeza.py`
(fase 2), o único módulo que alcança o `storage.apagar_por_excecao`.

- **elegíveis:** tomadas locais, narrações e as prévias e acabamentos (gerações
  `roteiro.montagem`/`roteiro.acabamento`) com `desuso_em` há mais de 90 dias e ainda com o
  arquivo;
- **protegidos** (calculado na hora, nunca gravado): tudo o que está numa `roteiro_entregas`
  (narração, prévia, acabamento, tomadas e keyframes); a tomada escolhida de cada cena; a tomada
  atual de cada posição e a narração ativa (e a prévia e o acabamento apontados) de roteiro não
  arquivado; as tomadas do Flow nunca entram (só as locais são elegíveis).

`filtrar` é puro: recebe os ids elegíveis e os protegidos e devolve o que sai.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.cenas.models import Cena, CenaTomada, TomadaOrigem
from sociman_api.geracao.models import Geracao, GeracaoCandidato
from sociman_api.roteiros.models import Roteiro, RoteiroCena, RoteiroEntrega, RoteiroNarracao

JANELA = timedelta(days=90)
PASSOS_VIDEO = ("roteiro.montagem", "roteiro.acabamento")


@dataclass
class Conjunto:
    tomadas: set[uuid.UUID] = field(default_factory=set)
    narracoes: set[uuid.UUID] = field(default_factory=set)
    geracoes: set[uuid.UUID] = field(default_factory=set)


def filtrar(elegiveis: Conjunto, protegidos: Conjunto) -> tuple[Conjunto, int]:
    """O que sai (puro) e quantos ficaram por estarem protegidos."""
    sai = Conjunto(tomadas=elegiveis.tomadas - protegidos.tomadas,
                   narracoes=elegiveis.narracoes - protegidos.narracoes,
                   geracoes=elegiveis.geracoes - protegidos.geracoes)
    mantidos = (len(elegiveis.tomadas & protegidos.tomadas)
                + len(elegiveis.narracoes & protegidos.narracoes)
                + len(elegiveis.geracoes & protegidos.geracoes))
    return sai, mantidos


def _uuid(valor: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(valor)) if valor else None
    except ValueError:
        return None


def protegidos(db: Session) -> Conjunto:
    p = Conjunto()
    for e in db.scalars(select(RoteiroEntrega)):
        p.narracoes.add(e.narracao_id)
        p.geracoes |= {e.montagem_geracao_id, e.acabamento_geracao_id}
        p.tomadas |= {t for t in (_uuid(x.get("tomadaId")) for x in e.posicoes or []) if t}
    p.tomadas |= {t for t in db.scalars(select(Cena.tomada_escolhida_id).where(
        Cena.tomada_escolhida_id.is_not(None)))}
    vivos = select(Roteiro.id).where(Roteiro.archived_at.is_(None))
    p.tomadas |= {t for t in db.scalars(select(RoteiroCena.tomada_id).where(
        RoteiroCena.tomada_id.is_not(None), RoteiroCena.roteiro_id.in_(vivos)))}
    for r in db.scalars(select(Roteiro).where(Roteiro.archived_at.is_(None))):
        if r.narracao_id:
            p.narracoes.add(r.narracao_id)
        p.geracoes |= {g for g in (r.montagem_geracao_id, r.acabamento_geracao_id) if g}
    return p


def elegiveis(db: Session, agora: datetime, lote: int) -> Conjunto:
    limite = agora - JANELA
    return Conjunto(
        tomadas=set(db.scalars(select(CenaTomada.id).where(
            CenaTomada.origem == TomadaOrigem.geracao_local, CenaTomada.limpa_em.is_(None),
            CenaTomada.desuso_em.is_not(None), CenaTomada.desuso_em < limite)
            .order_by(CenaTomada.desuso_em).limit(lote))),
        narracoes=set(db.scalars(select(RoteiroNarracao.id).where(
            RoteiroNarracao.limpa_em.is_(None), RoteiroNarracao.desuso_em.is_not(None),
            RoteiroNarracao.desuso_em < limite).order_by(RoteiroNarracao.desuso_em)
            .limit(lote))),
        geracoes=set(db.scalars(select(Geracao.id).where(
            Geracao.passo.in_(PASSOS_VIDEO), Geracao.desuso_em.is_not(None),
            Geracao.desuso_em < limite, Geracao.id.in_(select(GeracaoCandidato.geracao_id).where(
                GeracaoCandidato.video_key.is_not(None))))
            .order_by(Geracao.desuso_em).limit(lote))))
