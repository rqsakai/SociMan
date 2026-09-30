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
- `/tiktok/v2/...` (spec 015, T039): uma TikTok de mentira, apontada por `TIKTOK_API_URL`, com
  exatamente os pedidos do cliente (`ALLOWED`, research R21): OAuth (token e revoke),
  `user/info`, `creator_info`, os dois `init`, `status/fetch`, o `PUT` das partes em
  `/tiktok/upload/` e o avatar em `/tiktok/avatar/` (host em `TIKTOK_UPLOAD_HOSTS`). O Direct
  Post exige `post_info` com a privacidade do `creator_info` (sandbox: só `SELF_ONLY`) e recusa
  conteúdo de marca como "Só eu"; o `status` chega a `PUBLISH_COMPLETE` com o id do post. O login
  do navegador é interceptado pelo Playwright, que volta com `code=e2e-<handle>`: a TikTok
  falsa responde como a conta `<handle>` (`open_id` = `open-<handle>`). Rotas de controle, só do
  e2e (o cliente da API nunca as chama): `GET /tiktok-e2e/pedidos[?handle=h]` (tudo o que a
  TikTok falsa recebeu, sem segredo) e `POST /tiktok-e2e/falhas` com
  `{handle, endpoint, falha}`: a próxima chamada de `endpoint` para `handle` falha com
  `sem_resposta` (cria e não responde), `5xx` ou um código da TikTok; no `status`, a falha é o
  `fail_reason` do `FAILED`. O e2e nunca chama a TikTok.
- leitura de métricas (spec 016, T078): `video/list`, `video/query`, os stats no `user/info` e o
  `publicaly_available_post_id` de um rascunho que o dono "finalizou" no app, com contadores que
  evoluem no tempo e rotas de controle próprias (ver o bloco "leitura de métricas" abaixo).

Nada aqui publica: não existe `/api/social` (princípio I).
"""

import itertools
import json
import re
import secrets
import struct
import subprocess
import tempfile
import threading
import time
import uuid
import zlib
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


# ---- TikTok (spec 015, T039) ----

TT_HOST = "openshorts-fake:8000"  # upload e avatar (TIKTOK_UPLOAD_HOSTS=openshorts-fake)
TT_ESCOPOS = "user.info.basic,user.info.profile,video.upload,video.publish"
TT_PASSOS_STATUS = 1  # consultas em PROCESSING_UPLOAD antes do estado final
TT_LOG_ID = "202609290000000000000000E2E"
TT_HTTP = {"access_token_invalid": 401, "scope_not_authorized": 401, "rate_limit_exceeded": 429,
           "spam_risk_too_many_pending_share": 403, "spam_risk_too_many_posts": 403,
           "unaudited_client_can_only_post_to_private_accounts": 403,
           "internal_error": 500}
TT_CAMINHOS = {
    ("POST", "/v2/oauth/token/"): "token",
    ("POST", "/v2/oauth/revoke/"): "revoke",
    ("GET", "/v2/user/info/"): "user_info",
    ("POST", "/v2/post/publish/creator_info/query/"): "creator_info",
    ("POST", "/v2/post/publish/inbox/video/init/"): "inbox_init",
    ("POST", "/v2/post/publish/video/init/"): "video_init",
    ("POST", "/v2/post/publish/status/fetch/"): "status",
}
SEM_RESPOSTA = object()  # o pedido chegou (e a TikTok criou), a resposta não sai
TT = {"access": {}, "refresh": {}, "envios": {}, "uploads": {}, "pedidos": [], "falhas": []}
_TT_SEQ = itertools.count(1)


def _handle_de(open_id: str | None) -> str | None:
    return open_id.removeprefix("open-") if open_id else None


def _tt_ok(data: dict) -> tuple[int, dict]:
    return 200, {"data": data, "error": {"code": "ok", "message": "", "log_id": TT_LOG_ID}}


def _tt_erro(codigo: str) -> tuple[int, dict]:
    return TT_HTTP.get(codigo, 400), {"error": {"code": codigo, "message": f"e2e: {codigo}",
                                                "log_id": TT_LOG_ID}}


def _tt_falha(endpoint: str, handle: str | None) -> str | None:
    """A falha injetada para este `endpoint` e `handle` (uso único)."""
    with LOCK:
        for i, f in enumerate(TT["falhas"]):
            if f["endpoint"] == endpoint and f["handle"] == handle:
                return TT["falhas"].pop(i)["falha"]
    return None


def _tt_registrar(metodo: str, endpoint: str, handle: str | None, **extra) -> None:
    with LOCK:
        TT["pedidos"].append({"metodo": metodo, "endpoint": endpoint, "handle": handle,
                              "em": _iso(datetime.now(UTC)), **extra})


def _tt_tokens(open_id: str) -> tuple[int, dict]:
    n = next(_TT_SEQ)
    access = f"act.e2e-{n}-{secrets.token_hex(6)}"
    refresh = f"rft.e2e-{n}-{secrets.token_hex(6)}"
    TT["access"][access] = open_id
    TT["refresh"][refresh] = open_id
    escopos = TT_MET["escopos"].get(_handle_de(open_id), TT_ESCOPOS)  # spec 016: o que o dono marcou
    TT_MET["token_escopos"][access] = escopos
    return 200, {"access_token": access, "refresh_token": refresh, "open_id": open_id,
                 "scope": escopos, "expires_in": 86400, "refresh_expires_in": 31536000,
                 "token_type": "Bearer"}


def _tt_oauth(endpoint: str, form: dict[str, str]) -> tuple[int, dict]:
    if endpoint == "revoke":
        open_id = TT["access"].pop(form.get("token", ""), None)
        _tt_registrar("POST", "revoke", _handle_de(open_id))
        TT["refresh"] = {k: v for k, v in TT["refresh"].items() if v != open_id}
        return 200, {}
    grant = form.get("grant_type")
    if grant == "authorization_code":
        code = form.get("code", "")
        handle = code.removeprefix("e2e-") if code.startswith("e2e-") else None
        _tt_registrar("POST", "token", handle, grant=grant, pkce="code_verifier" in form)
        if handle is None:
            return 400, {"error": "invalid_grant", "error_description": "code inválido",
                         "log_id": TT_LOG_ID}
        return _tt_tokens(f"open-{handle}")
    if grant == "refresh_token":
        open_id = TT["refresh"].pop(form.get("refresh_token", ""), None)
        _tt_registrar("POST", "token", _handle_de(open_id), grant=grant)
        if open_id is None:
            return 400, {"error": "invalid_grant", "error_description": "refresh revogado",
                         "log_id": TT_LOG_ID}
        return _tt_tokens(open_id)
    return 400, {"error": "invalid_request", "error_description": "", "log_id": TT_LOG_ID}


def _regra_partes_ok(size: int, chunk: int, total: int) -> bool:
    """Regra da TikTok real (sem os limites de 5–64 MB, para os testes usarem partes pequenas):
    total = floor(size/chunk); com 1 parte, chunk == size (o bug do sandbox em 2026-09-29)."""
    if total == 1:
        return chunk == size
    return total == size // chunk


TT_PRIVACIDADES = ["SELF_ONLY"]  # app sem auditoria (sandbox): só "Só eu"
TT_POST_INFO_BOOL = ("disable_comment", "disable_duet", "disable_stitch", "brand_organic_toggle",
                     "brand_content_toggle", "is_aigc")


def _tt_post_info(info: object) -> str | None:
    """Como a TikTok confere o `post_info` do Direct Post: privacidade entre as opções do
    `creator_info` e conteúdo de marca (parceria paga) nunca como "Só eu"."""
    if not isinstance(info, dict) or not isinstance(info.get("title", ""), str) \
            or any(not isinstance(info.get(k, False), bool) for k in TT_POST_INFO_BOOL):
        return "invalid_params"
    if info.get("privacy_level") not in TT_PRIVACIDADES:
        return "privacy_level_option_mismatch"
    if info.get("brand_content_toggle") and info.get("privacy_level") == "SELF_ONLY":
        return "invalid_params"
    return None


def _tt_init(open_id: str, corpo: dict, direto: bool) -> tuple[int, dict]:
    fonte = corpo.get("source_info") or {}
    size, chunk = int(fonte.get("video_size", 0)), int(fonte.get("chunk_size", 0))
    total = int(fonte.get("total_chunk_count", 0))
    if fonte.get("source") != "FILE_UPLOAD" or size <= 0 or chunk <= 0 or total <= 0 \
            or (not direto and "post_info" in corpo) \
                or not _regra_partes_ok(size, chunk, total):
        return _tt_erro("invalid_params")
    if direto:  # Direct Post: `post_info` obrigatório, com a privacidade do `creator_info`
        erro = _tt_post_info(corpo.get("post_info"))
        if erro:
            return _tt_erro(erro)
    n = next(_TT_SEQ)
    publish_id = f"v_{'pub' if direto else 'inbox'}_file~v2.e2e{n}"
    upload_token = secrets.token_hex(8)
    TT["envios"][publish_id] = {"open_id": open_id, "direto": direto, "video_size": size,
                                "recebidos": 0, "partes": [], "consultas": 0,
                                "fail_reason": None, "post_info": corpo.get("post_info")}
    TT["uploads"][upload_token] = publish_id
    return _tt_ok({"publish_id": publish_id, "upload_url":
                   f"http://{TT_HOST}/tiktok/upload/?upload_id={n}&upload_token={upload_token}"})


def _tt_status(corpo: dict, handle: str | None) -> tuple[int, dict]:
    envio = TT["envios"].get(corpo.get("publish_id", ""))
    if envio is None:
        return _tt_erro("invalid_params")
    envio["consultas"] += 1
    completo = envio["recebidos"] == envio["video_size"]
    dados = {"status": "PROCESSING_UPLOAD", "fail_reason": "", "uploaded_bytes": envio["recebidos"],
             "publicaly_available_post_id": []}
    if completo and envio["fail_reason"] is None:
        envio["fail_reason"] = _tt_falha("status", handle)
    if envio["fail_reason"]:
        dados.update(status="FAILED", fail_reason=envio["fail_reason"])
    elif completo and envio["consultas"] > TT_PASSOS_STATUS:
        if envio["direto"]:
            dados.update(status="PUBLISH_COMPLETE",
                         publicaly_available_post_id=[7_000_000_000_000_000_000 + envio["consultas"]])
        elif envio.get("post_id") is not None:  # spec 016: o dono finalizou o rascunho no app
            dados.update(status="PUBLISH_COMPLETE", publicaly_available_post_id=[envio["post_id"]])
        else:
            dados["status"] = "SEND_TO_USER_INBOX"
    return _tt_ok(dados)


def tiktok_api(metodo: str, caminho: str, headers, corpo: bytes) -> tuple[int, dict] | object:
    """Os pedidos do cliente `publicacao/tiktok/cliente.py`, com o caminho sem o `/tiktok`."""
    endpoint = TT_CAMINHOS.get((metodo, caminho))
    if endpoint is None:
        _tt_registrar(metodo, "desconhecido", None, caminho=caminho)
        return _tt_erro("invalid_params")
    if endpoint in ("token", "revoke"):
        return _tt_oauth(endpoint, {k: v[-1] for k, v in parse_qs(corpo.decode()).items()})
    token = (headers.get("authorization") or "").removeprefix("Bearer ").strip()
    open_id = TT["access"].get(token)
    handle = _handle_de(open_id)
    dados = json.loads(corpo or b"{}") if metodo == "POST" else {}
    extra = {"publish_id": dados.get("publish_id")} if endpoint == "status" else {}
    if endpoint.endswith("init"):
        info = dados.get("post_info")
        extra = {"post_info": info is not None,
                 "privacy_level": info.get("privacy_level") if isinstance(info, dict) else None,
                 "title": info.get("title") if isinstance(info, dict) else None}
    _tt_registrar(metodo, endpoint, handle, **extra)
    if open_id is None:
        return _tt_erro("access_token_invalid")
    falha = None if endpoint == "status" else _tt_falha(endpoint, handle)
    if falha == "5xx":
        return 503, {"error": {"code": "internal_error", "message": "", "log_id": TT_LOG_ID}}
    if falha and falha != "sem_resposta":
        return _tt_erro(falha)
    if endpoint == "user_info":
        resposta = _tt_ok({"user": {
            "open_id": open_id, "username": handle, "display_name": f"Apelido {handle}",
            "avatar_url": f"http://{TT_HOST}/tiktok/avatar/{handle}.png",
            **_tt_stats_conta(handle, token)}})
    elif endpoint in ("video_list", "video_query"):  # spec 016: leitura
        resposta = _tt_videos(endpoint, handle, token, dados)
    elif endpoint == "creator_info":
        resposta = _tt_ok({
            "creator_avatar_url": f"http://{TT_HOST}/tiktok/avatar/{handle}.png",
            "creator_username": handle, "creator_nickname": f"Apelido {handle}",
            "privacy_level_options": TT_PRIVACIDADES, "comment_disabled": False,
            "duet_disabled": False, "stitch_disabled": True, "max_video_post_duration_sec": 600})
    elif endpoint in ("inbox_init", "video_init"):
        resposta = _tt_init(open_id, dados, direto=endpoint == "video_init")
    else:
        resposta = _tt_status(dados, handle)
    return SEM_RESPOSTA if falha == "sem_resposta" else resposta


def tiktok_parte(query: str, faixa: str, corpo: bytes) -> int:
    """`PUT` de uma parte: confere `Content-Range`, a ordem e o tamanho (como a TikTok)."""
    upload_token = parse_qs(query).get("upload_token", [""])[0]
    publish_id = TT["uploads"].get(upload_token, "")
    envio = TT["envios"].get(publish_id)
    handle = _handle_de(envio["open_id"]) if envio else None
    _tt_registrar("PUT", "put", handle, content_range=faixa)
    if envio is None:
        return 404
    falha = _tt_falha("put", handle)
    if falha:
        return 503 if falha == "5xx" else 400
    try:
        unidade, resto = faixa.split(" ", 1)
        intervalo, total = resto.split("/")
        inicio, fim = (int(x) for x in intervalo.split("-"))
    except ValueError:
        return 400
    if unidade != "bytes" or int(total) != envio["video_size"] or fim - inicio + 1 != len(corpo) \
            or fim >= envio["video_size"]:
        return 416
    if inicio == envio["recebidos"]:
        envio["recebidos"] = fim + 1
        envio["partes"].append([inicio, fim])
    elif [inicio, fim] not in envio["partes"]:
        return 416
    return 201 if envio["recebidos"] == envio["video_size"] else 206


def avatar_png(handle: str, lado: int = 96) -> bytes:
    """PNG RGB `lado`×`lado` com a cor tirada do handle (o SociMan exige imagem ≥ 64 px)."""
    cor = zlib.crc32(handle.encode()).to_bytes(4, "big")[:3]
    linha = b"\x00" + cor * lado
    bruto = zlib.compress(linha * lado)

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + \
            struct.pack(">I", zlib.crc32(tipo + dados))

    ihdr = struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", ihdr) + bloco(b"IDAT", bruto) + \
        bloco(b"IEND", b"")


def tiktok_controle(metodo: str, caminho: str, query: str, corpo: bytes) -> tuple[int, dict]:
    """Rotas só do e2e: inspeção dos pedidos e injeção de falhas."""
    if metodo == "GET" and caminho == "/tiktok-e2e/pedidos":
        handle = parse_qs(query).get("handle", [None])[0]
        with LOCK:
            itens = [p for p in TT["pedidos"] if handle is None or p["handle"] == handle]
        return 200, {"items": itens}
    if metodo == "POST" and caminho == "/tiktok-e2e/falhas":
        f = json.loads(corpo or b"{}")
        with LOCK:
            TT["falhas"].append({"handle": f["handle"], "endpoint": f["endpoint"],
                                 "falha": f["falha"]})
        return 200, {"falhas": len(TT["falhas"])}
    if metodo == "POST" and caminho in TT_CONTROLE_016:
        return TT_CONTROLE_016[caminho](json.loads(corpo or b"{}"))
    return 404, {"detail": "Not Found"}


# ---- TikTok: leitura de métricas (spec 016, T078; research R17) ----
#
# `POST /v2/video/list/` (cursor em ms, `max_count` ≤ 20, só públicos, do mais novo para o mais
# antigo) e `POST /v2/video/query/` (até 20 ids, só os vídeos públicos da conta do token), com o
# escopo `video.list`; os stats da conta no `user/info`, com `user.info.stats`. Os contadores
# EVOLUEM no tempo: valor = base + ritmo por minuto × minutos desde o último ajuste (o ajuste
# pode baixar o número, como a TikTok faz ao corrigir). Os escopos concedidos vêm do que o dono
# "marcou" na tela da TikTok (`/tiktok-e2e/escopos`); sem isso, os da 015 (sem métricas).
# Controle, só do e2e:
# - `POST /tiktok-e2e/escopos {handle, escopos}`: escopos dos próximos logins da conta;
# - `POST /tiktok-e2e/videos {acao: "criar", handle, duracao, legenda, idade_s?, publico?,
#   views?, likes?, comments?, shares?, ritmo?}` → `{video}`; `{acao: "contadores", id, ...}`;
#   `{acao: "privado"|"publico", id}`;
# - `POST /tiktok-e2e/conta {handle, seguidores?, seguindo?, curtidas?, ritmo?}`;
# - `POST /tiktok-e2e/publicar-rascunho {handle, duracao, legenda, publish_id?, informar_id?}`:
#   o dono finaliza o último rascunho entregue (ou o `publish_id`) como post público; o `status`
#   passa a `PUBLISH_COMPLETE` com o `publicaly_available_post_id` (sem ele com
#   `informar_id=false`, para o casamento pela lista).
# Os ids são texto (passam de 2^53, como na TikTok).

TT_CAMINHOS.update({
    ("POST", "/v2/video/list/"): "video_list",
    ("POST", "/v2/video/query/"): "video_query",
})
TT_ESCOPOS_METRICAS = TT_ESCOPOS + ",user.info.stats,video.list"
TT_CONTADORES = ("views", "likes", "comments", "shares")
TT_CAMPOS_CONTADORES = {"views": "view_count", "likes": "like_count", "comments": "comment_count",
                        "shares": "share_count"}
TT_RITMO = {"views": 120.0, "likes": 12.0, "comments": 2.0, "shares": 1.0}  # por minuto
TT_MET = {"escopos": {}, "token_escopos": {}, "videos": {}, "contas": {}}
_TT_VIDEO_SEQ = itertools.count(1)


def _tt_escopo(token: str, escopo: str) -> bool:
    return escopo in TT_MET["token_escopos"].get(token, TT_ESCOPOS).split(",")


def _tt_valor(item: dict, nome: str) -> int:
    minutos = (time.time() - item["desde"]) / 60
    return max(0, int(item["base"][nome] + item["ritmo"].get(nome, 0) * minutos))


def _tt_ajustar(item: dict, dados: dict, nomes: tuple[str, ...]) -> None:
    """Novo ponto de partida dos contadores: os informados valem agora, os outros seguem de onde
    estavam; `ritmo` troca a velocidade (0 congela)."""
    base = {n: dados[n] if dados.get(n) is not None else _tt_valor(item, n) for n in nomes}
    item.update(base=base, desde=time.time())
    if isinstance(dados.get("ritmo"), dict):
        item["ritmo"] = {**item["ritmo"], **dados["ritmo"]}


def _tt_stats_conta(handle: str | None, token: str) -> dict:
    if not handle or not _tt_escopo(token, "user.info.stats"):
        return {}
    with LOCK:
        conta = TT_MET["contas"].setdefault(handle, {
            "base": {"seguidores": 1000, "seguindo": 50, "curtidas": 20000}, "desde": time.time(),
            "ritmo": {"seguidores": 5.0, "curtidas": 40.0}})
        publicos = sum(1 for v in TT_MET["videos"].values() if v["handle"] == handle and v["publico"])
        return {"follower_count": _tt_valor(conta, "seguidores"),
                "following_count": _tt_valor(conta, "seguindo"),
                "likes_count": _tt_valor(conta, "curtidas"), "video_count": publicos}


def _tt_video_json(v: dict) -> dict:
    return {"id": v["id"], "create_time": v["create_time"],
            "share_url": f"https://www.tiktok.com/@{v['handle']}/video/{v['id']}",
            "video_description": v["legenda"], "title": v["legenda"][:30], "duration": v["duracao"],
            "width": 1080, "height": 1920,
            **{campo: _tt_valor(v, n) for n, campo in TT_CAMPOS_CONTADORES.items()}}


def _tt_videos(endpoint: str, handle: str | None, token: str, dados: dict) -> tuple[int, dict]:
    if not _tt_escopo(token, "video.list"):
        return _tt_erro("scope_not_authorized")
    with LOCK:
        da_conta = sorted((v for v in TT_MET["videos"].values()
                           if v["handle"] == handle and v["publico"]),
                          key=lambda v: (v["create_time"], v["id"]), reverse=True)
        if endpoint == "video_query":
            ids = ((dados.get("filters") or {}).get("video_ids") or [])
            if not isinstance(ids, list) or not ids or len(ids) > 20:
                return _tt_erro("invalid_params")
            pedidos = {str(i) for i in ids}
            return _tt_ok({"videos": [_tt_video_json(v) for v in da_conta if v["id"] in pedidos]})
        max_count = int(dados.get("max_count") or 20)
        if not 1 <= max_count <= 20:
            return _tt_erro("invalid_params")
        cursor = dados.get("cursor")
        restantes = [v for v in da_conta if cursor is None or v["create_time"] * 1000 < int(cursor)]
        pagina = restantes[:max_count]
        return _tt_ok({"videos": [_tt_video_json(v) for v in pagina],
                       "cursor": pagina[-1]["create_time"] * 1000 if pagina else int(cursor or 0),
                       "has_more": len(restantes) > max_count})


def _tt_novo_video(handle: str, dados: dict, criado: float) -> dict:
    video = {"id": str(7_560_000_000_000_000 + next(_TT_VIDEO_SEQ) * 7919),
             "handle": handle, "create_time": int(criado), "duracao": int(dados.get("duracao", 3)),
             "legenda": str(dados.get("legenda", "")), "publico": bool(dados.get("publico", True)),
             "ritmo": dict(TT_RITMO), "base": {n: 0 for n in TT_CONTADORES}, "desde": time.time()}
    _tt_ajustar(video, {n: dados.get(n, 0) for n in TT_CONTADORES} | {"ritmo": dados.get("ritmo")},
                TT_CONTADORES)
    TT_MET["videos"][video["id"]] = video
    return video


def _tt_resumo(v: dict) -> dict:
    return {"id": v["id"], "handle": v["handle"], "create_time": v["create_time"],
            "duracao": v["duracao"], "legenda": v["legenda"], "publico": v["publico"],
            "share_url": f"https://www.tiktok.com/@{v['handle']}/video/{v['id']}",
            **{n: _tt_valor(v, n) for n in TT_CONTADORES}}


def _ctl_escopos(dados: dict) -> tuple[int, dict]:
    with LOCK:
        TT_MET["escopos"][dados["handle"]] = dados.get("escopos") or TT_ESCOPOS_METRICAS
    return 200, {"handle": dados["handle"], "escopos": TT_MET["escopos"][dados["handle"]]}


def _ctl_videos(dados: dict) -> tuple[int, dict]:
    acao = dados.get("acao")
    with LOCK:
        if acao == "criar":
            video = _tt_novo_video(dados["handle"], dados, time.time() - float(dados.get("idade_s", 0)))
            return 200, {"video": _tt_resumo(video)}
        video = TT_MET["videos"].get(str(dados.get("id")))
        if video is None:
            return 404, {"detail": "vídeo desconhecido"}
        if acao == "contadores":
            _tt_ajustar(video, dados, TT_CONTADORES)
        elif acao in ("privado", "publico"):
            video["publico"] = acao == "publico"
        else:
            return 400, {"detail": f"ação desconhecida: {acao}"}
        return 200, {"video": _tt_resumo(video)}


def _ctl_conta(dados: dict) -> tuple[int, dict]:
    with LOCK:
        conta = TT_MET["contas"].setdefault(dados["handle"], {
            "base": {"seguidores": 1000, "seguindo": 50, "curtidas": 20000}, "desde": time.time(),
            "ritmo": {"seguidores": 5.0, "curtidas": 40.0}})
        _tt_ajustar(conta, dados, ("seguidores", "seguindo", "curtidas"))
        return 200, {"conta": {n: _tt_valor(conta, n) for n in ("seguidores", "seguindo", "curtidas")}}


def _ctl_publicar_rascunho(dados: dict) -> tuple[int, dict]:
    handle = dados["handle"]
    with LOCK:
        rascunhos = [(pid, e) for pid, e in TT["envios"].items()
                     if not e["direto"] and _handle_de(e["open_id"]) == handle
                     and e["recebidos"] == e["video_size"] and e["fail_reason"] is None
                     and (dados.get("publish_id") in (None, pid))]
        if not rascunhos:
            return 404, {"detail": f"nenhum rascunho entregue de @{handle}"}
        publish_id, envio = rascunhos[-1]
        video = _tt_novo_video(handle, dados, time.time())
        if dados.get("informar_id", True):
            envio["post_id"] = int(video["id"])
        return 200, {"publish_id": publish_id, "video": _tt_resumo(video)}


TT_CONTROLE_016 = {
    "/tiktok-e2e/escopos": _ctl_escopos,
    "/tiktok-e2e/videos": _ctl_videos,
    "/tiktok-e2e/conta": _ctl_conta,
    "/tiktok-e2e/publicar-rascunho": _ctl_publicar_rascunho,
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

    def _tiktok(self, url, corpo: bytes) -> None:
        """TikTok falsa (spec 015): API, partes, avatar e as rotas de controle do e2e."""
        if url.path.startswith("/tiktok-e2e/"):
            return self._json(*tiktok_controle(self.command, url.path, url.query, corpo))
        if self.command == "PUT" and url.path == "/tiktok/upload/":
            codigo = tiktok_parte(url.query, self.headers.get("content-range", ""), corpo)
            self.send_response(codigo)
            self.send_header("content-length", "0")
            self.end_headers()
            return None
        if self.command == "GET" and url.path.startswith("/tiktok/avatar/"):
            dados = avatar_png(url.path.rsplit("/", 1)[-1].removesuffix(".png"))
            self.send_response(200)
            self.send_header("content-type", "image/png")
            self.send_header("content-length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)
            return None
        resposta = tiktok_api(self.command, url.path.removeprefix("/tiktok"), self.headers, corpo)
        if resposta is SEM_RESPOSTA:  # a TikTok recebeu (e criou), a resposta se perdeu
            self.close_connection = True
            return None
        return self._json(*resposta)

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        partes = url.path.strip("/").split("/")
        if url.path.startswith("/tiktok"):
            return self._tiktok(url, b"")
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
        if path.startswith("/tiktok"):
            return self._tiktok(urlsplit(self.path), corpo)
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
        if path.startswith("/tiktok"):
            return self._tiktok(urlsplit(self.path), self._corpo())
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
