"""Envios: seleção, avulso, enviar, confirmar qualidade, tentar de novo e descartar (R4, R6).

A linha é a seleção (`selecionado`) e depois o job no OpenShorts. Só as ações humanas geram
versão; submissão, polling, progresso e importação são estado de job (acompanhamento.py e
importacao.py).

Princípio II: enviar um vídeo de canal `sem_acordo` ou um avulso sem `confirmarAviso` responde
409 `aviso_direito` e nada é enviado. Dono e membro enviam depois de confirmar (Q3 = A). A versão
da ação "enviar" (`details.acao = "enviar"`) é o registro: autor (quem confirmou), data, fonte e
`direito_no_envio`. Envio não tem `revert` (exceção aprovada): refazer é um envio novo.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api import history, imaging
from sociman_api.auth.deps import Actor
from sociman_api.canais.models import CanalDireito, CanalFonte, VideoFonte
from sociman_api.cortes import service as cortes_service
from sociman_api.cortes.models import Corte
from sociman_api.envios import schemas, service_padroes
from sociman_api.envios.models import DireitoEnvio, Envio, EnvioOrigem, EnvioStatus
from sociman_api.errors import ApiError
from sociman_api.marca import service_kit
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, user_refs, versions_out

ENTITY = "envio"
LABEL = "Este envio"
NOT_FOUND = "Envio não encontrado"
AVISO = "O direito autoral deste vídeo é de sua responsabilidade"
MAX_URL = 2000
MAX_TITLE = 200
YOUTUBE_WATCH = "https://www.youtube.com/watch?v="

# Em andamento: não pode ser descartado (409), e conta como "já enviado".
EM_ANDAMENTO = frozenset({
    EnvioStatus.na_fila, EnvioStatus.aguardando_openshorts, EnvioStatus.confirmar_qualidade,
    EnvioStatus.processando, EnvioStatus.importando,
})
DESCARTAVEIS = frozenset({EnvioStatus.selecionado, EnvioStatus.falhou, EnvioStatus.sem_clipes,
                          EnvioStatus.pronto})


# ---- auxiliares ----

def get_envio_or_404(db: Session, envio_id: uuid.UUID, lock: bool = False) -> Envio:
    envio = db.get(Envio, envio_id, with_for_update=lock)
    if envio is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return envio


def precisa_aviso(envio: Envio, canal: CanalFonte | None) -> bool:
    """Avulso (sem canal) ou canal `sem_acordo` (princípio II)."""
    if envio.origem != EnvioOrigem.canal:
        return True
    return canal is None or canal.direito == CanalDireito.sem_acordo


def direito_atual(envio: Envio, canal: CanalFonte | None) -> DireitoEnvio:
    if envio.origem != EnvioOrigem.canal or canal is None:
        return DireitoEnvio.avulso
    return DireitoEnvio(canal.direito.value)


def _thumb(url: str | None) -> str | None:
    return imaging.remote_url(url, 320, 180) if url else None


def _config_out(config: dict[str, Any] | None) -> schemas.EnvioConfig | None:
    if config is None:
        return None
    return schemas.EnvioConfig(**{k: config.get(k) for k in schemas.EnvioConfig.model_fields})


def envios_out(db: Session, envios: Sequence[Envio]) -> list[schemas.Envio]:
    videos_ids = {e.video_fonte_id for e in envios if e.video_fonte_id}
    videos = {v.id: v for v in db.scalars(select(VideoFonte).where(VideoFonte.id.in_(videos_ids)))} \
        if videos_ids else {}
    canal_ids = {e.canal_fonte_id for e in envios if e.canal_fonte_id}
    canais = {c.id: c for c in db.scalars(select(CanalFonte).where(CanalFonte.id.in_(canal_ids)))} \
        if canal_ids else {}
    users = user_refs(db, [e.created_by for e in envios])
    out = []
    for e in envios:
        video = videos.get(e.video_fonte_id) if e.video_fonte_id else None
        canal = canais.get(e.canal_fonte_id) if e.canal_fonte_id else None
        out.append(schemas.Envio(
            id=e.id, perfil_id=e.perfil_id, origem=e.origem,
            video=schemas.VideoFonteRef(
                id=video.id, youtube_video_id=video.youtube_video_id,
                url=YOUTUBE_WATCH + video.youtube_video_id, title=video.title,
                thumbnail_url=_thumb(video.thumbnail_url), duration_s=video.duration_s, disponivel=video.disponivel,
            ) if video else None,
            canal=schemas.CanalRef(id=canal.id, title=canal.title, direito=canal.direito)
            if canal else None,
            source_url=e.source_url, source_title=e.source_title, status=e.status,
            config=_config_out(e.config), direito_no_envio=e.direito_no_envio,
            precisa_aviso=precisa_aviso(e, canal), progress=e.progress,
            queue_position=e.openshorts_queue_pos, clips_total=e.clips_total,
            clips_importados=e.clips_importados, error_message=e.error_message,
            sent_at=e.sent_at, finished_at=e.finished_at, archived=e.archived,
            version=e.version, created_at=e.created_at,
            created_by=users.get(e.created_by) if e.created_by else None,
        ))
    return out


def envio_out(db: Session, envio: Envio) -> schemas.Envio:
    return envios_out(db, [envio])[0]


def _refresh(db: Session, envio: Envio) -> Envio:
    db.flush()
    db.refresh(envio)
    return envio


def _duplicado(db: Session, perfil_id: uuid.UUID, *, video_fonte_id: uuid.UUID | None = None,
               source_url: str | None = None, exceto: uuid.UUID | None = None
               ) -> Envio | None:
    """Outro envio não descartado do mesmo vídeo (ou do mesmo link avulso) para o perfil."""
    query = select(Envio).where(Envio.perfil_id == perfil_id, Envio.archived_at.is_(None),
                                Envio.status != EnvioStatus.descartado)
    if video_fonte_id is not None:
        query = query.where(Envio.video_fonte_id == video_fonte_id)
    else:
        query = query.where(Envio.origem == EnvioOrigem.avulso_link,
                            Envio.source_url == source_url)
    if exceto is not None:
        query = query.where(Envio.id != exceto)
    # Um já enviado pesa mais que um só selecionado.
    rows = list(db.scalars(query.order_by(Envio.created_at)))
    enviados = [r for r in rows if r.status != EnvioStatus.selecionado]
    return (enviados or rows or [None])[0]


def _erro_duplicado(existente: Envio) -> ApiError:
    if existente.status == EnvioStatus.selecionado:
        return ApiError(409, "already_selected", "Este vídeo já está nos selecionados do perfil",
                        details={"envioId": str(existente.id)})
    return ApiError(409, "already_sent", "Este vídeo já foi enviado para corte neste perfil",
                    details={"envioId": str(existente.id)})


def _perfil_ativo(db: Session, perfil_id: uuid.UUID) -> None:
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")


def _valid_url(raw: str) -> str:
    url = raw.strip()
    parts = urlsplit(url)
    if (len(url) > MAX_URL or parts.scheme not in ("http", "https") or not parts.hostname
            or any(c.isspace() for c in url)):
        raise ApiError(400, "invalid_url", "Link inválido: use um endereço http(s) completo")
    return url


def _titulo(raw: str | None, fallback: str) -> str:
    text = " ".join((raw or "").split())
    return (text or " ".join(fallback.split()) or "Vídeo")[:MAX_TITLE]


def _criar(db: Session, actor: Actor, envio: Envio, duplicado: bool) -> Envio:
    envio.created_by = actor.user_id
    envio.updated_by = actor.user_id
    db.add(envio)
    db.flush()
    history.record(db, actor, ENTITY, envio, "created", None, history.snapshot(envio),
                   {"duplicado": duplicado})
    return _refresh(db, envio)


# ---- consultas ----

def listar(db: Session, perfil_id: uuid.UUID | None, status: Sequence[EnvioStatus] | None,
           limit: int, before: datetime | None) -> list[schemas.Envio]:
    """Mais recentes primeiro; `before` (cursor) é o `createdAt` do último item já visto."""
    query = select(Envio)
    if perfil_id is not None:
        query = query.where(Envio.perfil_id == perfil_id)
    if status:
        query = query.where(Envio.status.in_(list(status)))
    if before is not None:
        query = query.where(Envio.created_at < before)
    query = query.order_by(Envio.created_at.desc(), Envio.id.desc()).limit(limit)
    return envios_out(db, list(db.scalars(query)))


def detalhe(db: Session, envio_id: uuid.UUID) -> schemas.EnvioDetalhe:
    envio = get_envio_or_404(db, envio_id)
    cortes = list(db.scalars(select(Corte).where(Corte.envio_id == envio.id)
                             .order_by(Corte.clip_index, Corte.created_at)))
    return schemas.EnvioDetalhe(envio=envio_out(db, envio),
                                cortes=cortes_service.cortes_out(db, cortes))


def envio_versions(db: Session, envio_id: uuid.UUID) -> VersionsList:
    get_envio_or_404(db, envio_id)
    return versions_out(db, ENTITY, envio_id)


# ---- seleção (US2) ----

def selecionar(db: Session, actor: Actor, perfil_id: uuid.UUID,
               data: schemas.SelecionarIn) -> Envio:
    """Vídeo de canal (`videoFonteId`) ou avulso por link (`url`, `titulo?`) → `selecionado`."""
    if (data.video_fonte_id is None) == (data.url is None):
        raise ApiError(400, "validation_error", "Informe videoFonteId ou url")
    _perfil_ativo(db, perfil_id)

    if data.video_fonte_id is not None:
        video = db.get(VideoFonte, data.video_fonte_id)
        if video is None:
            raise ApiError(404, "not_found", "Vídeo não encontrado")
        if not video.disponivel:
            raise ApiError(409, "video_unavailable", "Este vídeo não está mais disponível")
        existente = _duplicado(db, perfil_id, video_fonte_id=video.id)
        if existente is not None and not data.confirmar_duplicado:
            raise _erro_duplicado(existente)
        envio = Envio(perfil_id=perfil_id, origem=EnvioOrigem.canal, video_fonte_id=video.id,
                      canal_fonte_id=video.canal_id,
                      source_url=YOUTUBE_WATCH + video.youtube_video_id,
                      source_title=_titulo(video.title, video.youtube_video_id))
        return _criar(db, actor, envio, existente is not None)

    url = _valid_url(data.url or "")
    existente = _duplicado(db, perfil_id, source_url=url)
    if existente is not None and not data.confirmar_duplicado:
        raise _erro_duplicado(existente)
    envio = Envio(perfil_id=perfil_id, origem=EnvioOrigem.avulso_link, source_url=url,
                  source_title=_titulo(data.titulo, url))
    return _criar(db, actor, envio, existente is not None)


def criar_avulso_arquivo(db: Session, actor: Actor, perfil_id: uuid.UUID, envio_id: uuid.UUID,
                         titulo: str, upload_key: str, size: int, duration_ms: int,
                         sha256: str) -> Envio:
    """O arquivo já está no bucket de vídeos (envios/upload.py)."""
    _perfil_ativo(db, perfil_id)
    envio = Envio(id=envio_id, perfil_id=perfil_id, origem=EnvioOrigem.avulso_arquivo,
                  source_title=_titulo(titulo, "Arquivo enviado"), upload_key=upload_key,
                  upload_bytes=size, upload_duration_ms=duration_ms, upload_sha256=sha256)
    return _criar(db, actor, envio, False)


def descartar(db: Session, actor: Actor, envio_id: uuid.UUID, version: int) -> Envio:
    """"Remover dos selecionados" (ou arquivar um envio terminado): `descartado`, sem apagar."""
    envio = get_envio_or_404(db, envio_id, lock=True)
    history.check_version(envio, version, LABEL)
    if envio.status not in DESCARTAVEIS or envio.archived:
        raise ApiError(409, "conflict", "Este envio está em andamento e não pode ser descartado")
    before = history.snapshot(envio)
    envio.status = EnvioStatus.descartado
    envio.archived_at = datetime.now(UTC)
    envio.archived_by = actor.user_id
    envio.updated_by = actor.user_id
    history.record(db, actor, ENTITY, envio, "archived", before, history.snapshot(envio))
    return _refresh(db, envio)


# ---- enviar (US3) ----

def _resolver_config(db: Session, perfil_id: uuid.UUID,
                     override: schemas.EnvioConfigIn | None) -> dict[str, Any]:
    """Padrões do perfil + override, validados (400 `invalid_config`), + a seção
    `openshorts.subtitle` do kit (se a legenda é a do kit) + a `kit_version`."""
    valores = service_padroes.valores_atuais(db, perfil_id)
    valores.pop("conta_padrao_id", None)
    if override is not None:
        valores |= override.model_dump(exclude_unset=True)
    if valores.get("marca_automatica") is None:
        valores["marca_automatica"] = False
    try:
        service_padroes.validar(valores)
    except service_padroes.ValoresInvalidos as exc:
        raise ApiError(400, "invalid_config", exc.message, details={"field": exc.field}) from exc
    doc, _ = service_kit.export_kit(db, perfil_id)
    config: dict[str, Any] = dict(valores)
    config["kit_version"] = doc.kit.version
    if valores["legenda"] == "kit":
        config["subtitle"] = doc.openshorts.subtitle.model_dump(mode="json")
    return config


def enviar(db: Session, actor: Actor, data: schemas.EnviarIn) -> list[Envio]:
    """Tudo ou nada (até 20): confere versão, status, disponibilidade, duplicado e o aviso de
    direito antes de mudar qualquer envio."""
    ids = [i.envio_id for i in data.items]
    if len(set(ids)) != len(ids):
        raise ApiError(400, "validation_error", "Envio repetido na lista")
    envios: dict[uuid.UUID, Envio] = {}
    for item in sorted(data.items, key=lambda i: i.envio_id):  # trava sempre na mesma ordem
        envio = get_envio_or_404(db, item.envio_id, lock=True)
        history.check_version(envio, item.version, LABEL)
        if envio.status != EnvioStatus.selecionado or envio.archived:
            raise ApiError(409, "conflict", "Só um envio selecionado pode ser enviado",
                           details={"envioId": str(envio.id)})
        envios[envio.id] = envio

    canal_ids = {e.canal_fonte_id for e in envios.values() if e.canal_fonte_id}
    canais = {c.id: c for c in db.scalars(select(CanalFonte).where(CanalFonte.id.in_(canal_ids)))} \
        if canal_ids else {}

    for envio in envios.values():
        if envio.video_fonte_id is not None:
            video = db.get(VideoFonte, envio.video_fonte_id)
            if video is None or not video.disponivel:
                raise ApiError(409, "video_unavailable", "Este vídeo não está mais disponível",
                               details={"envioId": str(envio.id)})

    avisos = [str(e.id) for e in envios.values()
              if precisa_aviso(e, canais.get(e.canal_fonte_id))]
    if avisos and not data.confirmar_aviso:
        raise ApiError(409, "aviso_direito", AVISO, details={"envioIds": sorted(avisos)})

    duplicados: dict[uuid.UUID, bool] = {}
    for envio in envios.values():
        outro = None
        if envio.video_fonte_id is not None:
            outro = _duplicado(db, envio.perfil_id, video_fonte_id=envio.video_fonte_id,
                               exceto=envio.id)
        elif envio.origem == EnvioOrigem.avulso_link:
            outro = _duplicado(db, envio.perfil_id, source_url=envio.source_url,
                               exceto=envio.id)
        enviado = outro is not None and outro.status != EnvioStatus.selecionado
        if enviado and not data.confirmar_duplicado:
            raise ApiError(409, "already_sent",
                           "Este vídeo já foi enviado para corte neste perfil",
                           details={"envioId": str(outro.id)})
        duplicados[envio.id] = enviado

    configs: dict[uuid.UUID, dict[str, Any]] = {}
    for perfil_id in {e.perfil_id for e in envios.values()}:
        configs[perfil_id] = _resolver_config(db, perfil_id, data.config)

    for item in data.items:
        envio = envios[item.envio_id]
        canal = canais.get(envio.canal_fonte_id) if envio.canal_fonte_id else None
        aviso = precisa_aviso(envio, canal)
        before = history.snapshot(envio)
        envio.config = configs[envio.perfil_id]
        envio.direito_no_envio = direito_atual(envio, canal)
        envio.aviso_confirmado = aviso and data.confirmar_aviso
        envio.status = EnvioStatus.na_fila
        _zerar_job(envio)
        envio.sent_at = func.now()
        envio.updated_by = actor.user_id
        details: dict[str, Any] = {
            "acao": "enviar", "duplicado": duplicados[envio.id],
            "canal_direito_atual": canal.direito.value if canal else None,
        }
        if aviso:
            details["aviso_confirmado_por"] = str(actor.user_id) if actor.user_id else None
        history.record(db, actor, ENTITY, envio, "updated", before, history.snapshot(envio),
                       details)
    db.flush()
    for envio in envios.values():
        db.refresh(envio)
    return [envios[i] for i in ids]


def _zerar_job(envio: Envio) -> None:
    """Estado de job limpo para uma (nova) submissão ao OpenShorts."""
    envio.openshorts_job_id = None
    envio.openshorts_queue_pos = None
    envio.progress = 0
    envio.clips_total = None
    envio.attempts = 0
    envio.next_attempt_at = None
    envio.last_polled_at = None
    envio.error_code = None
    envio.error_message = None
    envio.started_at = None
    envio.finished_at = None


def confirmar_qualidade(db: Session, actor: Actor, envio_id: uuid.UUID, version: int,
                        enviar_mesmo_assim: bool) -> Envio:
    """"Enviar mesmo assim" (`na_fila` com `force_low_quality`) ou "Descartar"."""
    envio = get_envio_or_404(db, envio_id, lock=True)
    history.check_version(envio, version, LABEL)
    if envio.status != EnvioStatus.confirmar_qualidade:
        raise ApiError(409, "conflict", "Este envio não está esperando a confirmação de qualidade")
    before = history.snapshot(envio)
    if enviar_mesmo_assim:
        envio.status = EnvioStatus.na_fila
        envio.force_low_quality = True
        _zerar_job(envio)
        acao = "enviar_mesmo_assim"
        action = "updated"
    else:
        envio.status = EnvioStatus.descartado
        envio.archived_at = datetime.now(UTC)
        envio.archived_by = actor.user_id
        acao = "descartar"
        action = "archived"
    envio.updated_by = actor.user_id
    history.record(db, actor, ENTITY, envio, action, before, history.snapshot(envio),
                   {"acao": acao})
    return _refresh(db, envio)


# A falha foi na importação (o job terminou no OpenShorts): "Importar de novo" volta a
# `importando`; clipes expirados ou falha do job pedem um job novo.
ERROS_IMPORTACAO = frozenset({"import_failed"})


def retry(db: Session, actor: Actor, envio_id: uuid.UUID, version: int) -> Envio:
    """"Tentar de novo": `falhou` → `na_fila` (job novo) ou → `importando` ("Importar de novo",
    quando a falha foi na importação e o job ainda existe; a trilha confere e, se o
    OpenShorts não o tiver mais, o envio falha com "clipes expirados")."""
    envio = get_envio_or_404(db, envio_id, lock=True)
    history.check_version(envio, version, LABEL)
    if envio.status != EnvioStatus.falhou or envio.archived:
        raise ApiError(409, "conflict", "Só um envio que falhou pode ser tentado de novo")
    before = history.snapshot(envio)
    if envio.error_code in ERROS_IMPORTACAO and envio.openshorts_job_id:
        envio.status = EnvioStatus.importando
        envio.attempts = 0
        envio.next_attempt_at = None
        envio.error_code = None
        envio.error_message = None
        envio.finished_at = None
        acao = "importar_de_novo"
    else:
        envio.status = EnvioStatus.na_fila
        _zerar_job(envio)
        envio.sent_at = func.now()
        acao = "tentar_de_novo"
    envio.updated_by = actor.user_id
    history.record(db, actor, ENTITY, envio, "updated", before, history.snapshot(envio),
                   {"acao": acao})
    return _refresh(db, envio)
