"""Marca "com ajuda da IA" nos saves existentes (research R10, data-model "Campo `ia`").

As rotas de salvar do asset, do perfil, do kit e da postagem aceitam o campo opcional `ia`
(`IaAplicacao[]`). O service chama `marcar` **antes** do `history.record`, na mesma transação:
para cada item que casa (a chamada existe, é do mesmo perfil e do mesmo alvo, o tipo casa com a
entidade e o campo mudou nesta versão), compara o valor salvo com a proposta e grava o desfecho
da chamada (`aplicada` ou `editada`). O que não casa é ignorado: o save nunca falha por causa
do campo `ia`. O retorno é o `details` da versão (`{"ia": [...]}`), com o autor humano de sempre.
"""

import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import Field, StringConstraints
from sqlalchemy.orm import Session

from sociman_api.auth.schemas import CamelModel
from sociman_api.history import ActorLike
from sociman_api.ia.models import IaChamada, IaDesfecho
from sociman_api.ia.tipos import TIPOS, TipoCampo, TipoCampoId

log = logging.getLogger(__name__)

MAX_APLICACOES = 10
MAX_ITENS = 20

ItemAplicado = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                                max_length=120)]


class IaAplicacao(CamelModel):
    """Um campo salvo a partir de uma chamada. `itens` só vale nos tipos `sugestoes`: o texto
    final dos itens daquela chamada que entraram na lista (nos outros, é ignorado)."""

    tipo_campo: TipoCampoId
    chamada_id: uuid.UUID
    itens: Annotated[list[ItemAplicado], Field(min_length=1, max_length=MAX_ITENS)] | None = None


IaAplicacoes = Annotated[list[IaAplicacao], Field(max_length=MAX_APLICACOES)]

_FINAIS = (IaDesfecho.descartada, IaDesfecho.erro)


@dataclass(frozen=True)
class _Alvo:
    """O que a chamada precisa casar: o perfil e a entidade salva (ou o conteúdo + conta)."""

    entidade: str  # asset | perfil | kit | postagem
    perfil_id: uuid.UUID
    entity_id: uuid.UUID
    tipo_asset: str | None = None
    conteudo_id: uuid.UUID | None = None  # spec 014 (na origem corte, = o id do corte)
    conta_id: uuid.UUID | None = None
    plataforma: str | None = None


def _valor(v: Any) -> Any:
    return getattr(v, "value", v)


def _alvo(entity_type: str, entidade: Any, perfil_id: uuid.UUID | None,
          plataforma: str | None) -> _Alvo:
    if entity_type == "perfil":
        return _Alvo("perfil", entidade.id, entidade.id)
    if entity_type == "postagem":
        assert perfil_id is not None, "postagem: passe o perfil do conteúdo"
        return _Alvo("postagem", perfil_id, entidade.id, conteudo_id=entidade.conteudo_id,
                     conta_id=entidade.conta_id, plataforma=plataforma)
    tipo_asset = _valor(entidade.tipo) if entity_type == "asset" else None
    return _Alvo(entity_type, entidade.perfil_id, entidade.id, tipo_asset=tipo_asset)


def _casa_alvo(chamada: Any, tipo: TipoCampo, alvo: _Alvo) -> bool:
    if tipo.entidade != alvo.entidade or chamada.perfil_id != alvo.perfil_id:
        return False
    if tipo.tipos_asset is not None and alvo.tipo_asset not in tipo.tipos_asset:
        return False
    if alvo.entidade == "kit":
        # Kit nunca salvo: a chamada foi gerada sem entity_id (a linha nasce neste save).
        return chamada.entity_type == "kit" and chamada.entity_id in (None, alvo.entity_id)
    if alvo.entidade == "postagem":
        if chamada.entity_type == "postagem":
            return chamada.entity_id == alvo.entity_id
        if chamada.entity_type not in ("corte", "conteudo") \
                or chamada.conteudo_id != alvo.conteudo_id:
            return False
        if chamada.conta_id is not None:
            return chamada.conta_id == alvo.conta_id
        # Linhas da 006: sem conta, só a plataforma.
        return alvo.plataforma is not None and _valor(chamada.plataforma) == alvo.plataforma
    return chamada.entity_type == alvo.entidade and chamada.entity_id == alvo.entity_id


def _mudou(antes: Mapping[str, Any] | None, depois: Mapping[str, Any], campo: str) -> bool:
    if antes is None:  # criação: conta só o que veio preenchido
        return bool(depois.get(campo))
    return antes.get(campo) != depois.get(campo)


def _texto(tipo: TipoCampo, valor: Any) -> str:
    texto = valor or ""
    return texto.strip() if tipo.limites.trim else texto


def _hashtag(tag: str) -> str:
    tag = tag.strip()
    return (tag if tag.startswith("#") else f"#{tag}").casefold()


def _lista(valor: Iterable[str] | None) -> list[str]:
    return [_hashtag(t) for t in valor or ()]


def _chave(item: str) -> str:
    return item.strip().casefold()


def _igual_proposta(tipo: TipoCampo, proposta: Mapping[str, Any],
                    depois: Mapping[str, Any]) -> bool:
    if tipo.formato == "texto":
        campo = tipo.campos[0]
        return _texto(tipo, depois.get(campo)) == _texto(tipo, proposta.get("texto"))
    if tipo.formato == "lista":
        return _lista(depois.get(tipo.campos[0])) == _lista(proposta.get("itens"))
    # textos_postagem: os três juntos.
    return (
        (depois.get("titulo") or "").strip() == (proposta.get("titulo") or "").strip()
        and (depois.get("descricao") or "").strip() == (proposta.get("descricao") or "").strip()
        and _lista(depois.get("hashtags")) == _lista(proposta.get("hashtags"))
    )


def _sugestoes(tipo: TipoCampo, chamada: Any, item: IaAplicacao,
               antes: Mapping[str, Any] | None,
               depois: Mapping[str, Any]) -> tuple[list[str], bool] | None:
    """Os itens desta chamada que entraram na lista agora (texto salvo) e se algum foi editado."""
    campo = tipo.campos[0]
    antes_set = {_chave(i) for i in (antes or {}).get(campo) or ()}
    salvos = {_chave(i): i for i in depois.get(campo) or ()}
    ja = {_chave(i) for i in chamada.itens_aplicados or ()}
    propostas = {i.strip() for i in (chamada.proposta or {}).get("itens") or ()}
    novos: list[str] = []
    editado = False
    for texto in item.itens or ():
        chave = _chave(texto)
        if chave not in salvos or chave in antes_set or chave in ja:
            continue
        if any(_chave(n) == chave for n in novos):
            continue
        final = salvos[chave]
        novos.append(final)
        editado = editado or final.strip() not in propostas
    if not novos:
        return None
    return novos, editado


def _agrupar(ia: Sequence[IaAplicacao]) -> list[IaAplicacao]:
    """Um item por chamada (itens da mesma chamada somados), na ordem em que chegaram."""
    por_id: dict[uuid.UUID, IaAplicacao] = {}
    for item in ia:
        atual = por_id.get(item.chamada_id)
        if atual is None:
            por_id[item.chamada_id] = item
        elif item.itens:
            itens = [*(atual.itens or []), *item.itens]
            por_id[item.chamada_id] = atual.model_copy(update={"itens": itens})
    return list(por_id.values())


def _aplicar(db: Session, actor: ActorLike, alvo: _Alvo, item: IaAplicacao,
             antes: Mapping[str, Any] | None, depois: Mapping[str, Any],
             versao: int, agora: datetime) -> dict[str, Any] | None:
    tipo = TIPOS.get(item.tipo_campo)
    if tipo is None:
        return None
    chamada = db.get(IaChamada, item.chamada_id, with_for_update=True)
    if chamada is None or chamada.tipo_campo != item.tipo_campo:
        return None
    if chamada.desfecho in _FINAIS or chamada.proposta is None:
        return None
    if not _casa_alvo(chamada, tipo, alvo):
        return None
    if not any(_mudou(antes, depois, c) for c in tipo.campos):
        return None

    entrada: dict[str, Any] = {"campo": ",".join(tipo.campos), "tipoCampo": tipo.id,
                               "chamadaId": str(chamada.id)}
    if tipo.formato == "sugestoes":
        resultado = _sugestoes(tipo, chamada, item, antes, depois)
        if resultado is None:
            return None
        novos, editado = resultado
        editada = editado or chamada.desfecho == IaDesfecho.editada
        chamada.itens_aplicados = [*(chamada.itens_aplicados or []), *novos]
        entrada["itens"] = novos
    else:
        if chamada.desfecho != IaDesfecho.sem_acao:  # texto/lista: uma aplicação só
            return None
        editada = not _igual_proposta(tipo, chamada.proposta, depois)

    chamada.desfecho = IaDesfecho.editada if editada else IaDesfecho.aplicada
    chamada.desfecho_em = agora
    chamada.desfecho_por = actor.user_id
    chamada.aplicada_versao = versao
    entrada["desfecho"] = chamada.desfecho.value
    return entrada


def marcar(db: Session, actor: ActorLike, entity_type: str, entidade: Any,
           antes: Mapping[str, Any] | None, depois: Mapping[str, Any],
           ia: Sequence[IaAplicacao] | None, *, perfil_id: uuid.UUID | None = None,
           plataforma: str | None = None) -> dict[str, Any] | None:
    """Marca as chamadas aplicadas neste save e devolve o `details` da versão (ou None).

    Chame depois de conferir que houve mudança e **antes** do `history.record` (a versão nova
    é a atual + 1; na criação, `antes` é None e a versão é 1). Na postagem, passe `perfil_id`
    (o do conteúdo) e a `plataforma` da conta (casa as linhas da 006, que não têm conta).
    """
    if not ia:
        return None
    versao = 1 if antes is None else (entidade.version or 0) + 1
    agora = datetime.now(UTC)
    alvo = _alvo(entity_type, entidade, perfil_id, plataforma)
    entradas = []
    for item in _agrupar(ia):
        try:
            entrada = _aplicar(db, actor, alvo, item, antes, depois, versao, agora)
        except Exception:  # nunca derruba o save por causa da marca
            log.exception("ia: falha ao marcar a chamada %s; ignorada", item.chamada_id)
            continue
        if entrada is not None:
            entradas.append(entrada)
    return {"ia": entradas} if entradas else None
