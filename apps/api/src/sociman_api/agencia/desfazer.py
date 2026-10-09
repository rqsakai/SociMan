"""Desfazer uma importação (research R10, FR-029): a reversão dela, sem apagar nada.

Na ordem inversa da aplicação, para cada item `criado`/`atualizado`:
- só mexe se a entidade continua na versão que a importação deixou (as versões que o próprio
  desfazer grava entram na conta); senão, `nao_desfeito(editado_depois)`;
- `criado` → arquiva pelo service (guia criado → salvo vazio, como o "limpar" da 017; arquivo de
  asset → `archive_file`); em uso (canal com envio, conteúdo com destino, asset no kit) →
  `nao_desfeito(em_uso)`;
- `atualizado` → reverte para a versão anterior pelo service (`revert_*`).
Tudo numa transação (a da requisição), com `history.origem_importacao` (`desfazer: true`).
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.agencia import aplicar, schemas
from sociman_api.agencia.models import (
    ENTITY_TYPE,
    ImportacaoEstado,
    ImportacaoItem,
    ItemResultado,
)
from sociman_api.anotacoes import service as anotacoes
from sociman_api.anotacoes.models import Anotacao, AnotacaoAlvo, AnotacaoSituacao
from sociman_api.assets import service as assets
from sociman_api.assets.models import Asset, AssetFile
from sociman_api.auth.deps import Actor
from sociman_api.canais import service_canais
from sociman_api.canais.models import CanalFonte
from sociman_api.conteudos import service as conteudos
from sociman_api.conteudos.models import Conteudo
from sociman_api.envios.models import Envio
from sociman_api.errors import ApiError
from sociman_api.ia import schemas_guia, service_guia
from sociman_api.ia.models import IaGuia
from sociman_api.perfis import service_contas, service_perfis
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.perfis.schemas import RevertIn
from sociman_api.postagem.models import Postagem

EM_USO = "em_uso"
EDITADO = "editado_depois"
_MODELOS = {"perfil": Perfil, "conta": Conta, "ia_guia": IaGuia, "anotacao": Anotacao,
            "canal": CanalFonte, "asset": Asset, "conteudo": Conteudo}


class _NaoDesfeito(Exception):
    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def _chave(db: Session, item: ImportacaoItem) -> str:
    if item.entity_type == "asset_file":
        f = db.get(AssetFile, item.entity_id)
        return f"asset:{f.asset_id if f else item.entity_id}"
    return f"{item.entity_type}:{item.entity_id}"


def _entidade(db: Session, chave: str):
    tipo, _, ident = chave.partition(":")
    obj = db.get(_MODELOS[tipo], uuid.UUID(ident), with_for_update=True)
    if obj is None:
        raise _NaoDesfeito(EDITADO)
    db.refresh(obj)
    return obj


def _criado(db: Session, actor: Actor, item: ImportacaoItem, obj) -> None:
    match item.entity_type:
        case "perfil":
            service_perfis.archive_perfil(db, actor, obj.id, obj.version)
        case "conta":
            service_contas.archive_conta(db, actor, obj.id, obj.version)
        case "ia_guia":
            service_guia.put_perfil(db, actor, obj.perfil_id, schemas_guia.GuiaIn(
                version=obj.version, campos=schemas_guia.GuiaCampos()))
        case "anotacao":
            if obj.situacao != AnotacaoSituacao.arquivada:
                anotacoes.arquivar(db, actor, obj.id, obj.version)
        case "canal":
            if db.scalar(select(Envio.id).where(Envio.canal_fonte_id == obj.id).limit(1)):
                raise _NaoDesfeito(EM_USO)
            service_canais.archive_canal(db, actor, obj.id, obj.version)
        case "asset":
            if not obj.archived:
                assets.archive_asset(db, actor, obj.id, obj.version)
        case "asset_file":
            f = db.get(AssetFile, item.entity_id)
            if f is not None and not f.archived and not obj.archived:
                assets.archive_file(db, actor, obj.id, f.id, obj.version)
        case "conteudo":
            if db.scalar(select(Postagem.id).where(Postagem.conteudo_id == obj.id,
                                                   Postagem.archived_at.is_(None)).limit(1)):
                raise _NaoDesfeito(EM_USO)
            conteudos.archive(db, actor, obj.id, obj.version)
            # a anotação de origem que a importação prendeu ao conteúdo (intocada) vai junto
            for nota in db.scalars(select(Anotacao).where(
                    Anotacao.alvo_tipo == AnotacaoAlvo.conteudo, Anotacao.alvo_id == obj.id,
                    Anotacao.situacao == AnotacaoSituacao.aberta, Anotacao.version == 1)):
                anotacoes.arquivar(db, actor, nota.id, nota.version)


_REVERTER: dict[str, Callable] = {
    "perfil": lambda db, a, o, to: service_perfis.revert_perfil(db, a, o.id, o.version, to),
    "conta": lambda db, a, o, to: service_contas.revert_conta(db, a, o.id, o.version, to),
    "ia_guia": lambda db, a, o, to: service_guia.revert_perfil(
        db, a, o.perfil_id, RevertIn(version=o.version, to_version=to)),
    "anotacao": lambda db, a, o, to: anotacoes.reverter(db, a, o.id, o.version, to),
    "canal": lambda db, a, o, to: service_canais.revert_canal(db, a, o.id, o.version, to),
    "asset": lambda db, a, o, to: assets.revert_asset(db, a, o.id, o.version, to),
}


def desfazer(db: Session, actor: Actor, importacao_id: uuid.UUID, version: int,
             agora: datetime | None = None) -> schemas.AgenciaImportacao:
    aplicar.marcar_interrompidas(db)
    imp = aplicar.importacao_or_404(db, importacao_id, lock=True)
    if imp.estado != ImportacaoEstado.concluida:
        raise ApiError(409, "importacao_nao_desfazivel",
                       "Só uma importação concluída pode ser desfeita")
    history.check_version(imp, version, "Esta importação")
    agora = agora or datetime.now(UTC)
    itens = db.scalars(select(ImportacaoItem).where(
        ImportacaoItem.importacao_id == imp.id,
        ImportacaoItem.resultado.in_((ItemResultado.criado, ItemResultado.atualizado)))
        .order_by(ImportacaoItem.ordem.desc())).all()
    # A versão que a importação deixou em cada entidade (a maior que ela gravou).
    esperado: dict[str, int] = {}
    for item in itens:
        chave = _chave(db, item)
        esperado[chave] = max(esperado.get(chave, 0), item.entity_version or 0)
    desfeitos = 0
    for item in itens:
        chave = _chave(db, item)
        origem = {"id": str(imp.id), "arquivo": item.arquivo, "trecho": item.trecho,
                  "desfazer": True}
        motivo: str | None = None
        try:
            with db.begin_nested(), history.origem_importacao(origem):
                obj = _entidade(db, chave)
                if obj.version != esperado[chave]:
                    raise _NaoDesfeito(EDITADO)
                if item.resultado == ItemResultado.criado:
                    _criado(db, actor, item, obj)
                else:
                    try:
                        _REVERTER[chave.partition(":")[0]](db, actor, obj,
                                                           (item.entity_version or 1) - 1)
                    except ApiError as e:
                        if e.code != "validation_error":  # "igual à atual": nada a desfazer
                            raise
                db.flush()
                db.refresh(obj)
                esperado[chave] = obj.version
        except _NaoDesfeito as n:
            motivo = n.motivo
        except ApiError as e:
            motivo = EM_USO if e.code in ("asset_in_use", "destino_em_uso", "envio_em_andamento") \
                else EDITADO
        if motivo is None:
            item.desfeito_em = agora
            desfeitos += 1
        else:
            item.desfazer_motivo = motivo
    antes = history.snapshot(imp)
    imp.estado = ImportacaoEstado.desfeita
    imp.desfeita_em = agora
    imp.desfeita_por = actor.user_id
    imp.updated_by = actor.user_id
    history.record(db, actor, ENTITY_TYPE, imp, "updated", antes, history.snapshot(imp),
                   {"acao": "desfeita", "desfeitos": desfeitos,
                    "naoDesfeitos": len(itens) - desfeitos})
    db.flush()
    return aplicar.importacao_out(db, imp)
