"""“Adotar no catálogo” (US6, FR-053): copia a ficha atual e as imagens de um produto do lago para
um produto da spec 012 (`produtos`) do perfil, com o vínculo `produtos.mercado_produto_id`, e cria
o interesse `manual` se não existir. **Só humano** (`RequireHuman`).

Dependência: a 012 nesta instalação (pacote `sociman_api.produtos` e a tabela `produtos`, ligados
pela migration `0026_uniao_mercado`). Sem ela, a ação responde 409 `passo_indisponivel` e nada é
gravado; o restante da 026 não depende disto.
"""

import importlib
import io
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from sociman_api import history, imaging, storage
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.mercado import interesses
from sociman_api.mercado.models import (
    Categoria,
    Ficha,
    Imagem,
    Interesse,
    InteresseOrigem,
    InteresseSituacao,
    Loja,
    Produto,
    ProdutoImagem,
)

log = logging.getLogger(__name__)

INDISPONIVEL = ApiError(409, "passo_indisponivel",
                        "Adotar no catálogo fica disponível quando o cadastro de produtos (spec 012) "
                        "estiver nesta instalação")


def catalogo_disponivel(db: Session) -> bool:
    """A 012 existe quando o pacote importa e a tabela `produtos` tem a coluna de ligação."""
    try:
        importlib.import_module("sociman_api.produtos.service")
    except ImportError:
        return False
    insp = inspect(db.get_bind())
    return insp.has_table("produtos") and any(
        c["name"] == "mercado_produto_id" for c in insp.get_columns("produtos"))


def ja_adotado(db: Session, mercado_produto_id: uuid.UUID, perfil_id: uuid.UUID) -> uuid.UUID | None:
    """O produto da 012 deste perfil já vinculado a este produto do lago (se a 012 existir)."""
    if not catalogo_disponivel(db):
        return None
    return db.execute(text("SELECT id FROM produtos WHERE perfil_id = :p AND mercado_produto_id = :m "
                           "ORDER BY created_at LIMIT 1"),
                      {"p": perfil_id, "m": mercado_produto_id}).scalar()


def adotados_em(db: Session, mercado_produto_id: uuid.UUID) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """`(perfil_id, produto_id)` dos produtos da 012 já vinculados (vazio sem a 012)."""
    if not catalogo_disponivel(db):
        return []
    return [(r[0], r[1]) for r in db.execute(text(
        "SELECT perfil_id, id FROM produtos WHERE mercado_produto_id = :m AND perfil_id IS NOT NULL "
        "ORDER BY created_at"), {"m": mercado_produto_id}).all()]


def adotar(db: Session, actor: Actor, mercado_produto_id: uuid.UUID, perfil_id: uuid.UUID
           ) -> dict[str, uuid.UUID]:
    """Cria o produto da 012 a partir da ficha e da galeria; devolve `{produtoId, interesseId}`."""
    interesses.perfil_ou_404(db, perfil_id)
    produto = db.get(Produto, mercado_produto_id)
    if produto is None:
        raise ApiError(404, "produto_nao_encontrado", "Produto de mercado não encontrado")
    if not catalogo_disponivel(db):
        raise INDISPONIVEL
    existente = ja_adotado(db, produto.id, perfil_id)
    if existente is not None:
        raise ApiError(409, "ja_adotado", "Este perfil já adotou este produto",
                       details={"produtoId": str(existente)})
    ficha = db.get(Ficha, produto.ficha_atual_id) if produto.ficha_atual_id else None
    if ficha is None:
        raise ApiError(409, "ficha_ausente", "A ficha ainda não foi coletada; aguarde a 1ª visita")
    produto_id = _adotar_com_012(db, actor, produto, ficha, perfil_id)
    vivo = db.scalar(select(Interesse).where(
        Interesse.perfil_id == perfil_id, Interesse.mercado_produto_id == produto.id,
        Interesse.origem == InteresseOrigem.manual,
        Interesse.situacao.in_((InteresseSituacao.ativo, InteresseSituacao.pausado))))
    if vivo is None:
        vivo = interesses.criar(db, actor, perfil_id, produto.id, InteresseOrigem.manual,
                                {"url": produto.url_canonica, "adotadoEm": str(produto_id)})
        interesses.aquecer(produto, datetime.now(UTC), 2)
    return {"produtoId": produto_id, "interesseId": vivo.id}


def _galeria(db: Session, ficha: Ficha) -> list[Imagem]:
    return list(db.scalars(select(Imagem).join(ProdutoImagem, ProdutoImagem.imagem_id == Imagem.id)
                           .where(ProdutoImagem.ficha_id == ficha.id)
                           .order_by(ProdutoImagem.posicao)))


def _adotar_com_012(db: Session, actor: Actor, produto: Produto, ficha: Ficha,
                    perfil_id: uuid.UUID) -> uuid.UUID:
    """A cópia em si: nome = título, categoria = caminho, `url_loja` da loja, obs = argumentos e
    descrição, até `MAX_VARIANTES` imagens copiadas para `images` do perfil (kind `produto`, pela
    validação da 012: imagens pequenas demais são ignoradas e contadas), e a versão da 012 com
    `details.origem = "mercado_026"`."""
    from sociman_api.produtos import service as produtos_service
    from sociman_api.produtos.aplicadores import gravar_versao

    fotos: list[io.BytesIO] = []
    ignoradas = 0
    for img in _galeria(db, ficha):
        if len(fotos) >= produtos_service.MAX_VARIANTES:
            break
        dados = storage.get(img.object_key, bucket="imagens")  # as imagens ficam no bucket de imagens (`mercado/<sha>`), o bruto no `mercado`
        try:
            imaging.validate_image(dados, "produto", max_bytes=produtos_service.MAX_BYTES)
        except ApiError as exc:
            log.info("adotar: imagem %s ignorada (%s)", img.sha256[:8], exc.message)
            ignoradas += 1
            continue
        fotos.append(io.BytesIO(dados))
    loja = db.get(Loja, ficha.loja_id) if ficha.loja_id else None
    categoria = db.get(Categoria, ficha.categoria_id) if ficha.categoria_id else None
    partes = [f"- {a}" for a in ficha.argumentos]
    if ficha.descricao:
        partes.append(ficha.descricao)
    obs = "\n".join(partes)[:5000]
    # `url_loja` da 012 recebe a URL da loja quando a rede a expôs; senão a página do produto,
    # que é o que o dono vai abrir para conferir.
    url_loja = loja.url if (loja is not None and loja.url) else produto.url_canonica
    p012 = produtos_service.criar(db, actor, perfil_id, ficha.titulo[:200], obs, url_loja, fotos)
    before = history.snapshot(p012)
    p012.mercado_produto_id = produto.id
    if categoria is not None and not p012.categoria:
        p012.categoria = categoria.caminho
    gravar_versao(db, actor, p012, before, "updated",
                  {"origem": "mercado_026", "mercadoProdutoId": str(produto.id),
                   "fichaId": str(ficha.id), "imagensCopiadas": len(fotos),
                   "imagensIgnoradas": ignoradas})
    return p012.id
