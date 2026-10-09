"""Cadastro padronizado do avatar e do cenário (spec 025, research R4–R6, R9, R15–R17).

- `aplicar_slot`: a escolha (ou o envio) num slot do kit: arquiva o arquivo ativo do slot, cria o
  `asset_files` `kit` com a geração de origem, apaga a `identidade`, recalcula o `kit_status` e
  grava **uma** versão (`kit_escolhido`). Com os 5 slots do avatar, pede a checagem de identidade
  (`avatar.identidade`, motor `claude`), com o humano da escolha como autor;
- `kit_out`: o bloco `kit` da leitura (slots, passos, geração aberta, checagem pendente);
- `registrar_consentimento`: só humano (a rota usa `RequireHuman`); `registrado_por` é o ator;
- `voz_padrao`: a voz padrão do avatar (mesmo perfil, não arquivada, não revogada, com referência).

A seta é `geracao → assets`: este módulo só importa o serviço da 021 dentro das funções (pedir a
checagem), como o `produtos/fluxo.py` da 012.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.assets import padrao
from sociman_api.assets.models import (
    Asset,
    AssetFile,
    AssetOrigem,
    AssetTipo,
    FileRole,
    KitStatus,
)
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Image

REVOGADO = "O consentimento foi revogado; este item não pode ser usado nem restaurado"


def consentimento_revogado() -> ApiError:
    return ApiError(409, "consentimento_revogado", REVOGADO)


def menor_proibido() -> ApiError:
    return ApiError(400, "menor_proibido", "Menores de idade não são permitidos")


def checar_menoridade(*textos: str | None) -> None:
    if padrao.checar_menoridade(*textos):
        raise menor_proibido()


def recalcular(asset: Asset) -> None:
    """O `kit_status` (R5); avatar e cenário da 007 sem slot nenhum ficam nulos."""
    slots = asset.slots_ativos()
    if asset.tipo not in (AssetTipo.avatar, AssetTipo.cenario):
        return
    if not slots and asset.kit_status is None:
        return
    asset.kit_status = KitStatus(padrao.situacao(asset.tipo.value, slots, asset.identidade))


def _derivados(db: Session, asset: Asset, imagem_antiga: uuid.UUID) -> list[dict[str, Any]]:
    """Arquivos ativos gerados a partir da imagem antiga do slot (aviso, R6)."""
    from sociman_api.geracao.models import Geracao

    out = []
    for f in asset.active_files():
        if f.geracao_id is None:
            continue
        g = db.get(Geracao, f.geracao_id)
        refs = (g.params or {}).get("referencias") or [] if g is not None else []
        if str(imagem_antiga) in refs:
            out.append({"fileId": str(f.id), "slot": f.slot, "look": f.look, "label": f.label})
    return out


def aplicar_slot(db: Session, actor: Actor, asset: Asset, imagens: list[tuple[str, Image]],
                 geracao_id: uuid.UUID | None, *, passo: str | None = None,
                 origem: AssetOrigem | None = None, automatico: bool = False
                 ) -> tuple[list[dict[str, Any]], uuid.UUID | None]:
    """Grava os slots (o par 3/4 numa versão só). Devolve os avisos `derivados_desatualizados` e o
    id da checagem pedida (quando o avatar completou os 5 slots)."""
    from sociman_api.assets import service as assets_service

    before = history.snapshot(asset)
    agora = datetime.now(UTC)
    derivados: list[dict[str, Any]] = []
    for slot, image in imagens:
        antigo = asset.slot_ativo(slot)
        if antigo is not None:
            if slot in ("rosto_origem", "rosto_frontal"):
                derivados += _derivados(db, asset, antigo.image_id)
            antigo.archived_at, antigo.archived_by = agora, actor.user_id
            db.flush()  # o UNIQUE parcial do slot (um ativo por slot)
        f = AssetFile(asset_id=asset.id, image_id=image.id, role=FileRole.kit, slot=slot,
                      position=0, geracao_id=geracao_id, created_by=actor.user_id)
        db.add(f)
        asset.arquivos.append(f)
        db.flush()
    if origem is not None:
        asset.origem = origem
    if asset.tipo == AssetTipo.avatar:
        asset.identidade = None
    if asset.tipo == AssetTipo.cenario and asset.primary_file_id is None:
        asset.primary_file_id = asset.slot_ativo("cena").id  # type: ignore[union-attr]
    assets_service._fix_primary(asset)
    recalcular(asset)
    details: dict[str, Any] = {"slots": [s for s, _ in imagens]}
    if geracao_id is not None:
        details |= {"geracao_id": str(geracao_id), "geracaoId": str(geracao_id),
                    "passo": passo}
    if automatico:
        details["automatico"] = True
    acao = "kit_escolhido" if geracao_id is not None else "updated"
    assets_service._record(db, actor, asset, acao, before, details=details)
    checagem = None
    if asset.tipo == AssetTipo.avatar and set(padrao.SLOTS_AVATAR) <= asset.slots_ativos():
        checagem = pedir_identidade(db, actor, asset)
    return derivados, checagem


def _abertas(db: Session, asset_id: uuid.UUID, passo: str) -> list[Any]:
    """As gerações do passo ainda não finais (inclusive `falhou`: tem "Tentar de novo")."""
    from sociman_api.geracao.models import FINAIS, Geracao, GeracaoAlvo

    return list(db.scalars(select(Geracao).where(
        Geracao.alvo_tipo == GeracaoAlvo.asset, Geracao.alvo_id == asset_id,
        Geracao.passo == passo, Geracao.status.not_in(FINAIS)).order_by(Geracao.created_at)))


def pedir_identidade(db: Session, actor: Actor, asset: Asset) -> uuid.UUID | None:
    """A checagem pedida pelo servidor (R4). Uma por vez: com uma aberta, não pede outra."""
    from sociman_api.geracao import service as geracao_service
    from sociman_api.geracao.models import GeracaoAlvo

    abertas = _abertas(db, asset.id, "avatar.identidade")
    if abertas:
        return abertas[0].id
    params = {"instrucao": "", "referencias": [str(asset.slot_ativo(s).image_id)
                                               for s in padrao.SLOTS_AVATAR],
              "rotulo": None, "texto": None, "extras": None}
    g = geracao_service.criar_para_alvo(db, actor, asset.perfil_id, "avatar.identidade",
                                        GeracaoAlvo.asset, asset.id, params)
    return g.id


# ---- leitura: o bloco `kit` ----

def kit_out(db: Session, asset: Asset) -> dict[str, Any] | None:
    """Os slots e os passos do kit (só avatar e cenário), na ordem de `padrao.SLOTS`."""
    from sociman_api.geracao import service as geracao_service

    if asset.tipo not in (AssetTipo.avatar, AssetTipo.cenario):
        return None
    ativos = asset.slots_ativos()
    slots_tipo = padrao.SLOTS_AVATAR if asset.tipo == AssetTipo.avatar else padrao.SLOTS_CENARIO
    notas = (asset.identidade or {}).get("notas") or {}
    origem = asset.origem.value if asset.origem else None
    slots = []
    for slot in slots_tipo:
        aberto, motivo = padrao.slot_aberto(slot, ativos)
        nota = notas.get(slot) or {}
        f = asset.slot_ativo(slot)
        slots.append({"slot": slot, "file_id": f.id if f else None, "aberto": aberto,
                      "motivo": motivo, "nota": nota.get("nota"),
                      "observacao": nota.get("observacao"),
                      "refazer": nota.get("nota") is not None
                      and int(nota["nota"]) < padrao.NOTA_MINIMA})
    passos_ids = padrao.PASSOS_KIT_AVATAR + ("avatar.look", "avatar.pose") \
        if asset.tipo == AssetTipo.avatar else ("cenario.cena", "cenario.variacao")
    passos = []
    for p in passos_ids:
        aberto, motivo = padrao.passo_aberto(p, ativos, origem)
        if asset.revogado:
            aberto, motivo = False, REVOGADO
        abertas = _abertas(db, asset.id, p)
        passos.append({"passo": p, "aberto": aberto, "motivo": motivo,
                       "geracao_aberta": geracao_service.resumo_out(db, abertas[-1])
                       if abertas else None})
    # Pendente: os 5 slots sem identidade e nenhuma checagem rodando (a que falhou conta como
    # pendente, com "Checar de novo" ou "Tentar de novo").
    vivas = [x for x in _abertas(db, asset.id, "avatar.identidade")
             if x.status.value != "falhou"]
    pendente = (asset.tipo == AssetTipo.avatar and set(padrao.SLOTS_AVATAR) <= ativos
                and asset.identidade is None and not vivas)
    proibidas = (asset.identidade or {}).get("proibidas") or []
    return {"slots": slots, "passos": passos, "checagem_pendente": pendente,
            "descricao_nao_aplicada": {"proibidas": proibidas} if proibidas else None}


# ---- consentimento (R9) ----

def _prova(db: Session, prova: dict[str, Any] | None) -> dict[str, str] | None:
    """A imagem ou o áudio da prova: de qualquer perfil base (spec 029, T028a)."""
    from sociman_api.geracao.models import Audio

    if not prova:
        return None
    if prova.get("image_id"):
        img = db.get(Image, prova["image_id"])
        if img is None:
            raise ApiError(400, "entrada_invalida", "prova: imagem não encontrada",
                           details={"field": "prova"})
        return {"image_id": str(img.id)}
    if prova.get("audio_id"):
        a = db.get(Audio, prova["audio_id"])
        if a is None:
            raise ApiError(400, "entrada_invalida", "prova: áudio não encontrado",
                           details={"field": "prova"})
        return {"audio_id": str(a.id)}
    return None


def montar_consentimento(db: Session, actor: Actor, perfil_id: uuid.UUID | None, nome: str,
                         data: date, observacao: str, prova: dict[str, Any] | None
                         ) -> dict[str, Any]:
    if data > datetime.now(UTC).date():
        raise ApiError(400, "entrada_invalida", "data: não pode ser no futuro",
                       details={"field": "data"})
    return {"nome": nome, "data": data.isoformat(), "observacao": observacao,
            "registrado_por": str(actor.user_id) if actor.user_id else None,
            "registrado_em": datetime.now(UTC).isoformat(),
            "prova": _prova(db, prova), "revogado_em": None, "revogado_por": None}


def registrar_consentimento(db: Session, actor: Actor, asset: Asset, version: int,
                            nome: str, data: date, observacao: str,
                            prova: dict[str, Any] | None) -> Asset:
    from sociman_api.assets import service as assets_service

    history.check_version(asset, version, "Este asset")
    if asset.tipo != AssetTipo.avatar:
        raise ApiError(400, "invalid_asset", "consentimento: só em avatar",
                       details={"field": "consentimento"})
    if asset.revogado:
        raise consentimento_revogado()
    if asset.origem in (AssetOrigem.upload, AssetOrigem.sintetico):
        raise ApiError(400, "invalid_asset", "consentimento: o avatar não é de pessoa real",
                       details={"field": "origem"})
    before = history.snapshot(asset)
    asset.consentimento = montar_consentimento(db, actor, asset.perfil_id, nome, data,
                                               observacao, prova)
    asset.origem = AssetOrigem.pessoa_real
    assets_service._record(db, actor, asset, "consentimento", before)
    return asset


def consentimento_out(db: Session, c: dict[str, Any] | None, *, para_mcp: bool
                      ) -> dict[str, Any] | None:
    """A prova sai só para humanos (R9): no MCP, `prova = null` e `temProva`."""
    from sociman_api import midia
    from sociman_api.geracao import audios as audios_mod
    from sociman_api.geracao.models import Audio
    from sociman_api.perfis.service_perfis import user_refs

    if not c:
        return None
    users = user_refs(db, [uuid.UUID(u) for u in (c.get("registrado_por"),
                                                  c.get("revogado_por")) if u])
    prova_in = c.get("prova") or {}
    prova = None
    if not para_mcp and prova_in.get("image_id"):
        prova = {"image_id": prova_in["image_id"],
                 "link": midia.link("imagem", uuid.UUID(prova_in["image_id"]), ttl=None).url}
    elif not para_mcp and prova_in.get("audio_id"):
        a = db.get(Audio, uuid.UUID(prova_in["audio_id"]))
        prova = {"audio": audios_mod.audio_out(a, user_refs(db, [a.created_by]))} if a else None
    reg = c.get("registrado_por")
    rev = c.get("revogado_por")
    return {"nome": c.get("nome"), "data": c.get("data"), "observacao": c.get("observacao", ""),
            "registrado_por": users.get(uuid.UUID(reg)) if reg else None,
            "registrado_em": c.get("registrado_em"), "prova": prova,
            "tem_prova": bool(prova_in), "revogado_em": c.get("revogado_em"),
            "revogado_por": users.get(uuid.UUID(rev)) if rev else None}


# ---- voz padrão (R15) ----

def validar_voz_padrao(db: Session, asset: Asset, voz_id: uuid.UUID | None) -> None:
    from sociman_api.vozes.models import Voz, VozStatus

    if voz_id is None:
        return
    # Spec 029 (T028a): a voz pode ser de qualquer perfil base.
    erro = ApiError(400, "voz_invalida", "Escolha uma voz aprovada",
                    details={"field": "vozId"})
    if asset.tipo != AssetTipo.avatar:
        raise erro
    voz = db.get(Voz, voz_id)
    if voz is None or voz.archived or voz.revogada:
        raise erro
    if voz.ref_audio_id is None or voz.status not in (VozStatus.aprovada, VozStatus.revisao):
        raise erro


def voz_padrao_out(db: Session, asset: Asset) -> dict[str, Any] | None:
    from sociman_api.vozes.models import Voz

    if asset.voz_id is None:
        return None
    voz = db.get(Voz, asset.voz_id)
    if voz is None:
        return None
    return {"id": voz.id, "name": voz.name, "status": voz.status, "arquivada": voz.archived,
            "revogada": voz.revogada}
