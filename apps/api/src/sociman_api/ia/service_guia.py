"""Guia de comunicação do perfil e da conta (spec 017, US1; data-model "Validação no save" e
"Histórico"; research R11 e R12).

A linha nasce na primeira edição (sem linha = `version 0`, campos vazios); não há DELETE nem
arquivamento ("limpar" é salvar vazio). Toda mutação trava a linha, faz `check_version` e grava
a versão em `entity_versions` (`entity_type = "ia_guia"`) na mesma transação, com o autor.
Salvar igual ao atual não cria versão. O `perfil_id` do guia da conta vem sempre da conta
carregada, nunca do cliente. Só o dono muda (as rotas usam `RequireOwner`); conta ou perfil
arquivado → 409. Nenhum texto do guia vai para log.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.ia import aplicacao, guia
from sociman_api.ia import schemas_guia as schemas
from sociman_api.ia.aplicacao import IaAplicacao
from sociman_api.ia.contexto import plataforma_label
from sociman_api.ia.models import GuiaEmojis, IaGuia
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.perfis.schemas import RevertIn, VersionsList
from sociman_api.perfis.service_contas import get_conta
from sociman_api.perfis.service_perfis import (
    get_perfil_or_404,
    target_state,
    user_refs,
    versions_out,
)

ENTITY = "ia_guia"
LABEL = "Este guia"
ROTULO_CAMPO = {"tom": "no tom", "faca": "no \"faça\"", "naoFaca": "no \"não faça\"",
                "vocabulario": "no vocabulário", "hashtagsFixas": "nas hashtags fixas",
                "exemplos": "nos exemplos"}


# ---- auxiliares ----

def _conflito_versao() -> ApiError:
    return ApiError(409, "version_conflict", f"{LABEL} foi alterado por outra pessoa; recarregue")


def _checar_ativos(perfil: Perfil, conta: Conta | None) -> None:
    if conta is not None and conta.archived:
        raise ApiError(409, "conflict", "Esta conta está arquivada")
    if perfil.archived:
        raise ApiError(409, "conflict", "Este perfil está arquivado")


def rotulo_conta(conta: Conta) -> str:
    return f"{plataforma_label(conta.platform, conta.platform_name)} @{conta.handle}"


def _campos(row: IaGuia | None) -> guia.GuiaCampos | None:
    return guia.GuiaCampos.de_linha(row) if row is not None else None


def _guia_out(db: Session, row: IaGuia | None, perfil_id: uuid.UUID,
              conta_id: uuid.UUID | None) -> schemas.Guia:
    campos = _campos(row) or guia.GuiaCampos()
    users = user_refs(db, [row.updated_by] if row is not None else [])
    return schemas.Guia(
        id=row.id if row is not None else None, perfil_id=perfil_id, conta_id=conta_id,
        campos=schemas.GuiaCampos.de_dominio(campos), tamanho=guia.tamanho(campos),
        version=row.version if row is not None else 0,
        updated_at=row.updated_at if row is not None else None,
        updated_by=users.get(row.updated_by) if row is not None and row.updated_by else None,
    )


def _efetivo_out(ef: guia.GuiaEfetivo) -> schemas.GuiaEfetivo:
    return schemas.GuiaEfetivo(
        proibidas=list(ef.proibidas), hashtags_fixas=list(ef.hashtags_fixas),
        emojis=ef.emojis, emojis_preferidos=list(ef.emojis_preferidos),
        max_hashtags_fixas=ef.max_hashtags_fixas)


def _conta_out(db: Session, conta: Conta, row: IaGuia | None) -> schemas.GuiaContaOut:
    perfil_row = guia.linha(db, conta.perfil_id, None)
    p, c = _campos(perfil_row), _campos(row)
    return schemas.GuiaContaOut(
        guia=_guia_out(db, row, conta.perfil_id, conta.id),
        perfil=_guia_out(db, perfil_row, conta.perfil_id, None),
        efetivo=_efetivo_out(guia.fundir(p, c)),
        conflitos=[schemas.Conflito(campo=x.campo, perfil=x.perfil, conta=x.conta,
                                    mensagem=x.mensagem) for x in guia.conflitos(p, c)])


# ---- validação (data-model, passos 1 a 5) ----

def _campo_raiz(caminho: str) -> str:
    return caminho.split(".", 1)[0]


def _cruzada_perfil(db: Session, perfil: Perfil, limpos: guia.GuiaCampos,
                    atual: guia.GuiaCampos | None) -> list[dict[str, Any]]:
    """Passo 5 no guia do perfil: cada conta não arquivada, com ou sem guia, respeita a soma das
    fixas; nas contas com guia, nenhuma proibida nova do perfil aparece no guia da conta."""
    antigas = {guia.normalizar(t) for t in (atual.proibidas if atual else ())}
    novas = [t for t in limpos.proibidas if guia.normalizar(t) not in antigas]
    contas = db.scalars(select(Conta).where(Conta.perfil_id == perfil.id,
                                            Conta.archived_at.is_(None))
                        .order_by(Conta.platform, Conta.handle))
    saida: list[dict[str, Any]] = []
    for conta in contas:
        c = _campos(guia.linha(db, perfil.id, conta.id))
        rotulo = rotulo_conta(conta)
        campos: list[str] = []
        mensagens: list[str] = []
        if c is not None and novas:
            achados = guia.proibidas_nos_campos(c, novas)
            for caminho, erro in achados.items():
                raiz = _campo_raiz(caminho)
                if raiz not in campos:
                    campos.append(raiz)
                    termo = erro.split("'", 1)[1].rstrip("'")
                    mensagens.append(f"A conta {rotulo} usa '{termo}' "
                                     f"{ROTULO_CAMPO.get(raiz, raiz)}; tire de lá antes")
        fixas = guia.fixas_somadas(limpos, c)
        maximo = guia.maximo_fixas(c)
        if len(fixas) > maximo:
            campos.append("hashtagsFixas")
            mensagens.append(f"A conta {rotulo} aceita no máximo {maximo} hashtags fixas; "
                             f"perfil e conta somariam {len(fixas)}")
        if campos:
            saida.append({"contaId": str(conta.id), "rotulo": rotulo, "campos": campos,
                          "mensagem": "; ".join(mensagens)})
    return saida


def validar_campos(db: Session, perfil: Perfil, conta: Conta | None,
                   campos: guia.GuiaCampos) -> guia.GuiaCampos:
    """A validação do save (PUT, revert e o "testar guia" da trilha B), na ordem do data-model.
    `conta = None` valida o guia do perfil. Devolve os campos limpos ou levanta 400
    `validation_error` com `details.fields` (e `details.contas`, no perfil)."""
    nivel: guia.Nivel = "perfil" if conta is None else "conta"
    limpos, erros = guia.validar_limites(campos, nivel)

    atual_perfil = _campos(guia.linha(db, perfil.id, None))
    if conta is None:
        termos = list(limpos.proibidas)
    else:
        termos = list(guia.fundir(atual_perfil, limpos).proibidas)
    for caminho, erro in guia.proibidas_nos_campos(limpos, termos).items():
        erros.setdefault(caminho, erro)

    contas: list[dict[str, Any]] = []
    if conta is None:
        contas = _cruzada_perfil(db, perfil, limpos, atual_perfil)
    elif "hashtagsFixas" not in erros and "maxHashtagsFixas" not in erros:
        fixas = guia.fixas_somadas(atual_perfil, limpos)
        maximo = guia.maximo_fixas(limpos)
        if len(fixas) > maximo:
            do_perfil = len(atual_perfil.hashtags_fixas) if atual_perfil else 0
            erros["hashtagsFixas"] = (
                f"perfil e conta somam {len(fixas)} hashtags fixas; o máximo desta conta é "
                f"{maximo}" + (f" ({do_perfil} vêm do perfil)" if do_perfil else ""))

    problemas = len(erros) + len(contas)
    if problemas:
        details: dict[str, Any] = {"fields": erros}
        if conta is None:
            details["contas"] = contas
        raise ApiError(400, "validation_error",
                       f"O guia tem {problemas} problema{'s' if problemas > 1 else ''}",
                       details=details)
    return limpos


# ---- escrita ----

def _aplicar(row: IaGuia, c: guia.GuiaCampos) -> None:
    row.tom = c.tom
    row.faca = list(c.faca)
    row.nao_faca = list(c.nao_faca)
    row.vocabulario = list(c.vocabulario)
    row.proibidas = list(c.proibidas)
    row.emojis = GuiaEmojis(c.emojis) if c.emojis is not None else None
    row.emojis_preferidos = list(c.emojis_preferidos)
    row.hashtags_fixas = list(c.hashtags_fixas)
    row.max_hashtags_fixas = c.max_hashtags_fixas
    row.exemplos = [dict(e) for e in c.exemplos]


def _salvar(db: Session, actor: Actor, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
            row: IaGuia | None, version: int, limpos: guia.GuiaCampos,
            ia: list[IaAplicacao] | None) -> IaGuia | None:
    """Cria (1ª edição), atualiza ou não faz nada (igual ao atual). Devolve a linha."""
    if row is None:
        if version != 0:
            raise _conflito_versao()
        if limpos.vazio:
            return None  # salvar vazio sem guia: nada muda
        row = IaGuia(perfil_id=perfil_id, conta_id=conta_id, created_by=actor.user_id,
                     updated_by=actor.user_id)
        _aplicar(row, limpos)
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:  # outra pessoa criou o guia ao mesmo tempo
            raise _conflito_versao() from exc
        after = history.snapshot(row)
        details = aplicacao.marcar(db, actor, "guia", row, None, after, ia,
                                   perfil_id=perfil_id)
        history.record(db, actor, ENTITY, row, "created", None, after, details)
        return row
    history.check_version(row, version, LABEL)
    before = history.snapshot(row)
    _aplicar(row, limpos)
    after = history.snapshot(row)
    if after == before:
        return row
    details = aplicacao.marcar(db, actor, "guia", row, before, after, ia, perfil_id=perfil_id)
    row.updated_by = actor.user_id
    history.record(db, actor, ENTITY, row, "updated", before, after, details)
    return row


def _saved(db: Session, row: IaGuia | None) -> None:
    db.flush()
    if row is not None:
        db.refresh(row)  # updated_at vem do banco


# ---- perfil ----

def obter_perfil(db: Session, perfil_id: uuid.UUID) -> schemas.GuiaOut:
    get_perfil_or_404(db, perfil_id)
    return schemas.GuiaOut(guia=_guia_out(db, guia.linha(db, perfil_id, None), perfil_id, None))


def put_perfil(db: Session, actor: Actor, perfil_id: uuid.UUID,
               body: schemas.GuiaIn) -> schemas.GuiaOut:
    perfil = get_perfil_or_404(db, perfil_id)
    _checar_ativos(perfil, None)
    row = guia.linha(db, perfil_id, None, lock=True)
    if row is not None:
        history.check_version(row, body.version, LABEL)
    limpos = validar_campos(db, perfil, None, body.campos.dominio())
    row = _salvar(db, actor, perfil_id, None, row, body.version, limpos, body.ia)
    _saved(db, row)
    return schemas.GuiaOut(guia=_guia_out(db, row, perfil_id, None))


def versions_perfil(db: Session, perfil_id: uuid.UUID) -> VersionsList:
    get_perfil_or_404(db, perfil_id)
    row = guia.linha(db, perfil_id, None)
    return versions_out(db, ENTITY, row.id) if row is not None else VersionsList(items=[])


def _reverter(db: Session, actor: Actor, perfil: Perfil, conta: Conta | None,
              body: RevertIn) -> IaGuia:
    """O snapshot da versão alvo, revalidado com as regras de hoje, numa versão `reverted`."""
    _checar_ativos(perfil, conta)
    row = guia.linha(db, perfil.id, conta.id if conta else None, lock=True)
    if row is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    history.check_version(row, body.version, LABEL)
    state = target_state(db, ENTITY, row, body.to_version)  # type: ignore[arg-type]
    limpos = validar_campos(db, perfil, conta, guia.GuiaCampos.de_snapshot(state))
    before = history.snapshot(row)
    _aplicar(row, limpos)
    after = history.snapshot(row)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    row.updated_by = actor.user_id
    history.record(db, actor, ENTITY, row, "reverted", before, after,
                   {"from_version": body.to_version})
    _saved(db, row)
    return row


def revert_perfil(db: Session, actor: Actor, perfil_id: uuid.UUID,
                  body: RevertIn) -> schemas.GuiaOut:
    perfil = get_perfil_or_404(db, perfil_id)
    row = _reverter(db, actor, perfil, None, body)
    return schemas.GuiaOut(guia=_guia_out(db, row, perfil_id, None))


# ---- conta ----

def _conta_e_perfil(db: Session, conta_id: uuid.UUID) -> tuple[Conta, Perfil]:
    conta = get_conta(db, conta_id)
    return conta, get_perfil_or_404(db, conta.perfil_id)


def obter_conta(db: Session, conta_id: uuid.UUID) -> schemas.GuiaContaOut:
    conta = get_conta(db, conta_id)
    return _conta_out(db, conta, guia.linha(db, conta.perfil_id, conta.id))


def put_conta(db: Session, actor: Actor, conta_id: uuid.UUID,
              body: schemas.GuiaIn) -> schemas.GuiaContaOut:
    conta, perfil = _conta_e_perfil(db, conta_id)
    _checar_ativos(perfil, conta)
    row = guia.linha(db, perfil.id, conta.id, lock=True)
    if row is not None:
        history.check_version(row, body.version, LABEL)
    limpos = validar_campos(db, perfil, conta, body.campos.dominio())
    row = _salvar(db, actor, perfil.id, conta.id, row, body.version, limpos, body.ia)
    _saved(db, row)
    return _conta_out(db, conta, row)


def versions_conta(db: Session, conta_id: uuid.UUID) -> VersionsList:
    conta = get_conta(db, conta_id)
    row = guia.linha(db, conta.perfil_id, conta.id)
    return versions_out(db, ENTITY, row.id) if row is not None else VersionsList(items=[])


def revert_conta(db: Session, actor: Actor, conta_id: uuid.UUID,
                 body: RevertIn) -> schemas.GuiaContaOut:
    conta, perfil = _conta_e_perfil(db, conta_id)
    row = _reverter(db, actor, perfil, conta, body)
    return _conta_out(db, conta, row)
