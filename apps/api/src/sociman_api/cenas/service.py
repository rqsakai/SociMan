"""Cenas do perfil (spec 010, contracts/http-api.md, research R2–R5).

Toda mutação trava a linha da cena, confere a `version`, recusa perfil arquivado e grava **uma**
versão em `entity_versions` na mesma transação (`history.record`). Nada é apagado: arquivar e
restaurar; a reversão é só do dono humano (a rota usa `RequireHumanOwner`).

Status (Q3): `rascunho` monta o prompt ao vivo; `pronta` congela o texto e as versões do avatar e
do cenário; `usada` vem do vínculo com um conteúdo (`usos.py`). Editar um campo de
`CAMPOS_PROMPT` numa `pronta` a devolve a `rascunho`; numa `usada`, 409 `cena_usada`.
"""

import base64
import binascii
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from sociman_api import history, imaging, midia
from sociman_api.assets.models import Asset, AssetTipo, FileRole
from sociman_api.auth.deps import Actor
from sociman_api.cenas import avisos as avisos_mod
from sociman_api.cenas import ingredientes, padroes, schemas
from sociman_api.cenas import prompt as prompt_mod
from sociman_api.cenas.models import (
    CAMPOS_EDITAVEIS,
    CAMPOS_PROMPT,
    Cena,
    CenaModo,
    CenaMovimento,
    CenaPlano,
    CenaStatus,
    CenaTomada,
    CenaUso,
)
from sociman_api.conteudos.models import Conteudo
from sociman_api.errors import ApiError
from sociman_api.ia import aplicacao
from sociman_api.ia import guia as guia_mod
from sociman_api.perfis.models import Image, Perfil
from sociman_api.perfis.schemas import Autor, VersionsList
from sociman_api.perfis.service_perfis import (
    apply_archived,
    get_perfil_or_404,
    target_state,
    versions_out,
)

ENTITY = "cena"
LABEL = "Esta cena"
NOT_FOUND = "Cena não encontrada"
CENA_USADA = "Esta cena já foi usada num vídeo; duplique para variar o prompt"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_UUIDS = ("avatar_id", "avatar_arquivo_id", "cenario_id", "cenario_arquivo_id",
          "produto_imagem_id")
_ENUMS = {"plano": CenaPlano, "movimento": CenaMovimento, "modo": CenaModo}
_CAMEL = {"avatar_id": "avatarId", "avatar_arquivo_id": "avatarArquivoId",
          "cenario_id": "cenarioId", "cenario_arquivo_id": "cenarioArquivoId",
          "produto_imagem_id": "produtoImagemId", "produto_nome": "produtoNome",
          "quadro_inicial": "quadroInicial", "quadro_final": "quadroFinal",
          "duracao_s": "duracaoS", "texto_tela": "textoTela"}
_ACENTOS = ("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")


def camel(campo: str) -> str:
    return _CAMEL.get(campo, campo)


def invalida(campo: str, mensagem: str) -> ApiError:
    return ApiError(422, "cena_invalida", f"{camel(campo)}: {mensagem}",
                    details={"field": camel(campo)})


def _usada() -> ApiError:
    return ApiError(409, "cena_usada", CENA_USADA)


# ---- leitura de apoio ----

def get_cena_or_404(db: Session, cena_id: uuid.UUID, lock: bool = False) -> Cena:
    cena = db.get(Cena, cena_id, with_for_update=lock)
    if cena is None:
        raise ApiError(404, "nao_encontrada", NOT_FOUND)
    return cena


def perfil_ativo(db: Session, perfil_id: uuid.UUID) -> Perfil:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    return perfil


def _editavel(db: Session, cena_id: uuid.UUID, version: int) -> Cena:
    cena = get_cena_or_404(db, cena_id, lock=True)
    history.check_version(cena, version, LABEL)
    perfil_ativo(db, cena.perfil_id)
    if cena.archived:
        raise ApiError(409, "arquivada", "Restaure a cena antes de alterar")
    return cena


def assets_da(db: Session, cena: Any) -> ingredientes.Assets:
    """`cena` pode ser a linha ou qualquer objeto com os três ids."""
    def _get(asset_id: uuid.UUID | None) -> Asset | None:
        return db.get(Asset, asset_id) if asset_id is not None else None
    return ingredientes.Assets(avatar=_get(cena.avatar_id), cenario=_get(cena.cenario_id),
                               produto=_get(cena.produto_imagem_id))


_TIPOS = {"avatar_id": (AssetTipo.avatar, "um avatar"),
          "cenario_id": (AssetTipo.cenario, "um cenário"),
          "produto_imagem_id": (AssetTipo.imagem, "uma imagem")}


def validar_refs(db: Session, perfil_id: uuid.UUID, valores: dict[str, Any],
                 novos: set[str], erro=invalida) -> None:
    """Assets do perfil e do tipo certo; o arquivo do avatar/cenário é desse asset. Asset ou
    arquivo arquivado só é recusado quando a referência é nova (`novos`)."""
    for campo, (tipo, rotulo) in _TIPOS.items():
        asset_id = valores.get(campo)
        if asset_id is None:
            continue
        asset = db.get(Asset, asset_id)
        if asset is None or asset.perfil_id != perfil_id or asset.tipo != tipo:
            raise erro(campo, f"escolha {rotulo} da biblioteca deste perfil")
        if campo in novos and asset.archived:
            raise erro(campo, "o asset está arquivado")
    for campo, dono, papeis in (("avatar_arquivo_id", "avatar_id",
                                 (FileRole.referencia, FileRole.pose)),
                                ("cenario_arquivo_id", "cenario_id", (FileRole.referencia,))):
        arquivo_id = valores.get(campo)
        if arquivo_id is None:
            continue
        asset = db.get(Asset, valores[dono]) if valores.get(dono) is not None else None
        f = next((f for f in asset.arquivos if f.id == arquivo_id), None) if asset else None
        if f is None or f.role not in papeis:
            raise erro(campo, "escolha um arquivo deste asset")
        if campo in novos and f.archived:
            raise erro(campo, "o arquivo está arquivado")
    if valores.get("produto_imagem_id") is not None and not (valores.get("produto_nome") or ""):
        raise erro("produto_nome", "informe o nome do produto da foto")


# ---- prompt, avisos e saída ----

def entrada(cena: Any, assets: ingredientes.Assets, estilo_padrao: str,
            negative_padrao: str) -> prompt_mod.Entrada:
    avatar = assets.avatar
    cenario = assets.cenario
    return prompt_mod.Entrada(
        acao=cena.acao, estilo_padrao=estilo_padrao, negative_padrao=negative_padrao,
        avatar=prompt_mod.AvatarIn(avatar.prompt, avatar.image_rules, avatar.version)
        if avatar is not None else None,
        cenario=prompt_mod.CenarioIn(cenario.prompt, cenario.version)
        if cenario is not None else None,
        plano=cena.plano, movimento=cena.movimento, camera=cena.camera, fala=cena.fala,
        estilo=cena.estilo, audio=cena.audio, modo=cena.modo,
        quadro_inicial=cena.quadro_inicial, quadro_final=cena.quadro_final,
        produto_nome=cena.produto_nome, produto_com_foto=assets.produto is not None,
        negative=cena.negative)


def montar(db: Session, cena: Cena,
           assets: ingredientes.Assets | None = None) -> prompt_mod.PromptMontado:
    assets = assets or assets_da(db, cena)
    estilo, negative = padroes.efetivos(db, cena.perfil_id)
    return prompt_mod.montar(entrada(cena, assets, estilo, negative))


def _texto_parte(papel: str, state: dict[str, Any] | None) -> str:
    """O texto da parte do avatar (descrição + regras) ou do cenário numa versão do asset."""
    if state is None:
        return ""
    if papel == "avatar":
        avatar = prompt_mod.AvatarIn(state.get("prompt"), state.get("image_rules"), 0)
        e = prompt_mod.Entrada(acao="x", estilo_padrao="", negative_padrao="", avatar=avatar)
        partes = prompt_mod.montar(e).partes
        return " ".join(p.texto for p in partes if p.parte in ("avatar", "regras"))
    return (state.get("prompt") or "").strip()


def _mudancas(db: Session, cena: Cena,
              assets: ingredientes.Assets) -> list[avisos_mod.Mudanca]:
    if cena.status == CenaStatus.rascunho:
        return []
    out = []
    for papel, asset, congelada in (("avatar", assets.avatar, cena.avatar_version_congelada),
                                    ("cenario", assets.cenario, cena.cenario_version_congelada)):
        if asset is None or congelada is None or asset.version == congelada:
            continue
        antes = _texto_parte(papel, history.version_state(db, "asset", asset.id, congelada))
        depois = _texto_parte(papel, history.snapshot(asset))
        if antes != depois:
            out.append(avisos_mod.Mudanca(papel, antes, depois))
    return out


def proibidas_do_perfil(db: Session, perfil_id: uuid.UUID) -> tuple[str, ...]:
    vigor = guia_mod.em_vigor(db, perfil_id, None)
    return guia_mod.fundir(vigor.perfil, None).proibidas


def avisos(db: Session, cena: Cena, assets: ingredientes.Assets) -> list[schemas.Aviso]:
    arquivados = [papel for papel, a in (("avatar", assets.avatar), ("cenario", assets.cenario),
                                         ("produto", assets.produto))
                  if a is not None and a.archived]
    lista = avisos_mod.calcular(avisos_mod.EntradaAvisos(
        acao=cena.acao, duracao_s=cena.duracao_s, modo=cena.modo, fala=cena.fala,
        texto_tela=cena.texto_tela, produto_nome=cena.produto_nome,
        produto_com_foto=assets.produto is not None,
        proibidas=proibidas_do_perfil(db, cena.perfil_id),
        mudancas=_mudancas(db, cena, assets), arquivados=arquivados))
    return [schemas.Aviso(codigo=a.codigo, mensagem=a.mensagem, campo=a.campo,
                          detalhe=a.detalhe) for a in lista]


def prompt_out(db: Session, cena: Cena, assets: ingredientes.Assets) -> schemas.PromptOut:
    if cena.status != CenaStatus.rascunho and cena.prompt_congelado is not None:
        return schemas.PromptOut(
            texto=cena.prompt_congelado, negative=cena.negative_congelado or "", partes=[],
            congelado=True, avatar_version=cena.avatar_version_congelada,
            cenario_version=cena.cenario_version_congelada)
    m = montar(db, cena, assets)
    return schemas.PromptOut(
        texto=m.texto, negative=m.negative,
        partes=[schemas.ParteOut(parte=p.parte, texto=p.texto) for p in m.partes],
        congelado=False, avatar_version=m.avatar_version, cenario_version=m.cenario_version)


def _ref(asset: Asset | None) -> schemas.AssetRef | None:
    if asset is None:
        return None
    return schemas.AssetRef(id=asset.id, nome=asset.name, arquivada=asset.archived)


def autores_de(db: Session, entity_type: str, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Autor]:
    """O autor da criação (versão 1) de cada entidade."""
    if not ids:
        return {}
    rows = list(db.scalars(select(history.EntityVersion).where(
        history.EntityVersion.entity_type == entity_type,
        history.EntityVersion.entity_id.in_(list(ids)), history.EntityVersion.version == 1)))
    nomes = history.autores(db, rows)
    return {r.entity_id: Autor(**nomes[r.id]) for r in rows}


def _sem_autor() -> Autor:
    return Autor(tipo="sistema", id=None, nome="sistema")


def tomada_out(t: CenaTomada, escolhida: bool, autor: Autor | None,
               com_video: bool = True) -> schemas.Tomada:
    video_url = midia.link("cena_tomada", t.id).url if com_video else None
    return schemas.Tomada(
        id=t.id, cena_id=t.cena_id, origem=t.origem, duracao_ms=t.duracao_ms, largura=t.largura,
        altura=t.altura, nao_vertical=t.largura >= t.altura, bytes=t.bytes,
        content_type=t.content_type,
        thumb_url=imaging.image_urls(t.miniatura_key)["thumb"], video_url=video_url,
        prompt_usado=t.prompt_usado, negative_usado=t.negative_usado, nota=t.nota,
        escolhida=escolhida, arquivada=t.archived, version=t.version, created_at=t.created_at,
        autor=autor or _sem_autor())


def _contagens(db: Session, ids: Sequence[uuid.UUID]) -> tuple[dict, dict]:
    if not ids:
        return {}, {}
    tomadas = dict(db.execute(
        select(CenaTomada.cena_id, func.count()).where(
            CenaTomada.cena_id.in_(list(ids)), CenaTomada.archived_at.is_(None))
        .group_by(CenaTomada.cena_id)).all())
    usos = dict(db.execute(
        select(CenaUso.cena_id, func.count()).where(
            CenaUso.cena_id.in_(list(ids)), CenaUso.desfeito_em.is_(None))
        .group_by(CenaUso.cena_id)).all())
    return tomadas, usos


def _thumb(db: Session, cena: Cena, assets: ingredientes.Assets,
           tomada: CenaTomada | None) -> str | None:
    """Miniatura: tomada escolhida → imagem do arquivo do avatar → nenhuma (iniciais no SPA)."""
    if tomada is not None:
        return imaging.image_urls(tomada.miniatura_key)["thumb"]
    f = ingredientes.arquivo(assets.avatar, cena.avatar_arquivo_id)
    image = db.get(Image, f.image_id) if f is not None else None
    return ingredientes.thumb_url(image) if image is not None else None


def resumos_out(db: Session, cenas: Sequence[Cena]) -> list[schemas.CenaResumo]:
    ids = [c.id for c in cenas]
    tomadas, usos = _contagens(db, ids)
    escolhidas = {t.id: t for t in db.scalars(select(CenaTomada).where(CenaTomada.id.in_(
        [c.tomada_escolhida_id for c in cenas if c.tomada_escolhida_id])))} if cenas else {}
    out = []
    for c in cenas:
        assets = assets_da(db, c)
        out.append(schemas.CenaResumo(
            id=c.id, perfil_id=c.perfil_id, nome=c.nome, status=c.status,
            duracao_s=c.duracao_s, modo=c.modo, avatar=_ref(assets.avatar),
            cenario=_ref(assets.cenario), produto_nome=c.produto_nome,
            thumb_url=_thumb(db, c, assets, escolhidas.get(c.tomada_escolhida_id)),
            tags=list(c.tags), arquivada=c.archived, tomadas=tomadas.get(c.id, 0),
            usos=usos.get(c.id, 0), updated_at=c.updated_at))
    return out


def usos_out(db: Session, cena_id: uuid.UUID) -> list[schemas.UsoOut]:
    rows = db.execute(
        select(Conteudo.id, Conteudo.titulo).join(CenaUso, CenaUso.conteudo_id == Conteudo.id)
        .where(CenaUso.cena_id == cena_id, CenaUso.desfeito_em.is_(None))
        .order_by(CenaUso.criado_em)).all()
    return [schemas.UsoOut(conteudo_id=cid, titulo=titulo or "Vídeo próprio",
                           link=f"/app/conteudos/{cid}") for cid, titulo in rows]


def cena_out(db: Session, cena: Cena, actor: Actor | None = None) -> schemas.Cena:
    db.flush()
    db.refresh(cena)  # updated_at vem do banco
    assets = assets_da(db, cena)
    tomada = db.get(CenaTomada, cena.tomada_escolhida_id) if cena.tomada_escolhida_id else None
    tomadas, _ = _contagens(db, [cena.id])
    autores = autores_de(db, ENTITY, [cena.id])
    tomada_autores = autores_de(db, "cena_tomada", [tomada.id]) if tomada else {}
    com_video = actor is None or actor.kind != "mcp_client"
    return schemas.Cena(
        **{f: getattr(cena, f) for f in CAMPOS_EDITAVEIS}, id=cena.id, perfil_id=cena.perfil_id,
        status=cena.status, version=cena.version, arquivada=cena.archived,
        avatar=_ref(assets.avatar), cenario=_ref(assets.cenario),
        produto_imagem=_ref(assets.produto), prompt=prompt_out(db, cena, assets),
        ingredientes=ingredientes.listar(db, assets, cena.avatar_arquivo_id,
                                         cena.cenario_arquivo_id),
        avisos=avisos(db, cena, assets),
        tomada_escolhida=tomada_out(tomada, True, tomada_autores.get(tomada.id), com_video)
        if tomada is not None else None,
        tomadas=tomadas.get(cena.id, 0), usos=usos_out(db, cena.id),
        thumb_url=_thumb(db, cena, assets, tomada), duplicada_de=cena.duplicada_de,
        created_at=cena.created_at, updated_at=cena.updated_at,
        autor=autores.get(cena.id) or _sem_autor())


# ---- consultas ----

def obter(db: Session, cena_id: uuid.UUID, actor: Actor | None = None) -> schemas.Cena:
    return cena_out(db, get_cena_or_404(db, cena_id), actor)


def versoes(db: Session, cena_id: uuid.UUID) -> VersionsList:
    get_cena_or_404(db, cena_id)
    return versions_out(db, ENTITY, cena_id)


def _encode(updated_at: datetime, cena_id: uuid.UUID) -> str:
    raw = f"{updated_at.isoformat()}|{cena_id}".encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, cena_id = raw.split("|")
        return datetime.fromisoformat(ts), uuid.UUID(cena_id)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ApiError(400, "validation_error", "cursor: inválido") from None


def _sem_acento(col):
    return func.translate(func.lower(col), *_ACENTOS)


def _termo(q: str) -> str:
    termo = guia_mod.normalizar(q)
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar(db: Session, perfil_id: uuid.UUID, *, q: str | None = None,
           status: Sequence[CenaStatus] = (), avatar_id: uuid.UUID | None = None,
           cenario_id: uuid.UUID | None = None, produto_imagem_id: uuid.UUID | None = None,
           tags: Sequence[str] = (), arquivadas: str = "false", cursor: str | None = None,
           limit: int = DEFAULT_LIMIT) -> schemas.CenasList:
    get_perfil_or_404(db, perfil_id)
    stmt = select(Cena).where(Cena.perfil_id == perfil_id)
    if arquivadas == "false":
        stmt = stmt.where(Cena.archived_at.is_(None))
    elif arquivadas == "true":
        stmt = stmt.where(Cena.archived_at.is_not(None))
    if status:
        stmt = stmt.where(Cena.status.in_(list(status)))
    if avatar_id is not None:
        stmt = stmt.where(Cena.avatar_id == avatar_id)
    if cenario_id is not None:
        stmt = stmt.where(Cena.cenario_id == cenario_id)
    if produto_imagem_id is not None:
        stmt = stmt.where(Cena.produto_imagem_id == produto_imagem_id)
    wanted = [t.strip().lower() for t in tags if t.strip()]
    if wanted:
        stmt = stmt.where(Cena.tags.contains(wanted))
    if q and q.strip():
        like = f"%{_termo(q)}%"
        stmt = stmt.where(or_(*(_sem_acento(func.coalesce(col, "")).like(like, escape="\\")
                                for col in (Cena.nome, Cena.acao, Cena.fala,
                                            Cena.produto_nome))))
    if cursor:
        ts, last_id = _decode(cursor)
        stmt = stmt.where(or_(Cena.updated_at < ts,
                              and_(Cena.updated_at == ts, Cena.id > last_id)))
    rows = list(db.scalars(stmt.order_by(Cena.updated_at.desc(), Cena.id).limit(limit + 1)))
    page, more = rows[:limit], len(rows) > limit
    return schemas.CenasList(
        items=resumos_out(db, page),
        next_cursor=_encode(page[-1].updated_at, page[-1].id) if more else None)


# ---- mutações ----

def _record(db: Session, actor: Actor, cena: Cena, action: str, before: dict[str, Any] | None,
            details: dict[str, Any] | None = None,
            ia: list[aplicacao.IaAplicacao] | None = None, sempre: bool = False) -> bool:
    """Grava a versão se algo mudou (criação sempre grava; `sempre` grava mesmo sem mudança de
    campo, ex.: o vínculo). Com `ia`, marca as chamadas aplicadas (008) na mesma transação."""
    db.flush()
    after = history.snapshot(cena)
    if before is not None and after == before and not sempre:
        return False
    marca = aplicacao.marcar(db, actor, ENTITY, cena, before, after, ia)
    if marca is not None:
        details = {**(details or {}), **marca}
    cena.updated_by = actor.user_id
    history.record(db, actor, ENTITY, cena, action, before, after, details)
    return True


def _aplicar_proposta(db: Session, actor: Actor, proposta_id: uuid.UUID | None,
                      cena: Cena, perfil_id: uuid.UUID, nova: bool) -> dict[str, Any] | None:
    """Spec 009 (proposta de cena): marca `aplicada` na mesma transação."""
    if proposta_id is None:
        return None
    if actor.kind != "user":
        raise ApiError(403, "somente_humano", "Só um humano aplica propostas")
    from sociman_api.anotacoes import service as anotacoes_service  # import tardio (ciclo)

    anotacoes_service.aplicar_cena(db, actor, proposta_id, perfil_id=perfil_id,
                                   cena_id=None if nova else cena.id, aplicada_em=cena.id)
    return {"proposta": {"id": str(proposta_id)}}


def criar(db: Session, actor: Actor, perfil_id: uuid.UUID, body: schemas.CenaIn) -> Cena:
    perfil_ativo(db, perfil_id)
    valores = body.model_dump(exclude={"proposta_id", "ia"})
    validar_refs(db, perfil_id, valores, novos=set(_UUIDS))
    cena = Cena(id=uuid.uuid4(), perfil_id=perfil_id, created_by=actor.user_id,
                updated_by=actor.user_id, **valores)
    db.add(cena)
    db.flush()
    details = _aplicar_proposta(db, actor, body.proposta_id, cena, perfil_id, nova=True)
    _record(db, actor, cena, "created", None, details, ia=body.ia)
    return cena


def _limpa_congelado(cena: Cena) -> None:
    cena.prompt_congelado = None
    cena.negative_congelado = None
    cena.avatar_version_congelada = None
    cena.cenario_version_congelada = None


_OBRIGATORIOS = ("nome", "acao", "duracao_s", "modo", "tags", "notas")


def mudancas_de(cena: Cena, changes: dict[str, Any]) -> dict[str, Any]:
    """Só o que difere do valor atual (nulo em campo obrigatório é ignorado)."""
    out = {}
    for campo, valor in changes.items():
        if valor is None and campo in _OBRIGATORIOS:
            continue
        if getattr(cena, campo) != valor:
            out[campo] = valor
    return out


def editar(db: Session, actor: Actor, cena_id: uuid.UUID, body: schemas.CenaPatch) -> Cena:
    cena = _editavel(db, cena_id, body.version)
    changes = mudancas_de(cena, body.model_dump(exclude_unset=True,
                                                exclude={"version", "proposta_id", "ia"}))
    prompt_mudou = bool(CAMPOS_PROMPT & changes.keys())
    if prompt_mudou and cena.status == CenaStatus.usada:
        raise _usada()
    # Trocar o avatar (ou o cenário) sem mandar o arquivo volta para o principal.
    for dono, arq in (("avatar_id", "avatar_arquivo_id"), ("cenario_id", "cenario_arquivo_id")):
        if dono in changes and arq not in changes and getattr(cena, arq) is not None:
            changes[arq] = None
    valores = {f: changes.get(f, getattr(cena, f)) for f in CAMPOS_EDITAVEIS}
    validar_refs(db, cena.perfil_id, valores, novos=set(changes) & set(_UUIDS))
    before = history.snapshot(cena)
    for campo, valor in changes.items():
        setattr(cena, campo, valor)
    details: dict[str, Any] = {}
    if prompt_mudou and cena.status == CenaStatus.pronta:
        cena.status = CenaStatus.rascunho
        _limpa_congelado(cena)
        details["acao"] = "voltou_rascunho"
    proposta = _aplicar_proposta(db, actor, body.proposta_id, cena, cena.perfil_id, nova=False)
    if proposta:
        details |= proposta
    _record(db, actor, cena, "updated", before, details or None, ia=body.ia,
            sempre=proposta is not None)
    return cena


def _congelar(db: Session, cena: Cena) -> None:
    with db.no_autoflush:
        m = montar(db, cena)
    cena.prompt_congelado = m.texto
    cena.negative_congelado = m.negative
    cena.avatar_version_congelada = m.avatar_version
    cena.cenario_version_congelada = m.cenario_version


def faltando(db: Session, cena: Cena) -> list[str]:
    out = []
    if not (cena.acao or "").strip():
        out.append("acao")
    if cena.modo == CenaModo.quadros:
        out += [camel(f) for f in ("quadro_inicial", "quadro_final")
                if not (getattr(cena, f) or "").strip()]
    assets = assets_da(db, cena)
    for campo, asset in (("avatarId", assets.avatar), ("cenarioId", assets.cenario),
                         ("produtoImagemId", assets.produto)):
        if asset is not None and asset.archived:
            out.append(campo)
    for campo, asset, arq in (("avatarArquivoId", assets.avatar, cena.avatar_arquivo_id),
                              ("cenarioArquivoId", assets.cenario, cena.cenario_arquivo_id)):
        f = ingredientes.arquivo(asset, arq)
        if arq is not None and (f is None or f.archived):
            out.append(campo)
    return out


def marcar_pronta(db: Session, actor: Actor, cena_id: uuid.UUID, version: int) -> Cena:
    cena = _editavel(db, cena_id, version)
    if cena.status != CenaStatus.rascunho:
        raise ApiError(409, "conflict", "Esta cena já está pronta")
    falta = faltando(db, cena)
    if falta:
        raise ApiError(422, "cena_incompleta", "Falta preencher ou trocar: " + ", ".join(falta),
                       details={"faltando": falta})
    before = history.snapshot(cena)
    _congelar(db, cena)  # antes do status: o montar consulta o banco (autoflush)
    cena.status = CenaStatus.pronta
    _record(db, actor, cena, "updated", before, {"acao": "pronta"})
    return cena


def voltar_rascunho(db: Session, actor: Actor, cena_id: uuid.UUID, version: int) -> Cena:
    cena = _editavel(db, cena_id, version)
    if cena.status == CenaStatus.usada:
        raise _usada()
    if cena.status != CenaStatus.pronta:
        raise ApiError(409, "conflict", "Esta cena já está em rascunho")
    before = history.snapshot(cena)
    cena.status = CenaStatus.rascunho
    _limpa_congelado(cena)
    _record(db, actor, cena, "updated", before, {"acao": "rascunho"})
    return cena


def remontar(db: Session, actor: Actor, cena_id: uuid.UUID, version: int) -> Cena:
    cena = _editavel(db, cena_id, version)
    if cena.status == CenaStatus.rascunho:
        raise ApiError(409, "cena_nao_pronta", "O prompt de um rascunho já é montado ao vivo")
    before = history.snapshot(cena)
    _congelar(db, cena)
    _record(db, actor, cena, "updated", before, {"acao": "remontar"}, sempre=True)
    return cena


def duplicar(db: Session, actor: Actor, cena_id: uuid.UUID) -> Cena:
    origem = get_cena_or_404(db, cena_id)
    perfil_ativo(db, origem.perfil_id)
    valores = {f: getattr(origem, f) for f in CAMPOS_EDITAVEIS}
    valores["tags"] = list(origem.tags)
    sufixo = " (cópia)"
    valores["nome"] = origem.nome[:120 - len(sufixo)] + sufixo
    cena = Cena(id=uuid.uuid4(), perfil_id=origem.perfil_id, duplicada_de=origem.id,
                status=CenaStatus.rascunho, created_by=actor.user_id, updated_by=actor.user_id,
                **valores)
    db.add(cena)
    db.flush()
    _record(db, actor, cena, "created", None, {"duplicadaDe": str(origem.id)})
    return cena


def arquivar(db: Session, actor: Actor, cena_id: uuid.UUID, version: int) -> Cena:
    cena = get_cena_or_404(db, cena_id, lock=True)
    history.check_version(cena, version, LABEL)
    perfil_ativo(db, cena.perfil_id)
    if cena.archived:
        raise ApiError(409, "arquivada", "Esta cena já está arquivada")
    before = history.snapshot(cena)
    cena.archived_at = datetime.now(UTC)
    cena.archived_by = actor.user_id
    _record(db, actor, cena, "archived", before)
    return cena


def restaurar(db: Session, actor: Actor, cena_id: uuid.UUID, version: int) -> Cena:
    cena = get_cena_or_404(db, cena_id, lock=True)
    history.check_version(cena, version, LABEL)
    perfil_ativo(db, cena.perfil_id)
    if not cena.archived:
        raise ApiError(409, "conflict", "Esta cena não está arquivada")
    before = history.snapshot(cena)
    cena.archived_at = None
    cena.archived_by = None
    _record(db, actor, cena, "restored", before)
    return cena


def tem_uso_ativo(db: Session, cena_id: uuid.UUID) -> bool:
    return db.scalar(select(func.count()).select_from(CenaUso).where(
        CenaUso.cena_id == cena_id, CenaUso.desfeito_em.is_(None))) > 0


def _de_snapshot(campo: str, valor: Any) -> Any:
    if valor is None:
        return None
    if campo in _UUIDS:
        return uuid.UUID(valor)
    if campo in _ENUMS:
        return _ENUMS[campo](valor)
    if campo == "tags":
        return list(valor)
    return valor


def reverter(db: Session, actor: Actor, cena_id: uuid.UUID, version: int,
             to_version: int) -> Cena:
    """Só o dono humano (rota). Recusado em `usada`; um snapshot `usada` sem vínculo ativo volta
    como `pronta` (research R5)."""
    cena = get_cena_or_404(db, cena_id, lock=True)
    history.check_version(cena, version, LABEL)
    perfil_ativo(db, cena.perfil_id)
    if cena.status == CenaStatus.usada:
        raise _usada()
    state = target_state(db, ENTITY, cena, to_version)
    before = history.snapshot(cena)
    for campo in CAMPOS_EDITAVEIS:
        setattr(cena, campo, _de_snapshot(campo, state[campo]))
    status = CenaStatus(state["status"])
    if status == CenaStatus.usada and not tem_uso_ativo(db, cena.id):
        status = CenaStatus.pronta
    cena.status = status
    cena.prompt_congelado = state["prompt_congelado"]
    cena.negative_congelado = state["negative_congelado"]
    cena.avatar_version_congelada = state["avatar_version_congelada"]
    cena.cenario_version_congelada = state["cenario_version_congelada"]
    escolhida = state["tomada_escolhida_id"]
    cena.tomada_escolhida_id = uuid.UUID(escolhida) if escolhida else None
    apply_archived(cena, state["archived"], actor)
    if history.snapshot(cena) == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    _record(db, actor, cena, "reverted", before, {"from_version": to_version})
    return cena
