"""As cenas que um vídeo guiado pode reaproveitar, com o nível (spec 031, research R7; FR-019,
FR-020 e FR-024). Só leitura.

- **`total`**: mesmo avatar, mesmo cenário e mesma variante do produto, cena `pronta`/`usada` com
  a sequência de quadros completa (nenhum provisório) e a tomada de cada trecho valendo
  (`estado.tomada_util_trecho`, R8): a posição usa a cena como está, sem GPU (SC-003);
- **`plano`**: o resto das que servem (outro avatar, cenário ou variante, ou uma cena da 010/011
  sem a sequência): a ação, a câmera, o movimento e os trechos vão para uma cena derivada;
- uma cena de **outro produto** nunca entra (FR-024); a sem produto entra como `plano`.

Como na 011, as cenas do perfil do roteiro e as sem perfil base, não arquivadas, das mais
recentes para as mais antigas.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sociman_api.cenas import quadros as cenas_quadros
from sociman_api.cenas.models import Cena, CenaStatus
from sociman_api.roteiros import estado
from sociman_api.roteiros.models import Roteiro, RoteiroProduto

LIMITE = 40


@dataclass(frozen=True)
class Candidata:
    cena: Cena
    nivel: str  # "total" | "plano"
    diferencas: tuple[str, ...]  # por que não é total (vazio no total)


def produto_do(r: Roteiro) -> RoteiroProduto | None:
    """O produto do vídeo guiado (um só, com a variante resolvida na criação)."""
    return min(r.produtos_rel, key=lambda p: p.ordem) if r.produtos_rel else None


def _diferencas(db: Session, r: Roteiro, c: Cena, rp: RoteiroProduto | None) -> list[str]:
    out = []
    if c.avatar_id != r.avatar_id:
        out.append("outro avatar")
    if c.cenario_id != r.cenario_id:
        out.append("outro cenário")
    if rp is None or c.produto_id != rp.produto_id:
        out.append("sem o produto")
    elif c.produto_variante_id != rp.produto_variante_id:
        out.append("outra cor do produto")
    if c.trechos is None:
        out.append("sem a sequência de quadros")
        return out
    if c.status not in (CenaStatus.pronta, CenaStatus.usada):
        out.append("ainda em rascunho")
    qs = cenas_quadros.ativos(db, c.id)
    if len(qs) != c.trechos + 1 or not cenas_quadros.completos(qs) or \
            any(q.provisorio for q in qs):
        out.append("sem os quadros aprovados")
    elif r.trecho_base_s is None or any(
            estado.tomada_util_trecho(db, c, t, r.trecho_base_s, None) is None
            for t in range(c.trechos)):
        out.append("sem os clipes de todos os trechos")
    return out


def classificar(db: Session, r: Roteiro, c: Cena) -> Candidata | None:
    """O nível de uma cena para o roteiro, ou None se ela não pode ser proposta (arquivada ou de
    outro produto)."""
    rp = produto_do(r)
    if c.archived or (c.produto_id is not None and (rp is None or c.produto_id != rp.produto_id)):
        return None
    dif = _diferencas(db, r, c, rp)
    return Candidata(cena=c, nivel="plano" if dif else "total", diferencas=tuple(dif))


def candidatas(db: Session, r: Roteiro, excluir: set[uuid.UUID] | None = None
               ) -> list[Candidata]:
    rp = produto_do(r)
    filtro_produto = Cena.produto_id.is_(None) if rp is None else \
        or_(Cena.produto_id == rp.produto_id, Cena.produto_id.is_(None))
    stmt = (select(Cena).where(Cena.archived_at.is_(None),
                               or_(Cena.perfil_id == r.perfil_id, Cena.perfil_id.is_(None)),
                               filtro_produto)
            .order_by(Cena.updated_at.desc(), Cena.id).limit(LIMITE))
    out = []
    for c in db.scalars(stmt):
        if excluir and c.id in excluir:
            continue
        cand = classificar(db, r, c)
        if cand is not None:
            out.append(cand)
    return out
