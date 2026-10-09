"""ComfyUI, shop-tts e `dockerctl` de mentira para os e2e da spec 021 (T029, T039). Só stdlib.

Atendidos pelo `openshorts-fake` (`server.py` repassa os prefixos), com o mesmo comportamento
dos fakes do pytest (`apps/api/tests/fakes/`):
- `/comfyui/*`: `system_stats` (VRAM; "ocupada" = pouca VRAM), `upload/image`, `prompt`,
  `history/{id}` (fica "rodando" por `segundos` e depois sai com a imagem), `view` (PNG
  sintético 768×1344 com a cor tirada da seed, feito com `zlib`/`struct`), `free`, `interrupt` e
  `queue` (GET e o `delete`);
- `/shop-tts/*` (contrato `v2`, spec 025): `health`, `voices`, `unload`, `v2/voices/register`
  (multipart), `v2/voices/design`, `v2/voices/import` (multipart), `v2/tts`, `v2/tts_paragraph`,
  `GET v2/lotes/{lote}/{arquivo}` (WAV sintético de 24 kHz), `DELETE v2/lotes/{lote}` e
  `DELETE v2/voices/{nome}`, como `apps/api/tests/fakes/shoptts_fake.py`;
- `/dockerctl/comfyui/memoria[/subir|/devolver]`: o limite de RAM do ComfyUI, com o token fixo
  de teste (`DOCKERCTL_TOKEN` do `docker-compose.e2e.yml`);
- controle, só do e2e: `POST /geracao-e2e/gpu {ocupada}`, `POST /geracao-e2e/lento {segundos}`,
  `GET /geracao-e2e/memoria` (os limites depois de cada ação) e `GET /geracao-e2e/pedidos`
  (os prompts recebidos, com a seed e o bloco), `GET /geracao-e2e/vozes-tts` (as vozes do
  shop-tts falso, as importadas e as apagadas).
"""

import hashlib
import hmac
import io
import json
import math
import re
import struct
import threading
import time
import uuid
import wave
import zlib
from email.parser import BytesParser
from email.policy import HTTP

GiB = 1024**3
NORMAL, JOB = 12 * GiB, 28 * GiB
TOKEN = "e2e-token-do-dockerctl-de-teste"  # liberado por valor no check:secrets
W, H = 768, 1344

_lock = threading.Lock()
ESTADO = {"ocupada": False, "segundos": 2.0, "memoria": NORMAL}
MEMORIA: list[int] = []
PROMPTS: dict[str, dict] = {}  # id → {inicio, workflow, seed, bloco, interrompido}
PEDIDOS: list[dict] = []
_PNG_CACHE: dict[int, bytes] = {}


def _png(seed: int) -> bytes:
    """PNG RGB 768×1344 de uma cor só (a cor vem da seed)."""
    if seed in _PNG_CACHE:
        return _PNG_CACHE[seed]
    cor = bytes(((seed * 37) % 200 + 30, (seed * 91) % 200 + 30, (seed * 53) % 200 + 30))
    linha = b"\x00" + cor * W
    cru = zlib.compress(linha * H, 6)

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return (struct.pack(">I", len(dados)) + tipo + dados
                + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))
    png = (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + bloco(b"IDAT", cru) + bloco(b"IEND", b""))
    _PNG_CACHE[seed] = png
    return png


def _seed(wf: dict) -> int:
    """A seed do workflow: o nó `PrimitiveInt` que alimenta o sampler (nos blocos da 021, é o
    único inteiro que não é largura nem altura)."""
    inteiros = [n["inputs"].get("value") for n in wf.values()
                if n.get("class_type") == "PrimitiveInt"]
    candidatos = [v for v in inteiros if isinstance(v, int) and v not in (W, H)]
    return candidatos[0] if candidatos else 0


def _saida(wf: dict) -> str:
    return next((nid for nid, n in wf.items() if n.get("class_type") == "SaveImage"), "9")


def comfyui(metodo: str, caminho: str, corpo: bytes, query: str = ""
            ) -> tuple[int, dict | bytes, str]:
    """(status, corpo, content-type) para `/comfyui/<caminho>`."""
    if metodo == "GET" and caminho == "/system_stats":
        livre = 1 * GiB if ESTADO["ocupada"] else 14 * GiB
        return 200, {"devices": [{"name": "fake", "vram_total": 16 * GiB, "vram_free": livre,
                                  "torch_vram_total": 0, "torch_vram_free": 0}]}, "json"
    if metodo == "POST" and caminho == "/upload/image":
        m = re.search(rb'filename="([^"]+)"', corpo)
        nome = m.group(1).decode() if m else "ref.png"
        return 200, {"name": nome, "subfolder": "sociman", "type": "input"}, "json"
    if metodo == "POST" and caminho == "/prompt":
        wf = json.loads(corpo or b"{}").get("prompt") or {}
        pid = str(uuid.uuid4())
        bloco = "keyframe" if any(n.get("class_type") == "LoadImage" for n in wf.values()) \
            else "cena"
        with _lock:
            PROMPTS[pid] = {"inicio": time.monotonic(), "workflow": wf, "seed": _seed(wf),
                            "bloco": bloco, "interrompido": False}
            PEDIDOS.append({"prompt_id": pid, "seed": _seed(wf), "bloco": bloco})
        return 200, {"prompt_id": pid, "number": len(PEDIDOS)}, "json"
    if metodo == "GET" and caminho.startswith("/history/"):
        pid = caminho.rsplit("/", 1)[-1]
        p = PROMPTS.get(pid)
        if p is None or (time.monotonic() - p["inicio"] < ESTADO["segundos"]
                         and not p["interrompido"]):
            return 200, {}, "json"
        if p["interrompido"]:
            return 200, {pid: {"status": {"status_str": "error", "messages": [
                ["execution_interrupted", {}]]}, "outputs": {}}}, "json"
        return 200, {pid: {"status": {"status_str": "success", "messages": []}, "outputs": {
            _saida(p["workflow"]): {"images": [{"filename": f"{pid}.png", "subfolder": "",
                                                "type": "output"}]}}}}, "json"
    if metodo == "GET" and caminho == "/view":
        m = re.search(r"filename=([0-9a-f-]+)\.png", query)
        pid = m.group(1) if m else ""
        seed = PROMPTS.get(pid, {}).get("seed", 0)
        return 200, _png(seed), "image/png"
    if metodo == "GET" and caminho == "/queue":
        agora = time.monotonic()
        rodando = [[i, pid, {}, {}, []] for i, (pid, p) in enumerate(PROMPTS.items())
                   if agora - p["inicio"] < ESTADO["segundos"] and not p["interrompido"]]
        return 200, {"queue_running": rodando[:1], "queue_pending": rodando[1:]}, "json"
    if metodo == "POST" and caminho == "/interrupt":
        with _lock:
            for p in PROMPTS.values():
                if time.monotonic() - p["inicio"] < ESTADO["segundos"]:
                    p["interrompido"] = True
        return 200, {}, "json"
    if metodo == "POST" and caminho in ("/queue", "/free"):
        return 200, {}, "json"
    return 404, {"detail": "Not Found"}, "json"


TAXA = 24000
_NOME_VOZ = re.compile(r"^[a-z0-9_]{2,40}$")
_NOME_ARQ = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
VOZES: dict[str, dict] = {n: {"file": f"/vozes/ref_{n}.wav", "text": "ref", "sha256": "0" * 64}
                          for n in ("animada", "calma", "explicativa")}
IMPORTADAS: list[dict] = []
VOZES_APAGADAS: list[str] = []
LOTES: dict[str, dict[str, bytes]] = {}


def _wav(segundos: float = 1.0, freq: float = 440.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        n = int(TAXA * segundos)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i
                                                                        / TAXA)))
                               for i in range(n)))
    return buf.getvalue()


def _multipart(corpo: bytes, content_type: str) -> dict[str, tuple[str | None, bytes]]:
    """nome → (arquivo, bytes)."""
    msg = BytesParser(policy=HTTP).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + corpo)
    partes = {}
    for parte in msg.iter_parts():
        nome = parte.get_param("name", header="content-disposition")
        if nome:
            partes[nome] = (parte.get_filename(), parte.get_payload(decode=True) or b"")
    return partes


def _lote(corpo: dict, arquivos: dict[str, bytes]) -> tuple[int, dict]:
    lid = uuid.uuid4().hex
    with _lock:
        LOTES[lid] = arquivos
    corpo["lote_id"] = lid
    return 200, corpo


def _candidatos(n: int, transcricao: str) -> tuple[list[dict], dict[str, bytes]]:
    cands, arquivos = [], {}
    for k in range(1, n + 1):
        inicio = round(0.5 + 9.0 * (k - 1), 2)
        cands.append({"n": k, "arquivo": f"candidato_{k}.wav", "teste": f"teste_{k}.wav",
                      "segundos": 1.0, "similaridade": round(0.97 - 0.01 * (k - 1), 3),
                      "transcricao": transcricao,
                      "janela": {"inicio_s": inicio, "fim_s": round(inicio + 8.5, 2)}})
        arquivos[f"candidato_{k}.wav"] = _wav(1.0, 220.0 + 20 * k)
        arquivos[f"teste_{k}.wav"] = _wav(1.0, 330.0 + 20 * k)
    return cands, arquivos


def _n(valor) -> int | None:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 3 else None


def _texto(partes: dict, nome: str) -> str:
    return partes[nome][1].decode() if nome in partes else ""


def shop_tts(metodo: str, caminho: str, corpo: bytes = b"", content_type: str = ""
             ) -> tuple[int, dict | bytes | None, str]:
    """(status, corpo, content-type) para `/shop-tts/<caminho>`; corpo None = 204."""
    if metodo == "GET" and caminho == "/health":
        return 200, {"status": "ok", "loaded": False, "voices": list(VOZES),
                     "vram_free_mb": 14000}, "json"
    if metodo == "GET" and caminho == "/voices":
        return 200, VOZES, "json"
    if metodo == "POST" and caminho == "/unload":
        return 200, {"unloaded": True}, "json"
    if metodo == "POST" and caminho == "/v2/voices/register":
        partes = _multipart(corpo, content_type)
        arq = partes.get("arquivo")
        n = _n(_texto(partes, "n"))
        if not arq or not arq[1] or not _NOME_VOZ.match(_texto(partes, "nome")) or n is None:
            return 422, {"detail": "pedido inválido"}, "json"
        comprimido = (arq[0] or "").lower().endswith((".ogg", ".opus", ".m4a", ".mp3"))
        transcricao = "Oi, gente! Hoje eu vou mostrar um achadinho incrível para vocês."
        cands, arquivos = _candidatos(n, transcricao)
        avisos = ["O áudio parece comprimido (WhatsApp); grave de novo pela interface de "
                  "áudio se der"] if comprimido else []
        return (*_lote({"analise": {"codec": "opus" if comprimido else "pcm_s16le",
                                    "bitrate": 32000 if comprimido else 384000,
                                    "sample_rate": 48000 if comprimido else TAXA,
                                    "piso_ruido_dbfs": -58.0, "snr_db": 36.5,
                                    "clipping_pct": 0.0, "duracao_s": 21.4, "avisos": avisos},
                        "transcricao": transcricao, "candidatos": cands}, arquivos), "json")
    if metodo == "POST" and caminho == "/v2/voices/design":
        dados = json.loads(corpo or b"{}")
        n = _n(dados.get("n"))
        if not _NOME_VOZ.match(str(dados.get("nome") or "")) or n is None or not str(
                dados.get("descricao") or "").strip():
            return 422, {"detail": "pedido inválido"}, "json"
        texto = dados.get("texto") or "Oi! Essa é a minha voz, prazer em te conhecer."
        cands, arquivos = _candidatos(n, texto)
        return (*_lote({"transcricao": texto, "candidatos": cands}, arquivos), "json")
    if metodo == "POST" and caminho == "/v2/voices/import":
        partes = _multipart(corpo, content_type)
        nome, ref = _texto(partes, "nome"), partes.get("ref")
        if not _NOME_VOZ.match(nome) or not ref or not _texto(partes, "ref_texto").strip():
            return 422, {"detail": "pedido inválido"}, "json"
        sha = hashlib.sha256(ref[1]).hexdigest()
        with _lock:
            VOZES[nome] = {"file": f"/vozes/ref_{nome}.wav",
                           "text": _texto(partes, "ref_texto"), "sha256": sha}
            IMPORTADAS.append({"nome": nome, "sha256": sha})
        return 200, {"nome": nome, "sha256": sha,
                     "importada_em": time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                                   time.gmtime())}, "json"
    if metodo == "POST" and caminho in ("/v2/tts", "/v2/tts_paragraph"):
        dados = json.loads(corpo or b"{}")
        frases = dados.get("sentences")
        if "out_dir" in dados or not isinstance(frases, list) or not frases:
            return 422, {"detail": "pedido inválido"}, "json"
        voz = dados.get("voice", "animada")
        if voz not in VOZES:
            return 404, {"detail": f"voz desconhecida: {voz}"}, "json"
        seed = int(dados.get("seed", 1))
        if caminho.endswith("paragraph"):
            total = float(len(frases))
            tempos = [{"index": i, "text": f, "start": float(i - 1), "end": float(i)}
                      for i, f in enumerate(frases, 1)]
            return (*_lote({"voice": voz, "arquivo": "narracao.wav", "frases": tempos,
                            "sample_rate": TAXA, "seconds": total, "similarity": 0.97,
                            "seed": seed, "transcript": " ".join(frases), "ok": True},
                           {"narracao.wav": _wav(total)}), "json")
        saida, arquivos = [], {}
        for i, f in enumerate(frases, 1):
            nome = f"frase_{i:02d}.wav"
            saida.append({"index": i, "text": f, "arquivo": nome, "similarity": 0.97,
                          "seconds": 1.0, "seed": seed, "transcript": f, "ok": True})
            arquivos[nome] = _wav(1.0, 300.0 + 10 * i)
        return (*_lote({"voice": voz, "sample_rate": TAXA, "total_seconds": float(len(frases)),
                        "frases": saida}, arquivos), "json")
    partes_path = caminho.strip("/").split("/")
    if partes_path[:2] == ["v2", "lotes"] and len(partes_path) in (3, 4):
        if not all(_NOME_ARQ.match(x) and ".." not in x for x in partes_path[2:]):
            return 400, {"detail": "caminho inválido"}, "json"
        if metodo == "GET" and len(partes_path) == 4:
            dados = LOTES.get(partes_path[2], {}).get(partes_path[3])
            return (200, dados, "audio/wav") if dados else (404, {"detail": "Not Found"}, "json")
        if metodo == "DELETE" and len(partes_path) == 3:
            with _lock:
                LOTES.pop(partes_path[2], None)
            return 204, None, "json"
    if partes_path[:2] == ["v2", "voices"] and len(partes_path) == 3 and metodo == "DELETE":
        with _lock:
            if VOZES.pop(partes_path[2], None) is None:
                return 404, {"detail": "voz não existe"}, "json"
            VOZES_APAGADAS.append(partes_path[2])
        return 204, None, "json"
    return 404, {"detail": "Not Found"}, "json"


def _estado_memoria() -> dict:
    m = ESTADO["memoria"]
    return {"memoria_bytes": m, "memoria_swap_bytes": m,
            "estado": "normal" if m == NORMAL else "job" if m == JOB else "outro"}


def dockerctl(metodo: str, caminho: str, autorizacao: str) -> tuple[int, dict]:
    if not hmac.compare_digest(autorizacao.encode(), f"Bearer {TOKEN}".encode()):
        return 401, {"detail": "token"}
    acoes = {("GET", "/comfyui/memoria"): None, ("POST", "/comfyui/memoria/subir"): JOB,
             ("POST", "/comfyui/memoria/devolver"): NORMAL}
    if (metodo, caminho) not in acoes:
        return 404, {"detail": "Not Found"}
    with _lock:
        novo = acoes[(metodo, caminho)]
        if novo is not None:
            ESTADO["memoria"] = novo
        MEMORIA.append(ESTADO["memoria"])
        return 200, _estado_memoria()


def controle(metodo: str, caminho: str, corpo: bytes) -> tuple[int, dict]:
    dados = json.loads(corpo or b"{}") if metodo == "POST" else {}
    if metodo == "POST" and caminho == "/geracao-e2e/gpu":
        ESTADO["ocupada"] = bool(dados.get("ocupada"))
        return 200, {"ocupada": ESTADO["ocupada"]}
    if metodo == "POST" and caminho == "/geracao-e2e/lento":
        ESTADO["segundos"] = float(dados.get("segundos", 2.0))
        return 200, {"segundos": ESTADO["segundos"]}
    if metodo == "GET" and caminho == "/geracao-e2e/memoria":
        return 200, {"historico": list(MEMORIA), **_estado_memoria()}
    if metodo == "GET" and caminho == "/geracao-e2e/pedidos":
        return 200, {"pedidos": list(PEDIDOS)}
    if metodo == "GET" and caminho == "/geracao-e2e/vozes-tts":
        return 200, {"vozes": sorted(VOZES), "importadas": list(IMPORTADAS),
                     "apagadas": list(VOZES_APAGADAS)}
    return 404, {"detail": "Not Found"}
