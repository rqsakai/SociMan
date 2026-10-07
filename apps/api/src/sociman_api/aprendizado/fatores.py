"""Fatores de cada post (spec 023, FR-013, R1), a partir do `PostAnalisado` da 019 e da
classificação.

Fatores: tema principal, estilo do gancho, tamanho do gancho, duração, faixa de 3 h, dia da
semana, canal-fonte, modo de envio e hashtag (as hashtags viram blocos em `analise.py`). Posts
sem vínculo entram só nos fatores que não dependem do corte (como na 019).

O estagnado é o da 019 (`analytics.alertas.desempenho`): ≥ 6 h e < 10% da mediana da conta na
mesma idade, ou ≤ 1 view sem 5 referências. Só leitura.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from sociman_api.analytics import alertas
from sociman_api.analytics.base import PostAnalisado
from sociman_api.aprendizado import constantes as K

FATORES = ("tema", "estilo_gancho", "gancho_tamanho", "duracao", "faixa_horario", "dia_semana",
           "canal_fonte", "modo", "hashtag")
ROTULO_FATOR = {"tema": "Tema", "estilo_gancho": "Estilo do gancho",
                "gancho_tamanho": "Tamanho do gancho", "duracao": "Duração",
                "faixa_horario": "Horário de publicação", "dia_semana": "Dia da semana",
                "canal_fonte": "Canal-fonte", "modo": "Modo de envio", "hashtag": "Hashtag"}
ROTULO_ESTILO = {"pergunta": "Pergunta", "revelacao": "Revelação", "numero_lista": "Número/lista",
                 "polemica": "Polêmica", "humor": "Humor", "voce_sabia": "Você sabia",
                 "ordem_direta": "Ordem direta", "outro": "Outro"}
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
MODOS = {"lembrete": "Lembrete", "criar_rascunho": "Rascunho", "publicar": "Publicar direto"}


@dataclass(frozen=True)
class ClassInfo:
    """O que a análise usa da classificação (sem a linha do ORM)."""

    tema_id: uuid.UUID | None
    estilo_gancho: str | None


@dataclass(frozen=True)
class Fator:
    fator: str
    valor: str
    rotulo: str


def faixa(valor: int | None, faixas: Sequence[tuple[int | None, str]]) -> tuple[str, str] | None:
    """(chave, rótulo) da faixa do valor; None sem valor."""
    if valor is None:
        return None
    for i, (ate, rotulo) in enumerate(faixas):
        if ate is None or valor <= ate:
            return str(i), rotulo
    return None  # pragma: no cover


def faixa_horario(hora: int) -> tuple[str, str]:
    ini = (hora // K.HORAS_FAIXA) * K.HORAS_FAIXA
    return str(ini), f"{ini:02d}h–{ini + K.HORAS_FAIXA:02d}h"


def de_post(p: PostAnalisado, c: ClassInfo | None,
            temas: Mapping[uuid.UUID, str]) -> list[Fator]:
    """Os fatores do post, exceto as hashtags (que viram blocos na análise)."""
    out: list[Fator] = []
    if c is not None and c.tema_id is not None and c.tema_id in temas:
        out.append(Fator("tema", str(c.tema_id), temas[c.tema_id]))
    if c is not None and c.estilo_gancho is not None:
        out.append(Fator("estilo_gancho", c.estilo_gancho,
                         ROTULO_ESTILO.get(c.estilo_gancho, c.estilo_gancho)))
    if p.vinculado and (g := faixa(p.gancho_caracteres, K.FAIXAS_GANCHO)):
        out.append(Fator("gancho_tamanho", *g))
    if d := faixa(p.duracao_s, K.FAIXAS_DURACAO):
        out.append(Fator("duracao", *d))
    out.append(Fator("faixa_horario", *faixa_horario(p.hora_local)))
    out.append(Fator("dia_semana", str(p.dia_semana), DIAS[p.dia_semana]))
    if p.canal_fonte is not None:
        out.append(Fator("canal_fonte", str(p.canal_fonte.id), p.canal_fonte.titulo))
    if p.vinculado and p.modo:
        out.append(Fator("modo", p.modo, MODOS.get(p.modo, p.modo)))
    return out


def estagnados(db: Session, posts: Sequence[PostAnalisado], agora: datetime) -> set[uuid.UUID]:
    """Os posts estagnados pela regra da 019 (alertas calculados na leitura)."""
    series = {p.serie_id for p in posts if not p.anonima}
    lista = alertas.desempenho(posts, alertas._pontos(db, series), agora)
    return {a.alvo.id for a in lista if a.tipo == "estagnado"}
