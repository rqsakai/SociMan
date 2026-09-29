"""OpenShorts e YouTube Data API de mentira para os e2e (spec 006, T078). Só stdlib.

Roda no serviço `openshorts-fake` do `docker-compose.e2e.yml` (imagem `sociman-api-e2e`, que já
tem o ffmpeg) e atende, na porta 8000:
- a parte da API do OpenShorts que o cliente `envios/openshorts.py` usa: `/health`,
  `POST /api/process`, `POST|PUT /api/uploads`, `GET /api/status/{job}`, `POST /api/subtitle`,
  `GET /api/clip/{job}/{i}/transcript` e `GET /videos/{job}/{arquivo}`. O job passa por
  `queued → processing → completed` em poucos segundos, e os clipes são MP4 sintéticos gerados
  com o ffmpeg na subida. Uma fonte com `sem-clipes` na URL ou no título termina em "No clips";
- `GET /youtube/v3/{channels,playlistItems,videos,search}`: dois canais e seus vídeos, sem
  miniaturas externas (`thumbnails` vazio, e a API devolve `null`). O e2e nunca chama o Google.

Nada aqui publica: não existe `/api/social` (princípio I).
"""

import json
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PORTA = 8000
N_CLIPES = 3
FILA_S = 1.5  # tempo em `queued`
PROCESSANDO_S = 2.5  # tempo em `processing`
NO_CLIPS = "No clips could be rendered from this video."
CORES = ("0x336699", "0x993366", "0x669933")
DIR = Path(tempfile.mkdtemp(prefix="openshorts-fake-"))

# ---- YouTube: dados de mentira ----

AGORA = datetime.now(UTC)
CANAIS = {
    "UCe2eCanalDeMentira0000A": {"title": "Canal de Mentira", "handle": "canaldementira",
                                 "subscribers": 45600},
    "UCe2eOutroCanalFake0000B": {"title": "Outro Canal Fake", "handle": "outrocanalfake",
                                 "subscribers": 1200},
}
# (id de 11, canal, título, dias atrás, duração ISO, views, likes, comentários)
VIDEOS = [
    ("e2eVideo001", "UCe2eCanalDeMentira0000A", "Review do notebook gamer", 1, "PT18M20S",
     54000, 3100, 420),
    ("e2eVideo002", "UCe2eCanalDeMentira0000A", "10 atalhos do teclado", 3, "PT9M05S",
     21000, 900, 80),
    ("e2eVideo003", "UCe2eCanalDeMentira0000A", "Montando um PC em 2026", 12, "PT42M00S",
     8000, 300, 25),
    ("e2eVideo004", "UCe2eCanalDeMentira0000A", "Live de perguntas", 20, "PT2H10M00S",
     3000, 100, 30),
    ("e2eVideo005", "UCe2eCanalDeMentira0000A", "Short rápido", 2, "PT30S", 90000, 5000, 100),
    ("e2eVideo006", "UCe2eOutroCanalFake0000B", "Entrevista com dev", 5, "PT55M00S",
     4000, 250, 40),
    ("e2eVideo007", "UCe2eOutroCanalFake0000B", "Dicas de carreira", 30, "PT15M00S",
     1500, 60, 9),
]


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canal_item(cid: str) -> dict:
    c = CANAIS[cid]
    n = sum(1 for v in VIDEOS if v[1] == cid)
    return {
        "kind": "youtube#channel", "etag": "x", "id": cid,
        "snippet": {"title": c["title"], "description": "Canal do e2e",
                    "customUrl": f"@{c['handle']}", "publishedAt": "2015-03-01T12:00:00Z",
                    "thumbnails": {}, "country": "BR"},
        "contentDetails": {"relatedPlaylists": {"likes": "", "uploads": "UU" + cid[2:]}},
        "statistics": {"viewCount": "1234567", "subscriberCount": str(c["subscribers"]),
                       "hiddenSubscriberCount": False, "videoCount": str(n)},
    }


def _video_item(v: tuple) -> dict:
    vid, cid, titulo, dias, duracao, views, likes, comentarios = v
    return {
        "kind": "youtube#video", "etag": "x", "id": vid,
        "snippet": {"publishedAt": _iso(AGORA - timedelta(days=dias, hours=2)),
                    "channelId": cid, "title": titulo, "description": f"Descrição de {titulo}",
                    "thumbnails": {}, "channelTitle": CANAIS[cid]["title"],
                    "liveBroadcastContent": "none"},
        "contentDetails": {"duration": duracao, "dimension": "2d", "definition": "hd",
                           "caption": "false"},
        "status": {"uploadStatus": "processed", "privacyStatus": "public", "embeddable": True},
        "statistics": {"viewCount": str(views), "likeCount": str(likes), "favoriteCount": "0",
                       "commentCount": str(comentarios)},
    }


def _lista(items: list, **extra) -> dict:
    return {"kind": "lista", "etag": "x", "items": items,
            "pageInfo": {"totalResults": len(items), "resultsPerPage": 50}, **extra}


def youtube(recurso: str, q: dict[str, str]) -> tuple[int, dict]:
    if recurso == "channels":
        if "id" in q:
            ids = q["id"].split(",")
        elif "forHandle" in q:
            h = q["forHandle"].removeprefix("@").lower()
            ids = [cid for cid, c in CANAIS.items() if c["handle"] == h]
        else:
            ids = []
        return 200, _lista([_canal_item(i) for i in ids if i in CANAIS])
    if recurso == "playlistItems":
        cid = "UC" + q.get("playlistId", "")[2:]
        if cid not in CANAIS:
            return 404, {"error": {"code": 404, "message": "playlist not found",
                                   "errors": [{"reason": "playlistNotFound"}]}}
        ids = [v[0] for v in sorted(VIDEOS, key=lambda v: v[3]) if v[1] == cid]
        items = [{"kind": "youtube#playlistItem", "id": f"pi-{v}",
                  "contentDetails": {"videoId": v}} for v in ids]
        return 200, _lista(items)
    if recurso == "videos":
        ids = set(q.get("id", "").split(","))
        return 200, _lista([_video_item(v) for v in VIDEOS if v[0] in ids])
    if recurso == "search":
        termo = q.get("q", "").lower()
        items = [{"kind": "youtube#searchResult",
                  "id": {"kind": "youtube#channel", "channelId": cid},
                  "snippet": {"channelId": cid, "title": c["title"], "channelTitle": c["title"]}}
                 for cid, c in CANAIS.items() if termo in c["title"].lower()][:1]
        return 200, _lista(items)
    return 404, {"error": {"code": 404, "message": "Not Found"}}


# ---- OpenShorts ----

def gerar_clipes() -> list[Path]:
    clipes = []
    for i, cor in enumerate(CORES[:N_CLIPES]):
        dest = DIR / f"clip_{i + 1}.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", f"color=c={cor}:s=360x640:d=3:r=24",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-shortest", str(dest)],
            check=True, timeout=120,
        )
        clipes.append(dest)
    return clipes


CLIPES: list[Path] = []
JOBS: dict[str, dict] = {}
UPLOADS: dict[str, int | None] = {}
LOCK = threading.Lock()


def _clip(job_id: str, i: int) -> dict:
    return {"start": 10.0 + 30 * i, "end": 35.5 + 30 * i,
            "viral_hook_text": f"Gancho do clipe {i + 1}",
            "video_title_for_youtube_short": f"Título do clipe {i + 1}",
            "video_description_for_tiktok": f"Descrição do clipe {i + 1} #corte",
            "predicted_score": 82 - i,
            "video_url": f"/videos/{job_id}/fonte_clip_{i + 1}.mp4"}


def process(body: dict) -> tuple[int, dict]:
    upload_id = body.get("upload_id")
    if upload_id is not None and not UPLOADS.get(upload_id):
        return 409, {"detail": "Upload not received yet"}
    fonte = f"{body.get('url') or ''} {body.get('title') or ''}".lower()
    job_id = str(uuid.uuid4())
    with LOCK:
        JOBS[job_id] = {"inicio": time.monotonic(), "body": body,
                        "sem_clipes": "sem-clipes" in fonte,
                        "clips": [_clip(job_id, i) for i in range(N_CLIPES)]}
    return 200, {"job_id": job_id, "status": "queued", "partial": None}


def status(job_id: str) -> tuple[int, dict]:
    job = JOBS.get(job_id)
    if job is None:
        return 404, {"detail": "Job not found"}
    passou = time.monotonic() - job["inicio"]
    base = {"logs": [f"Job {job_id} queued."], "partial": None}
    if passou < FILA_S:
        return 200, base | {"status": "queued", "result": None,
                            "queue": {"position": 1, "ahead": 0, "eta_seconds": 5}}
    if passou < FILA_S + PROCESSANDO_S:
        return 200, base | {"status": "processing", "queue": None,
                            "result": {"clips": job["clips"][:1]}}
    if job["sem_clipes"]:
        return 200, base | {"status": "failed", "queue": None, "result": None,
                            "logs": base["logs"] + [NO_CLIPS]}
    return 200, base | {"status": "completed", "queue": None,
                        "result": {"clips": job["clips"], "cost_analysis": None}}


def subtitle(body: dict) -> tuple[int, dict]:
    job = JOBS.get(str(body.get("job_id", "")))
    if job is None:
        return 404, {"detail": "Job not found"}
    idx = int(body.get("clip_index", 0))
    url = f"/videos/{body['job_id']}/subtitled_1700000000_fonte_clip_{idx + 1}.mp4"
    job["clips"][idx]["video_url"] = url
    return 200, {"success": True, "new_video_url": url}


def transcript(job_id: str, idx: int) -> tuple[int, dict]:
    if job_id not in JOBS:
        return 404, {"detail": "Job not found"}
    palavras = f"olá este é o clipe {idx + 1} do teste".split()
    return 200, {"captions": [{"text": w, "startMs": 300 * n, "endMs": 300 * n + 250}
                              for n, w in enumerate(palavras)],
                 "durationSec": 3.0, "language": "pt"}


class Handler(BaseHTTPRequestHandler):
    server_version = "openshorts-fake/1"

    def log_message(self, fmt: str, *args) -> None:  # log curto, sem query (sem a "chave")
        print(f"{self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}",
              flush=True)

    def _json(self, code: int, data: dict) -> None:
        corpo = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self) -> bytes:
        n = int(self.headers.get("content-length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        partes = url.path.strip("/").split("/")
        if url.path == "/health":
            return self._json(200, {"status": "ok"})
        if url.path.startswith("/youtube/v3/"):
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            return self._json(*youtube(partes[-1], q))
        if url.path.startswith("/api/status/"):
            return self._json(*status(partes[-1]))
        if url.path.startswith("/api/clip/") and partes[-1] == "transcript":
            return self._json(*transcript(partes[2], int(partes[3])))
        if url.path.startswith("/videos/") and len(partes) == 3:
            return self._video(partes[1], partes[2])
        return self._json(404, {"detail": "Not Found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        corpo = self._corpo()
        if path == "/api/uploads":
            upload_id = str(uuid.uuid4())
            UPLOADS[upload_id] = None
            return self._json(200, {"upload_id": upload_id, "method": "PUT",
                                    "upload_url": f"http://outro-host/api/uploads/{upload_id}"})
        if path == "/api/process":
            return self._json(*process(json.loads(corpo or b"{}")))
        if path == "/api/subtitle":
            return self._json(*subtitle(json.loads(corpo or b"{}")))
        return self._json(404, {"detail": "Not Found"})

    def do_PUT(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if not path.startswith("/api/uploads/"):
            return self._json(404, {"detail": "Not Found"})
        upload_id = path.rsplit("/", 1)[-1]
        if upload_id not in UPLOADS:
            return self._json(404, {"detail": "Unknown or expired upload_id"})
        total = 0
        restante = int(self.headers.get("content-length") or 0)
        while restante > 0:  # descarta em pedaços (o arquivo avulso pode ser grande)
            bloco = self.rfile.read(min(restante, 1 << 20))
            if not bloco:
                break
            total += len(bloco)
            restante -= len(bloco)
        UPLOADS[upload_id] = total
        return self._json(200, {"upload_id": upload_id, "bytes": total})

    def _video(self, job_id: str, nome: str) -> None:
        if job_id not in JOBS:
            return self._json(404, {"detail": "Not Found"})
        idx = 0
        for i in range(N_CLIPES):
            if nome.endswith(f"_clip_{i + 1}.mp4"):
                idx = i
        dados = CLIPES[idx].read_bytes()
        self.send_response(200)
        self.send_header("content-type", "video/mp4")
        self.send_header("content-length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


def main() -> None:
    CLIPES.extend(gerar_clipes())
    servidor = ThreadingHTTPServer(("0.0.0.0", PORTA), Handler)
    print(f"openshorts-fake pronto na porta {PORTA} ({len(CLIPES)} clipes em {DIR})",
          flush=True)
    servidor.serve_forever()


if __name__ == "__main__":
    main()
