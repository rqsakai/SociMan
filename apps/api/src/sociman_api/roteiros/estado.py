"""O que a máquina e as telas leem do roteiro (research R1, R10, R12 e R16): consultas e
derivações, sem gravar nada além dos campos técnicos das posições (`recalcular_tempos`).

- **ordem dos status:** cada status tem um nível; um `aguardando_X` fica logo depois do trabalho
  de X. A máquina reposiciona o roteiro no nível da primeira etapa que deixou de estar atual;
- **narração atual:** a ativa, com o áudio, e com o `texto_hash` igual ao de agora (R10);
- **tomada útil** de uma posição (R10): não arquivada, com o arquivo, com duração suficiente e,
  se local, do keyframe atual da cena. A da posição vale até se for do Flow (escolha manual); as
  outras candidatas são a escolhida da cena (local) e a local mais recente;
- **assinatura** da prévia: a narração e (ordem, tomada, duração) de cada posição. A prévia e o
  acabamento guardam a assinatura no `params.extras`; mudou, deixaram de ser atuais.
"""

import hashlib
import json
import math
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset, AssetTipo
from sociman_api.cenas.models import Cena, CenaTomada, TomadaOrigem
from sociman_api.geracao.models import TERMINADOS, Geracao, GeracaoStatus
from sociman_api.roteiros import pronuncia, tempos
from sociman_api.roteiros.models import (
    Pronuncia,
    Roteiro,
    RoteiroCena,
    RoteiroEtapa,
    RoteiroNarracao,
    RoteiroStatus,
)
from sociman_api.vozes.models import Voz, VozOrigem, VozStatus

S = RoteiroStatus
NIVEL: dict[RoteiroStatus, int] = {
    S.rascunho: 0, S.planejando: 1, S.aguardando_texto: 2, S.narrando: 3,
    S.aguardando_narracao: 4, S.gerando_keyframes: 5, S.aguardando_keyframes: 6,
    S.gerando_clipes: 7, S.aguardando_clipes: 8, S.montando: 9, S.aguardando_final: 10,
    S.finalizando: 11, S.pronto: 12,
}
ETAPA_DO_STATUS: dict[RoteiroStatus, RoteiroEtapa] = {
    S.planejando: RoteiroEtapa.plano, S.narrando: RoteiroEtapa.narracao,
    S.gerando_keyframes: RoteiroEtapa.keyframes, S.gerando_clipes: RoteiroEtapa.clipes,
    S.montando: RoteiroEtapa.montagem, S.finalizando: RoteiroEtapa.acabamento,
}
STATUS_DA_ETAPA = {e: s for s, e in ETAPA_DO_STATUS.items()}
# O portão de cada `aguardando_*` e o status de trabalho que vem depois dele.
PORTAO_DO_AGUARDANDO: dict[RoteiroStatus, str] = {
    S.aguardando_texto: "texto", S.aguardando_narracao: "narracao",
    S.aguardando_keyframes: "keyframes", S.aguardando_clipes: "clipes",
    S.aguardando_final: "final",
}
AGUARDANDO_DO_PORTAO = {p: s for s, p in PORTAO_DO_AGUARDANDO.items()}
DEPOIS_DO_PORTAO: dict[str, RoteiroStatus] = {
    "texto": S.narrando, "narracao": S.gerando_keyframes, "keyframes": S.gerando_clipes,
    "clipes": S.montando, "final": S.finalizando,
}
PASSO_DA_ETAPA: dict[RoteiroEtapa, str] = {
    RoteiroEtapa.plano: "roteiro.plano", RoteiroEtapa.narracao: "roteiro.narracao",
    RoteiroEtapa.keyframes: "cena.keyframe", RoteiroEtapa.clipes: "cena.clipe",
    RoteiroEtapa.montagem: "roteiro.montagem", RoteiroEtapa.acabamento: "roteiro.acabamento",
}


def nivel(status: RoteiroStatus) -> int:
    return NIVEL.get(status, -1)


# ---- voz, avatar e pronúncias ----

def pronuncias_do_perfil(db: Session, perfil_id: uuid.UUID) -> dict[str, str]:
    rows = db.scalars(select(Pronuncia).where(Pronuncia.perfil_id == perfil_id,
                                              Pronuncia.archived_at.is_(None))
                      .order_by(Pronuncia.created_at, Pronuncia.id))
    return {p.escrita: p.falada for p in rows}


def problema_da_voz(voz: Voz | None, *, para_narrar: bool = True) -> tuple[str, str] | None:
    """(código, mensagem) se a voz não pode narrar (FR-003, R16); None = pode."""
    if voz is None:
        return "sem_voz", "Escolha uma voz para o roteiro"
    if voz.revogada:
        return "consentimento_revogado", "Consentimento revogado: a voz não pode gerar nada novo"
    if voz.archived:
        return "voz_invalida", "A voz está arquivada"
    if voz.status != VozStatus.aprovada or voz.ref_audio_id is None:
        return "voz_invalida", "A voz ainda não foi aprovada"
    if voz.origem == VozOrigem.gravacao and not voz.consentimento:
        return "voz_invalida", "A voz de gravação precisa do consentimento"
    if para_narrar and voz.sincronizada_em is None:
        return "voz_nao_sincronizada", "A voz ainda não foi enviada ao serviço de voz"
    return None


def problema_do_avatar(avatar: Asset | None) -> tuple[str, str] | None:
    if avatar is None:
        return None
    if avatar.tipo != AssetTipo.avatar:
        return "invalid_roteiro", "O avatar precisa ser um asset do tipo avatar"
    if avatar.revogado:
        return "consentimento_revogado", ("Consentimento revogado: o avatar não pode gerar nada "
                                          "novo")
    return None


def hash_atual(db: Session, r: Roteiro, ref_audio_id: Any = ...) -> str | None:
    """O `texto_hash` que a narração de agora teria (R10); None sem voz. `ref_audio_id` troca a
    referência da voz (a revogação apaga a de agora, e o que já foi narrado continua valendo)."""
    voz = db.get(Voz, r.voz_id) if r.voz_id else None
    if voz is None or not r.frases:
        return None
    ref = voz.ref_audio_id if ref_audio_id is ... else ref_audio_id
    return pronuncia.hash_atual(list(r.frases), pronuncias_do_perfil(db, r.perfil_id), voz.id,
                                ref, r.velocidade)


def narracao_ativa(db: Session, r: Roteiro) -> RoteiroNarracao | None:
    return db.get(RoteiroNarracao, r.narracao_id) if r.narracao_id else None


def narracao_atual(db: Session, r: Roteiro) -> bool:
    n = narracao_ativa(db, r)
    if n is None or n.audio_id is None:
        return False
    if n.texto_hash == hash_atual(db, r):
        return True
    voz = db.get(Voz, n.voz_id)
    if voz is not None and voz.revogada and n.voz_id == r.voz_id:  # FR-048: o feito fica
        g = db.get(Geracao, n.geracao_id)
        ref = (g.params or {}).get("refAudioId") if g is not None else None
        return n.texto_hash == hash_atual(db, r, uuid.UUID(ref) if ref else None)
    return False


def posicoes(r: Roteiro) -> list[RoteiroCena]:
    return sorted(r.posicoes_rel, key=lambda p: p.ordem)


def recalcular_tempos(db: Session, r: Roteiro) -> bool:
    """`inicio_s`/`duracao_s` das posições pela narração ativa (R6), só quando ela é atual; senão
    nulos. Devolve se as durações existem."""
    n = narracao_ativa(db, r) if narracao_atual(db, r) else None
    pos = posicoes(r)
    limites = None
    if n is not None and pos:
        try:
            limites = tempos.limites(n.tempos, [list(p.frases) for p in pos], float(n.total_s))
        except tempos.TemposInvalidos:
            limites = None
    for i, p in enumerate(pos):
        inicio = Decimal(str(limites[i].inicio_s)) if limites else None
        duracao = Decimal(str(limites[i].duracao_s)) if limites else None
        if p.inicio_s != inicio or p.duracao_s != duracao:
            p.inicio_s, p.duracao_s = inicio, duracao
    db.flush()
    return limites is not None


# ---- tomadas ----

def _ms(duracao_s: Decimal | float) -> int:
    return math.ceil(round(float(duracao_s) * 1000, 3))


def tomada_serve(t: CenaTomada | None, cena: Cena, duracao_s: Decimal | float, *,
                 aceita_flow: bool) -> bool:
    if t is None or t.cena_id != cena.id or t.archived or t.limpa_em is not None:
        return False
    if t.duracao_ms < _ms(duracao_s):
        return False
    if t.origem == TomadaOrigem.flow_manual:
        return aceita_flow
    return t.keyframe_image_id is not None and t.keyframe_image_id == cena.keyframe_inicial_id


def tomada_util(db: Session, cena: Cena, duracao_s: Decimal | float,
                atual_id: uuid.UUID | None) -> CenaTomada | None:
    """A ordem de preferência do R10: a da posição, a escolhida da cena e a local mais recente."""
    atual = db.get(CenaTomada, atual_id) if atual_id else None
    if tomada_serve(atual, cena, duracao_s, aceita_flow=True):
        return atual
    escolhida = db.get(CenaTomada, cena.tomada_escolhida_id) if cena.tomada_escolhida_id \
        else None
    if tomada_serve(escolhida, cena, duracao_s, aceita_flow=False):
        return escolhida
    locais = db.scalars(select(CenaTomada).where(
        CenaTomada.cena_id == cena.id, CenaTomada.origem == TomadaOrigem.geracao_local,
        CenaTomada.archived_at.is_(None), CenaTomada.limpa_em.is_(None),
        CenaTomada.keyframe_image_id == cena.keyframe_inicial_id)
        .order_by(CenaTomada.created_at.desc(), CenaTomada.id))
    return next((t for t in locais if tomada_serve(t, cena, duracao_s, aceita_flow=False)), None)


def assinatura(r: Roteiro) -> str:
    carga = {"narracao": str(r.narracao_id),
             "posicoes": [[p.ordem, str(p.tomada_id), f"{Decimal(str(p.duracao_s or 0)):.3f}"]
                          for p in posicoes(r)]}
    return hashlib.sha256(json.dumps(carga, sort_keys=True).encode()).hexdigest()


# ---- gerações ----

def extras(g: Geracao) -> dict[str, Any]:
    return (g.params or {}).get("extras") or {}


def do_roteiro(g: Geracao) -> uuid.UUID | None:
    """O roteiro de uma geração (o alvo, ou o `extras.roteiroId` dos passos da cena)."""
    if g.alvo_tipo.value == "roteiro":
        return g.alvo_id
    rid = extras(g).get("roteiroId")
    try:
        return uuid.UUID(str(rid)) if rid else None
    except ValueError:
        return None


def abertas(db: Session, passo: str, *, alvo_id: uuid.UUID | None = None,
            roteiro_id: uuid.UUID | None = None) -> list[Geracao]:
    stmt = select(Geracao).where(Geracao.passo == passo, Geracao.status.not_in(TERMINADOS))
    if alvo_id is not None:
        stmt = stmt.where(Geracao.alvo_id == alvo_id)
    if roteiro_id is not None:
        stmt = stmt.where(Geracao.params["extras"]["roteiroId"].astext == str(roteiro_id))
    return list(db.scalars(stmt.order_by(Geracao.created_at, Geracao.id)))


def em_revisao(g: Geracao) -> bool:
    return g.status == GeracaoStatus.revisao
