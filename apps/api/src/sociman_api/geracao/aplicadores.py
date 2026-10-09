"""Aplicadores dos passos (research R15 e R16): o que cada passo faz com o alvo.

O protocolo `Aplicador` (coordenado com a 025 e a 012 em 2026-10-07):
- `validar_alvo(db, perfil_id, alvo_id, lock=False)`: existência (404 `alvo_nao_encontrado`), o
  tipo (409 `alvo_incompativel`) e o arquivamento (409 `alvo_arquivado`); devolve o alvo. Desde a
  029 (R14) o `perfil_id` (o perfil base da geração, pode ser nulo) não restringe o alvo: a
  biblioteca é da agência e o perfil base do item é só o padrão (`perfil_do_alvo`);
- `montar_params(db, actor, alvo, pedido)`: monta e valida o `params` (a instrução, o prompt, as
  referências e o `extras`, com as chaves que o passo aceita; chave desconhecida → 400
  `entrada_invalida` com `field = "extras.<chave>"`);
- `conferir_referencias(db, geracao)`: no claim, o gerador confere de novo as referências
  (sumiu ou foi arquivada → `MotorErro("entrada_invalida")`, dizendo qual);
- `alvo_version(alvo)`: a versão do alvo, para o controle otimista da escolha;
- `aplicar(db, actor, geracao, candidato)`: leva o resultado ao alvo, com a versão do alvo
  (`details.geracao_id`) na mesma transação. Só nos passos com `aplica_alvo`; nos passos com
  escolha, só a escolha humana chama (o gerador só chama nos `sem_escolha`, teste-guarda);
- `ao_mudar_estado(db, geracao, de, para)`: opcional (o padrão não faz nada). A 021 o chama na
  mesma transação de toda transição; não faz chamada de rede, e uma exceção desfaz a transição.

Na 021 só existe o do **`cenario.cena`** (o piloto, FR-030): a opção vira um arquivo `referencia`
do cenário. Passo sem aplicador → 409 `passo_indisponivel`. A seta é `geracao → assets`: o
pacote `assets` não importa `geracao`.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.assets import service as assets_service
from sociman_api.assets.models import Asset, AssetFile, AssetTipo, FileRole
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.geracao import passos
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.models import Geracao, GeracaoCandidato, GeracaoStatus
from sociman_api.perfis.models import Image


def entrada_invalida(field: str, message: str) -> ApiError:
    return ApiError(400, "entrada_invalida", f"{field}: {message}", details={"field": field})


def alvo_nao_encontrado() -> ApiError:
    return ApiError(404, "alvo_nao_encontrado", "Alvo não encontrado")


def alvo_arquivado() -> ApiError:
    return ApiError(409, "alvo_arquivado", "Restaure o item antes de gerar ou escolher")


def alvo_incompativel() -> ApiError:
    return ApiError(409, "alvo_incompativel", "Este passo não se aplica a este item")


@dataclass(frozen=True)
class Pedido:
    """O pedido já validado pelo schema (`GeracaoIn`), sem o alvo."""

    passo: passos.Passo
    instrucao: str
    referencias: list[uuid.UUID]
    rotulo: str | None
    texto: str | None
    extras: dict[str, Any] | None


class Aplicador:
    """Base com os padrões; cada passo disponível tem uma subclasse em `APLICADORES`."""

    extras_aceitos: frozenset[str] = frozenset()

    def validar_alvo(self, db: Session, perfil_id: uuid.UUID | None, alvo_id: uuid.UUID, *,
                     lock: bool = False) -> Any:
        raise NotImplementedError

    def perfil_do_alvo(self, alvo: Any) -> uuid.UUID | None:
        """O perfil base do item: o padrão do `perfilBaseId` ausente (spec 029, R4)."""
        return getattr(alvo, "perfil_id", None)

    def montar_params(self, db: Session, actor: Actor, alvo: Any, pedido: Pedido
                      ) -> dict[str, Any]:
        raise NotImplementedError

    def conferir_referencias(self, db: Session, geracao: Geracao) -> None:
        for image_id in geracao.params.get("referencias") or []:
            referencia_de_asset_ativo(db, uuid.UUID(image_id), no_job=True)

    def alvo_version(self, alvo: Any) -> int:
        return alvo.version

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        raise NotImplementedError

    def ao_mudar_estado(self, db: Session, geracao: Geracao, de: GeracaoStatus | None,
                        para: GeracaoStatus) -> None:
        return None

    # ---- o que cada motor recebe (o gerador chama; sem rede aqui) ----

    def entradas_comfyui(self, geracao: Geracao, seed: int | None,
                         refs: list[bytes]) -> list[dict[str, Any]]:
        """Os parâmetros do bloco para uma opção (por nome, como o contrato `params.json`). Uma
        lista: o par do `avatar.rostos_34` roda o bloco duas vezes (esquerda e direita)."""
        p = geracao.params
        bloco = p.get("bloco")
        prefixo = f"sociman/{geracao.id}"
        if bloco == "cena":
            return [{"prompt": p["prompt"], "width": 768, "height": 1344, "seed": seed,
                     "prefix": prefixo}]
        if bloco == "keyframe":
            entrada = {"base_image": refs[0] if refs else None, "instruction": p["prompt"],
                       "seed": seed, "prefix": prefixo}
            for i, ref in enumerate(refs[1:3], start=1):
                entrada[f"ref{i}"] = ref
            return [entrada]
        if bloco == "retrato":
            return [{"prompt": p["prompt"], "seed": seed, "prefix": prefixo}]
        if bloco == "cutout":
            return [{"image": refs[0] if refs else None, "prefix": prefixo}]
        raise MotorErro("internal", detalhe=f"bloco desconhecido: {bloco}")

    def normalizar(self, png: bytes) -> bytes:
        """A imagem que o motor devolveu, antes de validar e gravar (padrão: como veio)."""
        return png

    def preparar_referencia(self, data: bytes) -> bytes:
        """A foto de referência antes de subir ao ComfyUI (padrão: como está no MinIO)."""
        return data

    def mensagem_claude(self, db: Session, geracao: Geracao) -> str | list[dict[str, Any]]:
        """A mensagem do usuário dos passos de texto (a entrada vai em tags de dado): texto ou
        blocos de conteúdo (a ficha do produto manda as fotos, spec 012)."""
        raise NotImplementedError

    def pedido_tts(self, db: Session, geracao: Geracao) -> dict[str, Any]:
        """O pedido do motor `tts`: `{"op": "register", "audio_id", "nome", "tom"}`,
        `{"op": "design", "nome", "descricao", "texto"?}` ou `{"op": "tts", "corpo": {...}}`."""
        raise NotImplementedError

    # ---- auxiliares para as subclasses ----

    def conferir_extras(self, extras: dict[str, Any] | None) -> dict[str, Any] | None:
        for chave in extras or {}:
            if chave not in self.extras_aceitos:
                raise entrada_invalida(f"extras.{chave}", "não aceito neste passo")
        return extras or None


def referencia_de_asset_ativo(db: Session, image_id: uuid.UUID, *,
                              no_job: bool = False) -> Image:
    """O padrão dos passos de asset: a imagem está num arquivo ativo de um asset ativo da
    biblioteca (de qualquer perfil base, spec 029 R8). No pedido → 400 `entrada_invalida`
    (`field = referencias`); no job (`no_job`) → `MotorErro("entrada_invalida")` com a mensagem
    de qual referência."""
    linha = db.execute(
        select(Image, AssetFile, Asset)
        .join(AssetFile, AssetFile.image_id == Image.id)
        .join(Asset, Asset.id == AssetFile.asset_id)
        .where(Image.id == image_id)
    ).first()
    ok = linha is not None and not linha[1].archived and not linha[2].archived
    if ok:
        return linha[0]
    if no_job:
        raise MotorErro("entrada_invalida",
                        f"A foto de referência {str(image_id)[:8]} foi arquivada ou não existe "
                        "mais")
    raise entrada_invalida("referencias",
                           "use uma foto de um item ativo da biblioteca")


class CenarioCena(Aplicador):
    """`cenario.cena` (FR-030): instrução → opções 768×1344 sem pessoas → arquivo do cenário.

    Sem foto, o bloco `cena` (FLUX schnell) com o prompt + `REALISMO`; com uma foto de
    referência, o `keyframe` (Qwen Edit) com a instrução + `MANTER` (R6). Escolher anexa a
    opção como arquivo `referencia` do cenário (`notes = "Gerado (opção N)"`); o primeiro vira o
    principal. A 025 troca isso pelo slot `cena`.
    """

    tipo = AssetTipo.cenario

    def validar_alvo(self, db: Session, perfil_id: uuid.UUID | None, alvo_id: uuid.UUID, *,
                     lock: bool = False) -> Asset:
        asset = db.get(Asset, alvo_id, with_for_update=lock)
        if asset is None:
            raise alvo_nao_encontrado()
        if asset.tipo != self.tipo:
            raise alvo_incompativel()
        if asset.archived:
            raise alvo_arquivado()
        return asset

    def montar_params(self, db: Session, actor: Actor, alvo: Asset, pedido: Pedido
                      ) -> dict[str, Any]:
        instrucao = pedido.instrucao.strip()
        if not instrucao:
            raise entrada_invalida("instrucao", "descreva a cena")
        if len(pedido.referencias) > 1:
            raise entrada_invalida("referencias", "no máximo uma foto de referência")
        if pedido.texto is not None:
            raise entrada_invalida("texto", "não se aplica a este passo")
        extras = self.conferir_extras(pedido.extras)
        refs = [referencia_de_asset_ativo(db, r) for r in pedido.referencias]
        base = instrucao.rstrip(". ")
        if refs:
            bloco, prompt = "keyframe", f"{base}. {passos.MANTER}"
        else:
            bloco, prompt = "cena", f"{base}. {passos.REALISMO}"
        return {"instrucao": instrucao, "prompt": prompt, "bloco": bloco,
                "referencias": [str(r.id) for r in refs], "rotulo": pedido.rotulo,
                "texto": None, "extras": extras}

    def normalizar(self, png: bytes) -> bytes:
        from sociman_api.geracao.comfyui import normalizar_9x16

        return normalizar_9x16(png)

    def preparar_referencia(self, data: bytes) -> bytes:
        from sociman_api.geracao.comfyui import normalizar_9x16

        return normalizar_9x16(data)  # como o `referencia` do `cenarios.py`

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        asset = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        image = db.get(Image, candidato.image_id) if candidato.image_id else None
        if image is None:
            raise ApiError(400, "candidato_invalido", "Esta opção não tem mais o arquivo")
        before = history.snapshot(asset)
        assets_service._attach(db, actor, asset, image, FileRole.referencia,
                               {"notes": f"Gerado (opção {candidato.numero})"})
        details = {"geracao_id": str(geracao.id),
                   "candidato": {"id": str(candidato.id), "numero": candidato.numero}}
        if geracao.status == GeracaoStatus.rodando:  # passo sem escolha (FR-010, FR-031)
            details["automatico"] = True
        assets_service._record(db, actor, asset, "updated", before, details=details)


APLICADORES: dict[str, Aplicador] = {
    "cenario.cena": CenarioCena(),
}


def _registrar_025() -> None:
    """Spec 025: os passos do avatar, do cenário (o `cenario.cena` substitui o piloto acima) e das
    vozes. Import tardio: os módulos dependem deste."""
    from sociman_api.geracao import aplicadores_avatar, aplicadores_cenario, aplicadores_voz

    APLICADORES.update(aplicadores_avatar.APLICADORES)
    APLICADORES.update(aplicadores_cenario.APLICADORES)
    APLICADORES.update(aplicadores_voz.APLICADORES)


def para(passo_id: str) -> Aplicador | None:
    return APLICADORES.get(passo_id)


def chamar_gancho(db: Session, geracao: Geracao, de: GeracaoStatus | None,
                  para_: GeracaoStatus) -> None:
    """`ao_mudar_estado` do aplicador do passo (sem aplicador, nada)."""
    aplicador = APLICADORES.get(geracao.passo)
    if aplicador is not None:
        aplicador.ao_mudar_estado(db, geracao, de, para_)


_registrar_025()
