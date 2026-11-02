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

Spec 031 (vídeo guiado, data-model "Limpeza e revogação"):
- as **tomadas de trecho** são tomadas locais: entram pela mesma regra do `desuso_em` (quem troca
  ou solta o trecho marca), e ficam protegidas a tomada atual de cada trecho de roteiro não
  arquivado (`roteiro_trechos`) e as de um vídeo entregue (`posicoes[].trechos`);
- a **imagem de um quadro arquivado** (refeito) é elegível 90 dias depois do `archived_at` (o
  `desuso_em` do quadro). Fica protegida a imagem de quadro ativo (o quadro atual nunca é apagado;
  a cena derivada copia a imagem da origem) ou arquivado há menos de 90 dias, os espelhos
  `keyframe_inicial_id`/`keyframe_final_id` de qualquer cena, os quadros de um vídeo entregue
  (`posicoes[].quadros`) e a imagem que alguma tomada referencia como início ou fim (a tomada
  guarda a referência, `ck_tomadas_origem_local`). As opções não escolhidas são da fase 1.

`filtrar` é puro: recebe os ids elegíveis e os protegidos e devolve o que sai.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from sociman_api.cenas.models import Cena, CenaQuadro, CenaTomada, TomadaOrigem
from sociman_api.geracao.models import Geracao, GeracaoCandidato
from sociman_api.roteiros.models import (
    Roteiro,
    RoteiroCena,
    RoteiroEntrega,
    RoteiroNarracao,
    RoteiroTrecho,
)

JANELA = timedelta(days=90)
PASSOS_VIDEO = ("roteiro.montagem", "roteiro.acabamento")


@dataclass
class Conjunto:
    tomadas: set[uuid.UUID] = field(default_factory=set)
    narracoes: set[uuid.UUID] = field(default_factory=set)
    geracoes: set[uuid.UUID] = field(default_factory=set)
    imagens: set[uuid.UUID] = field(default_factory=set)  # 031: as dos quadros arquivados


def filtrar(elegiveis: Conjunto, protegidos: Conjunto) -> tuple[Conjunto, int]:
    """O que sai (puro) e quantos ficaram por estarem protegidos."""
    sai = Conjunto(tomadas=elegiveis.tomadas - protegidos.tomadas,
                   narracoes=elegiveis.narracoes - protegidos.narracoes,
                   geracoes=elegiveis.geracoes - protegidos.geracoes,
                   imagens=elegiveis.imagens - protegidos.imagens)
    mantidos = (len(elegiveis.tomadas & protegidos.tomadas)
                + len(elegiveis.narracoes & protegidos.narracoes)
                + len(elegiveis.geracoes & protegidos.geracoes)
                + len(elegiveis.imagens & protegidos.imagens))
    return sai, mantidos


def _uuid(valor: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(valor)) if valor else None
    except ValueError:
        return None


def protegidos(db: Session, agora: datetime | None = None) -> Conjunto:
    p = Conjunto()
    for e in db.scalars(select(RoteiroEntrega)):
        p.narracoes.add(e.narracao_id)
        p.geracoes |= {e.montagem_geracao_id, e.acabamento_geracao_id}
        for x in e.posicoes or []:
            p.tomadas |= {t for t in [_uuid(x.get("tomadaId"))] + [
                _uuid(y.get("tomadaId")) for y in x.get("trechos") or []] if t}
            p.imagens |= {i for i in (_uuid(q) for q in x.get("quadros") or []) if i}
    p.tomadas |= {t for t in db.scalars(select(Cena.tomada_escolhida_id).where(
        Cena.tomada_escolhida_id.is_not(None)))}
    vivos = select(Roteiro.id).where(Roteiro.archived_at.is_(None))
    p.tomadas |= {t for t in db.scalars(select(RoteiroCena.tomada_id).where(
        RoteiroCena.tomada_id.is_not(None), RoteiroCena.roteiro_id.in_(vivos)))}
    for r in db.scalars(select(Roteiro).where(Roteiro.archived_at.is_(None))):
        if r.narracao_id:
            p.narracoes.add(r.narracao_id)
        p.geracoes |= {g for g in (r.montagem_geracao_id, r.acabamento_geracao_id) if g}
    # 031: a tomada atual de cada trecho e as imagens de quadro ainda em uso.
    p.tomadas |= set(db.scalars(select(RoteiroTrecho.tomada_id).where(
        RoteiroTrecho.tomada_id.is_not(None), RoteiroTrecho.roteiro_id.in_(vivos))))
    limite = (agora if agora is not None else db.scalar(select(func.now()))) - JANELA
    p.imagens |= set(db.scalars(select(CenaQuadro.image_id).where(
        CenaQuadro.image_id.is_not(None),
        or_(CenaQuadro.archived_at.is_(None), CenaQuadro.archived_at >= limite))))
    for inicial, final in db.execute(select(Cena.keyframe_inicial_id, Cena.keyframe_final_id)
                                     .where(Cena.keyframe_inicial_id.is_not(None))):
        p.imagens |= {i for i in (inicial, final) if i}
    for inicio, fim in db.execute(select(CenaTomada.keyframe_image_id,
                                         CenaTomada.keyframe_fim_image_id)):
        p.imagens |= {i for i in (inicio, fim) if i}
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
            .order_by(Geracao.desuso_em).limit(lote))),
        # As que uma tomada referencia ficam de fora já aqui (protegidas para sempre, não podem
        # ocupar o lote e esconder as outras).
        imagens=set(db.scalars(select(CenaQuadro.image_id).where(
            CenaQuadro.archived_at.is_not(None), CenaQuadro.archived_at < limite,
            CenaQuadro.image_id.is_not(None),
            ~exists().where(or_(CenaTomada.keyframe_image_id == CenaQuadro.image_id,
                                CenaTomada.keyframe_fim_image_id == CenaQuadro.image_id)))
            .group_by(CenaQuadro.image_id)
            .order_by(func.min(CenaQuadro.archived_at)).limit(lote))))
