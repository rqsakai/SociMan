"""Recomendações por regra, calculadas na leitura (spec 023, US3; FR-034, FR-035, FR-038;
research R6).

As regras (constantes visíveis na tela) olham só o rendimento, e só efeitos de confiança
moderada ou forte, fora de "não separável", de "quase só com" e de "travada" (FR-028); um
efeito "puxado por 1" só vale se o efeito sem o maior post também passar:
- tema `ampliar` (≥ 1,5×) e `cortar` (≤ 0,5×, n ≥ 8);
- hashtag `fixar` (≥ 1,3×) e `evitar` (≤ 0,7×), só hashtag sozinha (um bloco de várias não);
- padrão de gancho, de duração e de horário (≥ 1,5×).

Chave estável `"<tipo>:<escopo>:<alvo>"`. Não aparecem: as já em vigor (preferência igual,
hashtag já fixa ou já evitada), as com aceite vigente e as rejeitadas, salvo quando o n dobrou
ou a faixa de confiança mudou (com o selo "já rejeitada em"). As abertas de hipótese entram
como estão. Nada é gravado aqui.
"""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.aprendizado import analise as an
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import fatores as fat
from sociman_api.aprendizado import preferencias as prefs
from sociman_api.aprendizado import schemas
from sociman_api.aprendizado.models import Decisao, DecisaoEstado, Tema
from sociman_api.perfis.service_perfis import get_perfil_or_404

BLOQUEANTES = ("nao_separavel", "quase_so_com", "travada")
PADROES = {"estilo_gancho": "padrao_gancho", "duracao": "padrao_duracao",
           "faixa_horario": "padrao_horario"}
TEXTO_PADRAO = {"padrao_gancho": "Gancho no estilo {r}", "padrao_duracao": "Clipes de {r}",
                "padrao_horario": "Publicar entre {r}"}
O_QUE_MUDA = {
    "tema_ampliar": "O Descobrir e o Mercado sobem vídeos deste tema, e o assistente passa a "
                    "recebê-lo como tema a ampliar.",
    "tema_cortar": "Vídeos deste tema somem do Descobrir e do Mercado (dá para mostrá-los com o "
                   "filtro), e o assistente evita o tema.",
    "hashtag_fixar": "A hashtag entra nas fixas do guia de comunicação, e o sistema a inclui em "
                     "toda geração de textos.",
    "hashtag_evitar": "O assistente não usa mais a hashtag, e o sistema a tira das propostas.",
    "padrao_gancho": "O assistente recebe o padrão como inspiração ao escrever.",
    "padrao_duracao": "O assistente recebe o padrão como inspiração ao escrever.",
    "padrao_horario": "O agendamento mostra a janela como dica (nada é agendado sozinho).",
}


@dataclass(frozen=True)
class Candidata:
    chave: str
    tipo: str
    alvo: schemas.AprendizadoAlvo
    efeito: an.Efeito
    motivo: str


def escopo_chave(conta_id: uuid.UUID | None) -> str:
    return f"conta:{conta_id}" if conta_id is not None else "perfil"


def _passa(e: an.Efeito, teste) -> bool:
    if e.theta is None or e.confianca not in K.CONFIANCAS_RECOMENDAVEIS:
        return False
    if any(e.tem(b) for b in BLOQUEANTES):
        return False
    if not teste(math.exp(e.theta), e):
        return False
    if e.tem("puxado_por_1"):
        return e.sem_maior_theta is not None and teste(math.exp(e.sem_maior_theta), e)
    return True


def _fmt(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def regras(efeitos: Sequence[an.Efeito], conta_id: uuid.UUID | None,
           conta_travada: bool = False) -> list[Candidata]:
    """As candidatas das regras de FR-035 (puro: testado sem banco)."""
    if conta_travada:  # R4: nenhuma recomendação nasce de evidência só de conta travada
        return []
    esc = escopo_chave(conta_id)
    out: list[Candidata] = []
    for e in efeitos:
        if e.parte != "rendimento":
            continue
        n = f"n = {e.n_posts}, {e.confianca}"
        if e.fator == "tema":
            alvo = schemas.AprendizadoAlvo(tema_id=uuid.UUID(e.valor), tema_nome=e.rotulo)
            if _passa(e, lambda x, _: x >= K.AMPLIAR_MIN):
                out.append(Candidata(f"tema_ampliar:{esc}:{e.valor}", "tema_ampliar", alvo, e,
                                     f"O tema {e.rotulo} rende ≈ {_fmt(math.exp(e.theta))}× o "
                                     f"típico da conta ({n})."))
            elif _passa(e, lambda x, ef: x <= K.CORTAR_MAX and ef.n_posts >= K.CORTAR_MIN_N):
                out.append(Candidata(f"tema_cortar:{esc}:{e.valor}", "tema_cortar", alvo, e,
                                     f"O tema {e.rotulo} rende ≈ {_fmt(math.exp(e.theta))}× o "
                                     f"típico da conta ({n})."))
        elif e.fator == "hashtag" and "+" not in e.valor:
            tag = f"#{e.valor}"
            alvo = schemas.AprendizadoAlvo(hashtag=tag)
            if _passa(e, lambda x, _: x >= K.FIXAR_MIN):
                out.append(Candidata(f"hashtag_fixar:{esc}:{tag}", "hashtag_fixar", alvo, e,
                                     f"{tag} rende ≈ {_fmt(math.exp(e.theta))}× dentro do mesmo "
                                     f"tema ({n})."))
            elif _passa(e, lambda x, _: x <= K.EVITAR_MAX):
                out.append(Candidata(f"hashtag_evitar:{esc}:{tag}", "hashtag_evitar", alvo, e,
                                     f"{tag} rende ≈ {_fmt(math.exp(e.theta))}× dentro do mesmo "
                                     f"tema ({n})."))
        elif e.fator in PADROES and _passa(e, lambda x, _: x >= K.PADRAO_MIN):
            tipo = PADROES[e.fator]
            texto = TEXTO_PADRAO[tipo].format(r=e.rotulo.lower() if tipo == "padrao_gancho"
                                              else e.rotulo)
            out.append(Candidata(f"{tipo}:{esc}:{e.valor}", tipo,
                                 schemas.AprendizadoAlvo(padrao=texto), e,
                                 f"{fat.ROTULO_FATOR[e.fator]} {e.rotulo} rende ≈ "
                                 f"{_fmt(math.exp(e.theta))}× o típico da conta ({n})."))
    return out


def reaparece(c: Candidata, d: Decisao) -> bool:
    """FR-038: a rejeitada volta com o n dobrado ou outra faixa de confiança."""
    return c.efeito.n_posts >= 2 * d.n_decisao or c.efeito.confianca != d.faixa_decisao


def efeito_out(e: an.Efeito) -> schemas.AprendizadoEfeito:
    return schemas.AprendizadoEfeito(
        fator=e.fator, valor=e.valor, rotulo=e.rotulo, parte=e.parte, efeito=e.efeito,
        intervalo=list(e.intervalo) if e.intervalo else None, n_posts=e.n_posts,
        n_dias=e.n_dias, confianca=e.confianca, faltam=e.faltam, mediana_bruta=e.mediana_bruta,
        avisos=[schemas.AprendizadoAviso(**a.__dict__) for a in e.avisos])


def _escopo(conta_id: uuid.UUID | None) -> schemas.AprendizadoEscopo:
    return schemas.AprendizadoEscopo(tipo="conta" if conta_id else "perfil", conta_id=conta_id)


def da_hipotese(d: Decisao) -> schemas.AprendizadoRecomendacao:
    alvo = schemas.AprendizadoAlvo(**{k: v for k, v in (d.evidencia.get("alvo") or {}).items()
                                      if k in ("temaId", "temaNome", "hashtag", "padrao")})
    return schemas.AprendizadoRecomendacao(
        chave=d.chave, tipo=d.tipo, escopo=_escopo(d.conta_id), alvo=alvo,  # type: ignore[arg-type]
        motivo=d.evidencia.get("motivo") or "Hipótese da análise da IA, escolhida pelo dono.",
        evidencia=None, o_que_muda=O_QUE_MUDA[d.tipo], origem="hipotese", decisao_id=d.id)


def _em_vigor(c: Candidata, ef: prefs.Efetivas, fixas: set[str]) -> bool:
    if c.tipo in ("tema_ampliar", "tema_cortar"):
        return ef.temas.get(str(c.alvo.tema_id)) == c.tipo.removeprefix("tema_")
    if c.tipo == "hashtag_fixar":
        return c.alvo.hashtag in fixas
    if c.tipo == "hashtag_evitar":
        return c.alvo.hashtag in ef.hashtags_evitar
    tipo = c.tipo.removeprefix("padrao_")
    return any(p.get("tipo") == tipo and p.get("texto") == c.alvo.padrao for p in ef.padroes)


def _guia_fixas(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None
                ) -> tuple[list[str], int]:
    from sociman_api.ia import guia

    p = guia.linha(db, perfil_id, None)
    pc = guia.GuiaCampos.de_linha(p) if p is not None else None
    if conta_id is None:
        return list(pc.hashtags_fixas if pc else ()), guia.FIXAS_PERFIL_MAX
    c = guia.linha(db, perfil_id, conta_id)
    cc = guia.GuiaCampos.de_linha(c) if c is not None else None
    return list(guia.fixas_somadas(pc, cc)), guia.maximo_fixas(cc)


@dataclass
class Calculadas:
    abertas: list[schemas.AprendizadoRecomendacao]
    decididas: list[schemas.AprendizadoDecisao]


def calcular(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None = None,
             medida: str = "h24", agora: datetime | None = None) -> Calculadas:
    get_perfil_or_404(db, perfil_id)
    res = an.calcular(db, perfil_id, conta_id, medida, agora=agora)  # type: ignore[arg-type]
    travada = conta_id is not None and conta_id in res.travadas
    candidatas = regras(res.efeitos, conta_id, travada)
    ef = prefs.efetivas(db, perfil_id, conta_id)
    fixas, maximo = _guia_fixas(db, perfil_id, conta_id)
    decisoes = list(db.scalars(select(Decisao).where(Decisao.perfil_id == perfil_id)
                               .order_by(Decisao.decidido_em.desc().nulls_first(),
                                         Decisao.created_at.desc())))
    ultima: dict[str, Decisao] = {}
    for d in decisoes:
        if d.estado != DecisaoEstado.aberta:
            ultima.setdefault(d.chave, d)
    abertas: list[schemas.AprendizadoRecomendacao] = []
    for c in candidatas:
        if _em_vigor(c, ef, set(fixas)):
            continue
        d = ultima.get(c.chave)
        rejeitada_em = None
        if d is not None and not d.revertida:
            if d.estado == DecisaoEstado.aceita:
                continue
            if not reaparece(c, d):
                continue
            rejeitada_em = d.decidido_em
        bloqueio = None
        if c.tipo == "hashtag_fixar" and len(fixas) >= maximo:
            bloqueio = schemas.AprendizadoBloqueio(code="fixas_no_maximo", fixas=fixas,
                                                   maximo=maximo)
        abertas.append(schemas.AprendizadoRecomendacao(
            chave=c.chave, tipo=c.tipo, escopo=_escopo(conta_id), alvo=c.alvo,  # type: ignore[arg-type]
            motivo=c.motivo, evidencia=efeito_out(c.efeito), o_que_muda=O_QUE_MUDA[c.tipo],
            origem="regra", ja_rejeitada_em=rejeitada_em, bloqueio=bloqueio))
    for d in decisoes:
        if d.estado == DecisaoEstado.aberta and d.conta_id == conta_id:
            abertas.append(da_hipotese(d))
    temas = {t.id: t for t in db.scalars(select(Tema).where(Tema.perfil_id == perfil_id))}
    decididas = []
    for d in decisoes:
        if d.estado == DecisaoEstado.aberta:
            continue
        tema_id = (d.evidencia.get("alvo") or {}).get("temaId")
        tema = temas.get(uuid.UUID(tema_id)) if tema_id else None
        superada = tema is not None and tema.archived
        decididas.append(prefs.decisao_out(db, d, superada))
    return Calculadas(abertas=abertas, decididas=decididas)


def out(c: Calculadas) -> schemas.AprendizadoRecomendacoesOut:
    return schemas.AprendizadoRecomendacoesOut(abertas=c.abertas, decididas=c.decididas)
