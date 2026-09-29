"""OpenShorts falso (T046): um `httpx.MockTransport` com estado, para o cliente de
`envios/openshorts.py`. Os testes nunca chamam o OpenShorts real.

Uso: `from fakes.openshorts_fake import openshorts_clip, openshorts_fake  # noqa: F401` e
`fake.client()` (o cliente com o transporte falso), passado a `rodar(db, client=...)`.

O que dá para ligar:
- `fora` (conexão recusada em tudo), `erro_5xx` (500 em tudo), `ocupado` (quantos
  `/api/process` respondem 429), `recusar` (`(status, detail)` no próximo `/api/process`);
- `needs_confirmation` (o `/api/process` pede confirmação de qualidade, menos com
  `force_low_quality`);
- `resultado`: `"ok"`, `"sem_clipes"` ("No clips could be rendered") ou `"falhou"`;
- `n_clipes`, `passos_fila` e `passos_processando` (quantos `GET /api/status` em cada fase);
- `expirar(job_id)` (404 em tudo daquele job, como depois da retenção de 24 h);
- `sem_fala` (índices cujo `/api/subtitle` e transcrição respondem 400);
- `falhar_download` (quantos downloads respondem 500);
- `inverter_ordem` e `desvio_s` (o próximo job devolve os clipes em ordem inversa e com o
  trecho deslocado, como um job novo do mesmo vídeo).

Os `/videos/*` servem um MP4 sintético de verdade (ffmpeg), para a importação rodar o ffprobe
e o MinIO de verdade. `requests` guarda todos os pedidos (guardas do princípio I).
"""

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from sociman_api.envios.openshorts import OpenShortsClient

BASE = "http://openshorts.test"
NO_CLIPS = "No clips could be rendered from this video."


def gerar_clipe(dest: Path, segundos: int = 2) -> bytes:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=0x336699:s=360x640:d={segundos}:r=24",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", str(dest)],
        check=True, timeout=120,
    )
    return dest.read_bytes()


@dataclass
class FakeJob:
    id: str
    body: dict[str, Any]
    n_clipes: int
    resultado: str
    polls: int = 0
    clips: list[dict[str, Any]] = field(default_factory=list)


class OpenShortsFake:
    def __init__(self, clip_bytes: bytes):
        self.clip_bytes = clip_bytes
        self.requests: list[httpx.Request] = []
        self.jobs: dict[str, FakeJob] = {}
        self.uploads: dict[str, bytes | None] = {}
        self.processados: list[dict[str, Any]] = []  # corpos do /api/process aceitos
        self.subtitles: list[dict[str, Any]] = []
        self.fora = False
        self.erro_5xx = False
        self.ocupado = 0
        self.recusar: tuple[int, str] | None = None
        self.needs_confirmation = False
        self.resultado = "ok"
        self.n_clipes = 3
        self.passos_fila = 1
        self.passos_processando = 1
        self.expirados: set[str] = set()
        self.sem_fala: set[int] = set()
        self.falhar_download = 0
        self.inverter_ordem = False
        self.desvio_s = 0.0
        self.transport = httpx.MockTransport(self._handle)

    # ---- para os testes ----

    def client(self) -> OpenShortsClient:
        return OpenShortsClient(base_url=BASE, transport=self.transport)

    def expirar(self, job_id: str) -> None:
        self.expirados.add(job_id)

    def pedidos(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path) for r in self.requests]

    def job(self) -> FakeJob:
        (job,) = self.jobs.values()
        return job

    # ---- servidor ----

    @staticmethod
    def _json(status: int, data: Any) -> httpx.Response:
        return httpx.Response(status, json=data)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if self.fora:
            raise httpx.ConnectError("conexão recusada", request=request)
        if self.erro_5xx:
            return self._json(500, {"detail": "Internal Server Error"})
        path, method = request.url.path, request.method
        parts = path.strip("/").split("/")
        if method == "GET" and path == "/health":
            return self._json(200, {"status": "ok"})
        if method == "POST" and path == "/api/uploads":
            upload_id = str(uuid.uuid4())
            self.uploads[upload_id] = None
            return self._json(200, {"upload_id": upload_id, "method": "PUT",
                                    "upload_url": f"http://outro-host/api/uploads/{upload_id}"})
        if method == "PUT" and path.startswith("/api/uploads/"):
            return self._put_upload(parts[-1], request)
        if method == "POST" and path == "/api/process":
            return self._process(json.loads(request.content))
        if method == "GET" and path.startswith("/api/status/"):
            return self._status(parts[-1])
        if method == "POST" and path == "/api/subtitle":
            return self._subtitle(json.loads(request.content))
        if method == "GET" and path.startswith("/api/clip/") and parts[-1] == "transcript":
            return self._transcript(parts[2], int(parts[3]))
        if method == "GET" and path.startswith("/videos/"):
            return self._video(parts[1], parts[2])
        return self._json(404, {"detail": "Not Found"})

    def _put_upload(self, upload_id: str, request: httpx.Request) -> httpx.Response:
        if upload_id not in self.uploads:
            return self._json(404, {"detail": "Unknown or expired upload_id"})
        self.uploads[upload_id] = request.content
        return self._json(200, {"upload_id": upload_id, "bytes": len(request.content)})

    def _process(self, body: dict[str, Any]) -> httpx.Response:
        if self.ocupado > 0:
            self.ocupado -= 1
            return self._json(429, {"detail": "Too many jobs"})
        if self.recusar is not None:
            status, detail = self.recusar
            self.recusar = None
            return self._json(status, {"detail": detail})
        upload_id = body.get("upload_id")
        if upload_id is not None and not self.uploads.get(upload_id):
            return self._json(409, {"detail": "Upload not received yet"})
        if self.needs_confirmation and not body.get("force_low_quality"):
            return self._json(200, {"needs_confirmation": True,
                                    "quality_check": {"max_height": 360, "min_height": 720,
                                                      "cookies_invalid": False}})
        job = FakeJob(id=str(uuid.uuid4()), body=body, n_clipes=self.n_clipes,
                      resultado=self.resultado)
        job.clips = [self._clip(job.id, i, self.desvio_s) for i in range(job.n_clipes)]
        if self.inverter_ordem:
            job.clips.reverse()
        self.jobs[job.id] = job
        self.processados.append(body)
        return self._json(200, {"job_id": job.id, "status": "queued", "partial": None})

    @staticmethod
    def _clip(job_id: str, i: int, desvio_s: float = 0.0) -> dict[str, Any]:
        return {
            "start": 10.0 + 30 * i + desvio_s, "end": 35.5 + 30 * i + desvio_s,
            "viral_hook_text": f"Gancho do clipe {i + 1}",
            "video_title_for_youtube_short": f"Título {i + 1}",
            "video_description_for_tiktok": f"Descrição {i + 1} #corte",
            "predicted_score": 81.6 - i,
            "video_url": f"/videos/{job_id}/fonte_clip_{i + 1}.mp4",
        }

    def _status(self, job_id: str) -> httpx.Response:
        job = self.jobs.get(job_id)
        if job is None or job_id in self.expirados:
            return self._json(404, {"detail": "Job not found"})
        job.polls += 1
        base = {"logs": [f"Job {job_id} queued."], "partial": None}
        if job.polls <= self.passos_fila:
            return self._json(200, base | {"status": "queued", "result": None,
                                           "queue": {"position": 2, "ahead": 1,
                                                     "eta_seconds": 600}})
        if job.polls <= self.passos_fila + self.passos_processando:
            return self._json(200, base | {"status": "processing", "queue": None,
                                           "result": {"clips": job.clips[:1]}})
        if job.resultado == "sem_clipes":
            return self._json(200, base | {"status": "failed", "queue": None, "result": None,
                                           "logs": base["logs"] + [NO_CLIPS]})
        if job.resultado == "falhou":
            return self._json(200, base | {"status": "failed", "queue": None, "result": None,
                                           "logs": base["logs"] + ["Download failed: 403", ""]})
        return self._json(200, base | {"status": "completed", "queue": None,
                                       "result": {"clips": job.clips, "cost_analysis": None}})

    def _subtitle(self, body: dict[str, Any]) -> httpx.Response:
        self.subtitles.append(body)
        job = self.jobs.get(body.get("job_id", ""))
        if job is None or job.id in self.expirados:
            return self._json(404, {"detail": "Job not found"})
        idx = int(body["clip_index"])
        if idx in self.sem_fala:
            return self._json(400, {"detail": "No words found for this clip range."})
        name = f"subtitled_1700000000_fonte_clip_{idx + 1}.mp4"
        job.clips[idx]["video_url"] = f"/videos/{job.id}/{name}"
        return self._json(200, {"success": True, "new_video_url": f"/videos/{job.id}/{name}"})

    def _transcript(self, job_id: str, idx: int) -> httpx.Response:
        if job_id not in self.jobs or job_id in self.expirados:
            return self._json(404, {"detail": "Job not found"})
        if idx in self.sem_fala:
            return self._json(400, {"detail": "Transcript not found in metadata"})
        words = [{"text": w, "startMs": 300 * n, "endMs": 300 * n + 250}
                 for n, w in enumerate(f"olá este é o clipe {idx + 1}".split())]
        return self._json(200, {"captions": words, "durationSec": 25.5, "language": "pt"})

    def _video(self, job_id: str, _name: str) -> httpx.Response:
        if job_id not in self.jobs or job_id in self.expirados:
            return self._json(404, {"detail": "Not Found"})
        if self.falhar_download > 0:
            self.falhar_download -= 1
            return self._json(500, {"detail": "boom"})
        return httpx.Response(200, content=self.clip_bytes,
                              headers={"content-type": "video/mp4"})


@pytest.fixture(scope="session")
def openshorts_clip(tmp_path_factory) -> bytes:
    return gerar_clipe(tmp_path_factory.mktemp("openshorts") / "clip.mp4")


@pytest.fixture
def openshorts_fake(openshorts_clip) -> OpenShortsFake:
    return OpenShortsFake(openshorts_clip)
