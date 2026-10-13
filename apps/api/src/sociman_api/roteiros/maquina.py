"""A máquina de estados do roteiro (research R1, data-model §Máquina; FR-007 a FR-011, FR-035 e
FR-036).

`avancar(db, roteiro, ator)` é idempotente e só toca o banco (nenhuma rede): olha a etapa, pede o
que falta (pelas gerações da 021) e muda o status. Ela é chamada pelas ações humanas (com
`humano=True`: as recusas viram `ApiError`) e pelo `gancho` dos aplicadores dos 6 passos, na
mesma transação do gerador (as recusas viram `falhou` com a etapa).

A cada volta:
1. `recalcular_tempos` (as durações saem da narração ativa, R6);
2. **reposicionar** (invalidação, FR-035/036): o roteiro volta ao nível da 1ª etapa que deixou de
   estar atual (narração desatualizada → `narrando`; keyframe faltando → `gerando_keyframes`;
   tomada não útil → `gerando_clipes`; prévia de outra assinatura → `montando`; entrega de outra
   assinatura → `finalizando`). Nada é apagado; as gerações que ficaram velhas são canceladas no
   nome de quem mudou;
3. o handler da etapa pede o que falta ou passa pelo **portão** (para em `aguardando_*` com o
   portão ligado e o modo `revisar`).

O roteiro é travado (`FOR UPDATE`) por quem chama. Uma chamada aninhada (o gancho da escolha
automática dentro de um handler) só marca "de novo", e o laço de fora segue.
"""

import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset
from sociman_api.auth.deps import ROTEIRO, Actor
from sociman_api.cenas import service as cenas_service
from sociman_api.cenas.models import Cena, CenaStatus, CenaTomada
from sociman_api.errors import ApiError
from sociman_api.geracao import service as geracao_service
from sociman_api.geracao.models import Geracao, GeracaoStatus
from sociman_api.produtos.models import Produto, ProdutoStatus
from sociman_api.roteiros import estado, pedidos
from sociman_api.roteiros.estado import S
from sociman_api.roteiros.models import (
    PosicaoAviso,
    Roteiro,
    RoteiroCena,
    RoteiroEntrega,
    RoteiroEtapa,
    RoteiroModo,
)
from sociman_api.vozes.models import Voz

VOLTAS = 30
_ATIVOS: ContextVar[frozenset[uuid.UUID]] = ContextVar("roteiro_ativos", default=frozenset())
_DE_NOVO: ContextVar[set[uuid.UUID] | None] = ContextVar("roteiro_de_novo", default=None)


class Falha(Exception):
    """Uma regra impede a etapa: na ação humana vira 409; na máquina, `falhou`."""

    def __init__(self, etapa: RoteiroEtapa, codigo: str, mensagem: str,
                 details: dict[str, Any] | None = None):
        super().__init__(mensagem)
        self.etapa, self.codigo, self.mensagem, self.details = etapa, codigo, mensagem, details


# ---- auxiliares ----

def travar(db: Session, roteiro_id: uuid.UUID) -> Roteiro | None:
    return db.get(Roteiro, roteiro_id, with_for_update=True)


def gate_ligado(r: Roteiro, portao: str) -> bool:
    return r.modo == RoteiroModo.revisar and bool((r.portoes or {}).get(portao, True))


def falhar(r: Roteiro, etapa: RoteiroEtapa, codigo: str | None, mensagem: str | None) -> None:
    r.status = S.falhou
    r.etapa_falhou = etapa
    r.erro_code = codigo or "internal"
    r.erro_message = mensagem or "A etapa falhou"


def limpar_falha(r: Roteiro) -> None:
    r.etapa_falhou = None
    r.erro_code = None
    r.erro_message = None


def avisar(r: Roteiro, codigo: str, mensagem: str, ordem: int | None = None) -> None:
    item = {"code": codigo, "message": mensagem, **({"ordem": ordem} if ordem is not None
                                                    else {})}
    if item not in (r.avisos or []):
        r.avisos = [*(r.avisos or []), item]


def cancelar(db: Session, ator: Actor, g: Geracao, motivo: str) -> None:
    """Cancela uma geração aberta que ficou velha (FR-036), no nome de quem mudou."""
    if g.status in (GeracaoStatus.escolhido, GeracaoStatus.descartada, GeracaoStatus.cancelada,
                    GeracaoStatus.entregue, GeracaoStatus.falhou):
        return
    geracao_service.cancelar(db, ator, g.id, g.version)
    g.etapa_mensagem = motivo


def cenas_do(db: Session, r: Roteiro) -> list[tuple[RoteiroCena, Cena]]:
    return [(p, db.get(Cena, p.cena_id)) for p in estado.posicoes(r)]


def roteiros_da_cena(db: Session, cena_id: uuid.UUID) -> list[uuid.UUID]:
    return list(dict.fromkeys(db.scalars(
        select(RoteiroCena.roteiro_id).join(Roteiro, Roteiro.id == RoteiroCena.roteiro_id)
        .where(RoteiroCena.cena_id == cena_id, Roteiro.archived_at.is_(None))
        .order_by(RoteiroCena.roteiro_id))))


def _distintas(pares: list[tuple[RoteiroCena, Cena]]) -> list[tuple[int, Cena]]:
    vistas: dict[uuid.UUID, tuple[int, Cena]] = {}
    for p, c in pares:
        vistas.setdefault(c.id, (p.ordem, c))
    return list(vistas.values())


# ---- o que está atual ----

def _keyframes_ok(db: Session, r: Roteiro, nivel: int) -> bool:
    pares = cenas_do(db, r)
    if not pares or any(c.archived for _, c in pares):
        return False
    for _, c in _distintas(pares):
        if c.keyframe_inicial_id is None:
            if nivel > estado.nivel(S.aguardando_keyframes):
                return False
            if not any(estado.em_revisao(g) for g in estado.abertas(db, "cena.keyframe",
                                                                    alvo_id=c.id)):
                return False
        elif nivel > estado.nivel(S.aguardando_keyframes) and c.status == CenaStatus.rascunho:
            return False
    return True


def _tomadas_ok(db: Session, r: Roteiro) -> bool:
    for p, c in cenas_do(db, r):
        if p.duracao_s is None or p.tomada_id is None:
            return False
        t = db.get(CenaTomada, p.tomada_id)
        if not estado.tomada_serve(t, c, p.duracao_s, aceita_flow=True):
            return False
    return True


def _geracao_atual(db: Session, geracao_id: uuid.UUID | None, assinatura: str) -> bool:
    g = db.get(Geracao, geracao_id) if geracao_id else None
    return g is not None and g.status == GeracaoStatus.escolhido and \
        estado.extras(g).get("assinatura") == assinatura


def previa_ok(db: Session, r: Roteiro) -> bool:
    return _geracao_atual(db, r.montagem_geracao_id, estado.assinatura(r))


def entrega_ok(db: Session, r: Roteiro) -> bool:
    ultima = db.scalar(select(RoteiroEntrega).where(RoteiroEntrega.roteiro_id == r.id)
                       .order_by(RoteiroEntrega.created_at.desc()).limit(1))
    return ultima is not None and _geracao_atual(db, ultima.acabamento_geracao_id,
                                                 estado.assinatura(r))


def reposicionar(db: Session, r: Roteiro) -> None:
    """Volta o roteiro ao nível da 1ª etapa que deixou de estar atual (FR-035, FR-036)."""
    n = estado.nivel(r.status)
    if n <= estado.nivel(S.narrando):
        return
    alvo = None
    if not estado.narracao_atual(db, r):
        alvo = S.narrando
    elif n > estado.nivel(S.gerando_keyframes) and not _keyframes_ok(db, r, n):
        alvo = S.gerando_keyframes
    elif n > estado.nivel(S.gerando_clipes) and not _tomadas_ok(db, r):
        alvo = S.gerando_clipes
    elif n > estado.nivel(S.montando) and not previa_ok(db, r):
        alvo = S.montando
    elif n > estado.nivel(S.finalizando) and not entrega_ok(db, r):
        alvo = S.finalizando
    if alvo is not None:
        r.status = alvo


# ---- portões ----

def passar_keyframes(db: Session, r: Roteiro, ator: Actor) -> bool:
    """Marca `pronta` as cenas em `rascunho` (R8) com o ator da passagem; se a validação de
    `pronta` falhar, o roteiro para em `aguardando_keyframes` com o motivo."""
    for ordem, c in _distintas(cenas_do(db, r)):
        if c.status != CenaStatus.rascunho:
            continue
        cena = db.get(Cena, c.id, with_for_update=True)
        try:
            with db.begin_nested():
                cenas_service.marcar_pronta(db, ator, cena, {"acao": "pronta_pelo_roteiro",
                                                             "roteiroId": str(r.id)})
        except ApiError as exc:
            avisar(r, "cena_incompleta", f"A cena da posição {ordem + 1} não pôde ficar pronta: "
                                         f"{exc.message}", ordem)
            r.status = S.aguardando_keyframes
            return False
    r.status = S.gerando_clipes
    return True


def passar(db: Session, r: Roteiro, ator: Actor, portao: str) -> None:
    if portao == "keyframes":
        passar_keyframes(db, r, ator)
        return
    r.status = estado.DEPOIS_DO_PORTAO[portao]


def portao(db: Session, r: Roteiro, nome: str) -> None:
    """Fim do trabalho de uma etapa: para no portão ligado, ou segue (no automático, com o ator
    `system:roteiro`)."""
    if gate_ligado(r, nome):
        r.status = estado.AGUARDANDO_DO_PORTAO[nome]
    else:
        passar(db, r, ROTEIRO, nome)


# ---- etapas ----

def _planejando(db: Session, r: Roteiro, ator: Actor) -> None:
    if estado.abertas(db, "roteiro.plano", alvo_id=r.id):
        return
    pedidos.plano(db, ator, r)


def _narrando(db: Session, r: Roteiro, ator: Actor) -> None:
    if estado.narracao_atual(db, r):
        portao(db, r, "narracao")
        return
    if not r.frases or not r.posicoes_rel:
        raise Falha(RoteiroEtapa.narracao, "invalid_roteiro", "O roteiro não tem frases ou cenas")
    texto_hash = estado.hash_atual(db, r)
    espera = False
    for g in estado.abertas(db, "roteiro.narracao", alvo_id=r.id):
        if (g.params or {}).get("textoHash") == texto_hash:
            espera = True
        else:
            cancelar(db, ator, g, "A narração ficou desatualizada")
    if espera:
        return
    voz = db.get(Voz, r.voz_id) if r.voz_id else None
    problema = estado.problema_da_voz(voz)
    if problema:
        raise Falha(RoteiroEtapa.narracao, *problema)
    pedidos.narracao(db, ator, r, voz, texto_hash)


def _conferir_avatar(db: Session, r: Roteiro, etapa: RoteiroEtapa, cena: Cena) -> None:
    avatar_id = cena.avatar_id or r.avatar_id
    problema = estado.problema_do_avatar(db.get(Asset, avatar_id) if avatar_id else None)
    if problema:
        raise Falha(etapa, *problema)


def _conferir_produto(db: Session, cena: Cena, ordem: int) -> None:
    produto = db.get(Produto, cena.produto_id) if cena.produto_id else None
    if produto is not None and (produto.archived or produto.status != ProdutoStatus.aprovado):
        raise Falha(RoteiroEtapa.keyframes, "produto_fora_de_aprovado",
                    f"O produto {produto.nome_comercial or produto.name} da posição {ordem + 1} "
                    "não está aprovado", {"ordem": ordem})


def _gerando_keyframes(db: Session, r: Roteiro, ator: Actor) -> None:
    from sociman_api.roteiros import automatico

    pares = cenas_do(db, r)
    arquivadas = [p.ordem for p, c in pares if c.archived]
    for p, c in pares:
        p.aviso = PosicaoAviso.cena_arquivada.value if c.archived else \
            (None if p.aviso == PosicaoAviso.cena_arquivada.value else p.aviso)
    if arquivadas:
        avisar(r, "cena_arquivada", "Troque ou restaure a cena arquivada para seguir",
               arquivadas[0])
        return
    faltam = [(o, c) for o, c in _distintas(pares) if c.keyframe_inicial_id is None]
    if not faltam:
        portao(db, r, "keyframes")
        return
    automatico_ = not gate_ligado(r, "keyframes")
    for ordem, c in faltam:
        abertas = estado.abertas(db, "cena.keyframe", alvo_id=c.id)
        # No automático, a geração de outro roteiro (que pode esperar um humano) não serve: a
        # escolha automática só vale para a geração pedida por este roteiro (R9).
        if any(not automatico_ or estado.do_roteiro(g) == r.id for g in abertas):
            continue
        _conferir_avatar(db, r, RoteiroEtapa.keyframes, c)
        _conferir_produto(db, c, ordem)
        pedidos.keyframe(db, ator, r, c, ordem)
    if automatico_:  # automático: a opção 1 de cada uma (R9)
        for _, c in faltam:
            for g in estado.abertas(db, "cena.keyframe", alvo_id=c.id):
                if estado.em_revisao(g) and estado.do_roteiro(g) == r.id:
                    automatico.tentar(db, g)
        return
    if all(any(estado.em_revisao(g) for g in estado.abertas(db, "cena.keyframe", alvo_id=c.id))
           for _, c in faltam):
        r.status = S.aguardando_keyframes


def _definir_tomada(db: Session, p: RoteiroCena, t: CenaTomada) -> None:
    if p.tomada_id == t.id:
        return
    anterior = db.get(CenaTomada, p.tomada_id) if p.tomada_id else None
    if anterior is not None and anterior.desuso_em is None:
        anterior.desuso_em = datetime.now(UTC)
    p.tomada_id = t.id
    t.desuso_em = None


def _gerando_clipes(db: Session, r: Roteiro, ator: Actor) -> None:
    pares = cenas_do(db, r)
    if any(p.duracao_s is None for p, _ in pares):
        return
    precisa: dict[uuid.UUID, tuple[int, Cena, float]] = {}
    regerando = {int(estado.extras(g).get("ordem", -1))
                 for _, c in pares for g in estado.abertas(db, "cena.clipe", alvo_id=c.id)
                 if estado.extras(g).get("roteiroId") == str(r.id)
                 and estado.extras(g).get("regerar")}
    for p, c in pares:
        if p.ordem in regerando and p.tomada_id is None:  # "Regerar esta cena": espera a nova
            precisa.setdefault(c.id, (p.ordem, c, 0.0))
            continue
        t = estado.tomada_util(db, c, p.duracao_s, p.tomada_id)
        if t is not None:
            _definir_tomada(db, p, t)
            if p.aviso == PosicaoAviso.tomada_curta.value:
                p.aviso = None
            continue
        atual = db.get(CenaTomada, p.tomada_id) if p.tomada_id else None
        if atual is not None and atual.duracao_ms < round(float(p.duracao_s) * 1000):
            p.aviso = PosicaoAviso.tomada_curta.value
        dur = float(p.duracao_s)
        if c.id not in precisa or precisa[c.id][2] < dur:
            precisa[c.id] = (p.ordem, c, dur)
    for ordem, c, dur in precisa.values():
        maximo = pedidos.duracao_max(c)
        if dur > maximo:
            raise Falha(RoteiroEtapa.clipes, "entrada_invalida",
                        f"A cena da posição {ordem + 1} precisa de {dur:.1f} s, e o motor "
                        f"{c.motor.value} vai até {maximo:.1f} s: divida as frases em duas "
                        "cenas", {"ordem": ordem})
        espera = False
        for g in estado.abertas(db, "cena.clipe", alvo_id=c.id):
            ex = estado.extras(g)
            if ex.get("keyframeId") != str(c.keyframe_inicial_id):
                cancelar(db, ator, g, "O keyframe da cena mudou")
            elif float(ex.get("duracaoS") or 0) >= dur:
                espera = True
        if espera:
            continue
        _conferir_avatar(db, r, RoteiroEtapa.clipes, c)
        pedidos.clipe(db, ator, r, c, ordem, dur)
    if not precisa:
        portao(db, r, "clipes")


def _montando(db: Session, r: Roteiro, ator: Actor) -> None:
    assinatura = estado.assinatura(r)
    if previa_ok(db, r):
        portao(db, r, "final")
        return
    espera = False
    for g in estado.abertas(db, "roteiro.montagem", alvo_id=r.id):
        if estado.extras(g).get("assinatura") == assinatura:
            espera = True
        else:
            cancelar(db, ator, g, "As cenas ou a narração mudaram")
    if not espera:
        pedidos.montagem(db, ator, r, assinatura)


def _finalizando(db: Session, r: Roteiro, ator: Actor) -> None:
    assinatura = estado.assinatura(r)
    if entrega_ok(db, r):
        return
    espera = False
    for g in estado.abertas(db, "roteiro.acabamento", alvo_id=r.id):
        if estado.extras(g).get("assinatura") == assinatura:
            espera = True
        else:
            cancelar(db, ator, g, "As cenas ou a narração mudaram")
    if not espera:
        pedidos.acabamento(db, ator, r, assinatura)


_HANDLERS = {S.planejando: _planejando, S.narrando: _narrando,
             S.gerando_keyframes: _gerando_keyframes, S.gerando_clipes: _gerando_clipes,
             S.montando: _montando, S.finalizando: _finalizando}


def _cancelar_seguintes(db: Session, r: Roteiro, ator: Actor) -> None:
    """Depois de voltar, a prévia e o acabamento abertos de outra assinatura ficam velhos."""
    assinatura = estado.assinatura(r)
    for passo in ("roteiro.montagem", "roteiro.acabamento"):
        for g in estado.abertas(db, passo, alvo_id=r.id):
            if estado.extras(g).get("assinatura") != assinatura:
                cancelar(db, ator, g, "Uma etapa anterior mudou")


def avancar(db: Session, r: Roteiro, ator: Actor, *, humano: bool = False) -> None:
    """Leva o roteiro até onde der sem esperar ninguém. `ator` é o autor dos pedidos e dos
    cancelamentos (o humano da ação, ou `pedidos.ator_da_maquina`)."""
    ativos = _ATIVOS.get()
    de_novo = _DE_NOVO.get()
    if r.id in ativos:
        if de_novo is not None:
            de_novo.add(r.id)
        return
    t1 = _ATIVOS.set(ativos | {r.id})
    t2 = _DE_NOVO.set(set()) if de_novo is None else None
    try:
        _laco(db, r, ator, humano)
    finally:
        _ATIVOS.reset(t1)
        if t2 is not None:
            _DE_NOVO.reset(t2)


def _laco(db: Session, r: Roteiro, ator: Actor, humano: bool) -> None:
    for _ in range(VOLTAS):
        if r.archived or r.status in (S.rascunho, S.falhou):
            return
        antes = r.status
        if estado.nivel(r.status) >= estado.nivel(S.narrando):
            estado.recalcular_tempos(db, r)
            reposicionar(db, r)
            if estado.nivel(r.status) < estado.nivel(antes):
                _cancelar_seguintes(db, r, ator)
        handler = _HANDLERS.get(r.status)
        if handler is None:
            if r.status == antes:
                return
            continue
        status = r.status
        try:
            handler(db, r, ator)
        except Falha as f:
            if humano:
                raise ApiError(409, f.codigo, f.mensagem, details=f.details) from None
            falhar(r, f.etapa, f.codigo, f.mensagem)
            return
        except ApiError as exc:  # perfil base arquivado, cena usada…
            if humano:
                raise
            falhar(r, estado.ETAPA_DO_STATUS.get(status, RoteiroEtapa.plano), exc.code,
                   exc.message)
            return
        db.flush()
        de_novo = _DE_NOVO.get()
        repetir = de_novo is not None and r.id in de_novo
        if repetir:
            de_novo.discard(r.id)
        if r.status == status and not repetir:
            return


# ---- gancho dos aplicadores (dentro da transação do gerador) ----

def _avancar_id(db: Session, roteiro_id: uuid.UUID) -> None:
    r = travar(db, roteiro_id)
    if r is not None and not r.archived:
        avancar(db, r, pedidos.ator_da_maquina(r))


def gancho(db: Session, g: Geracao, de: GeracaoStatus | None, para: GeracaoStatus) -> None:
    """`ao_mudar_estado` dos 6 passos: sem rede, só banco."""
    if de is None or para in (GeracaoStatus.cancelada, GeracaoStatus.descartada,
                              GeracaoStatus.rodando, GeracaoStatus.na_fila):
        return
    rid = estado.do_roteiro(g)
    if para == GeracaoStatus.falhou:
        r = travar(db, rid) if rid else None
        etapa = next((e for e, p in estado.PASSO_DA_ETAPA.items() if p == g.passo), None)
        if r is None or r.archived or etapa is None:
            return
        esperando = {RoteiroEtapa.keyframes: S.aguardando_keyframes,
                     RoteiroEtapa.clipes: S.aguardando_clipes}.get(etapa)
        if r.status in (estado.STATUS_DA_ETAPA[etapa], esperando):
            falhar(r, etapa, g.error_code, g.error_message)
        return
    if g.passo == "cena.keyframe" and para == GeracaoStatus.revisao:
        from sociman_api.roteiros import automatico

        automatico.tentar(db, g)
    alvos = [rid] if rid else []
    if g.passo in ("cena.keyframe", "cena.clipe"):
        alvos += roteiros_da_cena(db, g.alvo_id)
    for roteiro_id in dict.fromkeys(alvos):
        _avancar_id(db, roteiro_id)


def keyframe_mudou(db: Session, cena_id: uuid.UUID) -> None:
    """A troca de keyframe vale para a cena: todo roteiro não arquivado com ela avança (as
    tomadas antigas deixam de ser úteis e a posição volta aos clipes)."""
    for roteiro_id in roteiros_da_cena(db, cena_id):
        _avancar_id(db, roteiro_id)
