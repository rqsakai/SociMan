"""Ações humanas sobre o roteiro e as leituras (contracts/http-api.md da 011; FR-001 a FR-016,
FR-024, FR-027, FR-031, FR-035 e FR-036).

Toda ação trava o roteiro, confere a `version` (409 `version_conflict`), grava **uma** versão
(`entity_type = "roteiro"`, `details.acao`), marca quem comandou (`comandado_por`, R9) e chama
`maquina.avancar(..., humano=True)` na mesma transação: uma regra violada vira 409, e as
gerações pedidas têm o humano como autor. As invalidações são da máquina (reposicionar); aqui só
se gravam os dados novos.

Spec 029: avatar, voz, produtos e cenas podem ser de qualquer perfil base; o perfil do roteiro é
o perfil base de todas as gerações dele.
"""

import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from sociman_api import history, imaging, midia, storage
from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.cenas import service as cenas_service
from sociman_api.cenas.models import Cena, CenaStatus, CenaTomada, TomadaOrigem
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.geracao.models import Geracao, GeracaoCandidato
from sociman_api.perfis.models import Image, ImageKind, Perfil
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, target_state, versions_out
from sociman_api.produtos.models import Produto, ProdutoStatus
from sociman_api.roteiros import aplicadores, estado, maquina, pedidos, schemas, tempos
from sociman_api.roteiros.estado import S
from sociman_api.roteiros.models import (
    ENTITY,
    PORTOES_PADRAO,
    Roteiro,
    RoteiroCena,
    RoteiroModo,
    RoteiroNarracao,
    RoteiroPadroes,
    RoteiroProduto,
)
from sociman_api.vozes.models import Voz

LABEL = "Este roteiro"
NOT_FOUND = "Roteiro não encontrado"
LIMITE_PADRAO = 20
LIMITE_MAX = 50
KEYFRAME_MAX_BYTES = 20 * 1024 * 1024
ASPECTO_TOLERANCIA = 0.01
EDITAVEIS_NO_PLANO = ("frases", "posicoes", "produtos", "avatar_id")


def invalido(field: str, message: str) -> ApiError:
    return ApiError(400, "invalid_roteiro", f"{field}: {message}", details={"field": field})


def get_or_404(db: Session, roteiro_id: uuid.UUID, lock: bool = False) -> Roteiro:
    r = db.get(Roteiro, roteiro_id, with_for_update=lock)
    if r is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return r


def _editavel(db: Session, roteiro_id: uuid.UUID, version: int) -> Roteiro:
    r = get_or_404(db, roteiro_id, lock=True)
    history.check_version(r, version, LABEL)
    if r.archived:
        raise ApiError(409, "roteiro_arquivado", "Restaure o roteiro antes de mudar")
    return r


def _comandar(r: Roteiro, actor: Actor) -> None:
    r.comandado_por = actor.user_id
    r.updated_by = actor.user_id


def _record(db: Session, actor: Actor, r: Roteiro, action: str, before: dict[str, Any] | None,
            details: dict[str, Any] | None = None, sempre: bool = True) -> bool:
    db.flush()
    after = history.snapshot(r)
    if before is not None and after == before and not sempre:
        return False
    history.record(db, actor, ENTITY, r, action, before, after, details)
    return True


# ---- validações ----

def _produtos(db: Session, itens: list[schemas.ProdutoRoteiroIn]
              ) -> list[tuple[Produto, uuid.UUID | None]]:
    out, vistos = [], set()
    for i, item in enumerate(itens):
        produto = db.get(Produto, item.produto_id)
        if produto is None:
            raise invalido(f"produtos.{i}.produtoId", "produto não encontrado")
        if produto.archived or produto.status != ProdutoStatus.aprovado:
            raise ApiError(409, "produto_fora_de_aprovado",
                           f"O produto {produto.nome_comercial or produto.name} não está "
                           "aprovado", details={"field": f"produtos.{i}.produtoId"})
        if item.variante_id is not None:
            v = produto.variante(item.variante_id)
            if v is None or v.archived:
                raise invalido(f"produtos.{i}.varianteId", "variante ativa deste produto")
        chave = (produto.id, item.variante_id)
        if chave in vistos:
            raise invalido(f"produtos.{i}", "produto repetido")
        vistos.add(chave)
        out.append((produto, item.variante_id))
    return out


def _avatar(db: Session, avatar_id: uuid.UUID | None) -> Asset | None:
    if avatar_id is None:
        return None
    a = db.get(Asset, avatar_id)
    if a is None:
        raise invalido("avatarId", "use um avatar ativo da biblioteca")
    problema = estado.problema_do_avatar(a)
    if problema is None and a.archived:
        problema = ("invalid_roteiro", "use um avatar ativo da biblioteca")
    if problema:
        status = 409 if problema[0] == "consentimento_revogado" else 400
        raise ApiError(status, problema[0], problema[1], details={"field": "avatarId"})
    return a


def _voz(db: Session, voz_id: uuid.UUID | None) -> Voz | None:
    if voz_id is None:
        return None
    v = db.get(Voz, voz_id)
    if v is None:
        raise invalido("vozId", "voz não encontrada")
    problema = estado.problema_da_voz(v, para_narrar=False)
    if problema:
        status = 409 if problema[0] == "consentimento_revogado" else 400
        raise ApiError(status, problema[0], problema[1], details={"field": "vozId"})
    return v


def _validar_posicoes(db: Session, r: Roteiro, frases: list[str],
                      posicoes: list[schemas.PosicaoIn], novas: bool) -> None:
    maximo = get_settings().roteiro_max_cenas
    if novas and len(posicoes) > maximo and len(posicoes) > len(r.posicoes_rel):
        raise ApiError(409, "limite_cenas", f"O roteiro pode ter até {maximo} cenas",
                       details={"field": "posicoes", "limite": maximo})
    for i, p in enumerate(posicoes):
        cena = db.get(Cena, p.cena_id)
        if cena is None or (cena.archived and novas):
            raise invalido(f"posicoes.{i}.cenaId", "use uma cena ativa da biblioteca")
        if p.tomada_id is not None:
            t = db.get(CenaTomada, p.tomada_id)
            if t is None or t.cena_id != cena.id:
                raise invalido(f"posicoes.{i}.tomadaId", "a tomada precisa ser desta cena")
    try:
        tempos.validar_posicoes([list(p.frases) for p in posicoes], list(range(len(frases))))
    except tempos.TemposInvalidos as exc:
        raise invalido("posicoes", f"toda frase em exatamente uma cena, em ordem ({exc})") \
            from None


def _trocar_posicoes(db: Session, r: Roteiro, posicoes: list[schemas.PosicaoIn]) -> None:
    antigas = {p.ordem: p for p in r.posicoes_rel}
    for velha in list(r.posicoes_rel):
        r.posicoes_rel.remove(velha)
    db.flush()
    for ordem, p in enumerate(posicoes):
        anterior = antigas.get(ordem)
        tomada = p.tomada_id
        if tomada is None and anterior is not None and anterior.cena_id == p.cena_id:
            tomada = anterior.tomada_id  # a mesma cena na mesma posição guarda a tomada
        r.posicoes_rel.append(RoteiroCena(roteiro_id=r.id, ordem=ordem, cena_id=p.cena_id,
                                          frases=list(p.frases), tomada_id=tomada))
    db.flush()


def _trocar_produtos(db: Session, r: Roteiro, produtos: list[tuple[Produto, uuid.UUID | None]]
                     ) -> None:
    for velho in list(r.produtos_rel):
        r.produtos_rel.remove(velho)
    db.flush()
    for ordem, (p, variante) in enumerate(produtos):
        r.produtos_rel.append(RoteiroProduto(roteiro_id=r.id, ordem=ordem, produto_id=p.id,
                                             produto_variante_id=variante))
    db.flush()


def padroes_do_perfil(db: Session, perfil_id: uuid.UUID) -> tuple[RoteiroModo, dict[str, bool]]:
    linha = db.get(RoteiroPadroes, perfil_id)
    if linha is None:
        return RoteiroModo.revisar, dict(PORTOES_PADRAO)
    return linha.modo, {**PORTOES_PADRAO, **(linha.portoes or {})}


# ---- criar, editar, arquivar ----

def criar(db: Session, actor: Actor, perfil_id: uuid.UUID, body: schemas.RoteiroIn) -> Roteiro:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    produtos = _produtos(db, body.produtos)
    avatar = _avatar(db, body.avatar_id)
    voz_id = body.voz_id
    avisos = []
    if voz_id is None and avatar is not None and avatar.voz_id is not None:
        padrao = db.get(Voz, avatar.voz_id)
        if estado.problema_da_voz(padrao, para_narrar=False) is None:
            voz_id = padrao.id
        else:
            avisos.append({"code": "voz_padrao_invalida",
                           "message": "A voz padrão do avatar não pode narrar; escolha outra"})
    _voz(db, voz_id)
    modo, portoes = padroes_do_perfil(db, perfil_id)
    r = Roteiro(id=uuid.uuid4(), perfil_id=perfil_id, nome=body.nome, brief=body.brief,
                avatar_id=avatar.id if avatar else None, voz_id=voz_id, modo=modo,
                portoes=portoes, avisos=avisos, comandado_por=actor.user_id,
                created_by=actor.user_id, updated_by=actor.user_id)
    db.add(r)
    db.flush()
    _trocar_produtos(db, r, produtos)
    _record(db, actor, r, "created", None, {"acao": "created"})
    return r


def editar(db: Session, actor: Actor, roteiro_id: uuid.UUID, body: schemas.RoteiroPatch
           ) -> Roteiro:
    r = _editavel(db, roteiro_id, body.version)
    campos = body.model_fields_set - {"version"}
    if r.status == S.planejando and campos & set(EDITAVEIS_NO_PLANO):
        raise ApiError(409, "roteiro_planejando", "Espere o plano chegar para editar")
    before = history.snapshot(r)
    if "nome" in campos and body.nome is not None:
        r.nome = body.nome
    if "brief" in campos and body.brief is not None:
        r.brief = body.brief
    if "avatar_id" in campos:
        r.avatar_id = _avatar(db, body.avatar_id).id if body.avatar_id else None
    if "voz_id" in campos:
        r.voz_id = _voz(db, body.voz_id).id if body.voz_id else None
    if "velocidade" in campos and body.velocidade is not None:
        r.velocidade = body.velocidade
    if "produtos" in campos and body.produtos is not None:
        _trocar_produtos(db, r, _produtos(db, body.produtos))
    frases = list(body.frases) if "frases" in campos and body.frases is not None \
        else list(r.frases)
    if "posicoes" in campos and body.posicoes is not None:
        _validar_posicoes(db, r, frases, body.posicoes, novas=True)
        r.frases = frases
        _trocar_posicoes(db, r, body.posicoes)
    elif "frases" in campos and body.frases is not None:
        atuais = [schemas.PosicaoIn(cena_id=p.cena_id, frases=list(p.frases),
                                    tomada_id=p.tomada_id) for p in estado.posicoes(r)]
        if atuais:
            _validar_posicoes(db, r, frases, atuais, novas=False)
        r.frases = frases
    _comandar(r, actor)
    if not _record(db, actor, r, "updated", before, {"acao": "updated"}, sempre=False):
        return r
    maquina.avancar(db, r, actor, humano=True)
    return r


def _cancelar_abertas(db: Session, actor: Actor, r: Roteiro) -> int:
    n = 0
    for passo in estado.PASSO_DA_ETAPA.values():
        vistas = {g.id: g for g in estado.abertas(db, passo, alvo_id=r.id)}
        vistas |= {g.id: g for g in estado.abertas(db, passo, roteiro_id=r.id)}
        for g in vistas.values():
            maquina.cancelar(db, actor, g, "O roteiro foi arquivado")
            n += 1
    return n


def arquivar(db: Session, actor: Actor, roteiro_id: uuid.UUID, version: int) -> Roteiro:
    r = get_or_404(db, roteiro_id, lock=True)
    history.check_version(r, version, LABEL)
    if r.archived:
        raise ApiError(409, "roteiro_arquivado", "Este roteiro já está arquivado")
    before = history.snapshot(r)
    canceladas = _cancelar_abertas(db, actor, r)
    agora = datetime.now(UTC)
    r.archived_at, r.archived_by = agora, actor.user_id
    n = estado.narracao_ativa(db, r)
    if n is not None and n.desuso_em is None:
        n.desuso_em = agora
    for gid in (r.montagem_geracao_id, r.acabamento_geracao_id):
        g = db.get(Geracao, gid) if gid else None
        if g is not None and g.desuso_em is None:
            g.desuso_em = agora
    _comandar(r, actor)
    _record(db, actor, r, "archived", before, {"acao": "archived", "canceladas": canceladas})
    return r


def restaurar(db: Session, actor: Actor, roteiro_id: uuid.UUID, version: int) -> Roteiro:
    r = get_or_404(db, roteiro_id, lock=True)
    history.check_version(r, version, LABEL)
    if not r.archived:
        raise ApiError(409, "conflict", "Este roteiro não está arquivado")
    before = history.snapshot(r)
    r.archived_at, r.archived_by = None, None
    n = estado.narracao_ativa(db, r)
    if n is not None:
        n.desuso_em = None
    _comandar(r, actor)
    _record(db, actor, r, "restored", before, {"acao": "restored"})
    maquina.avancar(db, r, actor, humano=True)
    return r


def reverter(db: Session, actor: Actor, roteiro_id: uuid.UUID, version: int,
             to_version: int) -> Roteiro:
    """Só o dono humano (rota). Volta o conteúdo (texto, escolhas, produtos e posições); o status
    é recalculado pela máquina, e o arquivamento continua como está."""
    r = _editavel(db, roteiro_id, version)
    state = target_state(db, ENTITY, r, to_version)
    before = history.snapshot(r)
    r.nome, r.brief = state["nome"], state["brief"]
    r.avatar_id = uuid.UUID(state["avatar_id"]) if state["avatar_id"] else None
    r.voz_id = uuid.UUID(state["voz_id"]) if state["voz_id"] else None
    r.frases = list(state["frases"])
    r.velocidade = Decimal(str(state["velocidade"]))
    r.modo = RoteiroModo(state["modo"])
    r.portoes = dict(state["portoes"])
    produtos = [(db.get(Produto, uuid.UUID(p["produto_id"])),
                 uuid.UUID(p["produto_variante_id"]) if p["produto_variante_id"] else None)
                for p in state.get("produtos") or []]
    _trocar_produtos(db, r, [(p, v) for p, v in produtos if p is not None])
    _trocar_posicoes(db, r, [schemas.PosicaoIn(cena_id=uuid.UUID(p["cena_id"]),
                                               frases=list(p["frases"]),
                                               tomada_id=uuid.UUID(p["tomada_id"])
                                               if p["tomada_id"] else None)
                             for p in state.get("posicoes") or []])
    _comandar(r, actor)
    _record(db, actor, r, "reverted", before, {"from_version": to_version})
    maquina.avancar(db, r, actor, humano=True)
    return r


# ---- etapas ----

def planejar(db: Session, actor: Actor, roteiro_id: uuid.UUID, version: int) -> Roteiro:
    r = _editavel(db, roteiro_id, version)
    pode = r.status in (S.rascunho, S.aguardando_texto) or (
        r.status == S.falhou and r.etapa_falhou is not None
        and r.etapa_falhou.value == "plano")
    if not pode:
        raise ApiError(409, "estado_invalido", "O plano só é pedido no rascunho ou no texto")
    _produtos(db, [schemas.ProdutoRoteiroIn(produto_id=p.produto_id,
                                            variante_id=p.produto_variante_id)
                   for p in sorted(r.produtos_rel, key=lambda p: p.ordem)])
    _avatar(db, r.avatar_id)
    before = history.snapshot(r)
    r.status = S.planejando
    maquina.limpar_falha(r)
    r.avisos = []
    _comandar(r, actor)
    _record(db, actor, r, "updated", before, {"acao": "planejar"})
    maquina.avancar(db, r, actor, humano=True)
    return r


def _conferir_texto(db: Session, r: Roteiro) -> None:
    if not r.frases:
        raise invalido("frases", "escreva ao menos uma frase")
    atuais = [schemas.PosicaoIn(cena_id=p.cena_id, frases=list(p.frases), tomada_id=p.tomada_id)
              for p in estado.posicoes(r)]
    if not atuais:
        raise invalido("posicoes", "o roteiro precisa de ao menos uma cena")
    _validar_posicoes(db, r, list(r.frases), atuais, novas=False)
    for i, p in enumerate(estado.posicoes(r)):
        if db.get(Cena, p.cena_id).archived:
            raise invalido(f"posicoes.{i}.cenaId", "a cena foi arquivada; troque ou restaure")


def aprovar(db: Session, actor: Actor, roteiro_id: uuid.UUID, body: schemas.AprovarIn
            ) -> Roteiro:
    r = _editavel(db, roteiro_id, body.version)
    if r.status != estado.AGUARDANDO_DO_PORTAO[body.portao]:
        raise ApiError(409, "portao_fora_de_hora",
                       f"O roteiro não está esperando a aprovação de {body.portao}",
                       details={"status": r.status.value})
    if body.portao == "texto":
        _conferir_texto(db, r)
    if body.portao == "keyframes":
        faltam = [p.ordem for p, c in maquina.cenas_do(db, r) if c.keyframe_inicial_id is None]
        if faltam:
            raise ApiError(409, "keyframes_pendentes",
                           f"Escolha o keyframe da posição {faltam[0] + 1} antes de aprovar",
                           details={"ordem": faltam[0]})
    before = history.snapshot(r)
    _comandar(r, actor)
    r.avisos = [a for a in (r.avisos or []) if a.get("code") != "cena_incompleta"]
    maquina.passar(db, r, actor, body.portao)
    _record(db, actor, r, "updated", before, {"acao": "aprovar", "portao": body.portao})
    maquina.avancar(db, r, actor, humano=True)
    return r


def controle(db: Session, actor: Actor, roteiro_id: uuid.UUID, body: schemas.ControleIn
             ) -> Roteiro:
    """FR-009: ligar um portão para numa etapa futura; desligar o portão em que o roteiro está
    parado (ou ligar o automático) equivale a aprovar, no nome de quem mudou."""
    r = _editavel(db, roteiro_id, body.version)
    before = history.snapshot(r)
    de = {"modo": r.modo.value, "portoes": dict(r.portoes or {})}
    r.modo = body.modo
    r.portoes = body.portoes.model_dump()
    para = {"modo": r.modo.value, "portoes": dict(r.portoes)}
    _comandar(r, actor)
    details: dict[str, Any] = {"acao": "controle", "de": de, "para": para}
    parado = estado.PORTAO_DO_AGUARDANDO.get(r.status)
    if parado is not None and not maquina.gate_ligado(r, parado):
        if parado == "texto":
            _conferir_texto(db, r)
        details["aprovou"] = parado
        maquina.passar(db, r, actor, parado)
    if not _record(db, actor, r, "updated", before, details, sempre=False):
        return r
    maquina.avancar(db, r, actor, humano=True)
    return r


def tentar_de_novo(db: Session, actor: Actor, roteiro_id: uuid.UUID, version: int) -> Roteiro:
    """FR-011: retoma da etapa que falhou, sem refazer as anteriores que continuam atuais."""
    r = _editavel(db, roteiro_id, version)
    if r.status != S.falhou or r.etapa_falhou is None:
        raise ApiError(409, "estado_invalido", "Só um roteiro que falhou pode tentar de novo")
    before = history.snapshot(r)
    erro = {"etapa": r.etapa_falhou.value, "code": r.erro_code, "message": r.erro_message}
    r.status = estado.STATUS_DA_ETAPA[r.etapa_falhou]
    maquina.limpar_falha(r)
    _comandar(r, actor)
    _record(db, actor, r, "updated", before, {"acao": "tentar_de_novo", "erroAnterior": erro})
    maquina.avancar(db, r, actor, humano=True)
    return r


# ---- por posição ----

def _posicao(r: Roteiro, ordem: int) -> RoteiroCena:
    p = next((p for p in r.posicoes_rel if p.ordem == ordem), None)
    if p is None:
        raise ApiError(404, "not_found", "Posição não encontrada")
    return p


def regerar_keyframe(db: Session, actor: Actor, roteiro_id: uuid.UUID, ordem: int,
                     body: schemas.RegerarKeyframeIn) -> Roteiro:
    r = _editavel(db, roteiro_id, body.version)
    if estado.nivel(r.status) < estado.nivel(S.narrando) and r.status != S.falhou:
        raise ApiError(409, "estado_invalido", "Aprove o texto antes dos keyframes")
    p = _posicao(r, ordem)
    cena = cenas_service.get_cena_or_404(db, p.cena_id, lock=True)
    if cena.archived:
        raise ApiError(409, "arquivada", "Restaure a cena antes de regerar")
    if cena.status == CenaStatus.usada and cena.keyframe_inicial_id is not None:
        raise ApiError(409, "cena_usada", cenas_service.CENA_USADA)
    problema = estado.problema_do_avatar(db.get(Asset, cena.avatar_id or r.avatar_id)
                                         if (cena.avatar_id or r.avatar_id) else None)
    if problema:
        raise ApiError(409, *problema)
    mudou = {}
    if body.instrucao is not None and body.instrucao != (cena.keyframe_instrucao or ""):
        mudou["keyframe_instrucao"] = body.instrucao or None
    if body.referencias is not None and list(body.referencias) != list(cena.keyframe_refs or []):
        achadas = set(db.scalars(select(Image.id).where(Image.id.in_(body.referencias))))
        if any(i not in achadas for i in body.referencias):
            raise invalido("referencias", "use imagens da biblioteca")
        mudou["keyframe_refs"] = list(body.referencias)
    if mudou:
        cenas_service.conferir_locais_em_usada(db, cena, set(mudou))
        antes = history.snapshot(cena)
        for campo, valor in mudou.items():
            setattr(cena, campo, valor)
        cenas_service._record(db, actor, cena, "updated", antes,
                              {"acao": "keyframe_instrucao", "roteiroId": str(r.id)})
    for g in estado.abertas(db, "cena.keyframe", alvo_id=cena.id):
        maquina.cancelar(db, actor, g, "Pedido outro keyframe")
    _comandar(r, actor)
    # A escolha da opção nova (humana ou automática) é que muda o keyframe e as etapas depois.
    pedidos.keyframe(db, actor, r, cena, ordem)
    return r


def enviar_keyframe(db: Session, actor: Actor, roteiro_id: uuid.UUID, ordem: int,
                    version: int, data: bytes) -> Roteiro:
    """FR-027: a imagem pronta vira o keyframe sem geração (validada pelo conteúdo, aspecto da
    cena ±1%, normalizada para a resolução da cena com o recorte central)."""
    r = _editavel(db, roteiro_id, version)
    p = _posicao(r, ordem)
    cena = cenas_service.get_cena_or_404(db, p.cena_id, lock=True)
    if len(data) > KEYFRAME_MAX_BYTES:
        raise ApiError(413, "payload_too_large", "Imagem maior que 20 MB")
    info = imaging.validate_image(data, "keyframe", max_bytes=KEYFRAME_MAX_BYTES)
    esperado = cena.largura / cena.altura
    if abs(info.width / info.height - esperado) > esperado * ASPECTO_TOLERANCIA:
        raise ApiError(400, "invalid_image",
                       f"A imagem precisa ter a proporção da cena ({cena.largura}×{cena.altura})",
                       details={"field": "arquivo", "largura": cena.largura,
                                "altura": cena.altura})
    png = aplicadores.ajustar(data, cena.largura, cena.altura)
    final = imaging.validate_image(png, "keyframe", max_bytes=KEYFRAME_MAX_BYTES * 2)
    key = imaging.object_key(r.perfil_id, final.ext)
    storage.put(key, png, final.content_type)
    img = Image(perfil_id=r.perfil_id, kind=ImageKind.keyframe, object_key=key,
                content_type=final.content_type, bytes=final.bytes, width=final.width,
                height=final.height, sha256=final.sha256, created_by=actor.user_id)
    db.add(img)
    db.flush()
    for g in estado.abertas(db, "cena.keyframe", alvo_id=cena.id):
        maquina.cancelar(db, actor, g, "O keyframe foi enviado à mão")
    cenas_service.definir_keyframe(db, actor, cena, img.id,
                                   details={"upload": True, "roteiroId": str(r.id)})
    _comandar(r, actor)
    db.flush()
    maquina.avancar(db, r, actor, humano=True)
    for outro in maquina.roteiros_da_cena(db, cena.id):
        if outro != r.id:
            o = db.get(Roteiro, outro, with_for_update=True)
            maquina.avancar(db, o, pedidos.ator_da_maquina(o))
    return r


def regerar_clipe(db: Session, actor: Actor, roteiro_id: uuid.UUID, ordem: int,
                  body: schemas.RegerarClipeIn) -> Roteiro:
    r = _editavel(db, roteiro_id, body.version)
    p = _posicao(r, ordem)
    cena = cenas_service.get_cena_or_404(db, p.cena_id, lock=True)
    if cena.keyframe_inicial_id is None or cena.status == CenaStatus.rascunho:
        raise ApiError(409, "cena_nao_pronta", "A cena precisa do keyframe aprovado antes do clipe")
    if p.duracao_s is None:
        raise ApiError(409, "estado_invalido", "A cena ainda não tem duração (falta a narração)")
    motor = body.motor.value if body.motor is not None else cena.motor.value
    if body.motor is not None and body.motor != cena.motor and cena.status != CenaStatus.usada:
        antes = history.snapshot(cena)
        cena.motor = body.motor
        cenas_service._record(db, actor, cena, "updated", antes,
                              {"acao": "motor", "roteiroId": str(r.id)})
    problema = estado.problema_do_avatar(db.get(Asset, cena.avatar_id or r.avatar_id)
                                         if (cena.avatar_id or r.avatar_id) else None)
    if problema:
        raise ApiError(409, *problema)
    if float(p.duracao_s) > pedidos.duracao_max(cena) and body.motor is None:
        raise ApiError(409, "tomada_longa", "A cena passa da duração máxima do motor")
    for g in estado.abertas(db, "cena.clipe", alvo_id=cena.id):
        maquina.cancelar(db, actor, g, "Pedido outro clipe")
    before = history.snapshot(r)
    p.tomada_id = None
    _comandar(r, actor)
    g = pedidos.clipe(db, actor, r, cena, ordem, p.duracao_s, motor)
    g.params = {**g.params, "extras": {**estado.extras(g), "regerar": True}}
    _record(db, actor, r, "updated", before, {"acao": "regerar_clipe", "ordem": ordem,
                                              "motor": motor, "geracaoId": str(g.id)})
    maquina.avancar(db, r, actor, humano=True)
    return r


def escolher_tomada(db: Session, actor: Actor, roteiro_id: uuid.UUID, ordem: int,
                    body: schemas.EscolherTomadaIn) -> Roteiro:
    r = _editavel(db, roteiro_id, body.version)
    p = _posicao(r, ordem)
    cena = db.get(Cena, p.cena_id)
    t = db.get(CenaTomada, body.tomada_id)
    if t is None or t.cena_id != cena.id:
        raise invalido("tomadaId", "a tomada precisa ser desta cena")
    if t.archived or t.limpa_em is not None:
        raise ApiError(409, "arquivada", "A tomada está arquivada ou sem o arquivo")
    if t.origem == TomadaOrigem.geracao_local and t.keyframe_image_id != cena.keyframe_inicial_id:
        raise ApiError(409, "keyframe_antigo", "A tomada é de um keyframe antigo da cena")
    if p.duracao_s is not None and t.duracao_ms < round(float(p.duracao_s) * 1000):
        raise ApiError(400, "tomada_curta", "A tomada é mais curta que a cena",
                       details={"field": "tomadaId"})
    before = history.snapshot(r)
    maquina._definir_tomada(db, p, t)
    p.aviso = None
    _comandar(r, actor)
    _record(db, actor, r, "updated", before, {"acao": "escolher_tomada", "ordem": ordem,
                                              "tomadaId": str(t.id)})
    maquina.avancar(db, r, actor, humano=True)
    return r


# ---- leituras ----

def _link(kind: midia.MidiaKind, entity_id: uuid.UUID) -> str:
    return midia.link(kind, entity_id, ttl=get_settings().midia_link_ttl_s).url


def _geracao_aberta(g: Geracao) -> schemas.GeracaoAberta:
    return schemas.GeracaoAberta(id=g.id, passo=g.passo, status=g.status.value,
                                 progress=g.progress, etapa_mensagem=g.etapa_mensagem)


def _cena_out(db: Session, c: Cena) -> schemas.CenaRoteiro:
    img = db.get(Image, c.keyframe_inicial_id) if c.keyframe_inicial_id else None
    return schemas.CenaRoteiro(
        id=c.id, nome=c.nome, status=c.status, motor=c.motor, largura=c.largura,
        altura=c.altura, arquivada=c.archived, perfil_id=c.perfil_id,
        keyframe_image_id=c.keyframe_inicial_id,
        keyframe_url=imaging.image_urls(img.object_key)["medium"] if img else None,
        keyframe_geracao_id=c.keyframe_geracao_id, keyframe_instrucao=c.keyframe_instrucao,
        keyframe_refs=cenas_service.locais_out(db, c)["keyframe_refs"], version=c.version)


def _tomada_out(t: CenaTomada, cena: Cena) -> schemas.TomadaRoteiro:
    return schemas.TomadaRoteiro(
        id=t.id, origem=t.origem, motor=t.motor, duracao_ms=t.duracao_ms,
        video_url=_link("cena_tomada", t.id) if t.video_key else None,
        miniatura_url=imaging.image_urls(t.miniatura_key)["thumb"] if t.miniatura_key else None,
        keyframe_antigo=cenas_service.keyframe_antigo(t, cena), limpa=t.limpa_em is not None)


def _previa_out(db: Session, gid: uuid.UUID | None, assinatura: str) -> schemas.PreviaOut | None:
    g = db.get(Geracao, gid) if gid else None
    if g is None:
        return None
    cand = db.get(GeracaoCandidato, g.escolhido_id) if g.escolhido_id else None
    return schemas.PreviaOut(
        geracao_id=g.id,
        video_url=_link("geracao_video", cand.id) if cand and cand.video_key else None,
        duracao_ms=cand.video_duracao_ms if cand else None,
        atual=estado.extras(g).get("assinatura") == assinatura)


def detalhe_out(db: Session, r: Roteiro) -> schemas.RoteiroDetalhe:
    db.flush()
    db.refresh(r)
    perfil = db.get(Perfil, r.perfil_id)
    avatar = db.get(Asset, r.avatar_id) if r.avatar_id else None
    voz = db.get(Voz, r.voz_id) if r.voz_id else None
    produtos = []
    for rp in sorted(r.produtos_rel, key=lambda p: p.ordem):
        prod = db.get(Produto, rp.produto_id)
        v = prod.variante(rp.produto_variante_id) if rp.produto_variante_id else None
        produtos.append(schemas.ProdutoRoteiro(
            produto_id=prod.id, nome_comercial=prod.nome_comercial, nome=prod.name,
            variante_id=rp.produto_variante_id, cor=v.cor_pt if v else None,
            aprovado=prod.status == ProdutoStatus.aprovado and not prod.archived))
    criadas_aqui = {uuid.UUID(c) for c in _cenas_criadas_pelo_plano(db, r)}
    posicoes = []
    for p in estado.posicoes(r):
        c = db.get(Cena, p.cena_id)
        t = db.get(CenaTomada, p.tomada_id) if p.tomada_id else None
        abertas = [g for passo in ("cena.keyframe", "cena.clipe")
                   for g in estado.abertas(db, passo, alvo_id=c.id)]
        posicoes.append(schemas.PosicaoOut(
            ordem=p.ordem, cena=_cena_out(db, c), frases=list(p.frases),
            inicio_s=float(p.inicio_s) if p.inicio_s is not None else None,
            duracao_s=float(p.duracao_s) if p.duracao_s is not None else None,
            tomada=_tomada_out(t, c) if t else None, aviso=p.aviso,
            reaproveitada=c.id not in criadas_aqui,
            geracoes_abertas=[_geracao_aberta(g) for g in abertas]))
    n = estado.narracao_ativa(db, r)
    narracao = None
    if n is not None:
        narracao = schemas.NarracaoOut(
            id=n.id, audio_url=_link("audio", n.audio_id) if n.audio_id else None,
            tempos=[schemas.TempoFrase(**t) for t in n.tempos or []], total_s=float(n.total_s),
            similaridade=float(n.similaridade), velocidade=float(n.velocidade), voz_id=n.voz_id,
            desatualizada=not estado.narracao_atual(db, r), limpa=n.limpa_em is not None,
            created_at=n.created_at)
    anteriores = db.scalar(select(func.count()).select_from(RoteiroNarracao).where(
        RoteiroNarracao.roteiro_id == r.id, RoteiroNarracao.id != r.narracao_id
        if r.narracao_id else True)) or 0
    assinatura = estado.assinatura(r)
    abertas_roteiro = [g for passo in ("roteiro.plano", "roteiro.narracao", "roteiro.montagem",
                                       "roteiro.acabamento")
                       for g in estado.abertas(db, passo, alvo_id=r.id)]
    return schemas.RoteiroDetalhe(
        id=r.id, perfil_id=r.perfil_id, perfil_nome=perfil.name if perfil else None,
        nome=r.nome, brief=r.brief,
        avatar=schemas.AvatarRef(id=avatar.id, nome=avatar.name,
                                 kit_status=avatar.kit_status.value if avatar.kit_status
                                 else None, revogado=avatar.revogado) if avatar else None,
        voz=schemas.VozRef(id=voz.id, nome=voz.name, origem=voz.origem.value,
                           revogada=voz.revogada) if voz else None,
        formato=r.formato, frases=list(r.frases), velocidade=float(r.velocidade), modo=r.modo,
        portoes=schemas.portoes_de(r.portoes), status=r.status, etapa_falhou=r.etapa_falhou,
        erro=schemas.ErroRoteiro(code=r.erro_code, message=r.erro_message or "")
        if r.erro_code else None,
        avisos=[schemas.AvisoRoteiro(**a) for a in r.avisos or []], produtos=produtos,
        posicoes=posicoes, narracao=narracao, narracoes_anteriores=anteriores,
        previa=_previa_out(db, r.montagem_geracao_id, assinatura),
        acabamento=_previa_out(db, r.acabamento_geracao_id, assinatura),
        conteudo_id=r.conteudo_id,
        geracoes_abertas=[_geracao_aberta(g) for g in abertas_roteiro],
        max_cenas=get_settings().roteiro_max_cenas, arquivado=r.archived, version=r.version,
        created_at=r.created_at, updated_at=r.updated_at)


def _cenas_criadas_pelo_plano(db: Session, r: Roteiro) -> list[str]:
    rows = db.scalars(select(history.EntityVersion.entity_id).where(
        history.EntityVersion.entity_type == "cena", history.EntityVersion.version == 1,
        history.EntityVersion.details["roteiroId"].astext == str(r.id)))
    return [str(i) for i in rows]


def detalhe(db: Session, roteiro_id: uuid.UUID) -> schemas.RoteiroDetalhe:
    return detalhe_out(db, get_or_404(db, roteiro_id))


def versoes(db: Session, roteiro_id: uuid.UUID) -> VersionsList:
    get_or_404(db, roteiro_id)
    return versions_out(db, ENTITY, roteiro_id)


def _cursor(updated_at: datetime, rid: uuid.UUID) -> str:
    raw = json.dumps([updated_at.isoformat(), str(rid)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _ler_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        ts, rid = json.loads(raw)
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except (ValueError, TypeError) as exc:
        raise ApiError(400, "validation_error", "cursor inválido") from exc


def listar(db: Session, perfil_id: uuid.UUID | None, *, status: list[Any] | None = None,
           produto_id: uuid.UUID | None = None, arquivados: bool = False, q: str | None = None,
           cursor: str | None = None, limite: int = LIMITE_PADRAO) -> schemas.RoteirosPagina:
    stmt = select(Roteiro)
    if perfil_id is not None:
        get_perfil_or_404(db, perfil_id)
        stmt = stmt.where(Roteiro.perfil_id == perfil_id)
    stmt = stmt.where(Roteiro.archived_at.is_not(None) if arquivados
                      else Roteiro.archived_at.is_(None))
    if status:
        stmt = stmt.where(Roteiro.status.in_(status))
    if produto_id is not None:
        stmt = stmt.where(Roteiro.id.in_(select(RoteiroProduto.roteiro_id).where(
            RoteiroProduto.produto_id == produto_id)))
    if q:
        termo = f"%{q.strip()}%"
        stmt = stmt.where(or_(Roteiro.nome.ilike(termo), Roteiro.brief.ilike(termo)))
    if cursor:
        ts, rid = _ler_cursor(cursor)
        stmt = stmt.where(tuple_(Roteiro.updated_at, Roteiro.id) < tuple_(ts, rid))
    limite = max(1, min(limite, LIMITE_MAX))
    rows = list(db.scalars(stmt.order_by(Roteiro.updated_at.desc(), Roteiro.id.desc())
                           .limit(limite + 1)))
    proximo = _cursor(rows[limite - 1].updated_at, rows[limite - 1].id) if len(rows) > limite \
        else None
    rows = rows[:limite]
    nomes = dict(db.execute(select(Perfil.id, Perfil.name).where(
        Perfil.id.in_({r.perfil_id for r in rows}))).all()) if rows else {}
    itens = []
    for r in rows:
        produtos = [db.get(Produto, p.produto_id) for p in sorted(r.produtos_rel,
                                                                  key=lambda p: p.ordem)]
        mini = None
        for p in estado.posicoes(r):
            c = db.get(Cena, p.cena_id)
            img = db.get(Image, c.keyframe_inicial_id) if c and c.keyframe_inicial_id else None
            if img is not None:
                mini = imaging.image_urls(img.object_key)["thumb"]
                break
        itens.append(schemas.RoteiroResumo(
            id=r.id, perfil_id=r.perfil_id, perfil_nome=nomes.get(r.perfil_id), nome=r.nome,
            status=r.status, etapa_falhou=r.etapa_falhou,
            produtos=[p.nome_comercial or p.name for p in produtos if p is not None],
            cenas=len(r.posicoes_rel), miniatura_url=mini, arquivado=r.archived,
            conteudo_id=r.conteudo_id, updated_at=r.updated_at))
    return schemas.RoteirosPagina(itens=itens, proximo=proximo)

