"""Ações humanas sobre as gerações e as leituras (contracts/http-api.md, research R10 e R16).

Spec 029 (R4, R14): a biblioteca é da agência. O alvo vale por si (de qualquer perfil base), e a
geração grava em `perfil_id` o **perfil base usado**, resolvido por `perfis.base.resolver` a
partir do `perfilBaseId` do pedido (ausente = o do item; `null` = nenhum; um id = aquele).

Toda ação humana (pedir, escolher, cancelar, tentar de novo, gerar outras) roda numa transação
só: trava a geração, confere a `version` (409 `version_conflict`), grava a versão da geração em
`entity_versions` (`entity_type = "geracao"`, com os `details` do R10) e chama o gancho
`ao_mudar_estado` do aplicador. Escolher também grava a versão do alvo (`details.geracao_id`),
com o humano que escolheu como autor (FR-009). Não há "reverter" (exceção do princípio VII, como
o envio da 006): o caminho de volta é pedir outra geração.
"""

import base64
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from sociman_api import history, imaging, midia
from sociman_api.assets.service import image_ref
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.geracao import aplicadores, audios, passos, schemas, seeds
from sociman_api.geracao.fila import transicao
from sociman_api.geracao.models import (
    ENTITY,
    FINAIS,
    Audio,
    Geracao,
    GeracaoAlvo,
    GeracaoCandidato,
    GeracaoMotor,
    GeracaoStatus,
)
from sociman_api.perfis import base
from sociman_api.perfis.models import Image, Perfil
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, user_refs, versions_out

LABEL = "Esta geração"
NOT_FOUND = "Geração não encontrada"
CADASTRO = {GeracaoAlvo.asset: "avatar", GeracaoAlvo.voz: "voz", GeracaoAlvo.produto: "produto"}
LIMITE_PADRAO = 20
LIMITE_MAX = 50


# ---- auxiliares ----

def get_or_404(db: Session, geracao_id: uuid.UUID, lock: bool = False) -> Geracao:
    g = db.get(Geracao, geracao_id, with_for_update=lock)
    if g is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return g


def _passo(passo_id: str) -> passos.Passo:
    passo = passos.get(passo_id)
    if passo is None:
        raise aplicadores.entrada_invalida("passo", "passo desconhecido")
    return passo


def _aplicador(passo: passos.Passo) -> aplicadores.Aplicador:
    aplicador = aplicadores.para(passo.id)
    if aplicador is None:
        raise ApiError(409, "passo_indisponivel",
                       f"Este passo chega com o cadastro de {CADASTRO[passo.alvo_tipo]}")
    return aplicador


def _motor_configurado(motor: GeracaoMotor) -> None:
    """503 só sem a URL do serviço; sem a chave do Claude a geração é criada e falha com
    mensagem clara (US4, cenário 5), sem ficar presa na fila."""
    s = get_settings()
    url = {GeracaoMotor.comfyui: s.comfyui_url, GeracaoMotor.tts: s.shop_tts_url}.get(motor)
    if url is not None and not url.strip():
        nome = "ComfyUI (COMFYUI_URL)" if motor == GeracaoMotor.comfyui \
            else "serviço de voz (SHOP_TTS_URL)"
        raise ApiError(503, "geracao_indisponivel", f"O {nome} não está configurado")


def _record(db: Session, actor: Actor, g: Geracao, action: str,
            before: dict[str, Any] | None, details: dict[str, Any]) -> None:
    db.flush()
    g.updated_by = actor.user_id
    history.record(db, actor, ENTITY, g, action, before, history.snapshot(g), details)


def _usa_seeds(passo: passos.Passo) -> bool:
    return passo.motor != GeracaoMotor.claude and passo.bloco != "cutout"


def _nova(db: Session, actor: Actor, perfil_id: uuid.UUID | None, passo: passos.Passo,
          alvo_tipo: GeracaoAlvo, alvo_id: uuid.UUID, params: dict[str, Any], n: int,
          de_geracao_id: uuid.UUID | None = None) -> Geracao:
    """Cria a geração na fila (seeds novas, R7), com a versão `created` e o gancho."""
    if _usa_seeds(passo):
        params = {**params, "seeds": seeds.novas(db, alvo_tipo, alvo_id, passo.id, n)}
    else:
        params = {**params, "seeds": []}
    params["n"] = n
    g = Geracao(perfil_id=perfil_id, alvo_tipo=alvo_tipo, alvo_id=alvo_id, passo=passo.id,
                motor=passo.motor, params=params, n_opcoes=n, status=GeracaoStatus.na_fila,
                de_geracao_id=de_geracao_id, created_by=actor.user_id, updated_by=actor.user_id)
    db.add(g)
    db.flush()
    details: dict[str, Any] = {"passo": passo.id, "motor": passo.motor.value,
                               "alvoTipo": alvo_tipo.value, "alvoId": str(alvo_id),
                               "nOpcoes": n}
    if de_geracao_id is not None:
        details["deGeracaoId"] = str(de_geracao_id)
    history.record(db, actor, ENTITY, g, "created", None, history.snapshot(g), details)
    aplicadores.chamar_gancho(db, g, None, GeracaoStatus.na_fila)
    return g


def criar_para_alvo(db: Session, actor: Actor, perfil_id: uuid.UUID | None, passo_id: str,
                    alvo_tipo: GeracaoAlvo, alvo_id: uuid.UUID, params: dict[str, Any], *,
                    perfil_base: base.Pedido = base.AUSENTE) -> Geracao:
    """Pedido montado pelo cadastro do próprio alvo (o produto da 012, R1): o `params` já vem
    pronto do fluxo do alvo, que validou as referências. Seeds novas como no `pedir` (R7).

    `perfil_id` é o perfil base do item. Sem `perfil_base`, vale ele, como antes da 029 (os
    pedidos que o próprio cadastro encadeia não recusam o perfil arquivado); com ele (pedido
    humano), passa pelo `resolver`."""
    passo = _passo(passo_id)
    if passo.alvo_tipo != alvo_tipo:
        raise aplicadores.alvo_incompativel()
    _aplicador(passo)
    if perfil_base is not base.AUSENTE:
        perfil = base.resolver(db, perfil_id, perfil_base)
        perfil_id = perfil.id if perfil is not None else None
    return _nova(db, actor, perfil_id, passo, alvo_tipo, alvo_id, params, passo.n_padrao)


# ---- pedir ----

def pedir(db: Session, actor: Actor, body: schemas.GeracaoIn,
          perfil_caminho: uuid.UUID | None = None) -> Geracao:
    """`POST /api/geracoes`; a rota antiga por perfil passa o `perfil_caminho`, que vira o padrão
    do `perfilBaseId` ausente (e mantém o 404 e o 409 `perfil_archived` de antes)."""
    pedido_base = body.perfil_base_pedido()
    if perfil_caminho is not None:
        perfil = get_perfil_or_404(db, perfil_caminho)
        if perfil.archived:
            raise ApiError(409, "perfil_archived", "O perfil está arquivado")
        if pedido_base is base.AUSENTE:
            pedido_base = perfil_caminho
    if body.alvo_tipo == GeracaoAlvo.produto:  # a 012 usa rotas próprias (R16)
        raise aplicadores.alvo_incompativel()
    passo = _passo(body.passo)
    if passo.alvo_tipo != body.alvo_tipo:
        raise aplicadores.alvo_incompativel()
    aplicador = _aplicador(passo)
    n = body.n_opcoes or passo.n_padrao
    if n > passo.n_max:
        raise aplicadores.entrada_invalida("nOpcoes", f"no máximo {passo.n_max} neste passo")
    for ref in body.referencias:  # o service só confere que existe; o resto é do aplicador
        if db.get(Image, ref) is None:
            raise aplicadores.entrada_invalida("referencias", "a imagem não existe")
    _motor_configurado(passo.motor)
    alvo = aplicador.validar_alvo(db, perfil_caminho, body.alvo_id)
    perfil_base = base.resolver(db, aplicador.perfil_do_alvo(alvo), pedido_base)
    perfil_id = perfil_base.id if perfil_base is not None else None
    pedido = aplicadores.Pedido(passo=passo, instrucao=body.instrucao,
                                referencias=list(body.referencias), rotulo=body.rotulo,
                                texto=body.texto, extras=body.extras)
    params = aplicador.montar_params(db, actor, alvo, pedido)
    return _nova(db, actor, perfil_id, passo, body.alvo_tipo, body.alvo_id, params, n)


# ---- escolher ----

def escolher(db: Session, actor: Actor, geracao_id: uuid.UUID,
             body: schemas.EscolherIn) -> tuple[Geracao, Any]:
    g = get_or_404(db, geracao_id, lock=True)
    if g.status != GeracaoStatus.revisao:
        raise ApiError(409, "geracao_decidida", "Esta geração já foi decidida")
    history.check_version(g, body.version, LABEL)
    cand = db.get(GeracaoCandidato, body.candidato_id)
    if cand is None or cand.geracao_id != g.id or (cand.image_id is None
                                                   and cand.audio_id is None):
        raise ApiError(400, "candidato_invalido", "Esta opção não é desta geração")
    aplicador = _aplicador(_passo(g.passo))
    alvo = aplicador.validar_alvo(db, g.perfil_id, g.alvo_id, lock=True)
    if aplicador.alvo_version(alvo) != body.alvo_version:
        raise ApiError(409, "version_conflict", "O item mudou; recarregue e escolha de novo",
                       details={"versaoAtual": aplicador.alvo_version(alvo)})
    before = history.snapshot(g)
    aplicador.aplicar(db, actor, g, cand)
    g.escolhido_id = cand.id
    g.etapa_mensagem = None
    transicao(db, g, GeracaoStatus.escolhido)
    _record(db, actor, g, "updated", before,
            {"acao": "escolher", "candidatoId": str(cand.id), "numero": cand.numero})
    db.flush()
    return g, alvo


# ---- cancelar, tentar de novo, gerar outras (US3) ----

def cancelar(db: Session, actor: Actor, geracao_id: uuid.UUID, version: int) -> Geracao:
    """Vale em `na_fila`, `rodando`, `revisao` e `falhou`, até com o alvo arquivado (FR-015). O
    gerador vê a `cancelada` no próximo heartbeat e para o motor (R9)."""
    g = get_or_404(db, geracao_id, lock=True)
    if g.status in FINAIS:
        raise ApiError(409, "geracao_finalizada", "Esta geração já terminou")
    history.check_version(g, version, LABEL)
    before, de = history.snapshot(g), g.status
    g.heartbeat_at = None
    g.etapa_mensagem = None
    g.next_attempt_at = None
    if g.status == GeracaoStatus.falhou:  # o erro fica no histórico; a cancelada não tem erro
        g.error_code = g.error_message = None
    transicao(db, g, GeracaoStatus.cancelada)
    _record(db, actor, g, "updated", before, {"acao": "cancelar", "de": de.value})
    return g


def tentar_de_novo(db: Session, actor: Actor, geracao_id: uuid.UUID, version: int) -> Geracao:
    """Só em `falhou` (FR-012): mesma entrada, espera e tentativas zeradas; o erro anterior fica
    no histórico."""
    g = get_or_404(db, geracao_id, lock=True)
    if g.status != GeracaoStatus.falhou:
        raise ApiError(409, "estado_invalido", "Só uma geração que falhou pode tentar de novo")
    history.check_version(g, version, LABEL)
    aplicador = _aplicador(_passo(g.passo))
    aplicador.validar_alvo(db, g.perfil_id, g.alvo_id)
    before = history.snapshot(g)
    erro = {"code": g.error_code, "message": g.error_message}
    g.error_code = g.error_message = None
    g.attempts, g.interrupcoes, g.progress = 0, 0, 0
    g.next_attempt_at = g.heartbeat_at = g.finished_at = g.started_at = None
    g.etapa_mensagem = None
    transicao(db, g, GeracaoStatus.na_fila)
    _record(db, actor, g, "updated", before, {"acao": "tentar_de_novo", "erroAnterior": erro})
    return g


def gerar_outras(db: Session, actor: Actor, geracao_id: uuid.UUID, version: int) -> Geracao:
    """Só em `revisao` (FR-013): a nova (mesma entrada, seeds novas) é criada, com o gancho,
    **antes** de a antiga virar `descartada`, na mesma transação."""
    g = get_or_404(db, geracao_id, lock=True)
    if g.status != GeracaoStatus.revisao:
        raise ApiError(409, "estado_invalido", "Só uma geração em revisão pode gerar outras")
    history.check_version(g, version, LABEL)
    passo = _passo(g.passo)
    aplicador = _aplicador(passo)
    aplicador.validar_alvo(db, g.perfil_id, g.alvo_id)
    params = {k: v for k, v in g.params.items() if k not in ("seeds", "n")}
    nova = _nova(db, actor, g.perfil_id, passo, g.alvo_tipo, g.alvo_id, params, g.n_opcoes,
                 de_geracao_id=g.id)
    before = history.snapshot(g)
    g.etapa_mensagem = None
    transicao(db, g, GeracaoStatus.descartada)
    _record(db, actor, g, "updated", before,
            {"acao": "gerar_outras", "novaGeracaoId": str(nova.id)})
    return nova


# ---- leituras ----

def _link(kind: midia.MidiaKind, entity_id: uuid.UUID) -> schemas.Link:
    lk = midia.link(kind, entity_id, ttl=get_settings().midia_link_ttl_s)
    return schemas.Link(url=lk.url, expires_at=lk.expires_at)


def _imagem_out(img: Image | None) -> schemas.ImagemCandidato | None:
    if img is None:
        return None
    return schemas.ImagemCandidato(image_id=img.id, width=img.width, height=img.height,
                                   url=imaging.preview_url(img.object_key),
                                   link=_link("imagem", img.id))


def _candidatos_out(db: Session, cands: list[GeracaoCandidato]) -> list[schemas.CandidatoGeracao]:
    image_ids = {i for c in cands for i in (c.image_id, c.image_par_id) if i}
    imgs = {i.id: i for i in db.scalars(select(Image).where(Image.id.in_(image_ids)))} \
        if image_ids else {}
    audio_ids: set[uuid.UUID] = {c.audio_id for c in cands if c.audio_id}
    for c in cands:
        teste = (c.metricas or {}).get("teste_audio_id")
        if teste:
            audio_ids.add(uuid.UUID(teste))
    auds = {a.id: a for a in db.scalars(select(Audio).where(Audio.id.in_(audio_ids)))} \
        if audio_ids else {}
    users = user_refs(db, [a.created_by for a in auds.values()])
    out = []
    for c in cands:
        teste = (c.metricas or {}).get("teste_audio_id")
        teste_audio = auds.get(uuid.UUID(teste)) if teste else None
        out.append(schemas.CandidatoGeracao(
            id=c.id, numero=c.numero, seed=c.seed,
            imagem=_imagem_out(imgs.get(c.image_id)) if c.image_id else None,
            imagem_par=_imagem_out(imgs.get(c.image_par_id)) if c.image_par_id else None,
            audio=audios.audio_out(auds[c.audio_id], users) if c.audio_id in auds else None,
            metricas={k: v for k, v in (c.metricas or {}).items() if k != "teste_audio_id"},
            teste_audio=audios.audio_out(teste_audio, users) if teste_audio else None))
    return out


def _nomes_perfis(db: Session, gs: list[Geracao]) -> dict[uuid.UUID, str]:
    ids = {g.perfil_id for g in gs if g.perfil_id is not None}
    return dict(db.execute(select(Perfil.id, Perfil.name).where(Perfil.id.in_(ids))).all()) \
        if ids else {}


def _resumo_campos(db: Session, g: Geracao, refs: dict[uuid.UUID, Image], users: dict,
                   n_candidatos: int, miniatura: str | None,
                   nomes: dict[uuid.UUID, str]) -> dict[str, Any]:
    p = g.params or {}
    passo = passos.get(g.passo)
    return {
        "id": g.id, "perfil_id": g.perfil_id,
        "perfil_nome": nomes.get(g.perfil_id) if g.perfil_id else None,
        "alvo_tipo": g.alvo_tipo, "alvo_id": g.alvo_id,
        "passo": g.passo, "motor": g.motor, "instrucao": p.get("instrucao") or "",
        "referencias": [image_ref(refs[uuid.UUID(r)]) for r in p.get("referencias") or []
                        if uuid.UUID(r) in refs],
        "rotulo": p.get("rotulo"), "texto": p.get("texto"), "extras": p.get("extras"),
        "n_opcoes": g.n_opcoes, "status": g.status, "progress": g.progress,
        "etapa_mensagem": g.etapa_mensagem, "attempts": g.attempts,
        "next_attempt_at": g.next_attempt_at,
        "erro": schemas.Erro(code=g.error_code, message=g.error_message or "")
        if g.error_code else None,
        "escolhido_id": g.escolhido_id, "started_at": g.started_at,
        "finished_at": g.finished_at, "limpa_em": g.limpa_em,
        "sem_escolha": bool(passo and passo.sem_escolha), "de_geracao_id": g.de_geracao_id,
        "version": g.version, "created_at": g.created_at,
        "created_by": users.get(g.created_by) if g.created_by else None,
        "updated_at": g.updated_at, "n_candidatos": n_candidatos,
        "miniatura_escolhido": miniatura,
    }


def _refs(db: Session, gs: list[Geracao]) -> dict[uuid.UUID, Image]:
    ids = {uuid.UUID(r) for g in gs for r in (g.params or {}).get("referencias") or []}
    return {i.id: i for i in db.scalars(select(Image).where(Image.id.in_(ids)))} if ids else {}


def resumo_out(db: Session, g: Geracao) -> schemas.GeracaoResumo:
    """O resumo de uma geração (as rotas do produto devolvem o pedido que criaram, 012)."""
    n = db.scalar(select(func.count()).select_from(GeracaoCandidato)
                  .where(GeracaoCandidato.geracao_id == g.id)) or 0
    users = user_refs(db, [g.created_by])
    return schemas.GeracaoResumo(**_resumo_campos(db, g, _refs(db, [g]), users, n, None,
                                                  _nomes_perfis(db, [g])))


def detalhe(db: Session, geracao_id: uuid.UUID) -> schemas.GeracaoDetalhe:
    g = get_or_404(db, geracao_id)
    db.refresh(g)
    return geracao_out(db, g)


def geracao_out(db: Session, g: Geracao) -> schemas.GeracaoDetalhe:
    cands = list(db.scalars(select(GeracaoCandidato).where(GeracaoCandidato.geracao_id == g.id)
                            .order_by(GeracaoCandidato.numero)))
    candidatos = _candidatos_out(db, cands)
    escolhido = next((c for c in candidatos if c.id == g.escolhido_id), None)
    miniatura = escolhido.imagem.url if escolhido and escolhido.imagem else None
    users = user_refs(db, [g.created_by])
    return schemas.GeracaoDetalhe(**_resumo_campos(db, g, _refs(db, [g]), users, len(cands),
                                                   miniatura, _nomes_perfis(db, [g])),
                                  candidatos=candidatos)


def versoes(db: Session, geracao_id: uuid.UUID) -> VersionsList:
    get_or_404(db, geracao_id)
    return versions_out(db, ENTITY, geracao_id)


def _cursor(created_at: datetime, gid: uuid.UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(gid)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _ler_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        ts, gid = json.loads(raw)
        return datetime.fromisoformat(ts), uuid.UUID(gid)
    except (ValueError, TypeError) as exc:
        raise ApiError(400, "validation_error", "cursor inválido") from exc


def listar(db: Session, perfil_id: uuid.UUID | None, *, alvo_tipo: GeracaoAlvo | None = None,
           alvo_id: uuid.UUID | None = None, status: list[GeracaoStatus] | None = None,
           passo: str | None = None, cursor: str | None = None,
           limite: int = LIMITE_PADRAO) -> schemas.GeracoesPagina:
    """Por perfil (a rota antiga: as gerações com aquele perfil base usado) ou, sem perfil, as
    do alvo (`GET /api/geracoes`, de qualquer perfil base)."""
    stmt = select(Geracao)
    if perfil_id is not None:
        get_perfil_or_404(db, perfil_id)
        stmt = stmt.where(Geracao.perfil_id == perfil_id)
    if alvo_tipo is not None:
        stmt = stmt.where(Geracao.alvo_tipo == alvo_tipo)
    if alvo_id is not None:
        stmt = stmt.where(Geracao.alvo_id == alvo_id)
    if status:
        stmt = stmt.where(Geracao.status.in_(status))
    if passo is not None:
        stmt = stmt.where(Geracao.passo == passo)
    if cursor:
        ts, gid = _ler_cursor(cursor)
        stmt = stmt.where(tuple_(Geracao.created_at, Geracao.id) < tuple_(ts, gid))
    limite = max(1, min(limite, LIMITE_MAX))
    gs = list(db.scalars(stmt.order_by(Geracao.created_at.desc(), Geracao.id.desc())
                         .limit(limite + 1)))
    proximo = _cursor(gs[limite - 1].created_at, gs[limite - 1].id) if len(gs) > limite \
        else None
    gs = gs[:limite]
    ids = [g.id for g in gs]
    contagem = dict(db.execute(
        select(GeracaoCandidato.geracao_id, func.count()).where(
            GeracaoCandidato.geracao_id.in_(ids)).group_by(GeracaoCandidato.geracao_id)).all()
    ) if ids else {}
    escolhidos = {g.escolhido_id for g in gs if g.escolhido_id}
    minis: dict[uuid.UUID, str] = {}
    if escolhidos:
        for cid, key in db.execute(
                select(GeracaoCandidato.id, Image.object_key)
                .join(Image, Image.id == GeracaoCandidato.image_id)
                .where(GeracaoCandidato.id.in_(escolhidos))):
            minis[cid] = imaging.image_urls(key)["medium"]
    refs = _refs(db, gs)
    users = user_refs(db, [g.created_by for g in gs])
    nomes = _nomes_perfis(db, gs)
    itens = [schemas.GeracaoResumo(**_resumo_campos(
        db, g, refs, users, contagem.get(g.id, 0), minis.get(g.escolhido_id), nomes))
        for g in gs]
    return schemas.GeracoesPagina(itens=itens, proximo=proximo)
