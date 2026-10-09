"""Produtos (spec 012, contracts/api.md, research R2, R4 e R8–R12, R16; spec 029: da agência,
com perfil base opcional).

Toda mutação trava a linha do produto, confere a `version` (409 `version_conflict`), recusa
produto arquivado e grava **uma** versão do produto na mesma transação
(`history.record`), com as variantes no snapshot. Nada é apagado: produtos e variantes são
arquivados; a reversão (só o dono humano) volta a ficha e as imagens sem gerar nada.

As fotos são validadas **todas** antes de gravar qualquer uma (nada fica pela metade): HD
conferido (`datadir`, 503/507), até 20 MB cada, PNG/JPG/WebP ≥ 512×512, no bucket `imagens`.
Depois de cada mudança, `fluxo.reavaliar` decide o status e pede as gerações que faltam.

Spec 029: criar com perfil base arquivado continua recusado (`perfil_archived`), mas o produto de
um perfil arquivado segue editável (FR-010); o perfil base muda pelo PATCH, numa versão.
"""

import base64
import binascii
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, BinaryIO

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from sociman_api import datadir, history, imaging, midia, storage
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.estudio.nomes import perfil_nomes
from sociman_api.geracao import service as geracao_service
from sociman_api.geracao.models import FINAIS, Geracao, GeracaoStatus
from sociman_api.perfis import base as perfil_base
from sociman_api.perfis.models import Image, ImageKind, Perfil
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_imagens import read_limited
from sociman_api.perfis.service_perfis import (
    apply_archived,
    get_perfil_or_404,
    target_state,
    user_refs,
    versions_out,
)
from sociman_api.produtos import aplicadores as _aplicadores  # noqa: F401 — registra os passos
from sociman_api.produtos import estados, ficha, flat, fluxo, schemas, usos
from sociman_api.produtos.aplicadores import gravar_versao
from sociman_api.produtos.models import (
    CAMPOS_FICHA,
    ENTITY,
    MAX_VARIANTES,
    Produto,
    ProdutoFichaPor,
    ProdutoStatus,
    ProdutoVariante,
)

LABEL = "Este produto"
NOT_FOUND = "Produto não encontrado"
MAX_BYTES = 20 * 1024 * 1024
LIMITE_PADRAO = 48
LIMITE_MAX = 100
_TEXTOS = ("nome_comercial", "categoria", "material_en", "material_pt", "formato_corte",
           "tamanho_relativo", "descricao_prompt", "descricao_venda")
_ACENTOS = ("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
_DOBRA = str.maketrans(*_ACENTOS)


# ---- auxiliares ----

def get_or_404(db: Session, produto_id: uuid.UUID, lock: bool = False) -> Produto:
    produto = db.get(Produto, produto_id, with_for_update=lock)
    if produto is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return produto


def _perfil_ativo(db: Session, perfil_id: uuid.UUID | None) -> Perfil | None:
    """O perfil base de um produto novo: sem perfil passa; arquivado é recusado."""
    if perfil_id is None:
        return None
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    return perfil


def perfil_base_novo(db: Session, perfil_id: uuid.UUID | None) -> None:
    """O `perfilId` da rota da agência: inexistente → 400 `perfil_invalido`; arquivado → 409."""
    if perfil_base.perfil_existente(db, perfil_id) is not None:
        _perfil_ativo(db, perfil_id)


def _editavel(db: Session, produto_id: uuid.UUID, version: int) -> Produto:
    produto = get_or_404(db, produto_id, lock=True)
    history.check_version(produto, version, LABEL)
    if produto.archived:
        raise ApiError(409, "produto_arquivado", "Restaure o produto antes de editar")
    return produto


def _variante_or_404(produto: Produto, variante_id: uuid.UUID) -> ProdutoVariante:
    variante = produto.variante(variante_id)
    if variante is None:
        raise ApiError(404, "not_found", "Variante não encontrada")
    return variante


def _limite_variantes() -> ApiError:
    return ApiError(409, "limite_variantes",
                    f"No máximo {MAX_VARIANTES} variantes ativas por produto")


def _renumerar(produto: Produto) -> None:
    for i, v in enumerate(produto.ativas()):
        v.position = i


def _ler_foto(stream: BinaryIO, field: str) -> tuple[bytes, imaging.ImageInfo]:
    """Lê até 20 MB e valida pelo conteúdo; o erro diz qual foto (`fotos[N]`)."""
    try:
        data = read_limited(stream, max_bytes=MAX_BYTES)
        info = imaging.validate_image(data, "produto", max_bytes=MAX_BYTES,
                                      too_large_message="Imagem grande demais (máximo 40 "
                                                        "megapixels)")
    except ApiError as exc:
        mensagem = exc.message
        if mensagem == "Imagem pequena demais":
            mensagem = "Imagem pequena demais (mínimo 512×512)"
        raise ApiError(400, "invalid_image", f"{field}: {mensagem}",
                       details={"field": field}) from exc
    return data, info


def _gravar_foto(db: Session, actor: Actor, perfil_id: uuid.UUID | None, data: bytes,
                 info: imaging.ImageInfo) -> Image:
    key = imaging.object_key(perfil_id, info.ext)
    # O objeto vai antes do commit; se a transação falhar, sobra um objeto sem referência
    # (nunca apagamos objetos), o que é inofensivo.
    storage.put(key, data, info.content_type)
    image = Image(perfil_id=perfil_id, kind=ImageKind.produto, object_key=key,
                  content_type=info.content_type, bytes=info.bytes, width=info.width,
                  height=info.height, sha256=info.sha256, created_by=actor.user_id)
    db.add(image)
    db.flush()
    return image


def _nova_variante(db: Session, actor: Actor, produto: Produto, image: Image) -> ProdutoVariante:
    v = ProdutoVariante(produto_id=produto.id, position=len(produto.ativas()),
                        original_image_id=image.id, created_by=actor.user_id)
    db.add(v)
    produto.variantes_rel.append(v)
    db.flush()
    return v


def _cancelar_abertas(db: Session, actor: Actor, produto: Produto, passo: str | None = None
                      ) -> None:
    """Cancela as gerações do produto ainda não finais (inclusive `falhou`), pela 021."""
    for g in fluxo.geracoes(db, produto.id):
        if g.status not in FINAIS and (passo is None or g.passo == passo):
            geracao_service.cancelar(db, actor, g.id, g.version)


# ---- leitura ----

def _imagem_ref(img: Image | None) -> schemas.ImagemRef | None:
    if img is None:
        return None
    link = midia.link("imagem", img.id, ttl=None).url
    return schemas.ImagemRef(image_id=img.id, largura=img.width, altura=img.height,
                             thumb_url=imaging.image_urls(img.object_key)["thumb"], url=link,
                             download_url=f"{link}?download=1")


def _imagens(db: Session, produtos: Sequence[Produto]) -> dict[uuid.UUID, Image]:
    ids = {i for p in produtos for v in p.variantes_rel
           for i in (v.original_image_id, v.recorte_image_id, v.flat_image_id) if i}
    return {i.id: i for i in db.scalars(select(Image).where(Image.id.in_(ids)))} if ids else {}


def _ficha_out(produto: Produto) -> schemas.Ficha | None:
    if produto.ficha_por is None and not any(getattr(produto, c) for c in _TEXTOS):
        return None
    return schemas.Ficha(**{c: getattr(produto, c) for c in CAMPOS_FICHA})


def _avisos(produto: Produto, v: ProdutoVariante, gs: dict[uuid.UUID, Geracao]) -> list[str]:
    avisos: list[str] = []
    if v.flat_geracao_id is not None:
        g = gs.get(v.flat_geracao_id)
        gravada = (g.params or {}).get("instrucao") if g else None
        if gravada is not None and gravada != flat.instrucao(produto, v):
            avisos.append("flat_desatualizado")
    if not v.archived and not estados.tem_cor(v):
        avisos.append("sem_cor")
    return avisos


def _passos(gs: list[Geracao]) -> list[schemas.PassoProduto]:
    """As não finais e a última de cada passo × variante, da mais nova para a mais antiga."""
    ultima: dict[tuple[str, uuid.UUID | None], Geracao] = {}
    for g in gs:
        ultima[(g.passo, fluxo._variante_id(g))] = g
    escolhidas = {g.id for g in gs if g.status not in FINAIS} | {g.id for g in ultima.values()}
    out = []
    for g in reversed(gs):
        if g.id not in escolhidas:
            continue
        erro = schemas.ErroPasso(code=g.error_code, message=g.error_message or "") \
            if g.error_code else None
        out.append(schemas.PassoProduto(
            id=g.id, passo=g.passo, variante_id=fluxo._variante_id(g), status=g.status,
            progress=g.progress, etapa_mensagem=g.etapa_mensagem, erro=erro,
            n_opcoes=g.n_opcoes, version=g.version, created_at=g.created_at))
    return out


def produto_out(db: Session, produto: Produto) -> schemas.Produto:
    db.flush()
    db.refresh(produto)  # updated_at vem do banco
    imgs = _imagens(db, [produto])
    gs = fluxo.geracoes(db, produto.id)
    por_id = {g.id: g for g in gs}
    users = user_refs(db, [produto.created_by, produto.updated_by])
    variantes = [
        schemas.Variante(
            id=v.id, position=v.position, cor_en=v.cor_en, cor_pt=v.cor_pt,
            original=_imagem_ref(imgs[v.original_image_id]),
            recorte=_imagem_ref(imgs.get(v.recorte_image_id)) if v.recorte_image_id else None,
            flat=_imagem_ref(imgs.get(v.flat_image_id)) if v.flat_image_id else None,
            flat_geracao_id=v.flat_geracao_id, avisos=_avisos(produto, v, por_id),
            archived_at=v.archived_at)
        for v in sorted(produto.variantes_rel, key=lambda x: (x.archived, x.position))]
    pendencias = [schemas.Pendencia(variante_id=p.variante_id, motivo=p.motivo)
                  for p in estados.pendencias(produto, produto.ativas(), fluxo.abertas(gs))]
    return schemas.Produto(
        id=produto.id, perfil_id=produto.perfil_id,
        perfil_nome=perfil_nomes(db, [produto.perfil_id]).get(produto.perfil_id),
        name=produto.name, obs=produto.obs,
        url_loja=produto.url_loja, status=produto.status, estado=produto.estado,
        ficha_por=produto.ficha_por, ficha=_ficha_out(produto), variantes=variantes,
        passos=_passos(gs), pendencias=pendencias, usos=usos.do_produto(db, produto.id),
        version=produto.version, archived_at=produto.archived_at,
        created_at=produto.created_at,
        created_by=users.get(produto.created_by) if produto.created_by else None,
        updated_at=produto.updated_at,
        updated_by=users.get(produto.updated_by) if produto.updated_by else None)


def ver(db: Session, produto_id: uuid.UUID) -> schemas.Produto:
    return produto_out(db, get_or_404(db, produto_id))


def versoes(db: Session, produto_id: uuid.UUID) -> VersionsList:
    get_or_404(db, produto_id)
    return versions_out(db, ENTITY, produto_id)


def _encode(updated_at: datetime, pid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{updated_at.isoformat()}|{pid}".encode()).rstrip(
        b"=").decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, pid = raw.split("|")
        return datetime.fromisoformat(ts), uuid.UUID(pid)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ApiError(400, "validation_error", "cursor: inválido") from None


def _sem_acento(col):
    return func.translate(func.lower(col), *_ACENTOS)


def _termo(q: str) -> str:
    termo = q.strip().lower().translate(_DOBRA)
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar(db: Session, perfil_id: uuid.UUID, **kw) -> schemas.ProdutosLista:
    """A lista por perfil (012, obsoleta na 029): a da agência com aquele perfil base."""
    get_perfil_or_404(db, perfil_id)
    return listar_agencia(db, perfil_id, **kw)


def listar_agencia(db: Session, filtro: perfil_base.Filtro, *,
                   status: Sequence[ProdutoStatus] = (), arquivados: str = "false",
                   q: str | None = None, cursor: str | None = None,
                   limit: int = LIMITE_PADRAO) -> schemas.ProdutosLista:
    """Spec 029: `filtro` None = todos; `sem` = sem perfil base; ou um perfil."""
    stmt = perfil_base.aplicar_filtro(select(Produto), Produto.perfil_id, filtro)
    if arquivados == "false":
        stmt = stmt.where(Produto.archived_at.is_(None))
    elif arquivados == "so":
        stmt = stmt.where(Produto.archived_at.is_not(None))
    if status:
        stmt = stmt.where(Produto.status.in_(list(status)))
    if q and q.strip():
        termo = f"%{_termo(q)}%"
        stmt = stmt.where(or_(_sem_acento(Produto.name).like(termo, escape="\\"),
                              _sem_acento(func.coalesce(Produto.nome_comercial, "")).like(
                                  termo, escape="\\")))
    if cursor:
        ts, last = _decode(cursor)
        stmt = stmt.where(or_(Produto.updated_at < ts,
                              and_(Produto.updated_at == ts, Produto.id > last)))
    limit = max(1, min(limit, LIMITE_MAX))
    rows = list(db.scalars(stmt.order_by(Produto.updated_at.desc(), Produto.id)
                           .limit(limit + 1)))
    page, mais = rows[:limit], len(rows) > limit
    imgs = _imagens(db, page)
    nomes = perfil_nomes(db, [p.perfil_id for p in page])
    itens = []
    for p in page:
        ativas = p.ativas()
        capa = None
        if ativas:
            img = imgs.get(ativas[0].recorte_image_id or ativas[0].original_image_id)
            capa = imaging.image_urls(img.object_key)["thumb"] if img else None
        itens.append(schemas.ProdutoResumo(
            id=p.id, perfil_id=p.perfil_id,
            perfil_nome=nomes.get(p.perfil_id) if p.perfil_id else None, name=p.name, nome_comercial=p.nome_comercial, categoria=p.categoria,
            status=p.status, estado=p.estado, variantes_ativas=len(ativas), thumb_url=capa,
            updated_at=p.updated_at, version=p.version))
    proximo = _encode(page[-1].updated_at, page[-1].id) if mais else None
    return schemas.ProdutosLista(itens=itens, proximo_cursor=proximo)


# ---- criar e editar (US1) ----

def criar(db: Session, actor: Actor, perfil_id: uuid.UUID | None, name: str, obs: str,
          url_loja: str | None, fotos: Sequence[BinaryIO]) -> Produto:
    _perfil_ativo(db, perfil_id)
    if len(fotos) > MAX_VARIANTES:
        raise _limite_variantes()
    if fotos:
        datadir.ensure_writable()  # HD fora ou cheio: 503/507 antes de ler as fotos
    lidas = [_ler_foto(f, f"fotos[{i}]") for i, f in enumerate(fotos)]
    produto = Produto(perfil_id=perfil_id, name=name, obs=obs, url_loja=url_loja,
                      created_by=actor.user_id, updated_by=actor.user_id)
    db.add(produto)
    db.flush()
    for data, info in lidas:
        _nova_variante(db, actor, produto, _gravar_foto(db, actor, perfil_id, data, info))
    fluxo.reavaliar(db, actor, produto, "edicao")
    gravar_versao(db, actor, produto, None, "created")
    return produto


def editar(db: Session, actor: Actor, produto_id: uuid.UUID,
           body: schemas.ProdutoPatch) -> Produto:
    produto = _editavel(db, produto_id, body.version)
    mudancas = body.model_dump(exclude_unset=True, exclude={"version"})
    if "perfil_id" in mudancas:  # spec 029: o perfil base (arquivado é aceito)
        perfil_base.perfil_existente(db, mudancas["perfil_id"])
    before = history.snapshot(produto)
    for campo in ("name", "obs"):
        if mudancas.get(campo) is not None:
            setattr(produto, campo, mudancas[campo])
    if "url_loja" in mudancas:
        produto.url_loja = mudancas["url_loja"]
    if "perfil_id" in mudancas:
        produto.perfil_id = mudancas["perfil_id"]
    gravar_versao(db, actor, produto, before)
    return produto


def pedir_ficha(db: Session, actor: Actor, produto_id: uuid.UUID, version: int) -> Geracao:
    """Pede (de novo) a ficha ao Claude: sem ficha e sem `produto.ficha` não final."""
    produto = _editavel(db, produto_id, version)
    if produto.ficha_por is not None:
        raise ApiError(409, "ficha_existente", "Este produto já tem ficha; edite a ficha")
    if any(g.passo == estados.FICHA and g.status not in FINAIS
           for g in fluxo.geracoes(db, produto.id)):
        raise ApiError(409, "estado_invalido", "Já há um pedido de ficha; tente de novo ou "
                                               "cancele antes")
    if not produto.ativas():
        raise ApiError(409, "produto_incompleto", "Envie pelo menos uma foto",
                       details={"pendencias": [{"varianteId": None, "motivo": "sem_variante"}]})
    return fluxo.pedir(db, actor, produto, estados.FICHA)


# ---- recorte e flat (US2) ----

def refazer_flat(db: Session, actor: Actor, produto_id: uuid.UUID, variante_id: uuid.UUID,
                 version: int) -> Geracao:
    produto = _editavel(db, produto_id, version)
    variante = _variante_or_404(produto, variante_id)
    if variante.archived:
        raise ApiError(409, "estado_invalido", "Restaure a variante antes")
    if not produto.precisa_flat:
        raise ApiError(409, "estado_invalido", "Este produto não usa flat lay")
    ultima = next((g for g in reversed(fluxo.geracoes(db, produto.id))
                   if g.passo == estados.FLAT and fluxo._variante_id(g) == variante.id), None)
    if ultima is not None and ultima.status == GeracaoStatus.revisao:
        raise ApiError(409, "estado_invalido", "Há opções esperando escolha: use Gerar outras")
    if ultima is not None and ultima.status not in FINAIS | {GeracaoStatus.falhou}:
        raise ApiError(409, "estado_invalido", "Já há um flat em andamento para esta variante")
    if not estados.campos_completos(produto) or produto.ficha_por is None \
            or not estados.tem_cor(variante) or variante.recorte_image_id is None:
        pend = [p for p in estados.pendencias(produto, [variante], [])
                if p.motivo in ("ficha_incompleta", "sem_cor", "sem_recorte")]
        raise ApiError(409, "produto_incompleto", "Complete a ficha e o recorte antes",
                       details={"pendencias": [{"varianteId": str(p.variante_id)
                                                if p.variante_id else None, "motivo": p.motivo}
                                               for p in pend]})
    before = history.snapshot(produto)
    g = fluxo.pedir(db, actor, produto, estados.FLAT, variante)
    fluxo.reavaliar(db, actor, produto, "edicao")
    gravar_versao(db, actor, produto, before, details={"acao": "refazer_flat",
                                                       "geracao_id": str(g.id)})
    return g


def refazer_recorte(db: Session, actor: Actor, produto_id: uuid.UUID, variante_id: uuid.UUID,
                    version: int) -> Geracao:
    """O recorte que falhou ou foi cancelado não volta sozinho (R8): o humano pede de novo."""
    produto = _editavel(db, produto_id, version)
    variante = _variante_or_404(produto, variante_id)
    if variante.archived:
        raise ApiError(409, "estado_invalido", "Restaure a variante antes")
    if variante.recorte_image_id is not None:
        raise ApiError(409, "estado_invalido", "Esta variante já tem recorte")
    if produto.ficha_por is None:
        raise ApiError(409, "produto_incompleto", "A ficha vem antes do recorte",
                       details={"pendencias": [{"varianteId": None,
                                                "motivo": "ficha_incompleta"}]})
    if any(g.passo == estados.RECORTE and fluxo._variante_id(g) == variante.id
           and g.status not in FINAIS | {GeracaoStatus.falhou}
           for g in fluxo.geracoes(db, produto.id)):
        raise ApiError(409, "estado_invalido", "Já há um recorte em andamento para esta variante")
    return fluxo.pedir(db, actor, produto, estados.RECORTE, variante)


# ---- ficha, variantes e aprovar (US3) ----

def _vazio_para_none(valor: str) -> str | None:
    return valor if valor.strip() else None


def salvar_ficha(db: Session, actor: Actor, produto_id: uuid.UUID,
                 body: schemas.SalvarFichaIn) -> Produto:
    produto = _editavel(db, produto_id, body.version)
    # Vazio = não preenchido (a ficha à mão pode ir por partes; completa só para aprovar, R9).
    campos: dict[str, Any] = {}
    for campo, valor in body.ficha.model_dump().items():
        if isinstance(valor, str):
            valor = _vazio_para_none(valor)
        elif isinstance(valor, list):
            valor = [item for item in valor if item.strip()]
        campos[campo] = valor
    for campo, mensagem in ficha.problemas_campos(campos):
        raise schemas.invalid(campo, mensagem)
    ativas = {v.id: v for v in produto.ativas()}
    for i, cor in enumerate(body.cores):
        if cor.variante_id not in ativas:
            raise schemas.invalid(f"cores[{i}].varianteId", "variante ativa deste produto")
    before = history.snapshot(produto)
    for campo in CAMPOS_FICHA:
        setattr(produto, campo, campos[campo])
    for cor in body.cores:
        v = ativas[cor.variante_id]
        v.cor_en, v.cor_pt = _vazio_para_none(cor.cor_en), _vazio_para_none(cor.cor_pt)
    mudou = history.snapshot(produto) != before
    if produto.ficha_por is None:
        produto.ficha_por = ProdutoFichaPor.humano
    elif produto.ficha_por == ProdutoFichaPor.ia and mudou:
        produto.ficha_por = ProdutoFichaPor.ia_editada
    _cancelar_abertas(db, actor, produto, estados.FICHA)
    fluxo.reavaliar(db, actor, produto, "edicao" if mudou else "gancho")
    gravar_versao(db, actor, produto, before, details={"acao": "salvar_ficha"})
    return produto


def variante_criar(db: Session, actor: Actor, produto_id: uuid.UUID, version: int,
                   foto: BinaryIO) -> Produto:
    produto = _editavel(db, produto_id, version)
    if len(produto.ativas()) >= MAX_VARIANTES:
        raise _limite_variantes()
    datadir.ensure_writable()
    data, info = _ler_foto(foto, "foto")
    before = history.snapshot(produto)
    _nova_variante(db, actor, produto, _gravar_foto(db, actor, produto.perfil_id, data, info))
    fluxo.reavaliar(db, actor, produto, "edicao")
    gravar_versao(db, actor, produto, before, details={"acao": "variante_criar"})
    return produto


def variante_editar(db: Session, actor: Actor, produto_id: uuid.UUID, variante_id: uuid.UUID,
                    body: schemas.VarianteEditarIn) -> Produto:
    produto = _editavel(db, produto_id, body.version)
    v = _variante_or_404(produto, variante_id)
    if v.archived:
        raise ApiError(409, "estado_invalido", "Restaure a variante antes de editar")
    mudancas = body.model_dump(exclude_unset=True, exclude={"version"})
    before = history.snapshot(produto)
    for campo in ("cor_en", "cor_pt"):
        if campo in mudancas:
            valor = mudancas[campo]
            setattr(v, campo, _vazio_para_none(valor) if valor is not None else None)
    mudou = history.snapshot(produto) != before
    fluxo.reavaliar(db, actor, produto, "edicao" if mudou else "gancho")
    gravar_versao(db, actor, produto, before, details={"acao": "variante_editar"})
    return produto


def variante_arquivar(db: Session, actor: Actor, produto_id: uuid.UUID,
                      variante_id: uuid.UUID, version: int) -> Produto:
    produto = _editavel(db, produto_id, version)
    v = _variante_or_404(produto, variante_id)
    if v.archived:
        raise ApiError(409, "conflict", "Esta variante já está arquivada")
    if len(produto.ativas()) <= 1:
        raise schemas.invalid("varianteId", "é a última variante ativa; arquive o produto")
    before = history.snapshot(produto)
    v.archived_at, v.archived_by = datetime.now(UTC), actor.user_id
    _renumerar(produto)
    fluxo.reavaliar(db, actor, produto, "gancho")
    gravar_versao(db, actor, produto, before, details={"acao": "variante_arquivar"})
    return produto


def variante_restaurar(db: Session, actor: Actor, produto_id: uuid.UUID,
                       variante_id: uuid.UUID, version: int) -> Produto:
    produto = _editavel(db, produto_id, version)
    v = _variante_or_404(produto, variante_id)
    if not v.archived:
        raise ApiError(409, "conflict", "Esta variante não está arquivada")
    if len(produto.ativas()) >= MAX_VARIANTES:
        raise _limite_variantes()
    before = history.snapshot(produto)
    v.position = len(produto.ativas())
    v.archived_at = v.archived_by = None
    fluxo.reavaliar(db, actor, produto, "edicao")
    gravar_versao(db, actor, produto, before, details={"acao": "variante_restaurar"})
    return produto


def variantes_ordenar(db: Session, actor: Actor, produto_id: uuid.UUID,
                      body: schemas.OrdemIn) -> Produto:
    produto = _editavel(db, produto_id, body.version)
    ativas = {v.id: v for v in produto.ativas()}
    if len(body.ids) != len(set(body.ids)) or set(body.ids) != set(ativas):
        raise schemas.invalid("ids", "a lista precisa ter todas as variantes ativas")
    before = history.snapshot(produto)
    for i, vid in enumerate(body.ids):
        ativas[vid].position = i
    gravar_versao(db, actor, produto, before, details={"acao": "variantes_ordenar"})
    return produto


def aprovar(db: Session, actor: Actor, produto_id: uuid.UUID, version: int) -> Produto:
    """Dono e membro (FR-021): só em `revisao` e sem pendências (FR-018)."""
    produto = _editavel(db, produto_id, version)
    if produto.status != ProdutoStatus.revisao:
        raise ApiError(409, "estado_invalido", "Só um produto em revisão pode ser aprovado")
    pend = estados.pendencias(produto, produto.ativas(),
                              fluxo.abertas(fluxo.geracoes(db, produto.id)))
    if pend:
        raise ApiError(409, "produto_incompleto", "Falta completar o cadastro",
                       details={"pendencias": [{"varianteId": str(p.variante_id)
                                                if p.variante_id else None, "motivo": p.motivo}
                                               for p in pend]})
    before = history.snapshot(produto)
    produto.status = ProdutoStatus.aprovado
    gravar_versao(db, actor, produto, before, details={"acao": "aprovar"})
    return produto


# ---- arquivo e histórico (US5) ----

def arquivar(db: Session, actor: Actor, produto_id: uuid.UUID, body: schemas.ArquivarIn
             ) -> Produto:
    """Só `archived_at` (R4): o status fica como estava. As gerações abertas continuam, a
    menos que `cancelarGeracoes` (o resultado entra no produto arquivado)."""
    produto = get_or_404(db, produto_id, lock=True)
    history.check_version(produto, body.version, LABEL)
    if produto.archived:
        raise ApiError(409, "conflict", "Este produto já está arquivado")
    if body.cancelar_geracoes:
        _cancelar_abertas(db, actor, produto)
    before = history.snapshot(produto)
    produto.archived_at, produto.archived_by = datetime.now(UTC), actor.user_id
    gravar_versao(db, actor, produto, before, "archived",
                  details={"cancelarGeracoes": body.cancelar_geracoes})
    return produto


def restaurar(db: Session, actor: Actor, produto_id: uuid.UUID, version: int) -> Produto:
    produto = get_or_404(db, produto_id, lock=True)
    history.check_version(produto, version, LABEL)
    if not produto.archived:
        raise ApiError(409, "conflict", "Este produto não está arquivado")
    before = history.snapshot(produto)
    produto.archived_at = produto.archived_by = None
    gravar_versao(db, actor, produto, before, "restored")
    return produto


def _uuid(valor: Any) -> uuid.UUID | None:
    return uuid.UUID(valor) if valor else None


def reverter(db: Session, actor: Actor, produto_id: uuid.UUID, version: int,
             to_version: int) -> Produto:
    """Volta a ficha, as cores, a ordem e as imagens da versão alvo, **sem gerar nada**
    (FR-023). Variante que não existia na versão alvo é arquivada. Nunca volta a `aprovado`."""
    produto = get_or_404(db, produto_id, lock=True)
    history.check_version(produto, version, LABEL)
    state = target_state(db, ENTITY, produto, to_version)
    before = history.snapshot(produto)
    agora = datetime.now(UTC)
    for campo in ("name", *CAMPOS_FICHA, "obs", "url_loja"):
        setattr(produto, campo, state[campo])
    produto.perfil_id = _uuid(state.get("perfil_id"))  # spec 029: o perfil base da versão
    produto.ficha_por = ProdutoFichaPor(state["ficha_por"]) if state["ficha_por"] else None
    alvo = {uuid.UUID(v["id"]): v for v in state["variantes"]}
    for v in produto.variantes_rel:
        snap = alvo.get(v.id)
        if snap is None:
            if not v.archived:
                v.archived_at, v.archived_by = agora, actor.user_id
            continue
        v.cor_en, v.cor_pt, v.position = snap["cor_en"], snap["cor_pt"], snap["position"]
        v.recorte_image_id = _uuid(snap["recorte_image_id"])
        v.flat_image_id = _uuid(snap["flat_image_id"])
        v.flat_geracao_id = _uuid(snap["flat_geracao_id"])
        if snap["archived"] and not v.archived:
            v.archived_at, v.archived_by = agora, actor.user_id
        elif not snap["archived"] and v.archived:
            v.archived_at = v.archived_by = None
    _renumerar(produto)
    apply_archived(produto, state["archived"], actor)
    if history.snapshot(produto) == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    # O status sai das regras (como um `reavaliar` que não pede nada): nunca `aprovado`.
    produto.status = estados.proximo(produto, produto.ativas(),
                                     fluxo.ultimas(fluxo.geracoes(db, produto.id)),
                                     "edicao").status
    gravar_versao(db, actor, produto, before, "reverted", details={"from_version": to_version})
    return produto
