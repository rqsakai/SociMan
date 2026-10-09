"""“Adotar no catálogo” (US6, FR-053): copia a ficha atual e as imagens de um produto do lago para
um produto da spec 012 (`produtos`) do perfil, com o vínculo `produtos.mercado_produto_id`, e cria
o interesse `manual` se não existir. **Só humano** (`RequireHuman`).

Dependência: a 012 mesclada nesta branch (pacote `sociman_api.produtos` e a tabela `produtos`). Sem
ela, a ação responde 409 `passo_indisponivel` e nada é gravado; o restante da 026 não depende disto.
"""

import importlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.mercado import interesses
from sociman_api.mercado.models import Ficha, Interesse, InteresseOrigem, InteresseSituacao, Produto

INDISPONIVEL = ApiError(409, "passo_indisponivel",
                        "Adotar no catálogo fica disponível quando o cadastro de produtos (spec 012) "
                        "estiver nesta instalação")


def catalogo_disponivel(db: Session) -> bool:
    """A 012 existe quando o pacote importa e a tabela `produtos` está no banco."""
    try:
        importlib.import_module("sociman_api.produtos.service")
    except ImportError:
        return False
    return inspect(db.get_bind()).has_table("produtos")


def ja_adotado(db: Session, mercado_produto_id: uuid.UUID, perfil_id: uuid.UUID) -> uuid.UUID | None:
    """O produto da 012 deste perfil já vinculado a este produto do lago (se a 012 existir)."""
    if not inspect(db.get_bind()).has_table("produtos"):
        return None
    return db.execute(text("SELECT id FROM produtos WHERE perfil_id = :p AND mercado_produto_id = :m "
                           "ORDER BY created_at LIMIT 1"),
                      {"p": perfil_id, "m": mercado_produto_id}).scalar()


def adotados_em(db: Session, mercado_produto_id: uuid.UUID) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """`(perfil_id, produto_id)` dos produtos da 012 já vinculados (vazio sem a 012)."""
    if not inspect(db.get_bind()).has_table("produtos"):
        return []
    return [(r[0], r[1]) for r in db.execute(text(
        "SELECT perfil_id, id FROM produtos WHERE mercado_produto_id = :m ORDER BY created_at"),
        {"m": mercado_produto_id}).all()]


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


def _adotar_com_012(db: Session, actor: Actor, produto: Produto, ficha: Ficha,
                    perfil_id: uuid.UUID) -> uuid.UUID:
    """A cópia em si (nome = título, categoria = caminho, url da loja, obs = argumentos, até 6
    variantes, imagens copiadas para `images` do perfil, `history.record` da 012 com
    `details.origem = "mercado_026"`). Fica para quando a 012 estiver mesclada nesta branch: o
    service dela ainda não existe aqui, e a cópia não pode ser escrita às cegas."""
    raise INDISPONIVEL
