"""Aplicadores dos passos `produto.*` da 021 (research R1, R5, R6 e R7): o que cada passo faz
no produto. Registrados em `geracao.aplicadores.APLICADORES` ao importar este módulo (o
`main.py` e o gerador importam).

- `produto.ficha` (motor `claude`, sem escolha): a mensagem leva as fotos numeradas; o
  resultado vai direto para a ficha e para as cores das variantes, com `ficha_por = ia`;
- `produto.recorte` (`cutout`, sem escolha): o recorte vai direto para a variante;
- `produto.flat` (`keyframe`, 2 opções): só a escolha humana aplica (o gerador nunca chama).

Toda aplicação grava **uma** versão do produto (o resultado e o status que o `fluxo.reavaliar`
decidiu), com `details.geracao_id`; nos passos sem escolha, `automatico = true` e o autor é
quem pediu. O produto arquivado continua recebendo o que já estava em andamento (R4); pedir,
escolher e gerar outras recusam (`validar_alvo`).
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from sociman_api import history, storage
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.geracao import aplicadores as base
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.models import Geracao, GeracaoCandidato, GeracaoStatus
from sociman_api.perfis.models import Image
from sociman_api.produtos import estados, ficha, fluxo
from sociman_api.produtos.models import CAMPOS_FICHA, ENTITY, Produto, ProdutoFichaPor


def _produto(db: Session, produto_id: uuid.UUID, lock: bool = False) -> Produto | None:
    return db.get(Produto, produto_id, with_for_update=lock)


def gravar_versao(db: Session, actor: Actor, produto: Produto, before: dict[str, Any] | None,
                  action: str = "updated", details: dict[str, Any] | None = None) -> bool:
    """Grava a versão se algo mudou (criação sempre grava). Devolve se gravou."""
    db.flush()
    after = history.snapshot(produto)
    if before is not None and after == before:
        return False
    produto.updated_by = actor.user_id
    history.record(db, actor, ENTITY, produto, action, before, after, details)
    return True


def _details(geracao: Geracao, candidato: GeracaoCandidato) -> dict[str, Any]:
    details: dict[str, Any] = {"geracao_id": str(geracao.id), "passo": geracao.passo,
                               "candidato": {"id": str(candidato.id),
                                             "numero": candidato.numero}}
    if geracao.status == GeracaoStatus.rodando:  # passo sem escolha (FR-010, FR-031)
        details["automatico"] = True
    return details


def _ator_do_pedido(geracao: Geracao) -> Actor:
    return Actor(kind="user", user_id=geracao.created_by)


class _ProdutoBase(base.Aplicador):
    extras_aceitos = frozenset({"varianteId", "nome"})

    def validar_alvo(self, db: Session, perfil_id: uuid.UUID, alvo_id: uuid.UUID, *,
                     lock: bool = False) -> Produto:
        produto = _produto(db, alvo_id, lock)
        if produto is None or produto.perfil_id != perfil_id:
            raise base.alvo_nao_encontrado()
        if produto.archived:
            raise base.alvo_arquivado()
        return produto

    def montar_params(self, db: Session, actor: Actor, alvo: Any, pedido: base.Pedido
                      ) -> dict[str, Any]:
        raise base.alvo_incompativel()  # o pedido genérico já recusa antes (R1)

    def conferir_referencias(self, db: Session, geracao: Geracao) -> None:
        """No claim: as referências são imagens de uma variante deste produto (a original, ou
        o recorte no flat)."""
        produto = _produto(db, geracao.alvo_id)
        if produto is None:
            raise MotorErro("entrada_invalida", "O produto não existe mais")
        validas = {i for v in produto.variantes_rel
                   for i in (v.original_image_id, v.recorte_image_id) if i}
        for ref in geracao.params.get("referencias") or []:
            if uuid.UUID(ref) not in validas or db.get(Image, uuid.UUID(ref)) is None:
                raise MotorErro("entrada_invalida",
                                f"A foto {ref[:8]} não é mais deste produto")

    def variante_do_pedido(self, produto: Produto, geracao: Geracao, *, humano: bool = False):
        vid = ((geracao.params or {}).get("extras") or {}).get("varianteId")
        variante = produto.variante(uuid.UUID(vid)) if vid else None
        if variante is None or variante.archived:
            mensagem = "A variante foi arquivada ou não é deste produto"
            if humano:
                raise base.entrada_invalida("candidatoId", mensagem)
            raise MotorErro("entrada_invalida", mensagem)
        return variante

    def ao_mudar_estado(self, db: Session, geracao: Geracao, de: GeracaoStatus | None,
                        para: GeracaoStatus) -> None:
        """Rede de segurança (R8): ao terminar com sucesso, reavaliar o produto. O `aplicar` já
        reavalia na mesma versão; aqui só sobra algo se outra ação mudou o produto no meio."""
        if de is None or para != GeracaoStatus.escolhido:
            return
        produto = _produto(db, geracao.alvo_id, lock=True)
        if produto is None:
            return
        before = history.snapshot(produto)
        ator = _ator_do_pedido(geracao)
        fluxo.reavaliar(db, ator, produto)
        gravar_versao(db, ator, produto, before, details={"geracao_id": str(geracao.id)})


class ProdutoFicha(_ProdutoBase):
    """`produto.ficha`: uma chamada com as fotos; o resultado vai direto para o produto."""

    def mensagem_claude(self, db: Session, geracao: Geracao) -> list[dict[str, Any]]:
        p = geracao.params or {}
        fotos = []
        for ref in p.get("referencias") or []:
            img = db.get(Image, uuid.UUID(ref))
            if img is None:
                raise MotorErro("entrada_invalida", f"A foto {ref[:8]} não existe mais")
            fotos.append(storage.get(img.object_key))
        nome = (p.get("extras") or {}).get("nome") or ""
        return ficha.montar_mensagem(fotos, nome, p.get("instrucao") or "")

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        produto = _produto(db, geracao.alvo_id, lock=True)
        if produto is None:
            raise MotorErro("entrada_invalida", "O produto não existe mais")
        if produto.ficha_por is not None:  # a IA nunca sobrescreve a ficha à mão (R9)
            raise MotorErro("entrada_invalida", "A ficha já foi preenchida")
        dados = (candidato.metricas or {}).get("ficha")
        if not isinstance(dados, dict):
            raise MotorErro("internal", detalhe="candidato da ficha sem a ficha")
        before = history.snapshot(produto)
        for campo in CAMPOS_FICHA:
            setattr(produto, campo, dados[campo])
        produto.ficha_por = ProdutoFichaPor.ia
        # A foto N do pedido é a N-ésima referência (a original de uma variante).
        cores = {c["foto"]: c for c in dados.get("cores") or []}
        originais = {v.original_image_id: v for v in produto.variantes_rel}
        for n, ref in enumerate(geracao.params.get("referencias") or [], start=1):
            variante = originais.get(uuid.UUID(ref))
            cor = cores.get(n)
            if variante is not None and cor is not None and variante.cor_en is None \
                    and variante.cor_pt is None:
                variante.cor_en, variante.cor_pt = cor["en"], cor["pt"]
        fluxo.reavaliar(db, actor, produto)
        gravar_versao(db, actor, produto, before,
                      details={**_details(geracao, candidato),
                               "prompt_version": ficha.PROMPT_VERSION})


class ProdutoRecorte(_ProdutoBase):
    """`produto.recorte`: o candidato único vai direto para a variante (R6)."""

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        produto = _produto(db, geracao.alvo_id, lock=True)
        if produto is None:
            raise MotorErro("entrada_invalida", "O produto não existe mais")
        variante = self.variante_do_pedido(produto, geracao)
        if candidato.image_id is None:
            raise MotorErro("internal", detalhe="recorte sem imagem")
        before = history.snapshot(produto)
        variante.recorte_image_id = candidato.image_id
        fluxo.reavaliar(db, actor, produto)
        gravar_versao(db, actor, produto, before, details=_details(geracao, candidato))


class ProdutoFlat(_ProdutoBase):
    """`produto.flat`: 2 opções; a escolhida vai para a variante, com a geração (R3, R7)."""

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        produto = _produto(db, geracao.alvo_id, lock=True)
        if produto is None:
            raise base.alvo_nao_encontrado()
        variante = self.variante_do_pedido(produto, geracao, humano=True)
        refs = geracao.params.get("referencias") or []
        if not refs or uuid.UUID(refs[0]) != variante.recorte_image_id:
            raise base.entrada_invalida(
                "candidatoId", "o recorte da variante mudou depois deste pedido; peça outro flat")
        if candidato.image_id is None:
            raise ApiError(400, "candidato_invalido", "Esta opção não tem mais o arquivo")
        before = history.snapshot(produto)
        variante.flat_image_id = candidato.image_id
        variante.flat_geracao_id = geracao.id
        fluxo.reavaliar(db, actor, produto, evento="gancho")
        gravar_versao(db, actor, produto, before, details=_details(geracao, candidato))


def registrar() -> None:
    base.APLICADORES.update({estados.FICHA: ProdutoFicha(), estados.RECORTE: ProdutoRecorte(),
                             estados.FLAT: ProdutoFlat()})


registrar()
