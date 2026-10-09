"""Casamento de um vídeo da rede com um destino do SociMan (research R10; Q3 = A).

Três condições, todas explicáveis e testáveis:
- **data:** `publicado_em` do vídeo dentro da janela da âncora do destino (a entrega do
  rascunho, `−5 min` a `+14 d`; ou o clique "Marcar como postado" de um lembrete, `−24 h` a
  `+1 h`). Um lembrete antes do clique não tem âncora e **nunca liga sozinho**;
- **duração:** `|V.duracao_s − duração do conteúdo em s| ≤ 1` (a rede arredonda para inteiro);
- **legenda:** Jaccard dos tokens normalizados (≥ 0,5 ou uma contém a outra → compatível; a do
  vídeo com menos de 3 tokens → neutra; o resto → incompatível).

A decisão automática exige **candidato único nos dois sentidos** (`pares_unicos`). O bloqueio
de um destino (houve `vinculo_desfeito` no histórico) e a âncora vêm do banco (`ancora`,
`bloqueados`). Nada aqui grava.
"""

import re
import unicodedata
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.conteudos.models import Conteudo, Modo
from sociman_api.cortes.models import Corte
from sociman_api.history import EntityVersion
from sociman_api.postagem.models import DestinoEstado, Postagem

Classe = Literal["compativel", "neutra", "incompativel"]
TipoAncora = Literal["entrega", "postado"]

JACCARD_MIN = 0.5
TOKENS_MIN = 3  # abaixo disso, a legenda do vídeo é "neutra" (o dono não colou a legenda)
DURACAO_TOLERANCIA_S = 1
# Janela de `publicado_em` em torno da âncora, bordas incluídas (R10, Q3 = A).
JANELAS: dict[TipoAncora, tuple[timedelta, timedelta]] = {
    "entrega": (timedelta(minutes=5), timedelta(days=14)),
    "postado": (timedelta(hours=24), timedelta(hours=1)),
}
DESFEITO = "vinculo_desfeito"

_HASHTAG = re.compile(r"#\w+", re.UNICODE)
_NAO_PALAVRA = re.compile(r"[^\w\s]|_", re.UNICODE)


# ---- legenda ----

def normalizar(texto: str | None) -> list[str]:
    """Minúsculas, sem acento, sem `#tags`, sem emoji, sem pontuação, sem espaço repetido."""
    if not texto:
        return []
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                         if not unicodedata.combining(c))
    sem_tags = _HASHTAG.sub(" ", sem_acento)
    return _NAO_PALAVRA.sub(" ", sem_tags).split()


def classificar_legenda(legenda_video: str | None, legenda_destino: str | None) -> Classe:
    """`L(V)` (a da rede) contra `L(D)` (`publicacao.legenda.legenda_tiktok(destino)`)."""
    v = normalizar(legenda_video)
    if len(v) < TOKENS_MIN:
        return "neutra"
    d = normalizar(legenda_destino)
    if not d:
        return "incompativel"
    tv, td = " ".join(v), " ".join(d)
    if tv in td or td in tv:
        return "compativel"
    sv, sd = set(v), set(d)
    jaccard = len(sv & sd) / len(sv | sd)
    return "compativel" if jaccard >= JACCARD_MIN else "incompativel"


# ---- duração e âncora ----

def duracao_compativel(video_s: float, conteudo_s: float | None) -> bool:
    return conteudo_s is not None and abs(video_s - conteudo_s) <= DURACAO_TOLERANCIA_S


@dataclass(frozen=True)
class Ancora:
    tipo: TipoAncora
    em: datetime

    def contem(self, publicado_em: datetime) -> bool:
        antes, depois = JANELAS[self.tipo]
        return self.em - antes <= publicado_em <= self.em + depois

    def minutos(self, publicado_em: datetime) -> int:
        return round((publicado_em - self.em).total_seconds() / 60)


def ancora(destino: Postagem, entregue_em: datetime | None) -> Ancora | None:
    """A âncora do destino (tabela de R10). `entregue_em` é o da busca do nível 1, se houver.

    - `criar_rascunho` com busca, em `rascunho_criado` ou `postado` → a entrega;
    - `lembrete` em `postado` → o clique "Marcar como postado" (`posted_at`);
    - o resto (lembrete antes do clique, `publicar`, `falhou`, arquivado) → nenhuma.
    """
    if destino.archived_at is not None:
        return None
    if destino.modo == Modo.criar_rascunho and entregue_em is not None \
            and destino.estado in (DestinoEstado.rascunho_criado, DestinoEstado.postado):
        return Ancora("entrega", entregue_em)
    if destino.modo == Modo.lembrete and destino.estado == DestinoEstado.postado \
            and destino.posted_at is not None:
        return Ancora("postado", destino.posted_at)
    return None


# ---- decisão ----

@dataclass(frozen=True)
class Par:
    video_id: uuid.UUID
    destino_id: uuid.UUID
    classe: Classe


def pares_unicos(pares: Iterable[Par]) -> tuple[list[Par], set[uuid.UUID]]:
    """(pares que ligam sozinhos, destinos ambíguos).

    Contam só os pares não incompatíveis (a data e a duração já foram conferidas por quem
    montou os pares). Um par liga quando o vídeo tem exatamente um destino **e** o destino tem
    exatamente um vídeo. Ambíguo: o destino com 2 ou mais vídeos, ou com um vídeo disputado por
    outro destino (nada é ligado; o dono escolhe).
    """
    validos = [p for p in pares if p.classe != "incompativel"]
    por_video = Counter(p.video_id for p in validos)
    por_destino = Counter(p.destino_id for p in validos)
    ligam = [p for p in validos if por_video[p.video_id] == 1 and por_destino[p.destino_id] == 1]
    ambiguos = {p.destino_id for p in validos
                if por_video[p.video_id] > 1 or por_destino[p.destino_id] > 1}
    return ligam, ambiguos


# ---- leituras do banco ----

def bloqueados(db: Session, destino_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Destinos com `vinculo_desfeito` no histórico: só se ligam pela ação do dono (R11)."""
    ids = list(set(destino_ids))
    if not ids:
        return set()
    return set(db.scalars(
        select(EntityVersion.entity_id).distinct()
        .where(EntityVersion.entity_type == "postagem", EntityVersion.entity_id.in_(ids),
               EntityVersion.details["acao"].astext == DESFEITO)
    ))


def duracoes_s(db: Session, conteudo_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, float]:
    """A duração do vídeo de cada conteúdo em segundos (a do corte ou a do vídeo próprio)."""
    ids = list(set(conteudo_ids))
    if not ids:
        return {}
    rows = db.execute(
        select(Conteudo.id, Conteudo.duration_ms, Corte.duration_ms)
        .outerjoin(Corte, Corte.id == Conteudo.corte_id)
        .where(Conteudo.id.in_(ids))
    )
    return {i: (proprio if proprio is not None else corte) / 1000
            for i, proprio, corte in rows if (proprio or corte) is not None}
