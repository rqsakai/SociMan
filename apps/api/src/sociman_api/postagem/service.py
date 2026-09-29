"""Postagens preparadas, sugestões de texto e calendário (US5 da spec 006, R9 e R10).

- Uma postagem por corte e conta de destino (Q2 = A), com histórico (`entity_type =
  "postagem"`): o snapshot é o histórico dos textos (US5-2).
- `agendado` exige o corte `pronto` (409 `corte_not_ready`); rascunho vale em qualquer corte não
  arquivado (inclusive em `revisao`).
- **`postado` só por ação humana**, em `marcar_postado` (princípio I; o guarda da T074 confere por
  AST que nenhum outro lugar atribui `EstadoPostagem.postado`). Nada aqui publica.
- A sugestão do Claude é gravada em `sugestoes_texto` (sucesso ou erro) e **não altera** a
  postagem: a tela preenche os campos, e o usuário salva.
"""

import re
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history, imaging
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.errors import ApiError
from sociman_api.marca.models import BrandKit
from sociman_api.perfis.models import Conta, ContaStatus, Perfil, Platform
from sociman_api.perfis.platforms import PLATFORMS
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import (
    apply_archived,
    target_state,
    user_refs,
    versions_out,
)
from sociman_api.postagem import schemas, textos
from sociman_api.postagem.models import EstadoPostagem, Postagem, SugestaoTexto

ENTITY = "postagem"
LABEL = "Esta postagem"
NOT_FOUND = "Postagem não encontrada"
CORTE_NOT_FOUND = "Corte não encontrado"
UQ_ATIVA = "uq_postagens_corte_conta_ativa"
TOLERANCIA_PASSADO = timedelta(minutes=1)
CALENDARIO_MAX_DIAS = 62
SEM_DATA_MAX = 200
ANTERIORES_MAX = 3
HASHTAG_RE = re.compile(r"^#\w{1,50}$", re.UNICODE)  # \w = [\p{L}\p{N}_]


def app_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


# ---- auxiliares ----

def _invalid(message: str) -> ApiError:
    return ApiError(400, "validation_error", message)


def get_postagem_or_404(db: Session, postagem_id: uuid.UUID, lock: bool = False) -> Postagem:
    postagem = db.get(Postagem, postagem_id, with_for_update=lock)
    if postagem is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return postagem


def _corte_or_404(db: Session, corte_id: uuid.UUID) -> Corte:
    corte = db.get(Corte, corte_id)
    if corte is None:
        raise ApiError(404, "not_found", CORTE_NOT_FOUND)
    return corte


def _conta_do_perfil(db: Session, corte: Corte, conta_id: uuid.UUID) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None or conta.perfil_id != corte.perfil_id:
        raise _invalid("A conta de destino precisa ser do perfil do corte")
    if conta.archived:
        raise _invalid("Esta conta está arquivada")
    return conta


def normalizar_hashtags(items: Iterable[str]) -> list[str]:
    """`"Dica"` → `"#dica"`: # na frente, sem repetir (sem diferenciar maiúsculas); 400 se
    alguma não casa com `^#[\\p{L}0-9_]{1,50}$`."""
    vistas: dict[str, str] = {}
    for raw in items:
        tag = raw.strip()
        tag = tag if tag.startswith("#") else f"#{tag}"
        if not HASHTAG_RE.match(tag):
            raise _invalid(f"Hashtag inválida: {raw.strip()} (uma palavra, sem espaço nem "
                           "pontuação, até 50 caracteres)")
        vistas.setdefault(tag.casefold(), tag)
    tags = list(vistas.values())
    if len(tags) > textos.HASHTAGS_MAX:
        raise _invalid(f"No máximo {textos.HASHTAGS_MAX} hashtags")
    return tags


def _aware(dt: datetime) -> datetime:
    """Sem offset, a data é local (APP_TZ); guardada sempre com fuso."""
    return dt.replace(tzinfo=app_tz()) if dt.tzinfo is None else dt


def _planned(dt: datetime) -> datetime:
    dt = _aware(dt)
    if dt < datetime.now(UTC) - TOLERANCIA_PASSADO:
        raise ApiError(400, "planned_in_past", "Esse horário já passou; escolha outro")
    return dt


def _check_agendavel(corte: Corte) -> None:
    if corte.status != CorteStatus.pronto or corte.archived:
        raise ApiError(409, "corte_not_ready",
                       "Só dá para agendar um corte pronto (com a marca aplicada)")


def _postagem_exists() -> ApiError:
    return ApiError(409, "postagem_exists", "Este corte já tem uma postagem para essa conta")


def _check_unica(db: Session, postagem: Postagem) -> None:
    with db.no_autoflush:
        outra = db.scalar(
            select(Postagem.id).where(
                Postagem.id != postagem.id, Postagem.corte_id == postagem.corte_id,
                Postagem.conta_id == postagem.conta_id, Postagem.archived_at.is_(None),
            ).limit(1)
        )
    if outra is not None and not postagem.archived:
        raise _postagem_exists()


def _flush_unica(db: Session) -> None:
    """Corrida entre a checagem e a escrita: o índice único parcial decide, com o mesmo 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == UQ_ATIVA:
            raise _postagem_exists() from exc
        raise


def _check_editavel(postagem: Postagem) -> None:
    if postagem.estado == EstadoPostagem.postado:
        raise ApiError(409, "conflict", "Esta postagem já foi marcada como postada")
    if postagem.archived:
        raise ApiError(409, "conflict", "Esta postagem está arquivada")


def _agendar(postagem: Postagem, corte: Corte, planned_at: datetime | None) -> None:
    """Com data: `agendado` (corte pronto, horário futuro); sem: volta a `rascunho`.
    Remarcar zera `lembrado_em` (a "Hora de postar" vale para o horário novo)."""
    if planned_at is None:
        postagem.estado = EstadoPostagem.rascunho
        postagem.planned_at = None
    else:
        _check_agendavel(corte)
        novo = _planned(planned_at)
        if postagem.planned_at != novo:
            postagem.lembrado_em = None
        postagem.estado = EstadoPostagem.agendado
        postagem.planned_at = novo
    if postagem.planned_at is None:
        postagem.lembrado_em = None


def _check_sugestao(db: Session, corte: Corte, sugestao_id: uuid.UUID | None) -> None:
    if sugestao_id is None:
        return
    sugestao = db.get(SugestaoTexto, sugestao_id)
    if sugestao is None or sugestao.corte_id != corte.id:
        raise _invalid("Sugestão não encontrada para este corte")


# ---- saídas ----

def _conta_ref(conta: Conta) -> schemas.ContaRef:
    return schemas.ContaRef(id=conta.id, platform=conta.platform,
                            platform_name=conta.platform_name, handle=conta.handle)


def postagens_out(db: Session, postagens: Sequence[Postagem]) -> list[schemas.Postagem]:
    contas = {c.id: c for c in db.scalars(
        select(Conta).where(Conta.id.in_({p.conta_id for p in postagens})))} if postagens else {}
    users = user_refs(db, [p.updated_by for p in postagens])
    tz = app_tz()
    return [
        schemas.Postagem(
            id=p.id, corte_id=p.corte_id, conta=_conta_ref(contas[p.conta_id]),
            titulo=p.titulo, descricao=p.descricao, hashtags=list(p.hashtags), estado=p.estado,
            planned_at=p.planned_at.astimezone(tz) if p.planned_at else None,
            posted_at=p.posted_at.astimezone(tz) if p.posted_at else None,
            posted_url=p.posted_url, lembrado=p.lembrado_em is not None, archived=p.archived,
            version=p.version, created_at=p.created_at, updated_at=p.updated_at,
            updated_by=users.get(p.updated_by) if p.updated_by else None,
        )
        for p in postagens
    ]


def postagem_out(db: Session, postagem: Postagem) -> schemas.Postagem:
    db.flush()
    db.refresh(postagem)
    return postagens_out(db, [postagem])[0]


def resumos_por_corte(
    db: Session, corte_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[schemas.PostagemResumo]]:
    """As postagens ativas (não arquivadas) de cada corte, para o `Corte.postagens` (T057)."""
    ids = list(set(corte_ids))
    out: dict[uuid.UUID, list[schemas.PostagemResumo]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.execute(
        select(Postagem, Conta)
        .join(Conta, Conta.id == Postagem.conta_id)
        .where(Postagem.corte_id.in_(ids), Postagem.archived_at.is_(None))
        .order_by(Postagem.created_at, Postagem.id)
    )
    tz = app_tz()
    for p, conta in rows:
        out[p.corte_id].append(schemas.PostagemResumo(
            id=p.id, conta_id=conta.id, plataforma=conta.platform, handle=conta.handle,
            estado=p.estado, planned_at=p.planned_at.astimezone(tz) if p.planned_at else None,
        ))
    return out


def list_postagens(db: Session, corte_id: uuid.UUID, archived: bool | None
                   ) -> list[schemas.Postagem]:
    _corte_or_404(db, corte_id)
    query = select(Postagem).where(Postagem.corte_id == corte_id)
    if archived is not None:
        query = query.where(Postagem.archived_at.is_not(None) if archived
                            else Postagem.archived_at.is_(None))
    return postagens_out(db, list(db.scalars(query.order_by(Postagem.created_at, Postagem.id))))


def list_versions(db: Session, postagem_id: uuid.UUID) -> VersionsList:
    get_postagem_or_404(db, postagem_id)
    return versions_out(db, ENTITY, postagem_id)


# ---- mutações ----

def create_postagem(db: Session, actor: Actor, corte_id: uuid.UUID,
                    body: schemas.CreatePostagemIn) -> Postagem:
    corte = _corte_or_404(db, corte_id)
    if corte.archived:
        raise ApiError(409, "conflict", "Este corte está arquivado")
    conta = _conta_do_perfil(db, corte, body.conta_id)
    _check_sugestao(db, corte, body.sugestao_id)
    postagem = Postagem(
        id=uuid.uuid4(), corte_id=corte.id, conta_id=conta.id, titulo=body.titulo,
        descricao=body.descricao, hashtags=normalizar_hashtags(body.hashtags),
        sugestao_id=body.sugestao_id, estado=EstadoPostagem.rascunho,
        created_by=actor.user_id, updated_by=actor.user_id,
    )
    if body.planned_at is not None:
        _agendar(postagem, corte, body.planned_at)
    _check_unica(db, postagem)
    db.add(postagem)
    history.record(db, actor, ENTITY, postagem, "created", None, history.snapshot(postagem))
    _flush_unica(db)
    return postagem


def update_postagem(db: Session, actor: Actor, postagem_id: uuid.UUID,
                    body: schemas.UpdatePostagemIn) -> Postagem:
    postagem = get_postagem_or_404(db, postagem_id, lock=True)
    history.check_version(postagem, body.version, LABEL)
    _check_editavel(postagem)
    corte = _corte_or_404(db, postagem.corte_id)
    before = history.snapshot(postagem)

    if body.conta_id is not None and body.conta_id != postagem.conta_id:
        postagem.conta_id = _conta_do_perfil(db, corte, body.conta_id).id
    if body.titulo is not None:
        postagem.titulo = body.titulo
    if body.descricao is not None:
        postagem.descricao = body.descricao
    if body.hashtags is not None:
        postagem.hashtags = normalizar_hashtags(body.hashtags)
    if body.sugestao_id is not None:
        _check_sugestao(db, corte, body.sugestao_id)
        postagem.sugestao_id = body.sugestao_id
    if "planned_at" in body.model_fields_set:
        _agendar(postagem, corte, body.planned_at)

    after = history.snapshot(postagem)
    if not history.diff(before, after):
        return postagem
    _check_unica(db, postagem)
    postagem.updated_by = actor.user_id
    history.record(db, actor, ENTITY, postagem, "updated", before, after)
    _flush_unica(db)
    return postagem


def marcar_postado(db: Session, actor: Actor, postagem_id: uuid.UUID, version: int,
                   posted_url: str | None) -> Postagem:
    """O ÚNICO lugar que atribui `postado` (princípio I): o dono postou à mão e registra."""
    postagem = get_postagem_or_404(db, postagem_id, lock=True)
    history.check_version(postagem, version, LABEL)
    _check_editavel(postagem)
    before = history.snapshot(postagem)
    postagem.estado = EstadoPostagem.postado
    postagem.posted_at = datetime.now(UTC)
    postagem.posted_url = posted_url
    postagem.updated_by = actor.user_id
    history.record(db, actor, ENTITY, postagem, "updated", before, history.snapshot(postagem),
                   {"acao": "postado"})
    db.flush()
    return postagem


def archive_postagem(db: Session, actor: Actor, postagem_id: uuid.UUID,
                     version: int) -> Postagem:
    postagem = get_postagem_or_404(db, postagem_id, lock=True)
    history.check_version(postagem, version, LABEL)
    if postagem.archived:
        raise ApiError(409, "conflict", "Esta postagem já está arquivada")
    before = history.snapshot(postagem)
    postagem.archived_at = datetime.now(UTC)
    postagem.archived_by = actor.user_id
    postagem.updated_by = actor.user_id
    history.record(db, actor, ENTITY, postagem, "archived", before, history.snapshot(postagem))
    db.flush()
    return postagem


def restore_postagem(db: Session, actor: Actor, postagem_id: uuid.UUID,
                     version: int) -> Postagem:
    postagem = get_postagem_or_404(db, postagem_id, lock=True)
    history.check_version(postagem, version, LABEL)
    if not postagem.archived:
        raise ApiError(409, "conflict", "Esta postagem não está arquivada")
    before = history.snapshot(postagem)
    postagem.archived_at = None
    postagem.archived_by = None
    _check_unica(db, postagem)
    postagem.updated_by = actor.user_id
    history.record(db, actor, ENTITY, postagem, "restored", before, history.snapshot(postagem))
    _flush_unica(db)
    return postagem


def revert_postagem(db: Session, actor: Actor, postagem_id: uuid.UUID, version: int,
                    to_version: int) -> Postagem:
    """Só o dono (rota). Volta textos, conta e data; nunca desfaz nem refaz `postado`."""
    postagem = get_postagem_or_404(db, postagem_id, lock=True)
    history.check_version(postagem, version, LABEL)
    if postagem.estado == EstadoPostagem.postado:
        raise ApiError(409, "conflict", "Esta postagem já foi marcada como postada")
    state = target_state(db, ENTITY, postagem, to_version)
    corte = _corte_or_404(db, postagem.corte_id)
    before = history.snapshot(postagem)

    conta_id = uuid.UUID(state["conta_id"])
    if conta_id != postagem.conta_id:
        postagem.conta_id = _conta_do_perfil(db, corte, conta_id).id
    postagem.titulo = state["titulo"]
    postagem.descricao = state["descricao"]
    postagem.hashtags = list(state["hashtags"])
    postagem.posted_url = state["posted_url"]
    planned = state["planned_at"]
    agendado = state["estado"] == EstadoPostagem.agendado.value and planned is not None
    _agendar(postagem, corte, datetime.fromisoformat(planned) if agendado else None)
    apply_archived(postagem, state["archived"], actor)

    after = history.snapshot(postagem)
    if after == before:
        raise _invalid("Essa versão é igual à atual")
    _check_unica(db, postagem)
    postagem.updated_by = actor.user_id
    history.record(db, actor, ENTITY, postagem, "reverted", before, after,
                   {"from_version": to_version})
    _flush_unica(db)
    return postagem


# ---- sugestões (Claude) ----

def _sugestao_out(s: SugestaoTexto) -> schemas.Sugestao:
    r = s.resultado or {}
    return schemas.Sugestao(id=s.id, plataforma=s.plataforma, titulo=r.get("titulo", ""),
                            descricao=r.get("descricao", ""), hashtags=r.get("hashtags", []),
                            ajustes=list(s.ajustes), model=s.model, created_at=s.created_at)


def list_sugestoes(db: Session, corte_id: uuid.UUID) -> list[schemas.Sugestao]:
    _corte_or_404(db, corte_id)
    rows = db.scalars(
        select(SugestaoTexto)
        .where(SugestaoTexto.corte_id == corte_id, SugestaoTexto.resultado.is_not(None))
        .order_by(SugestaoTexto.created_at.desc(), SugestaoTexto.id)
    )
    return [_sugestao_out(s) for s in rows]


def _perfil_contexto(db: Session, perfil: Perfil) -> textos.PerfilContexto:
    from sociman_api.marca.service_kit import current_tokens  # import tardio (ciclo)

    tokens, _ = current_tokens(db, perfil.id)
    contas = db.scalars(
        select(Conta).where(Conta.perfil_id == perfil.id, Conta.archived_at.is_(None),
                            Conta.status != ContaStatus.encerrada)
        .order_by(Conta.created_at, Conta.id)
    )
    return textos.PerfilContexto(
        nome=perfil.name, nicho=perfil.niche, bio=perfil.bio, idioma=perfil.language,
        bordoes=tuple(tokens.catchphrases), series=tuple(tokens.series),
        cta=tokens.end_card.cta if tokens.end_card.ligado else "",
        contas=tuple(f"{_plataforma_label(c.platform, c.platform_name)} @{c.handle}"
                     for c in contas),
    )


def _plataforma_label(platform: Platform, platform_name: str = "") -> str:
    return platform_name if platform == Platform.outra and platform_name \
        else PLATFORMS[platform].label


def _origem(db: Session, corte: Corte) -> tuple[str, str]:
    """(título do vídeo de origem, canal), quando o corte veio de um envio."""
    if corte.envio_id is None:
        return corte.original_filename, ""
    from sociman_api.canais.models import CanalFonte
    from sociman_api.envios.models import Envio

    envio = db.get(Envio, corte.envio_id)
    if envio is None:
        return "", ""
    canal = db.get(CanalFonte, envio.canal_fonte_id) if envio.canal_fonte_id else None
    return envio.source_title, canal.title if canal else ""


def _anteriores(db: Session, corte_id: uuid.UUID, plataforma: Platform
                ) -> tuple[dict[str, Any], ...]:
    rows = db.scalars(
        select(SugestaoTexto.resultado)
        .where(SugestaoTexto.corte_id == corte_id, SugestaoTexto.plataforma == plataforma,
               SugestaoTexto.resultado.is_not(None))
        .order_by(SugestaoTexto.created_at.desc()).limit(ANTERIORES_MAX)
    )
    return tuple(r for r in rows if r)


_ERROS: dict[str, tuple[int, str, str]] = {
    "timeout": (504, "textos_timeout", "O Claude demorou demais; tente de novo"),
    "refusal": (502, "claude_error",
                "O Claude não sugeriu textos para este clipe; escreva à mão"),
    "invalid": (502, "textos_invalidos",
                "O Claude devolveu textos fora dos limites; tente de novo ou escreva à mão"),
}


def _erro_api(status: int | None) -> ApiError:
    if status in (401, 403):
        msg = "A chave do Claude foi recusada; confira a ANTHROPIC_API_KEY"
    elif status == 429:
        msg = "O Claude está com muitas chamadas agora; tente em instantes"
    else:
        msg = "O Claude não respondeu; tente de novo"
    return ApiError(502, "claude_error", msg)


def sugerir(db: Session, actor: Actor, corte_id: uuid.UUID, body: schemas.SugestaoIn,
            client: textos.TextosClient | None) -> SugestaoTexto:
    """Uma sugestão para a plataforma da conta. Grava a chamada sempre (commit antes do erro,
    porque o `get_db` faz rollback quando a rota levanta)."""
    corte = _corte_or_404(db, corte_id)
    conta = _conta_do_perfil(db, corte, body.conta_id)
    if client is None:
        raise ApiError(503, "claude_unconfigured",
                       "O Claude não está configurado (ANTHROPIC_API_KEY); escreva os textos à "
                       "mão")
    perfil = db.get(Perfil, corte.perfil_id)
    assert perfil is not None
    video_titulo, canal = _origem(db, corte)
    clipe = textos.ClipeContexto(
        plataforma=conta.platform.value, video_titulo=video_titulo, canal=canal,
        openshorts_titulo=corte.openshorts_title or "",
        openshorts_descricao=corte.openshorts_description or "",
        gancho=corte.hook_text, transcricao=corte.transcript or "",
        anteriores=_anteriores(db, corte.id, conta.platform) if body.outra_versao else (),
    )
    res = client.sugerir(_perfil_contexto(db, perfil), clipe)
    row = SugestaoTexto(
        id=uuid.uuid4(), corte_id=corte.id, plataforma=conta.platform, model=res.model,
        prompt_version=textos.PROMPT_VERSION, ajustes=res.ajustes,
        erro_code=res.erro_code, input_tokens=res.input_tokens,
        output_tokens=res.output_tokens, cache_read_tokens=res.cache_read_tokens,
        duration_ms=res.duration_ms, created_by=actor.user_id,
    )
    if res.resultado is not None:  # None fica SQL NULL (atribuir None gravaria JSON null)
        row.resultado = res.resultado
    db.add(row)
    if res.erro_code is not None:
        db.commit()
        if res.erro_code in _ERROS:
            status, code, msg = _ERROS[res.erro_code]
            raise ApiError(status, code, msg)
        raise _erro_api(res.erro_status)
    db.flush()
    db.refresh(row)
    return row


def sugestao_out(s: SugestaoTexto) -> schemas.Sugestao:
    return _sugestao_out(s)


# ---- calendário ----

def calendario(db: Session, de: date, ate: date, perfil_id: uuid.UUID | None,
               plataforma: Platform | None) -> schemas.CalendarioOut:
    """Postagens com `planned_at` entre `de` e `ate` (dias locais em APP_TZ, inclusive) e os
    cortes prontos sem postagem agendada."""
    if ate < de:
        raise _invalid("A data final vem antes da inicial")
    if (ate - de).days + 1 > CALENDARIO_MAX_DIAS:
        raise _invalid(f"O calendário mostra até {CALENDARIO_MAX_DIAS} dias por vez")
    tz = app_tz()
    inicio = datetime.combine(de, time.min, tzinfo=tz)
    fim = datetime.combine(ate + timedelta(days=1), time.min, tzinfo=tz)

    query = (
        select(Postagem, Corte, Perfil)
        .join(Corte, Corte.id == Postagem.corte_id)
        .join(Perfil, Perfil.id == Corte.perfil_id)
        .join(Conta, Conta.id == Postagem.conta_id)
        .where(Postagem.archived_at.is_(None), Postagem.planned_at >= inicio,
               Postagem.planned_at < fim)
        .order_by(Postagem.planned_at, Postagem.id)
    )
    if perfil_id is not None:
        query = query.where(Corte.perfil_id == perfil_id)
    if plataforma is not None:
        query = query.where(Conta.platform == plataforma)
    rows = db.execute(query).all()
    base = postagens_out(db, [p for p, _, _ in rows])
    cores = _cores_perfis(db, {pf.id for _, _, pf in rows})
    items = [
        schemas.CalendarioItem(
            **b.model_dump(),
            corte=schemas.CorteCalendario(
                id=c.id, perfil_id=c.perfil_id, duration_ms=c.duration_ms, status=c.status,
                poster_url=imaging.poster_url(c.poster_key) if c.poster_key else None),
            perfil=schemas.PerfilCalendario(id=pf.id, name=pf.name, slug=pf.slug,
                                            cor=cores.get(pf.id)),
        )
        for b, (_, c, pf) in zip(base, rows, strict=True)
    ]

    marcada = exists().where(
        Postagem.corte_id == Corte.id, Postagem.archived_at.is_(None),
        Postagem.estado.in_([EstadoPostagem.agendado, EstadoPostagem.postado]),
    )
    sem = (
        select(Corte).where(Corte.status == CorteStatus.pronto, Corte.archived_at.is_(None),
                            ~marcada)
        .order_by(Corte.finished_at.desc().nulls_last(), Corte.id).limit(SEM_DATA_MAX)
    )
    if perfil_id is not None:
        sem = sem.where(Corte.perfil_id == perfil_id)
    cortes = list(db.scalars(sem))
    rascunhos = _titulos_rascunho(db, [c.id for c in cortes])
    cores.update(_cores_perfis(db, {c.perfil_id for c in cortes} - cores.keys()))
    sem_data = [
        schemas.SemData(
            corte_id=c.id, perfil_id=c.perfil_id,
            poster_url=imaging.poster_url(c.poster_key) if c.poster_key else None,
            titulo=rascunhos.get(c.id) or c.openshorts_title or c.hook_text,
            perfil_cor=cores.get(c.perfil_id),
        )
        for c in cortes
    ]
    return schemas.CalendarioOut(items=items, sem_data=sem_data)


_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _cores_perfis(db: Session, perfil_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Cor de cada perfil no calendário (R14): a 1ª cor da paleta do kit salvo. Perfil sem kit
    fica fora do dicionário (o SPA usa uma cor derivada do id)."""
    if not perfil_ids:
        return {}
    cores: dict[uuid.UUID, str] = {}
    for perfil_id, palette in db.execute(
        select(BrandKit.perfil_id, BrandKit.palette).where(BrandKit.perfil_id.in_(perfil_ids))
    ):
        valor = palette[0].get("valor") if palette and isinstance(palette[0], dict) else None
        if isinstance(valor, str) and _HEX.match(valor):
            cores[perfil_id] = valor.upper()
    return cores


def _titulos_rascunho(db: Session, corte_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not corte_ids:
        return {}
    rows = db.execute(
        select(Postagem.corte_id, Postagem.titulo)
        .where(and_(Postagem.corte_id.in_(corte_ids), Postagem.archived_at.is_(None),
                    Postagem.titulo != ""))
        .order_by(Postagem.created_at)
    )
    out: dict[uuid.UUID, str] = {}
    for corte_id, titulo in rows:
        out.setdefault(corte_id, titulo)
    return out
