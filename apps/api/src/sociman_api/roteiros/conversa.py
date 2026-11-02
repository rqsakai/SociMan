"""O chat do vídeo guiado (spec 031, research R5; FR-008 a FR-012, data-model `roteiro_conversa`).

- as perguntas saem **numa chamada só** (passo `roteiro.perguntas`, motor `claude`, sem escolha):
  o aplicador grava uma linha `pergunta` por pergunta, na **rodada** nova (refazer as perguntas
  abre outra rodada; nada é apagado: a tabela é só de inserção) e põe `conversa_estado =
  perguntando`;
- responder é só banco (< 150 ms): confere a pergunta e as opções, grava a `resposta` (autor =
  o humano) e, na última da rodada, `respondida`. Uma palavra proibida pelo guia do perfil base
  (017) no texto curto vira um `aviso` no chat e é tirada do que vai ao planejador;
- o roteiro ganha uma versão por resposta (`details.acao = "responder"`, princípio VII); a
  conversa em si (`conversa_estado`) é técnica, fora do snapshot.

Fechar e reabrir o vídeo retoma de onde parou: o estado sai das linhas gravadas.
"""

import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User
from sociman_api.errors import ApiError
from sociman_api.geracao.models import TERMINADOS, Geracao, GeracaoAlvo, GeracaoStatus
from sociman_api.ia import guia as guia_mod
from sociman_api.produtos.models import Produto
from sociman_api.roteiros import estado, pedidos, reuso, schemas
from sociman_api.roteiros.models import (
    ENTITY,
    ConversaEstado,
    ConversaTipo,
    Roteiro,
    RoteiroConversa,
)

AUTOR_IA = "system:roteiro"
PASSOS_CHAT = ("roteiro.perguntas", "roteiro.ajuste")


# ---- guia do perfil base ----

def guia_do(db: Session, perfil_id: uuid.UUID | None
            ) -> tuple[str | None, guia_mod.GuiaEfetivo, int | None]:
    """(texto do guia do perfil para o prompt, o efetivo das garantias, a versão enviada)."""
    if perfil_id is None:
        return None, guia_mod.GuiaEfetivo(), None
    guias = guia_mod.em_vigor(db, perfil_id, None)
    efetivo = guia_mod.fundir(guias.perfil, None)
    if guias.perfil is None:
        return None, efetivo, None
    texto = guia_mod.render(guias.perfil) or None
    return texto, efetivo, guias.perfil.version if texto else None


_PALAVRA = re.compile(r"(\w+)")


def sem_proibidas(texto: str, proibidas: tuple[str, ...]) -> tuple[str, list[str]]:
    """(o texto sem as proibidas, as encontradas). Tira as palavras inteiras que casam; se um
    termo de mais de uma palavra continuar casando, o texto inteiro sai."""
    achadas = guia_mod.achar_proibidas([texto], proibidas)
    if not achadas:
        return texto, []
    simples = {guia_mod.normalizar(p) for p in achadas if len(p.split()) == 1}
    partes = [p for p in _PALAVRA.split(texto) if guia_mod.normalizar(p) not in simples]
    limpo = " ".join("".join(partes).split())
    if guia_mod.achar_proibidas([limpo], proibidas):
        limpo = ""
    return limpo, achadas


# ---- linhas ----

def mensagens(db: Session, roteiro_id: uuid.UUID) -> list[RoteiroConversa]:
    return list(db.scalars(select(RoteiroConversa).where(RoteiroConversa.roteiro_id == roteiro_id)
                           .order_by(RoteiroConversa.seq)))


def adicionar(db: Session, r: Roteiro, tipo: ConversaTipo, conteudo: dict[str, Any], *,
              autor: Actor | None = None, pergunta_id: str | None = None,
              alvo: dict[str, Any] | None = None,
              ia_chamada_id: uuid.UUID | None = None) -> RoteiroConversa:
    """Uma mensagem nova (o roteiro está travado por quem chama: o `seq` não colide)."""
    seq = (db.scalar(select(func.max(RoteiroConversa.seq)).where(
        RoteiroConversa.roteiro_id == r.id)) or 0) + 1
    linha = RoteiroConversa(roteiro_id=r.id, seq=seq, tipo=tipo, pergunta_id=pergunta_id,
                            conteudo=conteudo, ia_chamada_id=ia_chamada_id,
                            autor_tipo="user" if autor is not None and autor.user_id else AUTOR_IA,
                            autor_id=autor.user_id if autor is not None else None)
    if alvo is not None:  # sem alvo, NULL (o JSONB gravaria o `null` do JSON)
        linha.alvo = alvo
    db.add(linha)
    db.flush()
    return linha


def _rodada(linhas: list[RoteiroConversa]) -> int:
    return max((int(m.conteudo.get("rodada") or 0) for m in linhas
                if m.tipo == ConversaTipo.pergunta), default=0)


def _da_rodada(linhas: list[RoteiroConversa], rodada: int
               ) -> tuple[list[RoteiroConversa], dict[str, RoteiroConversa]]:
    perguntas = [m for m in linhas if m.tipo == ConversaTipo.pergunta
                 and int(m.conteudo.get("rodada") or 0) == rodada]
    respostas = {m.pergunta_id: m for m in linhas if m.tipo == ConversaTipo.resposta
                 and int(m.conteudo.get("rodada") or 0) == rodada}
    return perguntas, respostas


def _atual(perguntas: list[RoteiroConversa], respostas: dict[str, RoteiroConversa]
           ) -> RoteiroConversa | None:
    return next((p for p in perguntas if p.pergunta_id not in respostas), None)


# ---- a mensagem das perguntas e as respostas para o plano ----

def _limpo(texto: str | None) -> str:
    return " ".join((texto or "").replace("<", "‹").replace(">", "›").split())


def mensagem_perguntas(db: Session, r: Roteiro) -> str:
    """Tudo em tags de dado; a `<instrucao>` é fixa (o operador não escreveu nada ainda)."""
    rp = reuso.produto_do(r)
    produto = db.get(Produto, rp.produto_id) if rp else None
    variante = produto.variante(rp.produto_variante_id) if produto and rp.produto_variante_id \
        else None
    avatar = db.get(Asset, r.avatar_id) if r.avatar_id else None
    cenario = db.get(Asset, r.cenario_id) if r.cenario_id else None
    guia, _, _ = guia_do(db, r.perfil_id)
    linhas = ["<instrucao>Faça as perguntas fechadas para montar este vídeo.</instrucao>",
              (f"<duracao>{r.duracao_alvo_s} s ({(r.duracao_alvo_s or 0) // (r.trecho_base_s or 1)}"
               f" trechos de {r.trecho_base_s} s)</duracao>")]
    if produto is not None:
        linhas.append(f"<produto>{_limpo(produto.nome_comercial or produto.name)} | categoria: "
                      f"{_limpo(produto.categoria)} | material: {_limpo(produto.material_pt)} | "
                      f"cor: {_limpo(variante.cor_pt if variante else None)} | venda: "
                      f"{_limpo(produto.descricao_venda)} | detalhes: "
                      f"{_limpo(', '.join(produto.detalhes_visiveis or []))}</produto>")
    linhas += [f"<avatar>{_limpo(avatar.prompt if avatar else None)}</avatar>",
               (f"<cenario>{_limpo((cenario.prompt or cenario.name) if cenario else None)}"
                "</cenario>")]
    if guia:
        linhas.append(f"<guia_perfil>{_limpo(guia)}</guia_perfil>")
    linhas.append("<cenas>")
    for c in reuso.candidatas(db, r):
        linhas.append(f'<cena nivel="{c.nivel}">{_limpo(c.cena.nome)}</cena>')
    linhas.append("</cenas>")
    return "\n".join(linhas)


def respostas_para_plano(db: Session, r: Roteiro) -> list[tuple[str, str]]:
    """(pergunta, resposta) da rodada atual, na ordem: os rótulos marcados e o texto curto, já
    sem as palavras proibidas do guia do perfil base."""
    _, efetivo, _ = guia_do(db, r.perfil_id)
    linhas = mensagens(db, r.id)
    perguntas, respostas = _da_rodada(linhas, _rodada(linhas))
    out = []
    for p in perguntas:
        resp = respostas.get(p.pergunta_id)
        if resp is None:
            continue
        rotulos = {o["id"]: o["rotulo"] for o in p.conteudo.get("opcoes") or []}
        partes = [rotulos.get(o, o) for o in resp.conteudo.get("opcoes") or []]
        texto, _ = sem_proibidas(resp.conteudo.get("texto") or "", efetivo.proibidas)
        if texto:
            partes.append(texto)
        out.append((p.conteudo.get("texto") or "", "; ".join(partes)))
    return out


# ---- o passo roteiro.perguntas ----

def pedir_perguntas(db: Session, ator: Actor, r: Roteiro) -> Geracao:
    return pedidos._criar(db, ator, r, "roteiro.perguntas", GeracaoAlvo.roteiro, r.id,
                          r.perfil_id, {"instrucao": ""})


def aplicar_perguntas(db: Session, geracao: Geracao, proposta: dict[str, Any] | None,
                      chamada_id: uuid.UUID | None) -> None:
    """O aplicador do `roteiro.perguntas`: as perguntas na rodada nova. Fora de hora (o roteiro
    arquivado ou a conversa já aberta por outra geração), a chamada fica só no registro."""
    r = db.get(Roteiro, geracao.alvo_id, with_for_update=True)
    if r is None or r.archived or not r.guiado or r.conversa_estado != ConversaEstado.sem_perguntas:
        return
    perguntas = (proposta or {}).get("perguntas") or []
    rodada = _rodada(mensagens(db, r.id)) + 1
    for q in perguntas:
        adicionar(db, r, ConversaTipo.pergunta, {**q, "rodada": rodada}, pergunta_id=q["id"],
                  ia_chamada_id=chamada_id)
    r.conversa_estado = ConversaEstado.perguntando if perguntas else ConversaEstado.respondida
    db.flush()


# ---- ações humanas ----

def _editavel_guiado(db: Session, roteiro_id: uuid.UUID, version: int) -> Roteiro:
    from sociman_api.roteiros import service

    r = service._editavel(db, roteiro_id, version)
    if not r.guiado:
        raise ApiError(409, "nao_guiado", "Este roteiro não é um vídeo guiado")
    return r


def _aberta(db: Session, r: Roteiro) -> Geracao | None:
    return next((g for passo in PASSOS_CHAT for g in estado.abertas(db, passo, alvo_id=r.id)),
                None)


def responder(db: Session, actor: Actor, roteiro_id: uuid.UUID, body: schemas.ResponderIn
              ) -> Roteiro:
    r = _editavel_guiado(db, roteiro_id, body.version)
    if r.conversa_estado != ConversaEstado.perguntando:
        raise ApiError(409, "conversa_fechada", "Não há pergunta esperando resposta")
    linhas = mensagens(db, r.id)
    rodada = _rodada(linhas)
    perguntas, respostas = _da_rodada(linhas, rodada)
    p = next((x for x in perguntas if x.pergunta_id == body.pergunta_id), None)
    if p is None:
        raise ApiError(422, "opcao_invalida", "Esta pergunta não está na conversa",
                       details={"field": "perguntaId"})
    if p.pergunta_id in respostas:
        raise ApiError(409, "pergunta_respondida", "Esta pergunta já foi respondida")
    validas = {o["id"] for o in p.conteudo.get("opcoes") or []}
    opcoes = list(dict.fromkeys(body.opcoes))
    if any(o not in validas for o in opcoes):
        raise ApiError(422, "opcao_invalida", "Escolha uma das opções da pergunta",
                       details={"field": "opcoes"})
    if len(opcoes) > 1 and not p.conteudo.get("multipla"):
        raise ApiError(422, "opcao_invalida", "Esta pergunta aceita uma opção só",
                       details={"field": "opcoes"})
    texto = (body.texto or "").strip()
    if not opcoes and not texto:
        raise ApiError(422, "opcao_invalida", "Escolha uma opção ou escreva uma resposta curta",
                       details={"field": "opcoes"})
    before = history.snapshot(r)
    conteudo: dict[str, Any] = {"opcoes": opcoes, "rodada": rodada}
    if texto:
        conteudo["texto"] = texto
    adicionar(db, r, ConversaTipo.resposta, conteudo, autor=actor, pergunta_id=p.pergunta_id)
    _, efetivo, _ = guia_do(db, r.perfil_id)
    _, achadas = sem_proibidas(texto, efetivo.proibidas) if texto else ("", [])
    if achadas:
        adicionar(db, r, ConversaTipo.aviso, {
            "code": "palavra_proibida", "palavras": achadas, "rodada": rodada,
            "texto": f"{', '.join(achadas)}: proibida(s) pelo guia do perfil; não entra(m) no "
                     "texto do vídeo."}, pergunta_id=p.pergunta_id)
    respostas[p.pergunta_id] = p  # a de agora
    if _atual(perguntas, respostas) is None:
        r.conversa_estado = ConversaEstado.respondida
    r.comandado_por = r.updated_by = actor.user_id
    db.flush()
    details: dict[str, Any] = {"acao": "responder", "perguntaId": p.pergunta_id,
                               "rodada": rodada, "opcoes": opcoes, "comTexto": bool(texto)}
    if achadas:
        details["proibidas"] = achadas
    history.record(db, actor, ENTITY, r, "updated", before, history.snapshot(r), details)
    return r


def refazer_perguntas(db: Session, actor: Actor, roteiro_id: uuid.UUID, version: int
                      ) -> Roteiro:
    """Outra rodada de perguntas (também o "tentar de novo" quando a IA não respondeu). As
    respostas dadas ficam gravadas; só a rodada nova vale para o plano."""
    from sociman_api.roteiros.estado import S

    r = _editavel_guiado(db, roteiro_id, version)
    if r.status not in (S.rascunho, S.aguardando_texto) and not (
            r.status == S.falhou and r.etapa_falhou is not None
            and r.etapa_falhou.value == "plano"):
        raise ApiError(409, "estado_invalido",
                       "As perguntas só são refeitas antes de o vídeo ser gerado")
    if _aberta(db, r) is not None or estado.abertas(db, "roteiro.plano", alvo_id=r.id):
        raise ApiError(409, "geracao_em_andamento", "Espere a IA terminar")
    before = history.snapshot(r)
    r.conversa_estado = ConversaEstado.sem_perguntas
    r.comandado_por = r.updated_by = actor.user_id
    pedir_perguntas(db, actor, r)
    db.flush()
    history.record(db, actor, ENTITY, r, "updated", before, history.snapshot(r),
                   {"acao": "refazer_perguntas"})
    return r


# ---- leitura ----

def _pergunta_out(m: RoteiroConversa) -> schemas.PerguntaConversa:
    c = m.conteudo
    return schemas.PerguntaConversa(
        id=m.pergunta_id or c.get("id") or "", texto=c.get("texto") or "",
        multipla=bool(c.get("multipla")), rodada=int(c.get("rodada") or 0),
        opcoes=[schemas.OpcaoConversa(id=o["id"], rotulo=o["rotulo"])
                for o in c.get("opcoes") or []],
        exemplos=list(c.get("exemplos") or []))


def _erro(db: Session, r: Roteiro) -> schemas.ErroRoteiro | None:
    """A última geração do chat falhou e nada mais novo foi pedido: "a IA não respondeu"."""
    g = db.scalar(select(Geracao).where(Geracao.alvo_id == r.id,
                                        Geracao.passo.in_(PASSOS_CHAT))
                  .order_by(Geracao.created_at.desc(), Geracao.id.desc()).limit(1))
    if g is None or g.status != GeracaoStatus.falhou:
        return None
    return schemas.ErroRoteiro(code=g.error_code or "internal",
                               message="A IA não respondeu; tente de novo")


def conversa_out(db: Session, r: Roteiro) -> schemas.ConversaOut:
    db.flush()
    linhas = mensagens(db, r.id)
    rodada = _rodada(linhas)
    perguntas, respostas = _da_rodada(linhas, rodada)
    atual = _atual(perguntas, respostas) if r.conversa_estado == ConversaEstado.perguntando \
        else None
    nomes = dict(db.execute(select(User.id, User.name).where(
        User.id.in_({m.autor_id for m in linhas if m.autor_id}))).all()) if linhas else {}
    aberta = _aberta(db, r)
    return schemas.ConversaOut(
        estado=r.conversa_estado, rodada=rodada,
        mensagens=[schemas.MensagemConversa(
            id=m.id, seq=m.seq, tipo=m.tipo, pergunta_id=m.pergunta_id, conteudo=m.conteudo,
            alvo=m.alvo, autor=schemas.AutorConversa(
                tipo=m.autor_tipo, id=m.autor_id,
                nome=nomes.get(m.autor_id) if m.autor_id else "IA"),
            created_at=m.created_at) for m in linhas],
        pergunta_atual=_pergunta_out(atual) if atual is not None else None,
        respondidas=sum(1 for p in perguntas if p.pergunta_id in respostas),
        total=len(perguntas),
        geracao_aberta=schemas.GeracaoAberta(
            id=aberta.id, passo=aberta.passo, status=aberta.status.value,
            progress=aberta.progress, etapa_mensagem=aberta.etapa_mensagem)
        if aberta is not None and aberta.status not in TERMINADOS else None,
        erro=None if aberta is not None else _erro(db, r), version=r.version)
