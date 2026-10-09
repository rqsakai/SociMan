"""Aplicadores do cenário padrão (spec 025, US5, research R2): `cenario.cena` (substitui o piloto
da 021: a opção vira o slot `cena`, e o cenário fica `completo`) e `cenario.variacao` (a partir da
cena, com rótulo único entre as variações ativas)."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.assets import padrao, service_padrao
from sociman_api.assets.models import Asset, AssetTipo, FileRole
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.geracao import aplicadores as base
from sociman_api.geracao import passos
from sociman_api.geracao.aplicadores_avatar import _AssetBase
from sociman_api.geracao.models import Geracao, GeracaoCandidato

VARIACAO_LABEL_IN_USE = "Já existe uma variação com esse rótulo neste cenário"


class _CenarioBase(_AssetBase):
    tipo = AssetTipo.cenario

    def normalizar(self, png: bytes) -> bytes:
        from sociman_api.geracao.comfyui import normalizar_9x16

        return normalizar_9x16(png)

    def preparar_referencia(self, data: bytes) -> bytes:
        from sociman_api.geracao.comfyui import normalizar_9x16

        return normalizar_9x16(data)


class Cena(_CenarioBase):
    """Sem foto, o bloco `cena` com o prompt + `REALISMO`; com uma foto, o `keyframe` com a
    instrução + `MANTER` (R6 da 021). A escolha vira o slot `cena` (trocar arquiva a anterior)."""

    passo = "cenario.cena"
    # Como no piloto da 021: várias cenas podem ser pedidas (escolher troca o slot).
    um_por_vez = False

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._comum(db, alvo, pedido)
        self.conferir_extras(pedido.extras)
        instrucao = pedido.instrucao.strip() or (alvo.prompt or "").strip()
        if not instrucao:
            raise base.entrada_invalida("instrucao", "descreva a cena")
        if len(pedido.referencias) > 1:
            raise base.entrada_invalida("referencias", "no máximo uma foto de referência")
        refs = [base.referencia_de_asset_ativo(db, r) for r in pedido.referencias]
        corpo = instrucao.rstrip(". ")
        if refs:
            bloco, prompt = "keyframe", f"{corpo}. {passos.MANTER}"
        else:
            bloco, prompt = "cena", f"{corpo}. {passos.REALISMO}"
        return {"instrucao": instrucao, "prompt": prompt, "bloco": bloco,
                "referencias": [str(r.id) for r in refs], "rotulo": pedido.rotulo,
                "texto": None, "extras": None}

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        service_padrao.aplicar_slot(db, actor, asset, [("cena", self._imagem(db,
                                                                             candidato.image_id))],
                                    geracao.id, passo=self.passo)


class Variacao(_CenarioBase):
    passo = "cenario.variacao"

    def _rotulo_livre(self, asset: Asset, rotulo: str) -> None:
        from sociman_api.assets import service as assets_service

        if assets_service.variacao_label_taken(asset, rotulo):
            raise ApiError(409, "variacao_label_in_use", VARIACAO_LABEL_IN_USE)

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._comum(db, alvo, pedido, por_rotulo=True)
        self.conferir_extras(pedido.extras)
        self._sem_referencias(pedido)
        rotulo = (pedido.rotulo or "").strip()
        if not rotulo:
            raise base.entrada_invalida("rotulo", "informe o rótulo da variação")
        self._rotulo_livre(alvo, rotulo)
        instrucao = pedido.instrucao.strip()
        if not instrucao:
            raise base.entrada_invalida("instrucao", "descreva o que muda")
        cena = self.imagem_do_slot(alvo, "cena")
        return self._params(alvo, pedido, padrao.VARIACAO.format(d=instrucao.rstrip(". ")),
                            "keyframe", [cena])

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        from sociman_api.assets import service as assets_service

        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        rotulo = geracao.params.get("rotulo") or ""
        self._rotulo_livre(asset, rotulo)
        image = self._imagem(db, candidato.image_id)
        before = history.snapshot(asset)
        f = assets_service._attach(db, actor, asset, image, FileRole.variacao,
                                   {"label": rotulo})
        f.geracao_id = geracao.id
        assets_service._flush_labels(db)
        assets_service._record(db, actor, asset, "updated", before, details={
            "geracao_id": str(geracao.id), "candidato": {"id": str(candidato.id),
                                                         "numero": candidato.numero}})


def _uuid(valor: Any) -> uuid.UUID:
    return valor if isinstance(valor, uuid.UUID) else uuid.UUID(str(valor))


APLICADORES: dict[str, base.Aplicador] = {"cenario.cena": Cena(), "cenario.variacao": Variacao()}
