"""O plano v2 do vídeo guiado (spec 031, research R4 e R7; FR-013, FR-019 a FR-023, FR-029 a
FR-031): a mensagem, o contexto da conferência e a aplicação. O `RoteiroPlano` de
`roteiros/aplicadores.py` delega para cá quando o roteiro é guiado.

A aplicação, numa transação, com o autor = quem pediu o plano (`details.ia`, como na 011):
- **reuso total** (`nivel = total` numa candidata `total` com os mesmos trechos): a posição usa a
  cena como está (nenhum quadro nem trecho é gerado, SC-003);
- **reuso do plano** (`nivel = plano`, ou um `total` que deixou de valer): uma cena **derivada**
  (`origem_cena_id`), com a ação, a câmera, o movimento, o motor e as instruções dos quadros da
  origem, e o avatar, o cenário e o produto do vídeo. A origem não muda (FR-022);
- **nova**: a cena da 010 com o cenário do roteiro e a sequência de `trechos + 1` quadros vazios
  com as instruções do plano.

As cenas novas e derivadas ficam na biblioteca com o perfil base do roteiro (FR-023). A soma
`Σ trechos × base` precisa fechar na duração (senão o plano falha); a fala acima do orçamento
depois das duas tentativas vira o aviso `fala_nao_cabe` da posição.
"""

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session, object_session

from sociman_api import history
from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.cenas import quadros as cenas_quadros
from sociman_api.cenas import schemas as cenas_schemas
from sociman_api.cenas import service as cenas_service
from sociman_api.cenas.models import Cena, CenaMotor, CenaPlano, CenaStatus
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.models import Geracao, GeracaoCandidato
from sociman_api.ia.models import IaChamada
from sociman_api.produtos.models import Produto
from sociman_api.roteiros import conversa, estado, grade, maquina, plano, reuso
from sociman_api.roteiros.models import ENTITY, PosicaoReuso, Roteiro, RoteiroCena

GENERICAS = ("Beginning of the shot: {acao}", "Middle of the shot: {acao}",
             "Later in the shot: {acao}", "End of the shot, final state: {acao}")


def contexto(db: Session, r: Roteiro) -> plano.ContextoV2:
    cands = tuple(plano.CandidataV2(
        id=str(c.cena.id), nome=c.cena.nome, acao=c.cena.acao,
        plano=c.cena.plano.value if c.cena.plano else None, nivel=c.nivel,  # type: ignore[arg-type]
        trechos=c.cena.trechos, motivo_plano=", ".join(c.diferencas) or None)
        for c in reuso.candidatas(db, r))
    return plano.ContextoV2(base=int(r.trecho_base_s or 0), alvo=int(r.duracao_alvo_s or 0),
                            candidatas=cands)


def _produto(db: Session, r: Roteiro) -> tuple[Produto | None, uuid.UUID | None]:
    rp = reuso.produto_do(r)
    return (db.get(Produto, rp.produto_id), rp.produto_variante_id) if rp else (None, None)


def mensagem(db: Session, r: Roteiro) -> str:
    produto, variante_id = _produto(db, r)
    v = produto.variante(variante_id) if produto and variante_id else None
    pp = plano.ProdutoParaPlano(
        nome=(produto.nome_comercial or produto.name) if produto else "",
        descricao_prompt=produto.descricao_prompt if produto else None,
        descricao_venda=produto.descricao_venda if produto else None,
        material_pt=produto.material_pt if produto else None, cor_pt=v.cor_pt if v else None)
    avatar = db.get(Asset, r.avatar_id) if r.avatar_id else None
    cenario = db.get(Asset, r.cenario_id) if r.cenario_id else None
    guia, _, _ = conversa.guia_do(db, r.perfil_id)
    ctx = contexto(db, r)
    return plano.montar_mensagem_v2(conversa.respostas_para_plano(db, r), pp,
                                    avatar.prompt if avatar else None,
                                    (cenario.prompt or cenario.name) if cenario else None,
                                    ctx.candidatas, ctx, guia)


def problemas(ctx: plano.ContextoV2):
    def conferir(parsed: Any) -> list[str]:
        return plano.problemas_contexto(parsed, ctx) \
            if isinstance(parsed, plano.PlanoSaidaV2) else []
    return conferir


# ---- as cenas ----

def _corpo(r: Roteiro, produto: Produto | None, variante: uuid.UUID | None,
           **campos: Any) -> cenas_schemas.CenaIn:
    try:
        return cenas_schemas.CenaIn(avatar_id=r.avatar_id, cenario_id=r.cenario_id,
                                    produto_id=produto.id if produto else None,
                                    produto_variante_id=variante if produto else None, **campos)
    except (ValidationError, ValueError) as exc:
        raise MotorErro("entrada_invalida", "A IA propôs uma cena fora do formato",
                        detalhe=str(exc)[:300]) from exc


def cena_nova(db: Session, actor: Actor, r: Roteiro, nova: dict[str, Any], trechos: int,
              ia: dict[str, Any]) -> Cena:
    produto, variante = _produto(db, r)
    body = _corpo(r, produto, variante, nome=nova["nome"][:120], acao=nova["acao"][:1000],
                  plano=CenaPlano(nova["plano"]) if nova.get("plano") else None,
                  movimento=nova.get("movimento"),
                  camera=(nova.get("camera") or None) and nova["camera"][:500])
    instrucoes = [q[:2000] for q in nova["quadros"]]
    cena = cenas_service.criar(
        db, actor, r.perfil_id, body, exige_ativo=False,
        locais={"motor": CenaMotor(plano.MOTOR_DO_PLANO),
                "keyframe_instrucao": instrucoes[0] or None},
        details={"ia": ia, "roteiroId": str(r.id), "guiado": True})
    cenas_quadros.criar(db, actor, cena, instrucoes, details={"roteiroId": str(r.id)})
    return cena


def instrucoes_da_origem(db: Session, origem: Cena, trechos: int) -> list[str]:
    """As instruções dos quadros da origem, se a sequência tem o mesmo tamanho; senão, as
    genéricas a partir da ação (início, meios e fim)."""
    qs = cenas_quadros.ativos(db, origem.id)
    if len(qs) == trechos + 1 and all(q.instrucao.strip() for q in qs):
        return [q.instrucao for q in qs]
    return genericas(origem.acao, trechos)


def genericas(acao: str, trechos: int) -> list[str]:
    """As instruções genéricas de `trechos + 1` quadros a partir da ação (início, meios e fim)."""
    papeis = {2: (0, 3), 3: (0, 1, 3), 4: (0, 1, 2, 3)}[trechos + 1]
    acao = acao.strip().rstrip(".")
    return [GENERICAS[i].format(acao=acao) for i in papeis]


def derivar(db: Session, actor: Actor, r: Roteiro, origem: Cena, trechos: int,
            ia: dict[str, Any] | None, *, instrucoes: list[str] | None = None, manter: int = 0,
            mudancas: dict[str, Any] | None = None,
            details: dict[str, Any] | None = None) -> Cena:
    """O reuso do plano (FR-022): uma cena nova a partir da origem, com o avatar, o cenário, o
    produto e o perfil base do vídeo (`cenas_service.derivar_cena`, com o histórico nas duas).
    A origem não é alterada."""
    produto, variante = _produto(db, r)
    info: dict[str, Any] = {"roteiroId": str(r.id), "guiado": True, **(details or {})}
    if ia is not None:
        info["ia"] = ia
    return cenas_service.derivar_cena(
        db, actor, origem, avatar_id=r.avatar_id, cenario_id=r.cenario_id,
        produto_id=produto.id if produto else None, produto_variante_id=variante,
        perfil_base_id=r.perfil_id,
        instrucoes=instrucoes or instrucoes_da_origem(db, origem, trechos), manter=manter,
        mudancas=mudancas, details=info)


def propria(db: Session, r: Roteiro, p: RoteiroCena) -> bool:
    """A cena da posição é deste vídeo (criada ou derivada pelo plano, ainda em `rascunho` e sem
    outro roteiro): um ajuste muda ela mesma. A do reuso total, a `usada` e a de outro vídeo são
    reaproveitadas: o ajuste deriva antes (FR-022)."""
    cena = db.get(Cena, p.cena_id)
    if cena is None or p.reuso == PosicaoReuso.total or cena.status != CenaStatus.rascunho:
        return False
    return maquina.roteiros_da_cena(db, cena.id) == [r.id]


def separar(db: Session, actor: Actor, r: Roteiro, p: RoteiroCena, *, manter: int,
            mudancas: dict[str, Any] | None = None,
            details: dict[str, Any] | None = None) -> Cena:
    """A cena que a posição pode mudar: a própria, ou uma derivada da reaproveitada (com os
    `manter` primeiros quadros já aprovados), que passa a ser a da posição (`reuso = plano`).
    As aprovações da posição caem."""
    cena = db.get(Cena, p.cena_id, with_for_update=True)
    if propria(db, r, p):
        return cena
    trechos = int(p.trechos or cena.trechos or 1)
    nova = derivar(db, actor, r, cena, trechos, None, manter=manter, mudancas=mudancas,
                   details=details)
    trocar_cena(p, nova, PosicaoReuso.plano, p.motivo)
    db.flush()
    return nova


def trocar_cena(p: RoteiroCena, cena: Cena, reuso_: PosicaoReuso, motivo: str | None) -> None:
    """A posição passa a usar a cena: as aprovações e as tomadas dos trechos (de outra cena)
    deixam de valer."""
    p.cena_id, p.reuso, p.motivo = cena.id, reuso_, motivo
    p.aprovado_keyframes_em = p.aprovado_keyframes_por = None
    p.aprovado_clipe_em = p.aprovado_clipe_por = None
    db = object_session(p)
    for x in list(p.trechos_rel):
        if db is not None:  # a tomada do trecho fica em desuso (R12, limpeza de 90 dias)
            maquina.desusar_tomada(db, x.tomada_id)
        x.tomada_id = None


# ---- aplicar ----

def _uuid(valor: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(valor))
    except ValueError:
        return None


def aplicar(db: Session, actor: Actor, r: Roteiro, geracao: Geracao,
            candidato: GeracaoCandidato, dados: dict[str, Any]) -> None:
    base, alvo = int(r.trecho_base_s), int(r.duracao_alvo_s)
    frases = list(dados["frases"])
    posicoes = [dict(p) for p in dados["posicoes"]]
    soma = sum(int(p["trechos"]) for p in posicoes) * base
    if soma != alvo:
        raise MotorErro("entrada_invalida",
                        f"A IA propôs cenas que somam {soma} s; a duração é {alvo} s")
    chamada_id = (candidato.metricas or {}).get("chamada_id")
    ia = {"chamadaId": chamada_id, "passo": "roteiro.plano",
          "promptVersion": plano.PROMPT_VERSION_V2}
    ctx = contexto(db, r)
    escolhidas: list[tuple[Cena, PosicaoReuso]] = []
    for n, p in enumerate(posicoes, start=1):
        trechos = int(p["trechos"])
        if not p.get("cenaId"):
            escolhidas.append((cena_nova(db, actor, r, p["nova"], trechos, ia),
                               PosicaoReuso.nova))
            continue
        origem = db.get(Cena, _uuid(p["cenaId"])) if _uuid(p["cenaId"]) else None
        cand = ctx.candidata(str(origem.id)) if origem is not None else None
        if origem is None or cand is None:
            raise MotorErro("entrada_invalida",
                            f"A IA propôs reaproveitar uma cena que não serve (cena {n})")
        if p.get("nivel") == "total" and cand.nivel == "total" and cand.trechos == trechos:
            escolhidas.append((origem, PosicaoReuso.total))
        else:
            escolhidas.append((derivar(db, actor, r, origem, trechos, ia), PosicaoReuso.plano))
    before = history.snapshot(r)
    r.frases = frases
    for velha in list(r.posicoes_rel):
        r.posicoes_rel.remove(velha)
    db.flush()
    avisos = []
    for ordem, (p, (cena, nivel)) in enumerate(zip(posicoes, escolhidas, strict=True)):
        trechos = int(p["trechos"])
        orcamento = grade.orcamento_chars(trechos * base)
        r.posicoes_rel.append(RoteiroCena(
            roteiro_id=r.id, ordem=ordem, cena_id=cena.id, frases=list(p["frases"]),
            trechos=trechos, reuso=nivel, motivo=(p.get("motivo") or "")[:300] or None,
            orcamento_chars=orcamento))
        fala = sum(len(frases[f]) for f in p["frases"] if 0 <= f < len(frases))
        if fala > orcamento:
            avisos.append({"code": "fala_nao_cabe", "ordem": ordem,
                           "message": f"A fala da cena {ordem + 1} tem {fala} caracteres e "
                                      f"cabem {orcamento}: encurte o texto ou aumente a duração"})
    row = db.get(IaChamada, _uuid(chamada_id)) if chamada_id and _uuid(chamada_id) else None
    if row is not None and row.proibidas:
        avisos.append({"code": "palavra_proibida",
                       "message": f"A IA usou {', '.join(row.proibidas)}, proibida(s) pelo guia; "
                                  "edite o texto no modo avançado"})
    r.avisos = avisos
    db.flush()
    estado.recalcular_tempos(db, r)  # no guiado, a duração de cada posição é a da grade
    maquina.portao(db, r, "texto")
    r.updated_by = actor.user_id
    history.record(db, actor, ENTITY, r, "updated", before, history.snapshot(r),
                   {"acao": "plano", "geracaoId": str(geracao.id), "ia": ia, "versaoPlano": 2,
                    "reuso": {k.value: sum(1 for _, x in escolhidas if x == k)
                              for k in PosicaoReuso}})
