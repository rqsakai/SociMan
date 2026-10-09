"""Aplicadores dos passos do avatar (spec 025, contracts/passos.md, research R3–R8): o kit padrão
(origem, frontal, par 3/4, corpo-base), a checagem de identidade e os looks e poses gerados.

Comum a todos, antes de criar a geração: avatar da biblioteca (de qualquer perfil base, spec
029), não arquivado e sem consentimento revogado; o passo aberto na ordem do kit (409 `passo_fechado`); uma geração aberta do mesmo
passo (por rótulo no look e na pose) → 409 `geracao_em_andamento`; termo de menoridade → 400
`menor_proibido`. O `prompt` do avatar **nunca** entra nos passos de edição (FR-016).

Só a escolha humana aplica os passos de imagem (o gerador só chama `aplicar` nos `sem_escolha`;
aqui, só a identidade).
"""

import io
import uuid
from datetime import UTC, datetime
from typing import Any

from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history, storage
from sociman_api.assets import padrao, service_padrao
from sociman_api.assets.models import Asset, AssetOrigem, AssetTipo, FileRole
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.geracao import aplicadores as base
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.models import FINAIS, Geracao, GeracaoAlvo, GeracaoCandidato
from sociman_api.perfis.models import Image

QUANDO_USAR_MAX = 300


def passo_fechado(motivo: str) -> ApiError:
    return ApiError(409, "passo_fechado", motivo)


def geracao_em_andamento() -> ApiError:
    return ApiError(409, "geracao_em_andamento",
                    "Já existe uma geração deste passo em andamento")


def abertas(db: Session, alvo_id: uuid.UUID, passo: str, rotulo: str | None = None
            ) -> list[Geracao]:
    """As do passo ainda não finais (inclusive `falhou`), opcionalmente do mesmo rótulo."""
    gs = list(db.scalars(select(Geracao).where(
        Geracao.alvo_tipo == GeracaoAlvo.asset, Geracao.alvo_id == alvo_id,
        Geracao.passo == passo, Geracao.status.not_in(FINAIS))))
    if rotulo is not None:
        gs = [g for g in gs if ((g.params or {}).get("rotulo") or "").lower() == rotulo.lower()]
    return gs


def _png(im: PILImage.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def tela_cinza(w: int, h: int, src: bytes | None = None) -> bytes:
    """A tela cinza-clara w×h; com `src`, a imagem encaixada e centralizada (sem cortar)."""
    tela = PILImage.new("RGB", (w, h), padrao.CINZA)
    if src is not None:
        with PILImage.open(io.BytesIO(src)) as im:
            im = im.convert("RGB")
            im.thumbnail((w, h), PILImage.LANCZOS)
            tela.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return _png(tela)


class _AssetBase(base.Aplicador):
    tipo = AssetTipo.avatar
    passo = ""
    um_por_vez = True  # uma geração aberta por passo (o `cenario.cena` da 021 aceita várias)

    def validar_alvo(self, db: Session, perfil_id: uuid.UUID | None, alvo_id: uuid.UUID, *,
                     lock: bool = False) -> Asset:
        asset = db.get(Asset, alvo_id, with_for_update=lock)
        if asset is None:
            raise base.alvo_nao_encontrado()
        if asset.tipo != self.tipo:
            raise base.alvo_incompativel()
        if asset.revogado:
            raise service_padrao.consentimento_revogado()
        if asset.archived:
            raise base.alvo_arquivado()
        return asset

    def _comum(self, db: Session, asset: Asset, pedido: base.Pedido,
               por_rotulo: bool = False) -> None:
        aberto, motivo = padrao.passo_aberto(self.passo, asset.slots_ativos(),
                                             asset.origem.value if asset.origem else None)
        if not aberto:
            raise passo_fechado(motivo or "Passo fechado")
        service_padrao.checar_menoridade(pedido.instrucao, pedido.rotulo,
                                         *(str(v) for v in (pedido.extras or {}).values()))
        if pedido.texto is not None:
            raise base.entrada_invalida("texto", "não se aplica a este passo")
        rotulo = pedido.rotulo if por_rotulo else None
        if self.um_por_vez and abertas(db, asset.id, self.passo, rotulo):
            raise geracao_em_andamento()

    def _sem_referencias(self, pedido: base.Pedido) -> None:
        if pedido.referencias:
            raise base.entrada_invalida("referencias", "este passo usa as imagens do kit")

    @staticmethod
    def imagem_do_slot(asset: Asset, slot: str) -> uuid.UUID:
        f = asset.slot_ativo(slot)
        if f is None:
            raise passo_fechado(f"Escolha {padrao.ROTULO_SLOT[slot]} antes")
        return f.image_id

    def _params(self, asset: Asset, pedido: base.Pedido, prompt: str, bloco: str,
                referencias: list[uuid.UUID], extras: dict[str, Any] | None = None
                ) -> dict[str, Any]:
        return {"instrucao": pedido.instrucao.strip(), "prompt": prompt, "bloco": bloco,
                "referencias": [str(r) for r in referencias], "rotulo": pedido.rotulo,
                "texto": None, "extras": extras}

    def _imagem(self, db: Session, image_id: uuid.UUID | None) -> Image:
        img = db.get(Image, image_id) if image_id else None
        if img is None:
            raise ApiError(400, "candidato_invalido", "Esta opção não tem mais o arquivo")
        return img


# ---- o kit (R3, R6, R7) ----

class RostoOrigem(_AssetBase):
    passo = "avatar.rosto_origem"

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._comum(db, alvo, pedido)
        self._sem_referencias(pedido)
        self.conferir_extras(pedido.extras)
        descricao = pedido.instrucao.strip()
        if not descricao:
            raise base.entrada_invalida("instrucao", "descreva a pessoa (adulta), em inglês")
        return self._params(alvo, pedido, padrao.ROSTO.format(p=descricao), "retrato", [])

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        service_padrao.aplicar_slot(db, actor, asset,
                                    [("rosto_origem", self._imagem(db, candidato.image_id))],
                                    geracao.id, passo=self.passo, origem=AssetOrigem.sintetico)


class RostoFrontal(_AssetBase):
    passo = "avatar.rosto_frontal"

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._comum(db, alvo, pedido)
        self._sem_referencias(pedido)
        self.conferir_extras(pedido.extras)
        ajuste = pedido.instrucao.strip()
        prompt = padrao.KIT_FRONTAL + (f" {ajuste}" if ajuste else "")
        return self._params(alvo, pedido, prompt, "keyframe",
                            [self.imagem_do_slot(alvo, "rosto_origem")])

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        service_padrao.aplicar_slot(db, actor, asset,
                                    [("rosto_frontal", self._imagem(db, candidato.image_id))],
                                    geracao.id, passo=self.passo)


class Rostos34(_AssetBase):
    """O par numa geração só (R3): cada opção roda o bloco duas vezes (esquerda e direita)."""

    passo = "avatar.rostos_34"

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._comum(db, alvo, pedido)
        self._sem_referencias(pedido)
        self.conferir_extras(pedido.extras)
        params = self._params(alvo, pedido, padrao.KIT_34_ESQ, "keyframe",
                              [self.imagem_do_slot(alvo, "rosto_frontal")])
        params["prompt_dir"] = padrao.KIT_34_DIR
        return params

    def entradas_comfyui(self, geracao: Geracao, seed: int | None,
                         refs: list[bytes]) -> list[dict[str, Any]]:
        p = geracao.params
        prefixo = f"sociman/{geracao.id}"
        return [{"base_image": refs[0], "instruction": instr, "seed": seed, "prefix": prefixo}
                for instr in (p["prompt"], p.get("prompt_dir") or padrao.KIT_34_DIR)]

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        service_padrao.aplicar_slot(
            db, actor, asset,
            [("rosto_34_esq", self._imagem(db, candidato.image_id)),
             ("rosto_34_dir", self._imagem(db, candidato.image_par_id))],
            geracao.id, passo=self.passo)


class CorpoBase(_AssetBase):
    """Duas estratégias, uma por opção (como o pipeline): ímpar = zoom out do frontal encaixado
    na tela cinza 9:16; par = tela cinza vazia com o frontal como referência do rosto."""

    passo = "avatar.corpo_base"

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._comum(db, alvo, pedido)
        self._sem_referencias(pedido)
        self.conferir_extras(pedido.extras)
        params = self._params(alvo, pedido, padrao.instrucao_corpo("rosto"), "keyframe",
                              [self.imagem_do_slot(alvo, "rosto_frontal")])
        params["prompt_tela"] = padrao.instrucao_corpo("tela")
        return params

    def entradas_comfyui(self, geracao: Geracao, seed: int | None,
                         refs: list[bytes]) -> list[dict[str, Any]]:
        p = geracao.params
        seeds = p.get("seeds") or []
        indice = seeds.index(seed) if seed in seeds else 0
        frontal = refs[0]
        w, h = padrao.W_CORPO, padrao.H_CORPO
        if indice % 2 == 0:
            entrada = {"base_image": tela_cinza(w, h, frontal), "instruction": p["prompt"]}
        else:
            entrada = {"base_image": tela_cinza(w, h), "instruction": p["prompt_tela"]}
        return [{**entrada, "ref1": frontal, "seed": seed, "prefix": f"sociman/{geracao.id}"}]

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        service_padrao.aplicar_slot(db, actor, asset,
                                    [("corpo_base", self._imagem(db, candidato.image_id))],
                                    geracao.id, passo=self.passo)


# ---- a checagem de identidade (R4) ----

class Identidade(_AssetBase):
    """Motor `claude`, sem escolha: as notas e a descrição vão direto ao avatar. Com palavra
    proibida do guia na descrição (sem 2ª tentativa), as notas entram, o `prompt` fica como
    estava e o desfecho da chamada fica `sem_acao` (o gerador não marca `aplicada`)."""

    passo = "avatar.identidade"

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._comum(db, alvo, pedido)
        self._sem_referencias(pedido)
        self.conferir_extras(pedido.extras)
        refs = [self.imagem_do_slot(alvo, s) for s in padrao.SLOTS_AVATAR]
        return {"instrucao": "", "referencias": [str(r) for r in refs], "rotulo": None,
                "texto": None, "extras": None}

    def mensagem_claude(self, db: Session, geracao: Geracao) -> list[dict[str, Any]]:
        import base64

        from sociman_api.produtos.ficha import reduzir

        blocos: list[dict[str, Any]] = []
        rotulos = ["REFERENCE (rosto_origem, the approved face):", *(
            f"{s}:" for s in padrao.SLOTS_AVATAR[1:])]
        for rotulo, ref in zip(rotulos, geracao.params.get("referencias") or [], strict=False):
            img = db.get(Image, uuid.UUID(ref))
            if img is None:
                raise MotorErro("entrada_invalida", "Uma imagem do kit não existe mais")
            dados = base64.standard_b64encode(reduzir(storage.get(img.object_key))).decode()
            blocos += [{"type": "text", "text": rotulo},
                       {"type": "image", "source": {"type": "base64",
                                                    "media_type": "image/jpeg", "data": dados}}]
        blocos.append({"type": "text", "text": "Score each kit slot and write descricao_prompt."})
        return blocos

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        from sociman_api.cenas.service import proibidas_do_perfil
        from sociman_api.ia import guia as guia_mod
        from sociman_api.ia.models import IaChamada

        asset = db.get(Asset, geracao.alvo_id, with_for_update=True)
        if asset is None or asset.revogado:
            raise MotorErro("entrada_invalida", "O avatar não está mais disponível")
        dados = (candidato.metricas or {}).get("identidade")
        if not isinstance(dados, dict):
            raise MotorErro("internal", detalhe="candidato da identidade sem notas")
        # Os slots mudaram depois do pedido: a checagem não vale (a próxima troca pede outra).
        atuais = [str(asset.slot_ativo(s).image_id) if asset.slot_ativo(s) else None
                  for s in padrao.SLOTS_AVATAR]
        if atuais != list(geracao.params.get("referencias") or []):
            raise MotorErro("entrada_invalida", "O kit mudou durante a checagem; peça de novo")
        descricao = dados.get("descricao_prompt") or ""
        # Spec 029: as proibidas do perfil base da geração (nenhum = nenhuma), não as do item.
        proibidas = guia_mod.achar_proibidas(
            [descricao], proibidas_do_perfil(db, geracao.perfil_id) if geracao.perfil_id else ())
        before = history.snapshot(asset)
        chamada_id = (candidato.metricas or {}).get("chamada_id")
        asset.identidade = {"modelo": None, "data": datetime.now(UTC).isoformat(),
                            "geracao_id": str(geracao.id), "notas": dados.get("notas") or {},
                            "proibidas": list(proibidas)}
        if chamada_id:
            row = db.get(IaChamada, uuid.UUID(chamada_id))
            if row is not None:
                asset.identidade["modelo"] = row.model
                row.proibidas = list(proibidas)
        if not proibidas:
            asset.prompt = descricao  # exatamente como veio (sem trim)
        candidato.metricas = {**(candidato.metricas or {}), "proibidas": list(proibidas)}
        service_padrao.recalcular(asset)
        details: dict[str, Any] = {"geracao_id": str(geracao.id), "geracaoId": str(geracao.id),
                                   "automatico": True}
        if chamada_id:
            details["ia"] = {"chamadaId": chamada_id}
        if proibidas:
            details["proibidas"] = list(proibidas)
        from sociman_api.assets import service as assets_service

        assets_service._record(db, actor, asset, "identidade", before, details=details)


# ---- looks e poses (US4, R7) ----

class _LookPose(_AssetBase):
    extras_aceitos = frozenset()

    def _base(self, db: Session, asset: Asset, pedido: base.Pedido) -> list[uuid.UUID]:
        """Base = corpo-base ou a pose em `referencias[0]`; o frontal é a referência do rosto."""
        frontal = self.imagem_do_slot(asset, "rosto_frontal")
        if len(pedido.referencias) > 1:
            raise base.entrada_invalida("referencias", "no máximo uma pose de base")
        if pedido.referencias:
            pose = next((f for f in asset.active_files(FileRole.pose)
                         if f.image_id == pedido.referencias[0]), None)
            if pose is None:
                raise base.entrada_invalida("referencias", "escolha uma pose ativa deste avatar")
            return [pose.image_id, frontal]
        return [self.imagem_do_slot(asset, "corpo_base"), frontal]

    def _rotulo(self, pedido: base.Pedido) -> str:
        rotulo = (pedido.rotulo or "").strip()
        if not rotulo:
            raise base.entrada_invalida("rotulo", "informe o rótulo")
        return rotulo


class Look(_LookPose):
    passo = "avatar.look"

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._comum(db, alvo, pedido, por_rotulo=True)
        self.conferir_extras(pedido.extras)
        self._rotulo(pedido)
        roupa = pedido.instrucao.strip()
        if not roupa:
            raise base.entrada_invalida("instrucao", "descreva a roupa toda")
        return self._params(alvo, pedido, padrao.LOOK.format(d=roupa), "keyframe",
                            self._base(db, alvo, pedido))

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        from sociman_api.assets import service as assets_service

        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        image = self._imagem(db, candidato.image_id)
        before = history.snapshot(asset)
        f = assets_service._attach(db, actor, asset, image, FileRole.referencia,
                                   {"look": geracao.params.get("rotulo")})
        f.geracao_id = geracao.id
        assets_service._record(db, actor, asset, "updated", before, details={
            "geracao_id": str(geracao.id), "candidato": {"id": str(candidato.id),
                                                         "numero": candidato.numero}})


class Pose(_LookPose):
    passo = "avatar.pose"
    extras_aceitos = frozenset({"quandoUsar"})

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: base.Pedido
                      ) -> dict[str, Any]:
        from sociman_api.assets import service as assets_service

        self._comum(db, alvo, pedido, por_rotulo=True)
        extras = self.conferir_extras(pedido.extras)
        rotulo = self._rotulo(pedido)
        if assets_service._pose_label_taken(alvo, rotulo):
            raise assets_service._pose_label_in_use()
        quando = (extras or {}).get("quandoUsar")
        if quando is not None and (not isinstance(quando, str) or len(quando) > QUANDO_USAR_MAX):
            raise base.entrada_invalida("extras.quandoUsar", f"até {QUANDO_USAR_MAX} caracteres")
        descricao = pedido.instrucao.strip()
        if not descricao:
            raise base.entrada_invalida("instrucao", "descreva a pose e a roupa vestida")
        return self._params(alvo, pedido, padrao.POSE.format(p=descricao), "keyframe",
                            self._base(db, alvo, pedido), extras)

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        from sociman_api.assets import service as assets_service

        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        rotulo = geracao.params.get("rotulo") or ""
        if assets_service._pose_label_taken(asset, rotulo):
            raise assets_service._pose_label_in_use()
        image = self._imagem(db, candidato.image_id)
        before = history.snapshot(asset)
        f = assets_service._attach(db, actor, asset, image, FileRole.pose, {
            "label": rotulo, "quando_usar": (geracao.params.get("extras") or {}).get(
                "quandoUsar")})
        f.geracao_id = geracao.id
        assets_service._record(db, actor, asset, "updated", before, details={
            "geracao_id": str(geracao.id), "candidato": {"id": str(candidato.id),
                                                         "numero": candidato.numero}})


APLICADORES: dict[str, base.Aplicador] = {
    "avatar.rosto_origem": RostoOrigem(), "avatar.rosto_frontal": RostoFrontal(),
    "avatar.rostos_34": Rostos34(), "avatar.corpo_base": CorpoBase(),
    "avatar.identidade": Identidade(), "avatar.look": Look(), "avatar.pose": Pose(),
}
