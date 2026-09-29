"""YouTube Data API falsa (T020): `httpx.MockTransport` com estado, que registra os pedidos.

Monta as respostas a partir de `tests/fixtures/youtube/*.json` (gravadas sem a chave). Uso:

    from fakes.youtube_fake import youtube_fake  # noqa: F401  (fixture)

    def test_x(youtube_fake):
        canal = youtube_fake.add_canal("UC…", "Nome", handle="nome")
        youtube_fake.add_video(canal, "abcdefghijk", published_at=..., views=100)
        client = youtube_fake.client(quota_daily=40)

`erro_proximo("keyInvalid")` (ou `falhar_sempre`) faz o próximo pedido (ou todos) falhar como o
Google falharia. `requests` guarda (método, recurso, params sem a chave).
"""

import copy
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from sociman_api.canais.youtube import YoutubeClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "youtube"
CHAVE_TESTE = "chave-de-teste-nao-vaza-123"
BASE_URL = "https://youtube.fake/youtube/v3"
ERROS = {
    "keyInvalid": (400, "error_keyInvalid.json"),
    "accessNotConfigured": (403, "error_accessNotConfigured.json"),
    "quotaExceeded": (403, "error_quotaExceeded.json"),
    "playlistNotFound": (404, "error_playlistNotFound.json"),
}


def fixture(nome: str) -> dict[str, Any]:
    return json.loads((FIXTURES / nome).read_text())


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class YoutubeFake:
    def __init__(self) -> None:
        self.canais: dict[str, dict[str, Any]] = {}
        self.handles: dict[str, str] = {}
        self.usernames: dict[str, str] = {}
        self.videos: dict[str, dict[str, Any]] = {}
        self.uploads: dict[str, list[str]] = {}  # playlist → ids, mais novo primeiro
        self.removidos: set[str] = set()  # ids que o videos.list não devolve mais
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.urls: list[str] = []  # URLs completas (para conferir a chave em params)
        self._erros: list[str] = []
        self.falhar_sempre: str | None = None
        self.page_size = 50

    # ---- dados ----

    def add_canal(self, channel_id: str, title: str = "The IT Nerd", handle: str | None = None,
                  username: str | None = None, subscribers: int | None = 45600,
                  avatar: str | None = "https://yt3.ggpht.com/avatar-teste") -> str:
        item = fixture("channel.json")
        item["id"] = channel_id
        item["snippet"]["title"] = title
        if handle:
            item["snippet"]["customUrl"] = f"@{handle}"
            self.handles[handle.lower()] = channel_id
        else:
            item["snippet"].pop("customUrl", None)
        if avatar is None:
            item["snippet"]["thumbnails"] = {}
        else:
            item["snippet"]["thumbnails"]["medium"]["url"] = avatar
        if subscribers is None:
            item["statistics"]["hiddenSubscriberCount"] = True
            item["statistics"].pop("subscriberCount", None)
        else:
            item["statistics"]["subscriberCount"] = str(subscribers)
        playlist = "UU" + channel_id[2:]
        item["contentDetails"]["relatedPlaylists"]["uploads"] = playlist
        self.uploads.setdefault(playlist, [])
        if username:
            self.usernames[username] = channel_id
        self.canais[channel_id] = item
        self._sync_count(channel_id)
        return channel_id

    def _sync_count(self, channel_id: str) -> None:
        item = self.canais[channel_id]
        item["statistics"]["videoCount"] = str(len(self.uploads["UU" + channel_id[2:]]))

    def add_video(self, channel_id: str, video_id: str, published_at: datetime,
                  views: int | None = 1000, likes: int | None = 50, comments: int | None = 5,
                  duration: str = "PT24M10S", live: str = "none", title: str | None = None,
                  thumb: bool = True) -> str:
        """Acrescenta no topo da playlist de uploads (mais novo primeiro)."""
        item = fixture("video.json")
        item["id"] = video_id
        item["snippet"]["channelId"] = channel_id
        item["snippet"]["publishedAt"] = iso(published_at)
        item["snippet"]["title"] = title or f"Vídeo {video_id}"
        item["snippet"]["liveBroadcastContent"] = live
        if thumb:
            for size in item["snippet"]["thumbnails"].values():
                size["url"] = size["url"].replace("vvvvvvvvvvv", video_id)
        else:
            item["snippet"]["thumbnails"] = {}
        item["contentDetails"]["duration"] = duration
        self.set_stats(item, views, likes, comments)
        self.videos[video_id] = item
        self.uploads["UU" + channel_id[2:]].insert(0, video_id)
        self._sync_count(channel_id)
        return video_id

    @staticmethod
    def set_stats(item: dict[str, Any], views: int | None, likes: int | None,
                  comments: int | None) -> None:
        stats = {"favoriteCount": "0"}
        for key, value in (("viewCount", views), ("likeCount", likes),
                           ("commentCount", comments)):
            if value is not None:
                stats[key] = str(value)
        item["statistics"] = stats

    def stats(self, video_id: str, views: int | None, likes: int | None = None,
              comments: int | None = None) -> None:
        self.set_stats(self.videos[video_id], views, likes, comments)

    def erro_proximo(self, tipo: str) -> None:
        self._erros.append(tipo)

    def contar(self, recurso: str) -> int:
        return sum(1 for _, r, _ in self.requests if r == recurso)

    # ---- transporte ----

    def _erro(self, tipo: str) -> httpx.Response:
        status, nome = ERROS[tipo]
        return httpx.Response(status, json=fixture(nome))

    def handler(self, request: httpx.Request) -> httpx.Response:
        recurso = request.url.path.rsplit("/", 1)[-1]
        params = dict(request.url.params)
        self.urls.append(str(request.url))
        params.pop("key", None)
        self.requests.append((request.method, recurso, params))
        if self._erros:
            return self._erro(self._erros.pop(0))
        if self.falhar_sempre:
            return self._erro(self.falhar_sempre)
        rota: Callable[[dict[str, str]], httpx.Response] | None = {
            "channels": self._channels, "videos": self._videos,
            "playlistItems": self._playlist, "search": self._search,
        }.get(recurso)
        if rota is None:
            return httpx.Response(404, json={"error": {"code": 404, "message": "Not Found"}})
        return rota(params)

    def _lista(self, items: list[dict[str, Any]], **extra: Any) -> httpx.Response:
        return httpx.Response(200, json={"kind": "lista", "etag": "x", "items": items,
                                         "pageInfo": {"totalResults": len(items),
                                                      "resultsPerPage": 50}, **extra})

    def _channels(self, params: dict[str, str]) -> httpx.Response:
        if "id" in params:
            ids = params["id"].split(",")
        elif "forHandle" in params:
            ids = [self.handles.get(params["forHandle"].removeprefix("@").lower(), "")]
        elif "forUsername" in params:
            ids = [self.usernames.get(params["forUsername"], "")]
        else:
            ids = []
        return self._lista([copy.deepcopy(self.canais[i]) for i in ids if i in self.canais])

    def _videos(self, params: dict[str, str]) -> httpx.Response:
        ids = params.get("id", "").split(",")
        return self._lista([copy.deepcopy(self.videos[i]) for i in ids
                            if i in self.videos and i not in self.removidos])

    def _playlist(self, params: dict[str, str]) -> httpx.Response:
        playlist = params.get("playlistId", "")
        if playlist not in self.uploads:
            return self._erro("playlistNotFound")
        ids = self.uploads[playlist]
        start = int(params.get("pageToken") or 0)
        pagina = ids[start:start + self.page_size]
        items = [{"kind": "youtube#playlistItem", "id": f"pi-{v}",
                  "contentDetails": {"videoId": v}} for v in pagina]
        extra: dict[str, Any] = {}
        if start + self.page_size < len(ids):
            extra["nextPageToken"] = str(start + self.page_size)
        resp = self._lista(items, **extra)
        body = resp.json()
        body["pageInfo"]["totalResults"] = len(ids)
        return httpx.Response(200, json=body)

    def _search(self, params: dict[str, str]) -> httpx.Response:
        q = params.get("q", "").lower()
        achados = [c for c in self.canais.values() if q in c["snippet"]["title"].lower()]
        items = []
        for c in achados[:1]:
            item = fixture("search_channel.json")["items"][0]
            item["id"]["channelId"] = c["id"]
            item["snippet"]["channelId"] = c["id"]
            items.append(item)
        return self._lista(items)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def client(self, quota_daily: int = 10000, key: str = CHAVE_TESTE,
               relogio: Callable[[], datetime] | None = None) -> YoutubeClient:
        return YoutubeClient(key, BASE_URL, quota_daily, transport=self.transport(),
                             relogio=relogio)


@pytest.fixture
def youtube_fake() -> YoutubeFake:
    return YoutubeFake()
