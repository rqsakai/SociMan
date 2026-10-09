"""Cliente da YouTube Data API v3, só leitura (research R2, princípio I).

- Lista fechada `ALLOWED`: só `GET` em `channels`, `playlistItems`, `videos` e `search`. Nada
  que escreva no YouTube (o guarda do princípio I confere).
- Cota em `youtube_cota` (um dia por data do Pacífico): cada chamada reserva o custo **antes**
  de ir ao Google, num `UPDATE … RETURNING` condicional, numa transação própria. Assim a
  unidade gasta fica registrada mesmo quando a requisição da API ou a volta do agendador
  termina em erro (e rollback). Limites sobre `YT_QUOTA_DAILY`: 80% → uma notificação
  `cota_youtube` por dia; 95% → a sync pausa (`CotaPausada`); 100% → 429 `youtube_quota`. Um
  `403 quotaExceeded` do Google encerra o dia.
- A chave vai só em `params` e nunca aparece em log nem em erro: o log registra só
  `recurso + custo + status`, o logger do httpx (que imprime a URL) fica em WARNING, e todo
  texto de erro passa por `redact` (`key=***`).
"""

import logging
import math
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from sociman_api.canais.models import VideoLive
from sociman_api.canais.resolve import Consulta
from sociman_api.config import get_settings
from sociman_api.db import get_engine
from sociman_api.errors import ApiError

log = logging.getLogger("sociman.youtube")
# O httpx registra a URL completa (com `key=`) em INFO: nunca pode chegar ao log.
logging.getLogger("httpx").setLevel(logging.WARNING)

ALLOWED = frozenset({
    ("GET", "channels"),
    ("GET", "playlistItems"),
    ("GET", "videos"),
    ("GET", "search"),
})

FUSO_COTA = ZoneInfo("America/Los_Angeles")
AVISO = 0.80
PAUSA = 0.95
TIMEOUT_S = 15.0
PREFIXO_CHAVE_INVALIDA = "Chave do YouTube inválida"
SEM_CHAVE = "A chave da API do YouTube não está configurada"
CANAL_NAO_ENCONTRADO = "Canal não encontrado no YouTube"
_PARTS_CANAL = "snippet,statistics,contentDetails"
_PARTS_VIDEO = "snippet,statistics,contentDetails,status,liveStreamingDetails"
_FIM_DO_DIA = {"quotaExceeded", "dailyLimitExceeded"}
_CHAVE_RUIM = {
    "keyInvalid": "a chave foi recusada",
    "API_KEY_INVALID": "a chave foi recusada",
    "keyExpired": "a chave expirou",
    "API_KEY_EXPIRED": "a chave expirou",
    "accessNotConfigured": "a YouTube Data API não está ativada no projeto da chave",
    "SERVICE_DISABLED": "a YouTube Data API não está ativada no projeto da chave",
    "ipRefererBlocked": "a chave não aceita pedidos deste servidor",
    "API_KEY_SERVICE_BLOCKED": "a chave não aceita a YouTube Data API",
}
_NAO_ENCONTRADO = {"playlistNotFound", "channelNotFound", "videoNotFound"}
_KEY_RE = re.compile(r"(key=)[^&\s\"'<>]+", re.IGNORECASE)


# ---- erros ----

class YoutubeErro(ApiError):
    """Erro tipado do YouTube. `chave_invalida` separa chave ruim de falha passageira."""

    def __init__(self, status: int, code: str, message: str, chave_invalida: bool = False,
                 details: dict[str, Any] | None = None):
        super().__init__(status, code, message, details=details)
        self.chave_invalida = chave_invalida


class CotaPausada(Exception):
    """A sync bateu 95% da cota do dia: pausa até `renova_em`."""

    def __init__(self, renova_em: datetime):
        super().__init__("cota do YouTube em 95%: sync pausada")
        self.renova_em = renova_em


def redact(texto: str, key: str = "") -> str:
    """Troca `key=…` por `key=***` e qualquer ocorrência literal da chave."""
    texto = _KEY_RE.sub(r"\1***", texto)
    if key:
        texto = texto.replace(key, "***")
    return texto


# ---- cota ----

@dataclass(frozen=True)
class CotaStatus:
    usadas: int
    limite: int
    renova_em: datetime

    @property
    def pausada(self) -> bool:
        return self.usadas >= math.floor(self.limite * PAUSA)

    @property
    def esgotada(self) -> bool:
        return self.usadas >= self.limite


def dia_cota(agora: datetime) -> date:
    return agora.astimezone(FUSO_COTA).date()


def renova_em(agora: datetime) -> datetime:
    """Próxima meia-noite do Pacífico (quando o Google zera a cota), em UTC."""
    amanha = dia_cota(agora) + timedelta(days=1)
    return datetime.combine(amanha, time(0), tzinfo=FUSO_COTA).astimezone(UTC)


def erro_cota(renova: datetime) -> ApiError:
    local = renova.astimezone(ZoneInfo(get_settings().app_tz))
    return ApiError(429, "youtube_quota",
                    f"A cota diária do YouTube acabou; volta às {local:%H:%M}",
                    details={"renovaEm": renova.isoformat()})


def cota_atual(db: Session, agora: datetime | None = None,
               limite: int | None = None) -> CotaStatus:
    agora = agora or datetime.now(UTC)
    usadas = db.execute(text("SELECT unidades FROM youtube_cota WHERE dia = :d"),
                        {"d": dia_cota(agora)}).scalar()
    return CotaStatus(usadas=usadas or 0, limite=limite or get_settings().yt_quota_daily,
                      renova_em=renova_em(agora))


def chave_invalida(db: Session) -> bool:
    """Algum canal ativo parou por chave recusada (`sync_error` com `PREFIXO_CHAVE_INVALIDA`)."""
    return db.execute(text(
        "SELECT EXISTS (SELECT 1 FROM canais_fonte WHERE archived_at IS NULL "
        "AND sync_status = 'erro' AND sync_error LIKE :p)"),
        {"p": PREFIXO_CHAVE_INVALIDA + "%"}).scalar() is True


def configurado() -> bool:
    return bool(get_settings().youtube_api_key.get_secret_value())


# ---- dados lidos ----

@dataclass(frozen=True)
class CanalInfo:
    youtube_channel_id: str
    title: str
    handle: str | None
    avatar_url: str | None
    subscribers: int | None
    video_count: int | None
    uploads_playlist_id: str


@dataclass(frozen=True)
class VideoInfo:
    youtube_video_id: str
    channel_id: str
    title: str
    description: str
    thumbnail_url: str | None
    published_at: datetime
    duration_s: int | None
    live: VideoLive
    views: int | None
    likes: int | None
    comments: int | None


@dataclass(frozen=True)
class PaginaPlaylist:
    video_ids: list[str]
    proxima: str | None
    total: int | None


_DURACAO = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_LIVE = {"live": VideoLive.ao_vivo, "upcoming": VideoLive.agendado}


def duracao_s(iso: str | None) -> int | None:
    """ISO 8601 do `contentDetails.duration` (`PT1H2M3S`, `P1DT2H`) em segundos."""
    m = _DURACAO.match(iso or "")
    if not m:
        return None
    d, h, mi, s = (int(g or 0) for g in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _thumb(snippet: dict[str, Any]) -> str | None:
    thumbs = snippet.get("thumbnails") or {}
    for size in ("medium", "high", "default"):
        url = (thumbs.get(size) or {}).get("url")
        if url:
            return url
    return None


def _parse_dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def parse_canal(item: dict[str, Any]) -> CanalInfo:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    custom = (snippet.get("customUrl") or "").strip()
    handle = custom.removeprefix("@").lower() if custom.startswith("@") else None
    hidden = bool(stats.get("hiddenSubscriberCount"))
    uploads = ((item.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
    return CanalInfo(
        youtube_channel_id=item["id"],
        title=snippet.get("title") or item["id"],
        handle=handle,
        avatar_url=_thumb(snippet),
        subscribers=None if hidden else _int(stats.get("subscriberCount")),
        video_count=_int(stats.get("videoCount")),
        # Sem o campo, a playlist de uploads segue a convenção UC… → UU….
        uploads_playlist_id=uploads or "UU" + item["id"][2:],
    )


def parse_video(item: dict[str, Any]) -> VideoInfo:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    return VideoInfo(
        youtube_video_id=item["id"],
        channel_id=snippet.get("channelId") or "",
        title=(snippet.get("title") or item["id"])[:500],
        description=(snippet.get("description") or "")[:5000],
        thumbnail_url=_thumb(snippet),
        published_at=_parse_dt(snippet["publishedAt"]),
        duration_s=duracao_s((item.get("contentDetails") or {}).get("duration")),
        live=_LIVE.get(snippet.get("liveBroadcastContent") or "none", VideoLive.nenhum),
        views=_int(stats.get("viewCount")),
        likes=_int(stats.get("likeCount")),
        comments=_int(stats.get("commentCount")),
    )


# ---- cliente ----

def _razoes(body: Any) -> tuple[list[str], str]:
    """(reasons, message) do envelope de erro do Google.

    O formato antigo traz `errors[].reason` (ex.: `quotaExceeded`); o novo, `details[].reason`
    (ex.: `API_KEY_INVALID`, com `badRequest` em `errors`). Vale qualquer um deles.
    """
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return [], ""
    reasons = [str(e["reason"]) for key in ("errors", "details")
               for e in err.get(key) or [] if isinstance(e, dict) and e.get("reason")]
    if err.get("status"):
        reasons.append(str(err["status"]))
    return reasons, str(err.get("message") or "")


class YoutubeClient:
    def __init__(self, api_key: str, base_url: str, quota_daily: int,
                 transport: httpx.BaseTransport | None = None,
                 relogio: Callable[[], datetime] | None = None):
        self._key = api_key
        self.quota_daily = quota_daily
        self.relogio = relogio or (lambda: datetime.now(UTC))
        self._http = httpx.Client(base_url=base_url.rstrip("/") + "/", transport=transport,
                                  timeout=TIMEOUT_S)

    @property
    def configurado(self) -> bool:
        return bool(self._key)

    def close(self) -> None:
        self._http.close()

    # -- cota --

    def _reservar(self, custo: int, sync: bool) -> None:
        """Soma o custo antes da chamada; recusa acima do teto (95% na sync, 100% no resto)."""
        agora = self.relogio()
        dia = dia_cota(agora)
        teto = math.floor(self.quota_daily * PAUSA) if sync else self.quota_daily
        with get_engine().begin() as conn:
            row = None
            if custo <= teto:
                row = conn.execute(text(
                    "INSERT INTO youtube_cota (dia, unidades) VALUES (:dia, :c) "
                    "ON CONFLICT (dia) DO UPDATE SET unidades = youtube_cota.unidades + :c "
                    "WHERE youtube_cota.unidades + :c <= :teto "
                    "RETURNING unidades"), {"dia": dia, "c": custo, "teto": teto}).first()
            if row is None:
                if sync:
                    raise CotaPausada(renova_em(agora))
                raise erro_cota(renova_em(agora))
            if row.unidades >= math.ceil(self.quota_daily * AVISO):
                self._avisar(conn, dia, row.unidades)

    def _avisar(self, conn: Any, dia: date, usadas: int) -> None:
        marcou = conn.execute(text(
            "UPDATE youtube_cota SET aviso_enviado = true "
            "WHERE dia = :dia AND NOT aviso_enviado RETURNING dia"), {"dia": dia}).first()
        if marcou is None:
            return
        from sociman_api.notificacoes import service as notificacoes
        from sociman_api.notificacoes.models import NotificacaoTipo

        with Session(bind=conn) as db:
            notificacoes.criar(
                db, NotificacaoTipo.cota_youtube, "Cota do YouTube em 80%",
                f"{usadas} de {self.quota_daily} unidades usadas hoje; em 95% a "
                "sincronização pausa até a cota renovar.",
                "/app/fontes", None, f"cota_youtube:{dia.isoformat()}",
                notificacoes.destinatarios_padrao(db, None))
            db.flush()

    def _encerrar_dia(self) -> None:
        with get_engine().begin() as conn:
            conn.execute(text(
                "INSERT INTO youtube_cota (dia, unidades) VALUES (:dia, :lim) "
                "ON CONFLICT (dia) DO UPDATE SET "
                "unidades = GREATEST(youtube_cota.unidades, :lim)"),
                {"dia": dia_cota(self.relogio()), "lim": self.quota_daily})

    # -- HTTP --

    def _get(self, recurso: str, params: dict[str, Any], custo: int, sync: bool) -> dict:
        if ("GET", recurso) not in ALLOWED:  # defesa: o princípio I fecha a lista
            raise ValueError(f"recurso do YouTube fora da lista permitida: {recurso}")
        if not self.configurado:
            raise YoutubeErro(503, "youtube_unconfigured", SEM_CHAVE)
        self._reservar(custo, sync)
        try:
            r = self._http.get(recurso, params={**params, "key": self._key})
        except httpx.HTTPError as exc:
            log.warning("youtube %s custo=%d falha de rede (%s)", recurso, custo,
                        type(exc).__name__)
            raise YoutubeErro(502, "youtube_error",
                              "Não foi possível falar com o YouTube; tente de novo") from None
        log.info("youtube %s custo=%d status=%d", recurso, custo, r.status_code)
        if r.status_code == 200:
            return r.json()
        raise self._erro(recurso, r)

    def _erro(self, recurso: str, r: httpx.Response) -> ApiError:
        try:
            body = r.json()
        except ValueError:
            body = None
        reasons, message = _razoes(body)
        reason = reasons[0] if reasons else ""
        if _FIM_DO_DIA.intersection(reasons):
            self._encerrar_dia()
            log.warning("youtube %s: o Google avisou cota esgotada", recurso)
            return erro_cota(renova_em(self.relogio()))
        chave = next((_CHAVE_RUIM[x] for x in reasons if x in _CHAVE_RUIM), None)
        if chave is not None:
            return YoutubeErro(502, "youtube_error", f"{PREFIXO_CHAVE_INVALIDA}: {chave}",
                               chave_invalida=True)
        if r.status_code == 404 or _NAO_ENCONTRADO.intersection(reasons):
            return YoutubeErro(404, "canal_not_found", CANAL_NAO_ENCONTRADO)
        detalhe = redact(message, self._key)[:300]
        return YoutubeErro(502, "youtube_error",
                           f"O YouTube recusou o pedido ({r.status_code}"
                           f"{' ' + reason if reason else ''}){': ' + detalhe if detalhe else ''}")

    # -- consultas --

    def canais(self, ids: list[str], sync: bool = False) -> list[CanalInfo]:
        if not ids:
            return []
        body = self._get("channels", {"part": _PARTS_CANAL, "id": ",".join(ids),
                                      "maxResults": 50}, 1, sync)
        return [parse_canal(i) for i in body.get("items") or []]

    def canal(self, consulta: Consulta) -> CanalInfo:
        """Resolve a entrada do usuário num canal (404 `canal_not_found` se não houver)."""
        if consulta.tipo == "id":
            itens = self.canais([consulta.valor])
        elif consulta.tipo in ("handle", "username"):
            campo = "forHandle" if consulta.tipo == "handle" else "forUsername"
            body = self._get("channels", {"part": _PARTS_CANAL, campo: consulta.valor}, 1, False)
            itens = [parse_canal(i) for i in body.get("items") or []]
        elif consulta.tipo == "busca":
            body = self._get("search", {"part": "snippet", "type": "channel",
                                        "q": consulta.valor, "maxResults": 1}, 100, False)
            achados = [((i.get("id") or {}).get("channelId")
                        or (i.get("snippet") or {}).get("channelId"))
                       for i in body.get("items") or []]
            itens = self.canais([a for a in achados if a][:1])
        else:  # vídeo → canal dono
            body = self._get("videos", {"part": "snippet", "id": consulta.valor}, 1, False)
            donos = [(i.get("snippet") or {}).get("channelId") for i in body.get("items") or []]
            itens = self.canais([d for d in donos if d][:1])
        if not itens:
            raise YoutubeErro(404, "canal_not_found", CANAL_NAO_ENCONTRADO)
        return itens[0]

    def playlist(self, playlist_id: str, pagina: str | None = None,
                 sync: bool = True) -> PaginaPlaylist:
        params: dict[str, Any] = {"part": "contentDetails", "playlistId": playlist_id,
                                  "maxResults": 50}
        if pagina:
            params["pageToken"] = pagina
        body = self._get("playlistItems", params, 1, sync)
        ids = [((i.get("contentDetails") or {}).get("videoId")
                or ((i.get("snippet") or {}).get("resourceId") or {}).get("videoId"))
               for i in body.get("items") or []]
        return PaginaPlaylist(video_ids=[v for v in ids if v],
                              proxima=body.get("nextPageToken"),
                              total=_int((body.get("pageInfo") or {}).get("totalResults")))

    def videos(self, ids: list[str], sync: bool = True) -> list[VideoInfo]:
        """Até 50 ids por chamada (1 unidade). Ids que não voltam estão indisponíveis."""
        if not ids:
            return []
        if len(ids) > 50:
            raise ValueError("videos.list aceita até 50 ids")
        body = self._get("videos", {"part": _PARTS_VIDEO, "id": ",".join(ids),
                                    "maxResults": 50}, 1, sync)
        out = []
        for item in body.get("items") or []:
            try:
                out.append(parse_video(item))
            except (KeyError, ValueError):
                log.warning("vídeo %s com dados incompletos; ignorado", item.get("id"))
        return out


def novo_cliente(transport: httpx.BaseTransport | None = None) -> YoutubeClient:
    s = get_settings()
    return YoutubeClient(s.youtube_api_key.get_secret_value(), s.youtube_api_url,
                         s.yt_quota_daily, transport=transport)


def get_youtube_client() -> Iterator[YoutubeClient]:
    """Dependência das rotas (os testes trocam por `app.dependency_overrides`)."""
    client = novo_cliente()
    try:
        yield client
    finally:
        client.close()
