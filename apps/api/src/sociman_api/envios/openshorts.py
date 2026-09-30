"""Cliente do OpenShorts (research R5, R6 e R7; princípio I).

Lista fechada: só `health()`, `process()`, `reserve_upload()`, `put_upload()`, `status()`,
`subtitle()`, `transcript()` e `download(video_url)`. Cada pedido passa por `_check`, que recusa
o que não estiver em `ALLOWED` (o guarda do princípio I confere a lista): nada de
`/api/social/*`, `/api/thumbnail/publish` nem `/api/saasshorts/post`. `download()` só aceita
caminhos sob `/videos/` do próprio OpenShorts.

Erros tipados, que as trilhas do agendador traduzem (tabela de R6):
- `OpenShortsFora`: conexão recusada, timeout ou 5xx (o envio espera com backoff);
- `OpenShortsOcupado`: 429;
- `OpenShortsNaoEncontrado`: 404 (job perdido ou clipes expirados pela retenção de 24 h);
- `OpenShortsRecusou`: os demais 4xx, com o `detail` do gerador.

O transporte entra por injeção (`get_openshorts_client(transport=...)`): os testes usam o fake
de `tests/fakes/openshorts_fake.py` e nunca chamam o OpenShorts real.
"""

import posixpath
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from sociman_api.config import get_settings

# (método, prefixo do caminho). Um prefixo terminado em "/" casa com o que vier depois.
ALLOWED: tuple[tuple[str, str], ...] = (
    ("GET", "/health"),
    ("POST", "/api/process"),
    ("POST", "/api/uploads"),
    ("PUT", "/api/uploads/"),
    ("GET", "/api/status/"),
    ("POST", "/api/subtitle"),
    ("GET", "/api/clip/"),
    ("GET", "/videos/"),
)
TIMEOUT = httpx.Timeout(30.0, connect=5.0)
# A legenda queima o clipe inteiro no CPU (30 a 60 s por clipe, R7): mais folga de leitura.
SUBTITLE_TIMEOUT = httpx.Timeout(600.0, connect=5.0)
UPLOAD_TIMEOUT = httpx.Timeout(600.0, connect=5.0)
CHUNK = 1024 * 1024


class OpenShortsError(Exception):
    def __init__(self, message: str, status: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status = status
        self.detail = detail


class OpenShortsFora(OpenShortsError):
    """Conexão recusada, timeout ou 5xx."""


class OpenShortsOcupado(OpenShortsError):
    """429: o gerador pediu para esperar."""


class OpenShortsNaoEncontrado(OpenShortsError):
    """404: o job (ou o clipe) não existe mais."""


class OpenShortsRecusou(OpenShortsError):
    """4xx (menos 404 e 429): o gerador recusou o pedido; `detail` diz por quê."""


def _allowed(method: str, path: str) -> bool:
    for m, prefix in ALLOWED:
        if m != method:
            continue
        if prefix.endswith("/") and path.startswith(prefix) and len(path) > len(prefix):
            return True
        if path == prefix:
            return True
    return False


def _detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:500]
    if isinstance(data, Mapping):
        detail = data.get("detail")
        if isinstance(detail, str):
            return detail[:500]
        if detail is not None:
            return str(detail)[:500]
    return str(data)[:500]


def _raise_for(resp: httpx.Response, what: str) -> None:
    status = resp.status_code
    if status < 400:
        return
    detail = _detail(resp)
    if status >= 500:
        raise OpenShortsFora(f"{what}: SociShorts respondeu {status}", status, detail)
    if status == 429:
        raise OpenShortsOcupado(f"{what}: SociShorts ocupado", status, detail)
    if status == 404:
        raise OpenShortsNaoEncontrado(f"{what}: não encontrado no SociShorts", status, detail)
    raise OpenShortsRecusou(f"{what}: SociShorts recusou ({status})", status, detail)


def video_path(video_url: str) -> str:
    """O caminho de um `video_url` do OpenShorts, só se estiver sob `/videos/` (e sem `..`).

    Aceita o caminho relativo (`/videos/<job>/<arquivo>`, como o gerador devolve) ou uma URL
    absoluta do próprio OpenShorts; qualquer outra coisa levanta `ValueError`.
    """
    parts = urlsplit(video_url)
    if parts.scheme or parts.netloc:
        base = urlsplit(get_settings().openshorts_url)
        if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
            raise ValueError("download fora do SociShorts")
    path = parts.path
    if not path.startswith("/videos/") or ".." in path.split("/"):
        raise ValueError("download só de /videos/")
    if posixpath.normpath(path) != path:
        raise ValueError("caminho de vídeo inválido")
    return path


class OpenShortsClient:
    def __init__(self, base_url: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = (base_url or get_settings().openshorts_url).rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, transport=transport, timeout=TIMEOUT,
                                  follow_redirects=False)

    def close(self) -> None:
        self._http.close()

    # ---- baixo nível ----

    def _request(self, method: str, path: str, what: str, **kwargs: Any) -> httpx.Response:
        if not _allowed(method, path):
            raise ValueError(f"pedido fora da lista do SociShorts: {method} {path}")
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:  # conexão recusada, DNS, timeout
            raise OpenShortsFora(f"{what}: SociShorts fora do ar ({type(exc).__name__})") from exc
        _raise_for(resp, what)
        return resp

    @staticmethod
    def _json(resp: httpx.Response, what: str) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError as exc:
            raise OpenShortsFora(f"{what}: resposta inválida do SociShorts") from exc
        if not isinstance(data, dict):
            raise OpenShortsFora(f"{what}: resposta inválida do SociShorts")
        return data

    # ---- a lista fechada ----

    def health(self, timeout: float | None = None) -> bool:
        try:
            kwargs: dict[str, Any] = {"timeout": timeout} if timeout is not None else {}
            self._request("GET", "/health", "health", **kwargs)
        except OpenShortsError:
            return False
        return True

    def process(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """`POST /api/process` em JSON. Devolve `{job_id, status}` ou `{needs_confirmation}`."""
        resp = self._request("POST", "/api/process", "process", json=dict(body))
        return self._json(resp, "process")

    def reserve_upload(self, filename: str) -> str:
        """Reserva o upload e devolve o `upload_id` (o `upload_url` devolvido é ignorado: o
        `PUT` vai sempre para `OPENSHORTS_URL`, R5)."""
        resp = self._request("POST", "/api/uploads", "upload", json={"filename": filename})
        upload_id = self._json(resp, "upload").get("upload_id")
        if not isinstance(upload_id, str) or not upload_id or "/" in upload_id:
            raise OpenShortsFora("upload: resposta sem upload_id")
        return upload_id

    def put_upload(self, upload_id: str, chunks: Iterable[bytes], size: int) -> dict[str, Any]:
        """`PUT /api/uploads/{id}` em streaming (os pedaços vêm do MinIO, sem passar pela RAM
        inteira)."""
        resp = self._request(
            "PUT", f"/api/uploads/{upload_id}", "upload", content=chunks,
            headers={"content-length": str(size), "content-type": "application/octet-stream"},
            timeout=UPLOAD_TIMEOUT,
        )
        return self._json(resp, "upload")

    def status(self, job_id: str) -> dict[str, Any]:
        resp = self._request("GET", f"/api/status/{job_id}", "status")
        return self._json(resp, "status")

    def subtitle(self, job_id: str, clip_index: int, style: Mapping[str, Any],
                 input_filename: str | None = None) -> str:
        """Queima a legenda do kit (`style` = seção `openshorts.subtitle`) e devolve o
        `new_video_url`."""
        body = dict(style) | {"job_id": job_id, "clip_index": clip_index}
        if input_filename:
            body["input_filename"] = input_filename
        resp = self._request("POST", "/api/subtitle", "legenda", json=body,
                             timeout=SUBTITLE_TIMEOUT)
        url = self._json(resp, "legenda").get("new_video_url")
        if not isinstance(url, str) or not url:
            raise OpenShortsFora("legenda: resposta sem new_video_url")
        return url

    def transcript(self, job_id: str, clip_index: int) -> dict[str, Any]:
        resp = self._request("GET", f"/api/clip/{job_id}/{clip_index}/transcript", "transcrição")
        return self._json(resp, "transcrição")

    def download(self, video_url: str, dest: Path) -> int:
        """Baixa o clipe em streaming para `dest` (no HD). Devolve os bytes."""
        path = video_path(video_url)
        if not _allowed("GET", path):
            raise ValueError(f"pedido fora da lista do SociShorts: GET {path}")
        size = 0
        try:
            with self._http.stream("GET", path) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    _raise_for(resp, "download")
                with dest.open("wb") as fh:
                    for chunk in resp.iter_bytes(CHUNK):
                        fh.write(chunk)
                        size += len(chunk)
        except httpx.TransportError as exc:
            raise OpenShortsFora(f"download: SociShorts fora do ar ({type(exc).__name__})") from exc
        return size


def get_openshorts_client(transport: httpx.BaseTransport | None = None) -> OpenShortsClient:
    """Fábrica (tests/fakes/__init__.py): None = o OpenShorts de `OPENSHORTS_URL`."""
    return OpenShortsClient(transport=transport)


# ---- corpo do /api/process (R6) ----

def corpo_process(config: Mapping[str, Any], *, url: str | None = None,
                  upload_id: str | None = None, force_low_quality: bool = False
                  ) -> dict[str, Any]:
    """O JSON do `/api/process` a partir de `envios.config`.

    `acknowledged: true` é a declaração do dono (o SociMan já registrou o direito e o aviso no
    histórico do envio); `auto_hook` é sempre false (o gancho é o do kit, queimado pelo worker
    da 004); `captions` só com a legenda do gerador (com a do kit, o `/api/subtitle` queima
    depois, R7); `target_clips` é omitido quando a IA decide.
    """
    if (url is None) == (upload_id is None):
        raise ValueError("informe url ou upload_id")
    body: dict[str, Any] = {"url": url} if url is not None else {"upload_id": upload_id}
    body |= {
        "acknowledged": True,
        "auto_hook": False,
        "captions": config["legenda"] == "gerador",
        "layouts": [config["layout"]],
        "output_format": config["formato"],
        "clip_min_seconds": config["clip_min_s"],
        "clip_max_seconds": config["clip_max_s"],
    }
    if config.get("quantidade") is not None:
        body["target_clips"] = config["quantidade"]
    if force_low_quality:
        body["force_low_quality"] = True
    return body
