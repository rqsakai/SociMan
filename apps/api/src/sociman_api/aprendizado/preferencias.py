"""Preferências do perfil e da conta e as decisões do dono (spec 023, US3; FR-036 a FR-039;
research R6 e R7).

- **Linha:** uma do perfil (`conta_id IS NULL`) e no máximo uma por conta; sem linha = `version
  0`. A do perfil guarda também `taxonomia_versao` (sobe a cada mudança de tema),
  `classificacao_auto`, `usar_desempenho` e `pedido_classificacao_em` (contadores técnicos, fora
  do snapshot);
- **Efetivas:** perfil + conta; a conta vence no mesmo tema, e as listas somam sem repetir;
- **Decidir:** o servidor recalcula a recomendação da chave (409 `recomendacao_mudou` se ela não
  existe mais), grava a decisão e, no aceite, a nova versão das preferências. "Fixar hashtag"
  grava no guia da 017 (máximo de fixas e proibidas valem; `details.origem =
  "recomendacao_023"`);
- **Reverter a decisão:** desfaz a preferência criada pelo aceite; a fixa sai pelo revert do guia
  (a tela avisa).

Nada aqui agenda, aprova, publica ou muda conteúdo (FR-039).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import schemas
from sociman_api.aprendizado.models import Decisao, DecisaoEstado, Preferencias, Tema
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.perfis.schemas import RevertIn, VersionsList
from sociman_api.perfis.service_perfis import (
    get_perfil_or_404,
    target_state,
    user_refs,
    versions_out,
)
from sociman_api.postagem import textos

ENTITY = "aprendizado_preferencias"
ENTITY_DECISAO = "aprendizado_decisao"
LABEL = "Estas preferências"
LABEL_DECISAO = "Esta decisão"
ORIGEM_GUIA = "recomendacao_023"


# ---- linha ----

def linha(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
          lock: bool = False) -> Preferencias | None:
    stmt = select(Preferencias)
    if conta_id is None:
        stmt = stmt.where(Preferencias.perfil_id == perfil_id, Preferencias.conta_id.is_(None))
    else:
        stmt = stmt.where(Preferencias.conta_id == conta_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _criar(db: Session, actor: Actor, perfil_id: uuid.UUID,
           conta_id: uuid.UUID | None) -> Preferencias:
    row = Preferencias(perfil_id=perfil_id, conta_id=conta_id, created_by=actor.user_id,
                       updated_by=actor.user_id)
    db.add(row)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:  # outra transação criou a linha ao mesmo tempo
        existente = linha(db, perfil_id, conta_id, lock=True)
        assert existente is not None
        return existente
    history.record(db, actor, ENTITY, row, "created", None, history.snapshot(row))
    return row


def travar_perfil(db: Session, actor: Actor, perfil_id: uuid.UUID) -> Preferencias:
    """A linha do perfil travada (criada, com histórico, na 1ª mudança de tema)."""
    return linha(db, perfil_id, None, lock=True) or _criar(db, actor, perfil_id, None)


def taxonomia_versao(db: Session, perfil_id: uuid.UUID) -> int:
    row = linha(db, perfil_id, None)
    return row.taxonomia_versao if row is not None else 0


def incrementar_taxonomia(db: Session, actor: Actor, perfil_id: uuid.UUID) -> int:
    row = travar_perfil(db, actor, perfil_id)
    row.taxonomia_versao += 1
    return row.taxonomia_versao


# ---- leitura ----

@dataclass(frozen=True)
class Efetivas:
    temas: dict[str, str]
    hashtags_evitar: tuple[str, ...]
    padroes: tuple[dict[str, Any], ...]
    usar_desempenho: bool
    classificacao_auto: bool
    perfil_version: int
    conta_version: int

    @property
    def cortados(self) -> set[str]:
        return {t for t, v in self.temas.items() if v == "cortar"}

    @property
    def ampliados(self) -> set[str]:
        return {t for t, v in self.temas.items() if v == "ampliar"}

    @property
    def vazias(self) -> bool:
        return not (self.temas or self.hashtags_evitar or self.padroes)


def _unir(*listas: Sequence[Any], chave=lambda x: x) -> tuple:
    vistos: dict[Any, Any] = {}
    for lista in listas:
        for item in lista:
            vistos.setdefault(chave(item), item)
    return tuple(vistos.values())


def efetivas(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None = None) -> Efetivas:
    """Só leitura (o Descobrir, o Mercado e o assistente importam esta função)."""
    p = linha(db, perfil_id, None)
    c = linha(db, perfil_id, conta_id) if conta_id is not None else None
    temas = {**(p.temas if p else {}), **(c.temas if c else {})}
    return Efetivas(
        temas=temas,
        hashtags_evitar=_unir(p.hashtags_evitar if p else (), c.hashtags_evitar if c else ()),
        padroes=_unir(p.padroes if p else (), c.padroes if c else (),
                      chave=lambda x: (x.get("tipo"), x.get("texto"))),
        usar_desempenho=p.usar_desempenho if p else True,
        classificacao_auto=p.classificacao_auto if p else True,
        perfil_version=p.version if p else 0, conta_version=c.version if c else 0)


def janela_preferida(ef: Efetivas) -> str | None:
    """A dica do agendamento: o 1º padrão de horário aceito (só leitura, FR-039)."""
    return next((x["texto"] for x in ef.padroes if x.get("tipo") == "horario"), None)


def out(row: Preferencias | None, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
        perfil_row: Preferencias | None = None) -> schemas.AprendizadoPreferencias:
    base = perfil_row if conta_id is not None else row
    return schemas.AprendizadoPreferencias(
        id=row.id if row else None, perfil_id=perfil_id, conta_id=conta_id,
        temas=dict(row.temas) if row else {},
        hashtags_evitar=list(row.hashtags_evitar) if row else [],
        padroes=[schemas.AprendizadoPadrao(**x) for x in (row.padroes if row else [])],
        classificacao_auto=base.classificacao_auto if base else True,
        usar_desempenho=base.usar_desempenho if base else True,
        taxonomia_versao=base.taxonomia_versao if base else 0,
        version=row.version if row else 0)


def _conta(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None) -> Conta | None:
    if conta_id is None:
        return None
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    if conta.perfil_id != perfil_id:
        raise ApiError(400, "conta_fora_do_perfil", "A conta não é do perfil escolhido")
    return conta


def obter(db: Session, perfil_id: uuid.UUID,
          conta_id: uuid.UUID | None) -> schemas.AprendizadoPreferenciasOut:
    get_perfil_or_404(db, perfil_id)
    _conta(db, perfil_id, conta_id)
    p = linha(db, perfil_id, None)
    c = linha(db, perfil_id, conta_id) if conta_id is not None else None
    ef = efetivas(db, perfil_id, conta_id)
    return schemas.AprendizadoPreferenciasOut(
        perfil=out(p, perfil_id, None),
        conta=out(c, perfil_id, conta_id, p) if conta_id is not None else None,
        efetivas=schemas.AprendizadoPreferenciasEfetivas(
            temas=dict(ef.temas), hashtags_evitar=list(ef.hashtags_evitar),  # type: ignore[arg-type]
            padroes=[schemas.AprendizadoPadrao(**x) for x in ef.padroes],
            usar_desempenho=ef.usar_desempenho, janela_preferida=janela_preferida(ef)))


# ---- escrita direta (PATCH, revert) ----

def _temas_validos(db: Session, perfil_id: uuid.UUID, temas: dict[str, str]) -> dict[str, str]:
    ids = []
    for t in temas:
        try:
            ids.append(uuid.UUID(t))
        except ValueError as exc:
            raise ApiError(400, "tema_invalido", "Tema inválido nas preferências") from exc
    if ids:
        validos = set(db.scalars(select(Tema.id).where(Tema.id.in_(ids),
                                                       Tema.perfil_id == perfil_id)))
        if len(validos) != len(set(ids)):
            raise ApiError(400, "tema_invalido", "Um tema das preferências não é do perfil")
    return {str(uuid.UUID(k)): v for k, v in temas.items()}


def hashtags_normalizadas(brutas: Sequence[str]) -> list[str]:
    out: list[str] = []
    for b in brutas:
        tag = textos.normalizar_hashtag(b)
        if tag is not None and tag not in out:
            out.append(tag)
    return out


def _gravar(db: Session, actor: Actor, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
            version: int | None, mudar, action: str = "updated",
            details: dict[str, Any] | None = None) -> Preferencias:
    """Trava (ou cria), confere a versão, aplica `mudar(row)` e grava a versão se mudou."""
    row = linha(db, perfil_id, conta_id, lock=True)
    if row is None:
        if version not in (None, 0):
            raise ApiError(409, "version_conflict",
                           f"{LABEL} foram alteradas por outra pessoa; recarregue",
                           details={"versaoAtual": 0})
        row = _criar(db, actor, perfil_id, conta_id)
    elif version is not None and row.version != version:
        raise ApiError(409, "version_conflict",
                       f"{LABEL} foram alteradas por outra pessoa; recarregue",
                       details={"versaoAtual": row.version})
    before = history.snapshot(row)
    mudar(row)
    after = history.snapshot(row)
    if after != before:
        row.updated_by = actor.user_id
        history.record(db, actor, ENTITY, row, action, before, after, details)
    db.flush()
    return row


def patch(db: Session, actor: Actor, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
          body: schemas.AprendizadoPreferenciasPatch) -> schemas.AprendizadoPreferencias:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "conflict", "Este perfil está arquivado")
    _conta(db, perfil_id, conta_id)
    if conta_id is not None and (body.classificacao_auto is not None
                                 or body.usar_desempenho is not None):
        raise ApiError(400, "validation_error",
                       "Classificação automática e desempenho no assistente são do perfil")
    temas = _temas_validos(db, perfil_id, body.temas) if body.temas is not None else None

    def mudar(row: Preferencias) -> None:
        if temas is not None:
            row.temas = temas
        if body.hashtags_evitar is not None:
            row.hashtags_evitar = hashtags_normalizadas(body.hashtags_evitar)
        if body.padroes is not None:
            row.padroes = [x.model_dump(mode="json") for x in body.padroes]
        if body.classificacao_auto is not None:
            row.classificacao_auto = body.classificacao_auto
        if body.usar_desempenho is not None:
            row.usar_desempenho = body.usar_desempenho

    row = _gravar(db, actor, perfil_id, conta_id, body.version, mudar)
    return out(row, perfil_id, conta_id, linha(db, perfil_id, None))


def versions(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None) -> VersionsList:
    get_perfil_or_404(db, perfil_id)
    _conta(db, perfil_id, conta_id)
    row = linha(db, perfil_id, conta_id)
    return versions_out(db, ENTITY, row.id) if row is not None else VersionsList(items=[])


def reverter(db: Session, actor: Actor, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
             body: RevertIn) -> schemas.AprendizadoPreferencias:
    get_perfil_or_404(db, perfil_id)
    _conta(db, perfil_id, conta_id)
    row = linha(db, perfil_id, conta_id, lock=True)
    if row is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    history.check_version(row, body.version, LABEL)
    state = target_state(db, ENTITY, row, body.to_version)  # type: ignore[arg-type]

    def mudar(r: Preferencias) -> None:
        r.temas = dict(state.get("temas") or {})
        r.hashtags_evitar = list(state.get("hashtags_evitar") or [])
        r.padroes = list(state.get("padroes") or [])
        r.classificacao_auto = state.get("classificacao_auto", True)
        r.usar_desempenho = state.get("usar_desempenho", True)

    row = _gravar(db, actor, perfil_id, conta_id, body.version, mudar, "reverted",
                  {"from_version": body.to_version})
    return out(row, perfil_id, conta_id, linha(db, perfil_id, None))


# ---- decisões ----

def decisao_out(db: Session, d: Decisao, superada: bool = False) -> schemas.AprendizadoDecisao:
    users = user_refs(db, [d.decidido_por])
    return schemas.AprendizadoDecisao(
        id=d.id, chave=d.chave, tipo=d.tipo,  # type: ignore[arg-type]
        escopo=schemas.AprendizadoEscopo(tipo="conta" if d.conta_id else "perfil",
                                         conta_id=d.conta_id),
        estado=d.estado.value, origem=d.origem, analise_id=d.analise_id,  # type: ignore[arg-type]
        evidencia=d.evidencia, texto=d.texto, motivo=d.motivo,
        decidido_por=users.get(d.decidido_por) if d.decidido_por else None,
        decidido_em=d.decidido_em, revertida_em=d.revertida_em, superada=superada,
        version=d.version)


def _aplicar(row: Preferencias, tipo: str, alvo: schemas.AprendizadoAlvo, texto: str | None,
             valor: Any) -> None:
    if tipo in ("tema_ampliar", "tema_cortar"):
        row.temas = {**row.temas, str(alvo.tema_id): tipo.removeprefix("tema_")}
    elif tipo == "hashtag_evitar":
        if alvo.hashtag not in row.hashtags_evitar:
            if len(row.hashtags_evitar) >= K.EVITAR_MAX_ITENS:
                raise ApiError(409, "evitar_no_maximo",
                               f"Já são {K.EVITAR_MAX_ITENS} hashtags a evitar; tire alguma antes")
            row.hashtags_evitar = [*row.hashtags_evitar, alvo.hashtag]
    elif tipo.startswith("padrao_"):
        novo = {"tipo": tipo.removeprefix("padrao_"), "texto": texto, "valor": valor}
        if not any(p.get("tipo") == novo["tipo"] and p.get("texto") == texto
                   for p in row.padroes):
            if len(row.padroes) >= K.PADROES_MAX:
                raise ApiError(409, "padroes_no_maximo",
                               f"Já são {K.PADROES_MAX} padrões; tire algum antes")
            row.padroes = [*row.padroes, novo]


def _desfazer(row: Preferencias, d: Decisao) -> None:
    alvo = d.evidencia.get("alvo") or {}
    if d.tipo in ("tema_ampliar", "tema_cortar"):
        tema = str(alvo.get("temaId"))
        if row.temas.get(tema) == d.tipo.removeprefix("tema_"):
            row.temas = {k: v for k, v in row.temas.items() if k != tema}
    elif d.tipo == "hashtag_evitar":
        row.hashtags_evitar = [h for h in row.hashtags_evitar if h != alvo.get("hashtag")]
    elif d.tipo.startswith("padrao_"):
        row.padroes = [p for p in row.padroes if not (
            p.get("tipo") == d.tipo.removeprefix("padrao_") and p.get("texto") == d.texto)]


def _fixar(db: Session, actor: Actor, perfil: Perfil, conta_id: uuid.UUID | None, hashtag: str,
           substituir: str | None, chave: str) -> schemas.AprendizadoGuiaRef:
    """"Fixar hashtag" no guia da 017 (da conta, ou do perfil no escopo perfil)."""
    from sociman_api.ia import guia, service_guia
    from sociman_api.ia.models import IaGuia

    conta = db.get(Conta, conta_id) if conta_id is not None else None
    tag = textos.normalizar_hashtag(hashtag)
    if tag is None:
        raise ApiError(400, "validation_error", "Hashtag inválida")
    row = guia.linha(db, perfil.id, conta_id, lock=True)
    atual = guia.GuiaCampos.de_linha(row) if row is not None else guia.GuiaCampos()
    perfil_row = guia.linha(db, perfil.id, None) if conta_id is not None else None
    perfil_campos = guia.GuiaCampos.de_linha(perfil_row) if perfil_row is not None else None
    efetivo = guia.fundir(perfil_campos, atual) if conta_id is not None else guia.fundir(atual,
                                                                                        None)
    nivel = "conta" if conta_id is not None else "perfil"
    if guia.achar_proibidas([tag], efetivo.proibidas):
        raise ApiError(400, "ia_proibida", f"{tag} é uma palavra proibida pelo guia")
    if tag in efetivo.hashtags_fixas:
        return schemas.AprendizadoGuiaRef(nivel=nivel, version=row.version if row else 0)
    fixas = list(atual.hashtags_fixas)
    if substituir:
        sub = textos.normalizar_hashtag(substituir)
        if sub not in fixas:
            raise ApiError(400, "validation_error",
                           f"{substituir} não é uma hashtag fixa deste guia")
        fixas = [f for f in fixas if f != sub]
    fixas.append(tag)
    novo = replace(atual, hashtags_fixas=tuple(fixas))
    if conta_id is None:
        excede = len(fixas) > guia.FIXAS_PERFIL_MAX
        maximo = guia.FIXAS_PERFIL_MAX
    else:
        maximo = guia.maximo_fixas(novo)
        excede = len(guia.fixas_somadas(perfil_campos, novo)) > maximo
    if excede:
        raise ApiError(409, "fixas_no_maximo",
                       f"O guia já tem o máximo de hashtags fixas ({maximo}); escolha uma para "
                       "trocar", details={"fixas": list(efetivo.hashtags_fixas),
                                          "maximo": maximo})
    if conta is not None and conta.archived:
        raise ApiError(409, "conflict", "Esta conta está arquivada")
    limpos = service_guia.validar_campos(db, perfil, conta, novo)
    details = {"origem": ORIGEM_GUIA, "chave": chave}
    if row is None:
        row = IaGuia(perfil_id=perfil.id, conta_id=conta_id, created_by=actor.user_id,
                     updated_by=actor.user_id)
        service_guia._aplicar(row, limpos)
        db.add(row)
        db.flush()
        history.record(db, actor, service_guia.ENTITY, row, "created", None,
                       history.snapshot(row), details)
    else:
        before = history.snapshot(row)
        service_guia._aplicar(row, limpos)
        row.updated_by = actor.user_id
        history.record(db, actor, service_guia.ENTITY, row, "updated", before,
                       history.snapshot(row), details)
    db.flush()
    return schemas.AprendizadoGuiaRef(nivel=nivel, version=row.version)


def _decisao_aberta(db: Session, perfil_id: uuid.UUID, chave: str) -> Decisao | None:
    return db.scalar(select(Decisao).where(
        Decisao.perfil_id == perfil_id, Decisao.chave == chave,
        Decisao.estado == DecisaoEstado.aberta).with_for_update())


def decidir(db: Session, actor: Actor, perfil_id: uuid.UUID,
            body: schemas.AprendizadoDecidirIn) -> schemas.AprendizadoDecidirOut:
    from sociman_api.aprendizado import recomendacoes  # import tardio (ciclo)

    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "conflict", "Este perfil está arquivado")
    agora = datetime.now(UTC)
    aberta = _decisao_aberta(db, perfil_id, body.chave)
    if aberta is not None:
        rec = recomendacoes.da_hipotese(aberta)
    else:
        abertas = recomendacoes.calcular(db, perfil_id, body.conta_id, body.medida).abertas
        rec = next((r for r in abertas if r.chave == body.chave and r.origem == "regra"), None)
        if rec is None:
            raise ApiError(409, "recomendacao_mudou",
                           "A recomendação mudou com os dados novos; recarregue a lista")
    conta_id = rec.escopo.conta_id
    evidencia = {"alvo": rec.alvo.model_dump(mode="json", by_alias=True),
                 "efeito": rec.evidencia.model_dump(mode="json", by_alias=True)
                 if rec.evidencia else None,
                 "taxonomiaVersao": taxonomia_versao(db, perfil_id), "motivo": rec.motivo}
    if aberta is not None:
        d = aberta
        before = history.snapshot(d)
        d.evidencia = {**d.evidencia, **{k: v for k, v in evidencia.items() if k != "efeito"}}
    else:
        n = rec.evidencia.n_posts if rec.evidencia else 0
        faixa = rec.evidencia.confianca if rec.evidencia else "indicio"
        d = Decisao(perfil_id=perfil_id, conta_id=conta_id, chave=rec.chave, tipo=rec.tipo,
                    origem="regra", estado=DecisaoEstado.aceita, evidencia=evidencia,
                    n_decisao=n, faixa_decisao=faixa, texto=rec.alvo.padrao
                    if rec.tipo.startswith("padrao_") else None,
                    created_by=actor.user_id, updated_by=actor.user_id)
        before = None
    d.estado = DecisaoEstado(body.decisao)
    d.motivo = body.motivo or None if body.decisao == "rejeitada" else None
    d.decidido_por, d.decidido_em = actor.user_id, agora
    d.updated_by = actor.user_id

    prefs_out = guia_ref = None
    if body.decisao == "aceita":
        if rec.tipo == "hashtag_fixar":
            guia_ref = _fixar(db, actor, perfil, conta_id, rec.alvo.hashtag or "",
                              body.substituir, rec.chave)
        else:
            valor = (rec.evidencia.valor if rec.evidencia else None)
            row = _gravar(db, actor, perfil_id, conta_id, None,
                          lambda r: _aplicar(r, rec.tipo, rec.alvo, d.texto, valor),
                          details={"decisao": rec.chave})
            d.preferencias_version = row.version
            prefs_out = out(row, perfil_id, conta_id, linha(db, perfil_id, None))
    if before is None:
        db.add(d)
        db.flush()
        history.record(db, actor, ENTITY_DECISAO, d, "created", None, history.snapshot(d),
                       {"chave": d.chave})
    else:
        history.record(db, actor, ENTITY_DECISAO, d, "updated", before, history.snapshot(d),
                       {"chave": d.chave})
    db.flush()
    return schemas.AprendizadoDecidirOut(decisao=decisao_out(db, d), preferencias=prefs_out,
                                         guia=guia_ref)


def reverter_decisao(db: Session, actor: Actor, decisao_id: uuid.UUID,
                     body: schemas.AprendizadoVersionIn) -> schemas.AprendizadoRevertOut:
    d = db.get(Decisao, decisao_id, with_for_update=True)
    if d is None:
        raise ApiError(404, "not_found", "Decisão não encontrada")
    history.check_version(d, body.version, LABEL_DECISAO)
    if d.estado == DecisaoEstado.aberta or d.revertida:
        raise ApiError(409, "conflict", "Só uma decisão tomada e ainda não revertida volta")
    before = history.snapshot(d)
    d.revertida_em, d.revertida_por = datetime.now(UTC), actor.user_id
    d.updated_by = actor.user_id
    prefs_out = aviso = link = None
    if d.estado == DecisaoEstado.aceita and d.tipo == "hashtag_fixar":
        alvo = d.evidencia.get("alvo") or {}
        aviso = (f"A hashtag {alvo.get('hashtag')} continua fixa no guia; tire pelo histórico do "
                 "guia, se quiser.")
        link = (f"/app/contas/{d.conta_id}/guia" if d.conta_id
                else f"/app/perfis/{d.perfil_id}?aba=guia")
    elif d.estado == DecisaoEstado.aceita:
        row = _gravar(db, actor, d.perfil_id, d.conta_id, None, lambda r: _desfazer(r, d),
                      details={"reverteDecisao": str(d.id)})
        prefs_out = out(row, d.perfil_id, d.conta_id, linha(db, d.perfil_id, None))
    history.record(db, actor, ENTITY_DECISAO, d, "reverted", before, history.snapshot(d),
                   {"chave": d.chave})
    db.flush()
    return schemas.AprendizadoRevertOut(decisao=decisao_out(db, d), preferencias=prefs_out,
                                        aviso=aviso, link_guia=link)
