"""Bloco `<desempenho>` do prompt `ia/3` (spec 023, US4; FR-044 a FR-047; research R8).

Só nos tipos `postagem.*` e no `guia.testar`, e só com `usar_desempenho` ligado no perfil:
- os temas `ampliar` (nomes) e os padrões aceitos (texto curto);
- as hashtags "evitar", com "não use" (o servidor também as tira da proposta, `ia/saida.py`);
- até 3 exemplos por regra fixa: maior resíduo encolhido entre os entregues da conta (ou do
  perfil, sem posts na conta) nos últimos 90 dias, de conta não travada e não anonimizada, sem
  palavra proibida efetiva; empate pelo mais recente.

Sem preferências e sem exemplos, não há bloco (e a chamada grava as versões como NULL).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.analytics import filtros
from sociman_api.aprendizado import analise as an
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import preferencias as prefs
from sociman_api.cortes.models import Corte
from sociman_api.ia import guia as guia_mod
from sociman_api.ia import prompt
from sociman_api.metricas.models import VideoRede

TIPOS = ("postagem.titulo", "postagem.descricao", "postagem.hashtags", "postagem.textos",
         "guia.testar")


@dataclass(frozen=True)
class Exemplo:
    video_id: uuid.UUID
    legenda: str
    gancho: str


@dataclass(frozen=True)
class Bloco:
    perfil_version: int
    conta_version: int | None
    ampliar: tuple[str, ...]
    padroes: tuple[str, ...]
    evitar: tuple[str, ...]
    exemplos: tuple[Exemplo, ...]

    def render(self) -> str:
        linhas: list[str] = []
        if self.ampliar:
            linhas.append("Temas que rendem (ampliar): " + "; ".join(self.ampliar))
        if self.padroes:
            linhas.append("Padrões aceitos pelo dono:" + "".join(f"\n- {p}" for p in self.padroes))
        if self.evitar:
            linhas.append("Hashtags a evitar (não use): " + " ".join(self.evitar))
        for e in self.exemplos:  # textos da rede: sem tag de fechamento dentro (R8)
            corpo = f"Legenda: {prompt._limpar(e.legenda)}" + (
                f"\nGancho: {prompt._limpar(e.gancho)}" if e.gancho else "")
            linhas.append(f'<exemplo post="{e.video_id}">\n{corpo}\n</exemplo>')
        return "\n".join(linhas)


def _encolhido(p: an.PostA) -> float:
    return p.peso * (p.desvio_rendimento or 0.0) / (p.peso + K.K_ENCOLHIMENTO)


def exemplos(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
             proibidas: tuple[str, ...], agora: datetime | None = None) -> list[Exemplo]:
    agora = agora or datetime.now(ZoneInfo("UTC"))
    hoje = agora.astimezone(ZoneInfo(filtros.fuso())).date()
    res = an.calcular(db, perfil_id, None, de=hoje - timedelta(days=K.EXEMPLOS_DIAS - 1),
                      ate=hoje, agora=agora, so=frozenset())
    travadas = set(res.travadas)
    candidatos = [p for p in res.posts if p.desvio_rendimento is not None
                  and p.conta not in travadas and not p.p.anonima]
    da_conta = [p for p in candidatos if p.conta == conta_id] if conta_id else []
    escolhidos = da_conta or candidatos
    escolhidos.sort(key=lambda p: (-_encolhido(p), -p.p.publicado_em.timestamp()))
    out: list[Exemplo] = []
    for p in escolhidos:
        video = db.get(VideoRede, p.p.video_id)
        if video is None or video.anonimizado_em is not None:
            continue
        legenda = (video.legenda or video.titulo or "").strip()[:K.EXEMPLO_LEGENDA_MAX]
        corte = db.get(Corte, p.p.conteudo_id) if p.p.conteudo_id else None
        gancho = ((corte.hook_text or "") if corte else "").strip()[:K.EXEMPLO_GANCHO_MAX]
        if not legenda or guia_mod.achar_proibidas([legenda, gancho], proibidas):
            continue
        out.append(Exemplo(p.p.video_id, legenda, gancho))
        if len(out) >= K.EXEMPLOS_MAX:
            break
    return out


def bloco(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
          proibidas: tuple[str, ...] = ()) -> Bloco | None:
    """O bloco do perfil (e da conta); None com `usar_desempenho` desligado ou sem nada."""
    from sociman_api.aprendizado.models import Tema

    ef = prefs.efetivas(db, perfil_id, conta_id)
    if not ef.usar_desempenho:
        return None
    nomes = {str(i): n for i, n in db.execute(select(Tema.id, Tema.nome).where(
        Tema.perfil_id == perfil_id))}
    ampliar = tuple(nomes[t] for t in sorted(ef.ampliados) if t in nomes)
    exs = exemplos(db, perfil_id, conta_id, proibidas)
    padroes = tuple(p["texto"] for p in ef.padroes if p.get("texto"))
    if not (ampliar or padroes or ef.hashtags_evitar or exs):
        return None
    return Bloco(perfil_version=ef.perfil_version,
                 conta_version=ef.conta_version if conta_id is not None else None,
                 ampliar=ampliar, padroes=padroes, evitar=tuple(ef.hashtags_evitar),
                 exemplos=tuple(exs))
