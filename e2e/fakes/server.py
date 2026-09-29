"""OpenShorts e YouTube Data API de mentira para os e2e (spec 006, T078). Só stdlib.

Roda no serviço `openshorts-fake` do `docker-compose.e2e.yml` (imagem `sociman-api-e2e`, que já
tem o ffmpeg) e atende, na porta 8000:
- a parte da API do OpenShorts que o cliente `envios/openshorts.py` usa: `/health`,
  `POST /api/process`, `POST|PUT /api/uploads`, `GET /api/status/{job}`, `POST /api/subtitle`,
  `GET /api/clip/{job}/{i}/transcript` e `GET /videos/{job}/{arquivo}`. O job passa por
  `queued → processing → completed` em alguns segundos; em `processing`, os `logs` são os de um
  job real (download, transcrição 25..100%, escolha dos momentos, clipe 1 pronto), revelados aos
  poucos, para a tela mostrar as etapas. Os clipes são MP4 sintéticos gerados
  com o ffmpeg na subida. Uma fonte com `sem-clipes` na URL ou no título termina em "No clips";
- `GET /youtube/v3/{channels,playlistItems,videos,search}`: dois canais e seus vídeos, sem
  miniaturas externas (`thumbnails` vazio, e a API devolve `null`). O e2e nunca chama o Google;
- `POST /v1/messages` (spec 008, T015): um Claude de mentira para o assistente de IA, apontado
  por `ANTHROPIC_BASE_URL`. Lê o schema pedido (`output_config.format`) e o tipo de campo do
  prompt e devolve um JSON válido e determinístico. Palavras na instrução: "lento" dorme além do
  timeout do cliente; "fora do limite" devolve um texto acima de qualquer limite. Nas sugestões,
  os itens nunca repetem um texto que já esteja no pedido (lista, aceitos e rejeitados). O e2e
  nunca chama a Anthropic.

Nada aqui publica: não existe `/api/social` (princípio I).
"""

import itertools
import json
import re
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
PROCESSANDO_S = 12.0  # tempo em `processing` (os blocos de log vão aparecendo nesse tempo)
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


def blocos_de_log(job_id: str) -> list[list[str]]:
    """Etapas de um job real do OpenShorts (logs de 2026-09-29), com o ruído que o SociMan
    ignora (TensorFlow, yt-dlp, segmentos da transcrição, UserWarning)."""
    return [
        [f"Job {job_id} queued.", "Job started by worker.",
         "INFO: Created TensorFlow Lite XNNPACK delegate for CPU.",
         "📥 Downloading video from YouTube...", "📥 Download attempt: HD",
         "W0000 00:00:1790697872.126668  657378 inference_feedback_manager.cc:114] Feedback "
         "manager requires a model with a single signature inference.",
         "[debug] Encodings: locale UTF-8, fs utf-8, pref UTF-8, out utf-8 (No ANSI)",
         f"[download] Destination: output/{job_id}/fonte.f299.mp4"],
        ["✅ Download succeeded (HD).", f"✅ Video downloaded in 3.1s: output/{job_id}/fonte.mp4",
         "🎛️  Choosing a layout for this video…", "🎙️  Transcribing video..."],
        ["🎙️ Transcribing… 25% (2s)"],
        ["🎙️ Transcribing… 50% (4s)"],
        ["🎙️ Transcribing… 75% (6s)", "🎙️ Transcribing… 100% (8s)",
         "Detected language 'pt', 12 segments", "[0.00s -> 4.20s]  olá, este é o vídeo",
         "🤖  Analyzing with local LLM at http://llm (2-pass: score → detail)...",
         "Built 3 scoring window(s)."],
        [f"🔥 Found {N_CLIPES} clips!", "🎬 Processing Clip 1: 10.0s - 35.5s",
         "Title: Título do clipe 1", "🚀 Reframe engine v2 (ffmpeg-native render)",
         "/app/scene_detection.py:109: UserWarning: The given NumPy array is not writable",
         "🎬 Scene engine: TransNetV2 — 27 scenes"],
        ["Analyzing Scenes: 100%|██████████| 27/27 [00:01<00:00, 18.0it/s]",
         f"✅ Clip 1 ready: output/{job_id}/fonte_clip_1.mp4",
         "🎬 Processing Clip 2: 40.0s - 65.5s"],
    ]


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
        blocos = blocos_de_log(job_id)
        n = 1 + int((passou - FILA_S) / PROCESSANDO_S * len(blocos))
        logs = [linha for bloco in blocos[:n] for linha in bloco]
        clips = job["clips"][:1] if n >= len(blocos) else []
        return 200, base | {"status": "processing", "queue": None, "logs": logs,
                            "result": {"clips": clips} if clips else None}
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


# ---- Claude (spec 008, T015) ----

TIPOS_IA = (
    "avatar.descricao_prompt", "avatar.tom_de_voz", "avatar.regras_imagem",
    "cenario.prompt_ambiente", "asset.nome", "asset.descricao", "perfil.bio", "kit.bordoes",
    "kit.series", "postagem.titulo", "postagem.descricao", "postagem.hashtags", "postagem.textos",
)
CLAUDE_LENTO_S = 25.0  # o `IaClient` desiste em 20 s
REGRA_EMOJI = "termine com um emoji"
EMOJI = " \U0001F525"
N_SUGESTOES = 5
_VERSAO = itertools.count(1)  # "Outra versão" nunca devolve o mesmo texto

# Um texto por tipo, dentro dos limites (≤ 80, o menor deles); `{n}` distingue as versões.
TEXTOS_IA = {
    "avatar.descricao_prompt": "Vintage 1950s shop girl, round face, red curls, pink apron "
                               "(version {n})",
    "cenario.prompt_ambiente": "Retro 1950s kitchen, soft window light, pastel palette "
                               "(version {n})",
    "avatar.tom_de_voz": "Animada e próxima, como amiga que achou uma pechincha (versão {n})",
    "avatar.regras_imagem": "Sempre com o avental rosa. Nunca mostrar outras marcas "
                            "(versão {n}).",
    "asset.nome": "Nome sugerido pela IA {n}",
    "asset.descricao": "Notas sugeridas pela IA, versão {n}.",
    "perfil.bio": "Bio sugerida pela IA, versão {n}: achadinhos baratos todo dia.",
    "postagem.titulo": "Título sugerido pela IA {n}",
    "postagem.descricao": "Descrição sugerida pela IA, versão {n}.",
}
SUGESTOES_IA = {
    "kit.bordoes": "Achado bom é achado dividido nº {k}",
    "kit.series": "Achado do dia {k}",
}


def _textos(valor: object) -> list[str]:
    """Todo texto de `system` e `messages` (string ou blocos)."""
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, list):
        return [t for v in valor for t in _textos(v)]
    if isinstance(valor, dict):
        return _textos(valor.get("text")) + _textos(valor.get("content"))
    return []


def _tag(texto: str, nome: str) -> str:
    achou = re.search(rf"<{nome}>(.*?)</{nome}>", texto, re.DOTALL)
    return achou.group(1).strip() if achou else ""


# O prompt diz "Campo: <rótulo> (<onde>)." (ia/prompt.py); o rótulo até o primeiro " (".
ROTULOS_IA = {
    "Descrição para prompts do avatar": "avatar.descricao_prompt",
    "Tom de voz do avatar": "avatar.tom_de_voz",
    "Regras de imagem do avatar": "avatar.regras_imagem",
    "Prompt do ambiente do cenário": "cenario.prompt_ambiente",
    "Nome do asset": "asset.nome",
    "Notas do asset": "asset.descricao",
    "Descrição do perfil": "perfil.bio",
    "Bordões": "kit.bordoes",
    "Séries": "kit.series",
    "Título da postagem": "postagem.titulo",
    "Descrição da postagem": "postagem.descricao",
    "Hashtags da postagem": "postagem.hashtags",
    "Textos da postagem": "postagem.textos",
}


def _tipo_ia(texto: str) -> str:
    achou = re.search(r"^Campo: (.+?) \(", texto, re.MULTILINE)
    if achou and achou.group(1) in ROTULOS_IA:
        return ROTULOS_IA[achou.group(1)]
    achou = re.search(r"[Tt]ipo de campo:\s*([a-z_]+\.[a-z_]+)", texto)
    if achou and achou.group(1) in TIPOS_IA:
        return achou.group(1)
    posicoes = [(texto.find(t), t) for t in TIPOS_IA if t in texto]
    return min(posicoes)[1] if posicoes else ""


def _ja_no_pedido(item: str, texto: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(item.casefold())}(?!\w)", texto.casefold()) is not None


def claude(body: dict) -> tuple[int, dict]:
    system = "\n".join(_textos(body.get("system")))
    user = "\n".join(_textos(body.get("messages")))
    texto = f"{system}\n{user}"
    fmt = (body.get("output_config") or {}).get("format") or {}
    props = list((fmt.get("schema") or {}).get("properties") or {})
    tipo = _tipo_ia(texto)
    instrucao = _tag(user, "instrucao")
    if instrucao.startswith("(sem instrução"):  # o texto padrão do prompt quando vem vazia
        instrucao = ""
    if "lento" in instrucao.lower():
        time.sleep(CLAUDE_LENTO_S)
    n = next(_VERSAO)
    emoji = EMOJI if REGRA_EMOJI in system else ""
    explicacao = f"Proposta {n} do Claude falso do e2e."
    if instrucao:
        explicacao += f" Segui a instrução: {instrucao[:80]}."
    avisos = ["Mantive as regras do campo."] if "system prompt" in instrucao.lower() else []
    if "titulo" in props:  # textos_postagem
        dados = {"titulo": f"Título sugerido pela IA {n}{emoji}",
                 "descricao": f"Descrição sugerida pela IA, versão {n}.",
                 "hashtags": ["#achadinhos", "#promo", f"#dica{n}"]}
    elif "itens" in props and (tipo == "postagem.hashtags"
                               or (not tipo and "hashtag" in texto.lower())):
        dados = {"itens": ["#achadinhos", "#promo", f"#dica{n}", "#compras"]}
    elif "itens" in props:  # sugestões (bordões e séries): nunca repete o que está no pedido
        modelo = SUGESTOES_IA.get(tipo, "Sugestão {k}")
        itens: list[str] = []
        k = 0
        while len(itens) < N_SUGESTOES:
            k += 1
            item = modelo.format(k=k)
            if not _ja_no_pedido(item, texto):
                itens.append(item)
        dados = {"itens": itens}
    else:
        campo = next((p for p in props if p not in ("explicacao", "avisos")), "proposta")
        if "fora do limite" in instrucao.lower():
            proposta = "Texto longo demais para caber no limite do campo. " * 60
        else:
            proposta = TEXTOS_IA.get(tipo, "Texto sugerido pela IA, versão {n}.").format(n=n)
            if instrucao and "system prompt" not in instrucao.lower():
                proposta += f" ({instrucao[:30]})"
            proposta += emoji
        dados = {campo: proposta}
    dados |= {"explicacao": explicacao, "avisos": avisos}
    return 200, {
        "id": f"msg_fake_{n}", "type": "message", "role": "assistant",
        "model": body.get("model") or "claude-sonnet-5-5",
        "content": [{"type": "text", "text": json.dumps(dados, ensure_ascii=False)}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 1200, "output_tokens": 150, "cache_read_input_tokens": 800,
                  "cache_creation_input_tokens": 0},
    }


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
        if path == "/v1/messages":
            try:
                return self._json(*claude(json.loads(corpo or b"{}")))
            except (BrokenPipeError, ConnectionResetError):  # o cliente desistiu ("lento")
                return None
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
