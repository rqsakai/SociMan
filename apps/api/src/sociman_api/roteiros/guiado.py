"""O "Novo vídeo" guiado (spec 031, US1; FR-001 a FR-007, FR-030 e FR-033).

`criar_guiado` confere os 6 blocos, todos da biblioteca da agência (029: qualquer perfil base):
- **perfil** (o perfil base do vídeo: guia, proibidas e padrões): inexistente → 400
  `perfil_invalido`; arquivado → 409 `perfil_base_arquivado`;
- **avatar** ativo do tipo avatar (senão 422 `cena_invalida`); consentimento revogado → 409;
- **voz** aprovada (sem ela, a voz padrão do avatar; nenhuma → 400 `voz_invalida`); revogada → 409
  `consentimento_revogado`;
- **cenário** ativo com a imagem `cena` do cadastro padronizado (o quadro 0 nasce dela, R3);
- **produto** aprovado (012) e a variante ativa com recorte (sem `varianteId`, a primeira);
- **duração** na grade de agora (`ROTEIRO_TRECHO_BASE_S` × 1..`ROTEIRO_GRADE_MAX`; senão 422
  `duracao_fora_da_grade`). O roteiro guarda a base (FR-033).

O roteiro nasce em `rascunho`, com o modo e os portões padrão do perfil, a versão `created` no
histórico e as perguntas do chat já pedidas (`roteiro.perguntas`, `conversa_estado =
sem_perguntas` até elas chegarem).

O wizard (US3): `aprovar_posicao` é a aprovação humana da sequência de quadros (ou dos trechos)
de uma posição (R9); com todas aprovadas, o portão passa. `recusar` é o "Não aprovo": o pedido
de troca vai para o chat e para o passo `roteiro.ajuste` (`roteiros/ajuste.py`). Nenhuma das duas
é da IA nem do MCP (rotas `RequireHuman`).
"""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset, AssetTipo
from sociman_api.auth.deps import Actor
from sociman_api.cenas import quadros as cenas_quadros
from sociman_api.cenas.models import Cena, CenaTomada
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.perfis import base as perfil_base
from sociman_api.produtos.models import Produto, ProdutoStatus
from sociman_api.roteiros import conversa, estado, grade, maquina, schemas
from sociman_api.roteiros.models import (
    ConversaEstado,
    PosicaoReuso,
    Roteiro,
    RoteiroAcabamento,
    RoteiroCena,
    RoteiroProduto,
    RoteiroStatus,
)
from sociman_api.vozes.models import Voz


def grade_out() -> schemas.GradeOut:
    s = get_settings()
    return schemas.GradeOut(trecho_base_s=s.roteiro_trecho_base_s,
                            opcoes=grade.opcoes(s.roteiro_trecho_base_s, s.roteiro_grade_max),
                            max_trechos_por_cena=grade.MAX_TRECHOS)


def invalida(field: str, message: str) -> ApiError:
    return ApiError(422, "cena_invalida", message, details={"field": field})


def conferir_duracao(duracao_s: int, base: int) -> None:
    maximo = get_settings().roteiro_grade_max
    if not grade.valida_duracao(duracao_s, base, maximo):
        raise ApiError(422, "duracao_fora_da_grade",
                       f"Escolha uma duração da grade: {', '.join(map(str, grade.opcoes(base, maximo)))} s",
                       details={"field": "duracaoS", "opcoes": grade.opcoes(base, maximo)})


def _avatar(db: Session, avatar_id) -> Asset:
    a = db.get(Asset, avatar_id)
    if a is None or a.tipo != AssetTipo.avatar or a.archived:
        if a is not None and a.revogado:
            raise ApiError(409, "consentimento_revogado", estado.problema_do_avatar(a)[1],
                           details={"field": "avatarId"})
        raise invalida("avatarId", "Escolha um avatar ativo da biblioteca")
    problema = estado.problema_do_avatar(a)
    if problema:
        status = 409 if problema[0] == "consentimento_revogado" else 422
        raise ApiError(status, problema[0] if status == 409 else "cena_invalida", problema[1],
                       details={"field": "avatarId"})
    return a


def _voz(db: Session, voz_id, avatar: Asset) -> Voz:
    escolhida = voz_id or avatar.voz_id
    if escolhida is None:
        raise ApiError(400, "voz_invalida",
                       "O avatar não tem voz padrão: escolha uma voz aprovada",
                       details={"field": "vozId"})
    v = db.get(Voz, escolhida)
    problema = estado.problema_da_voz(v, para_narrar=False)
    if problema:
        if problema[0] == "consentimento_revogado":
            raise ApiError(409, problema[0], problema[1], details={"field": "vozId"})
        mensagem = problema[1] if voz_id else \
            f"A voz padrão do avatar não pode narrar ({problema[1].lower()}): escolha outra"
        raise ApiError(400, "voz_invalida", mensagem, details={"field": "vozId"})
    return v


def _cenario(db: Session, cenario_id) -> Asset:
    c = db.get(Asset, cenario_id)
    if c is None or c.tipo != AssetTipo.cenario or c.archived:
        raise invalida("cenarioId", "Escolha um cenário ativo da biblioteca")
    if c.slot_ativo("cena") is None:
        raise invalida("cenarioId", "O cenário precisa da imagem da cena (cadastro padronizado)")
    return c


def _produto(db: Session, produto_id, variante_id) -> tuple[Produto, object]:
    p = db.get(Produto, produto_id)
    if p is None or p.archived or p.status != ProdutoStatus.aprovado:
        raise invalida("produtoId", "Escolha um produto aprovado do catálogo")
    if variante_id is not None:
        v = p.variante(variante_id)
        if v is None or v.archived or v.recorte_image_id is None:
            raise invalida("varianteId", "Escolha uma variante ativa e com recorte deste produto")
        return p, v
    v = next((x for x in p.ativas() if x.recorte_image_id is not None), None)
    if v is None:
        raise invalida("varianteId", "O produto não tem variante com recorte")
    return p, v


def nome_padrao(produto: Produto) -> str:
    hoje = datetime.now(ZoneInfo(get_settings().app_tz)).strftime("%d/%m")
    return f"{(produto.nome_comercial or produto.name)[:110]} – {hoje}"


def criar_guiado(db: Session, actor: Actor, body: schemas.RoteiroGuiadoIn) -> Roteiro:
    from sociman_api.roteiros import service  # padrões do perfil e o registro

    perfil = perfil_base.resolver(db, body.perfil_id, field="perfilId")
    base_s = get_settings().roteiro_trecho_base_s
    conferir_duracao(body.duracao_s, base_s)
    avatar = _avatar(db, body.avatar_id)
    voz = _voz(db, body.voz_id, avatar)
    cenario = _cenario(db, body.cenario_id)
    produto, variante = _produto(db, body.produto_id, body.variante_id)
    modo, portoes = service.padroes_do_perfil(db, perfil.id)
    r = Roteiro(perfil_id=perfil.id, nome=body.nome or nome_padrao(produto), brief="",
                avatar_id=avatar.id, voz_id=voz.id, modo=modo, portoes=portoes,
                tipo_video=body.tipo_video, cenario_id=cenario.id,
                duracao_alvo_s=body.duracao_s, trecho_base_s=base_s,
                acabamento_modo=RoteiroAcabamento(body.acabamento_modo or "leve"),
                conversa_estado=ConversaEstado.sem_perguntas, comandado_por=actor.user_id,
                created_by=actor.user_id, updated_by=actor.user_id)
    db.add(r)
    db.flush()
    r.produtos_rel.append(RoteiroProduto(roteiro_id=r.id, ordem=0, produto_id=produto.id,
                                         produto_variante_id=variante.id))
    db.flush()
    service._record(db, actor, r, "created", None, {"acao": "created", "guiado": True})
    conversa.pedir_perguntas(db, actor, r)
    return r


# ---- wizard: aprovar por posição e "Não aprovo" (US3; R6, R9; FR-015, FR-016, FR-034) ----

# Em que status cada alvo pode ser recusado (o item que o wizard mostra agora).
STATUS_DO_ALVO: dict[str, tuple[RoteiroStatus, ...]] = {
    "narracao": (RoteiroStatus.aguardando_narracao,),
    "quadros": (RoteiroStatus.gerando_keyframes, RoteiroStatus.aguardando_keyframes),
    "trecho": (RoteiroStatus.gerando_clipes, RoteiroStatus.aguardando_clipes),
    "final": (RoteiroStatus.aguardando_final,),
    "posicao": (RoteiroStatus.aguardando_texto,),
}
STATUS_DA_ETAPA: dict[str, tuple[RoteiroStatus, ...]] = {
    "keyframes": STATUS_DO_ALVO["quadros"], "clipe": STATUS_DO_ALVO["trecho"],
}
PORTAO_DA_ETAPA = {"keyframes": "keyframes", "clipe": "clipes"}


def _guiado_editavel(db: Session, roteiro_id, version: int) -> Roteiro:
    from sociman_api.roteiros import service

    r = service._editavel(db, roteiro_id, version)
    if not r.guiado:
        raise ApiError(409, "nao_guiado", "Este roteiro não é um vídeo guiado")
    return r


def ajuste_aberto(db: Session, r: Roteiro, ordem: int | None = None) -> bool:
    """Um "Não aprovo" ainda com a IA (da posição `ordem`, ou de qualquer item)."""
    for g in estado.abertas(db, "roteiro.ajuste", alvo_id=r.id):
        alvo = estado.extras(g).get("alvo") or {}
        if ordem is None or alvo.get("ordem") == ordem:
            return True
    return False


def problema_da_sequencia(db: Session, r: Roteiro, p: RoteiroCena) -> str | None:
    """Por que a sequência da posição não pode ser aprovada agora (None = pode)."""
    cena = db.get(Cena, p.cena_id)
    qs = cenas_quadros.ativos(db, cena.id)
    if not cenas_quadros.completos(qs):
        return f"A sequência da posição {p.ordem + 1} ainda não tem todos os quadros"
    if estado.abertas(db, "cena.keyframe", alvo_id=cena.id) or ajuste_aberto(db, r, p.ordem):
        return f"Espere a posição {p.ordem + 1} terminar de gerar"
    return None


def problema_dos_trechos(db: Session, r: Roteiro, p: RoteiroCena) -> str | None:
    cena = db.get(Cena, p.cena_id)
    qs = cenas_quadros.ativos(db, cena.id)
    for t in range(p.trechos or 0):
        x = p.trecho(t)
        tomada = db.get(CenaTomada, x.tomada_id) if x is not None and x.tomada_id else None
        if not estado.tomada_serve_trecho(db, tomada, cena, t, r.trecho_base_s, qs):
            return f"O trecho {t + 1} da posição {p.ordem + 1} ainda não foi gerado"
    if any(estado.extras(g).get("ordem") == p.ordem
           for g in estado.abertas(db, "cena.clipe", alvo_id=cena.id)) or \
            ajuste_aberto(db, r, p.ordem):
        return f"Espere a posição {p.ordem + 1} terminar de gerar"
    return None


def _marcar(db: Session, actor: Actor, r: Roteiro, p: RoteiroCena, etapa: str) -> None:
    """A aprovação humana de uma posição. Nos quadros, a sequência é da cena: toda posição com a
    mesma cena fica aprovada, e os provisórios deixam de ser."""
    agora = datetime.now(UTC)
    if etapa == "clipe":
        p.aprovado_clipe_em, p.aprovado_clipe_por = agora, actor.user_id
        return
    for outra in r.posicoes_rel:
        if outra.cena_id == p.cena_id:
            outra.aprovado_keyframes_em, outra.aprovado_keyframes_por = agora, actor.user_id
    cena = db.get(Cena, p.cena_id, with_for_update=True)
    cenas_quadros.confirmar(db, actor, cena, {"roteiroId": str(r.id), "ordem": p.ordem})


def aprovar_todas(db: Session, actor: Actor, r: Roteiro, etapa: str) -> None:
    """O `aprovar` global da 011 no guiado: aprova todas as posições que faltam (409
    `keyframes_pendentes` com a 1ª que não pode)."""
    for p in estado.posicoes(r):
        if maquina.posicao_aprovada(p, etapa):
            continue
        problema = problema_da_sequencia(db, r, p) if etapa == "keyframes" \
            else problema_dos_trechos(db, r, p)
        if problema:
            codigo = "keyframes_pendentes" if etapa == "keyframes" else "nada_a_aprovar"
            raise ApiError(409, codigo, problema, details={"ordem": p.ordem})
        _marcar(db, actor, r, p, etapa)
    db.flush()


def aprovar_posicao(db: Session, actor: Actor, roteiro_id, ordem: int,
                    body: schemas.AprovarPosicaoIn) -> Roteiro:
    """R9: aprova a sequência de quadros (ou os trechos) de uma posição. Com todas aprovadas e o
    roteiro parado no portão, ele passa (no nome de quem aprovou)."""
    from sociman_api.roteiros import service

    r = _guiado_editavel(db, roteiro_id, body.version)
    p = service._posicao(r, ordem)
    if r.status not in STATUS_DA_ETAPA[body.etapa]:
        raise ApiError(409, "etapa_errada", "O vídeo não está nesta etapa",
                       details={"status": r.status.value})
    if maquina.posicao_aprovada(p, body.etapa):
        raise ApiError(409, "nada_a_aprovar", "Esta posição já está aprovada")
    problema = problema_da_sequencia(db, r, p) if body.etapa == "keyframes" \
        else problema_dos_trechos(db, r, p)
    if problema:
        raise ApiError(409, "nada_a_aprovar", problema, details={"ordem": ordem})
    before = service.history.snapshot(r)
    _marcar(db, actor, r, p, body.etapa)
    service._comandar(r, actor)
    portao = PORTAO_DA_ETAPA[body.etapa]
    details: dict[str, Any] = {"acao": "aprovar_posicao", "etapa": body.etapa, "ordem": ordem}
    db.flush()
    if r.status == estado.AGUARDANDO_DO_PORTAO[portao] and maquina.todas_aprovadas(r, portao):
        maquina.passar(db, r, actor, portao)
        details["portao"] = portao
    service._record(db, actor, r, "updated", before, details)
    maquina.avancar(db, r, actor, humano=True)
    return r


def _conferir_alvo(db: Session, r: Roteiro, alvo: schemas.AlvoRecusa) -> None:
    from sociman_api.roteiros import service

    if r.status not in STATUS_DO_ALVO[alvo.tipo]:
        raise ApiError(409, "etapa_errada", "Este item não está esperando aprovação agora",
                       details={"status": r.status.value})
    if alvo.tipo not in ("quadros", "trecho", "posicao"):
        return
    if alvo.ordem is None:
        raise ApiError(422, "alvo_invalido", "Diga a posição do item recusado",
                       details={"field": "alvo.ordem"})
    p = service._posicao(r, alvo.ordem)
    if alvo.tipo == "posicao":
        return
    if alvo.tipo == "quadros":
        qs = cenas_quadros.ativos(db, p.cena_id)
        q = next((x for x in qs if x.ordem == (alvo.quadro or 0)), None)
        if q is None:
            raise ApiError(422, "alvo_invalido", "Este quadro não existe na posição",
                           details={"field": "alvo.quadro"})
        if q.image_id is None:
            raise ApiError(409, "etapa_errada", "Este quadro ainda não foi gerado")
        return
    if alvo.trecho is None or alvo.trecho >= (p.trechos or 0):
        raise ApiError(422, "alvo_invalido", "Este trecho não existe na posição",
                       details={"field": "alvo.trecho"})
    x = p.trecho(alvo.trecho)
    if x is None or x.tomada_id is None:
        raise ApiError(409, "etapa_errada", "Este trecho ainda não foi gerado")


def alvo_dict(alvo: schemas.AlvoRecusa) -> dict[str, Any]:
    return {k: v for k, v in alvo.model_dump().items() if v is not None}


def recusar(db: Session, actor: Actor, roteiro_id, body: schemas.RecusarIn) -> Roteiro:
    """O "Não aprovo" (R6): grava o pedido de troca no chat e pede o `roteiro.ajuste`, que
    devolve um esclarecimento (nada é gerado) ou a mudança, aplicada em nome de quem recusou."""
    from sociman_api.roteiros import ajuste, service

    r = _guiado_editavel(db, roteiro_id, body.version)
    _conferir_alvo(db, r, body.alvo)
    if conversa._aberta(db, r) is not None:
        raise ApiError(409, "geracao_em_andamento", "Espere a IA terminar o pedido anterior")
    opcoes = list(dict.fromkeys(body.opcoes))
    texto = (body.texto or "").strip()
    if not opcoes and not texto:
        raise ApiError(422, "opcao_invalida", "Escolha uma opção ou escreva o que trocar",
                       details={"field": "opcoes"})
    alvo = alvo_dict(body.alvo)
    before = service.history.snapshot(r)
    linha = ajuste.registrar_pedido(db, actor, r, alvo, opcoes, texto)
    g = ajuste.pedir(db, actor, r, alvo, linha)
    service._comandar(r, actor)
    service._record(db, actor, r, "updated", before,
                    {"acao": "recusar", "alvo": alvo, "opcoes": opcoes, "comTexto": bool(texto),
                     "pedido": linha.conteudo.get("pedido"), "geracaoId": str(g.id)})
    return r


# ---- modal de cenas (US4; R7; FR-019 a FR-024) ----

def _reuso_invalido(message: str, **details: Any) -> ApiError:
    return ApiError(422, "reuso_invalido", message, details={"field": "cenaId", **details})


def _cena_escolhida(db: Session, cena_id) -> Cena:
    cena = db.get(Cena, cena_id) if cena_id is not None else None
    if cena is None or cena.archived:
        raise _reuso_invalido("Escolha uma cena ativa da biblioteca")
    return cena


def definir_cena(db: Session, actor: Actor, roteiro_id, ordem: int,
                 body: schemas.DefinirCenaIn) -> Roteiro:
    """A troca do modal de cenas (FR-021), humana e com histórico (FR-037):
    - **total**: a cena da biblioteca como está, só se ela é candidata `total` com os trechos da
      posição (senão 422 `reuso_invalido`); nada é gerado (SC-003);
    - **plano**: uma cena derivada dela (FR-022), com o avatar, o cenário e o produto do vídeo;
      uma cena de outro produto entra só assim, à mão, com o aviso `cena_outro_produto` (FR-024);
    - **nova**: pede à IA a cena daquela posição (`roteiro.ajuste` com alvo `posicao`), que
      chega como cena nova da biblioteca com o perfil base do vídeo (FR-023).
    Antes do texto aprovado é o modal; depois, só no avançado (senão 409 `etapa_errada`)."""
    from sociman_api.roteiros import ajuste, plano_guiado, reuso, service

    r = _guiado_editavel(db, roteiro_id, body.version)
    p = service._posicao(r, ordem)
    if estado.nivel(r.status) < estado.nivel(RoteiroStatus.aguardando_texto) or \
            (r.status != RoteiroStatus.aguardando_texto and not body.avancado):
        raise ApiError(409, "etapa_errada", "As cenas só mudam no modal, antes de aprovar o "
                       "texto (depois, no modo avançado)", details={"status": r.status.value})
    if conversa._aberta(db, r) is not None or ajuste_aberto(db, r, ordem):
        raise ApiError(409, "geracao_em_andamento", "Espere a IA terminar o pedido anterior")
    before = service.history.snapshot(r)
    details: dict[str, Any] = {"acao": "definir_cena", "ordem": ordem, "reuso": body.reuso,
                               "cenaAnteriorId": str(p.cena_id)}
    if body.reuso == "nova":
        alvo = {"tipo": "posicao", "ordem": ordem}
        linha = ajuste.registrar_pedido(db, actor, r, alvo, ["Criar uma cena nova"], "")
        g = ajuste.pedir(db, actor, r, alvo, linha, nova=True)
        details["geracaoId"] = str(g.id)
    elif body.reuso == "total":
        cena = _cena_escolhida(db, body.cena_id)
        cand = reuso.classificar(db, r, cena)
        if cand is None:
            raise _reuso_invalido("Esta cena mostra outro produto: escolha o reuso do plano")
        if cand.nivel != "total":
            raise _reuso_invalido("Esta cena não serve como está (" +
                                  ", ".join(cand.diferencas) + "): use o reuso do plano",
                                  diferencas=list(cand.diferencas))
        if cena.trechos != p.trechos:
            raise _reuso_invalido(f"Esta cena tem {cena.trechos} trecho(s), e a posição tem "
                                  f"{p.trechos}: use o reuso do plano")
        plano_guiado.trocar_cena(p, cena, PosicaoReuso.total, "Escolhida pelo operador, sem custo.")
        details["cenaId"] = str(cena.id)
    else:
        origem = _cena_escolhida(db, body.cena_id)
        if reuso.classificar(db, r, origem) is None:  # outro produto: só à mão (FR-024)
            maquina.avisar(r, "cena_outro_produto", f"A cena da posição {ordem + 1} veio de uma "
                           "cena de outro produto: confira os quadros", ordem)
            details["outroProduto"] = True
        derivada = plano_guiado.derivar(db, actor, r, origem, int(p.trechos or 1), None,
                                        details={"ordem": ordem, "manual": True})
        plano_guiado.trocar_cena(p, derivada, PosicaoReuso.plano,
                     "Escolhida pelo operador; as imagens são refeitas.")
        details |= {"cenaId": str(derivada.id), "origemCenaId": str(origem.id)}
    service._comandar(r, actor)
    db.flush()
    service._record(db, actor, r, "updated", before, details)
    maquina.avancar(db, r, actor, humano=True)
    return r


def quadros_da_posicao(db: Session, roteiro_id, ordem: int) -> list[schemas.QuadroResumo]:
    from sociman_api.roteiros import service

    r = service.get_or_404(db, roteiro_id)
    p = service._posicao(r, ordem)
    return service.quadros_out(db, db.get(Cena, p.cena_id))
