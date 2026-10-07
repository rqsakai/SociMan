"""Afinidade dos vídeos-fonte com o perfil (spec 023, US4; FR-040 a FR-043; research R9).

Só leitura: o Descobrir (`canais/service_videos.py`) e as oportunidades do Mercado
(`analytics/mercado.py`) importam este módulo, com perfil escolhido.

- **Por tema** (uma vez por requisição): a_t = clamp(θ_t / ln 2, −1, 1) × peso da confiança
  (o θ só acima da amostra mínima); `ampliar` aceito → max(a_t + 0,5, 0,5); `cortar` → −1 e
  oculto. Preferências do dono valem mesmo com amostra pequena;
- **Por canal-fonte:** o mesmo cálculo sobre o fator canal;
- **Final:** a = clamp(0,7·a_tema + 0,3·a_canal, −1, 1); pontos = 20·a, somados ao score exibido
  (0–100). Entre os temas que casam, `cortar` vence, depois o de maior |a_t|;
- **Casamento** (plano B do R9): `translate(lower(título || ' ' || descrição))` sem acento contra
  `\\m(kw1|kw2…)\\M` custa segundos sobre dezenas de milhares de vídeos, então a trilha grava o
  resultado em `aprendizado_fonte_temas` (`fonte_temas.py`) e a leitura só consulta essa tabela.
  Enquanto o perfil não está casado com a taxonomia atual, a afinidade fica neutra.

Sem perfil, sem taxonomia ou tudo neutro: `valores` devolve None, e o chamador mantém a 006
intacta (FR-043). O direito do canal nunca é lido nem gravado aqui (princípio II).
"""

import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Numeric, String, case, cast, false, func, literal, select
from sqlalchemy.orm import Session

from sociman_api.aprendizado import constantes as K

ACENTOS = "áàâãäåéèêëíìîïóòôõöúùûüçñýÿ"
SEM_ACENTO = "aaaaaaeeeeiiiiooooouuuucnyy"


@dataclass(frozen=True)
class TemaAfinidade:
    id: uuid.UUID
    nome: str
    palavras: tuple[str, ...]
    a: float
    cortado: bool
    rotulo_efeito: str | None  # "≈ 2,4× o típico da conta" (o motivo)


@dataclass(frozen=True)
class Valores:
    perfil_id: uuid.UUID
    temas: tuple[TemaAfinidade, ...]
    canais: dict[uuid.UUID, float]

    @property
    def cortados(self) -> bool:
        return any(t.cortado for t in self.temas)


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def de_efeito(theta: float | None, confianca: str) -> float:
    if theta is None:
        return 0.0
    return _clamp(theta / math.log(2)) * K.PESO_CONFIANCA.get(confianca, 0.0)


def valores(db: Session, perfil_id: uuid.UUID | None) -> Valores | None:
    """Os pesos do perfil (None = neutro: a 006 fica igual)."""
    if perfil_id is None:
        return None
    from sociman_api.aprendizado import analise as an  # import tardio: `analytics` importa
    from sociman_api.aprendizado import preferencias as prefs  # este módulo (sem ciclo)
    from sociman_api.aprendizado.models import Tema

    temas = list(db.scalars(select(Tema).where(Tema.perfil_id == perfil_id,
                                               Tema.archived_at.is_(None))))
    if not any(t.palavras_chave for t in temas):  # FR-043: sem taxonomia, neutra (sem custo)
        return None
    from sociman_api.aprendizado import fonte_temas

    if not fonte_temas.em_dia(db, perfil_id):  # ainda não casado: neutra (sem regex na leitura)
        return None
    ef = prefs.efetivas(db, perfil_id)
    res = an.calcular(db, perfil_id, so=frozenset({"tema", "canal_fonte"}))
    canais: dict[uuid.UUID, float] = {}
    for e in res.efeitos:
        if e.fator == "canal_fonte" and e.parte == "rendimento":
            a = de_efeito(e.theta, e.confianca)
            if a:
                canais[uuid.UUID(e.valor)] = a
    out: list[TemaAfinidade] = []
    for t in temas:
        if not t.palavras_chave:
            continue
        e = an.efeito_de(res, "tema", str(t.id), "rendimento")
        a = de_efeito(e.theta if e else None, e.confianca if e else "amostra_pequena")
        pref = ef.temas.get(str(t.id))
        cortado = pref == "cortar"
        if pref == "ampliar":
            a = min(1.0, max(a + K.AMPLIAR_SOMA, K.AMPLIAR_SOMA))
        elif cortado:
            a = -1.0
        rotulo = None
        if e is not None and e.efeito is not None and not cortado:
            rotulo = f"≈ {e.efeito:.1f}× o típico da conta".replace(".", ",")
        elif pref == "ampliar":
            rotulo = "tema a ampliar"
        elif cortado:
            rotulo = "tema cortado"
        out.append(TemaAfinidade(t.id, t.nome, tuple(t.palavras_chave), a, cortado, rotulo))
    if not any(t.a for t in out) and not canais:
        return None
    return Valores(perfil_id, tuple(out), canais)


def regex(palavras: Sequence[str]) -> str:
    """`\\m(kw1|kw2)\\M` com as palavras escapadas (regex do PG, ARE)."""
    corpo = "|".join(re.escape(p) for p in palavras)
    return rf"\m({corpo})\M"


def texto_sem_acento(titulo: ColumnElement, descricao: ColumnElement) -> ColumnElement:
    return func.translate(func.lower(titulo + literal(" ") + func.coalesce(descricao, "")),
                          ACENTOS, SEM_ACENTO)


@dataclass(frozen=True)
class Expressoes:
    pontos: ColumnElement  # −20..20
    tema_id: ColumnElement  # texto (uuid) ou NULL
    cortado: ColumnElement  # bool


def _ordem(temas: Sequence[TemaAfinidade]) -> list[TemaAfinidade]:
    """`cortar` vence, depois o de maior |a|."""
    return sorted((t for t in temas if t.a or t.cortado),
                  key=lambda t: (not t.cortado, -abs(t.a), t.nome))


def expressoes(v: Valores, video_id: ColumnElement, canal_id: ColumnElement) -> Expressoes:
    from sociman_api.aprendizado.fonte_temas import FonteTema

    ordem = _ordem(v.temas)
    if ordem:
        casos = [(select(FonteTema.video_fonte_id).where(
            FonteTema.perfil_id == v.perfil_id, FonteTema.tema_id == t.id,
            FonteTema.video_fonte_id == video_id).exists(), t) for t in ordem]
        a_tema = case(*[(cond, literal(t.a)) for cond, t in casos], else_=literal(0.0))
        tema_id = case(*[(cond, literal(str(t.id))) for cond, t in casos],
                       else_=cast(None, String))
        cortados = [cond for cond, t in casos if t.cortado]
        cortado = case(*[(c, True) for c in cortados], else_=False) if cortados else false()
    else:
        a_tema, tema_id, cortado = literal(0.0), cast(None, String), false()
    if v.canais:
        a_canal = case(*[(canal_id == cid, literal(a)) for cid, a in v.canais.items()],
                       else_=literal(0.0))
    else:
        a_canal = literal(0.0)
    a = func.greatest(-1.0, func.least(1.0, K.PESO_TEMA * a_tema + K.PESO_CANAL * a_canal))
    return Expressoes(pontos=cast(a * K.PESO_AFINIDADE, Numeric), tema_id=tema_id,
                      cortado=cortado)


def score_com(score_exibido: ColumnElement, pontos: ColumnElement) -> ColumnElement:
    """O score exibido mais a afinidade, de 0 a 100, com 1 casa (a ordem e o cursor)."""
    return func.round(cast(func.greatest(0, func.least(100, score_exibido + pontos)), Numeric), 1)


def tema(v: Valores, tema_id: str | None) -> TemaAfinidade | None:
    if tema_id is None:
        return None
    return next((t for t in v.temas if str(t.id) == tema_id), None)


def motivo(v: Valores, tema_id: str | None, pontos: float, maior_006: float) -> str | None:
    """O motivo vira o tema quando |pontos| ≥ 10 e passa a maior contribuição da 006."""
    t = tema(v, tema_id)
    if t is None or abs(pontos) < K.MOTIVO_MIN_PONTOS or abs(pontos) <= maior_006:
        return None
    return f"Tema {t.nome}: {t.rotulo_efeito}" if t.rotulo_efeito else f"Tema {t.nome}"
