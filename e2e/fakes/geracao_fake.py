"""ComfyUI, shop-tts e `dockerctl` de mentira para os e2e da spec 021 (T029, T039). Só stdlib.

Atendidos pelo `openshorts-fake` (`server.py` repassa os prefixos), com o mesmo comportamento
dos fakes do pytest (`apps/api/tests/fakes/`):
- `/comfyui/*`: `system_stats` (VRAM; "ocupada" = pouca VRAM), `upload/image`, `prompt`,
  `history/{id}` (fica "rodando" por `segundos` e depois sai com a imagem), `view` (PNG
  sintético 768×1344 com a cor tirada da seed, feito com `zlib`/`struct`), `free`, `interrupt` e
  `queue` (GET e o `delete`);
- `/shop-tts/*`: só `health` e `unload` (o motor `tts` real chega com a 025; o e2e não pede voz);
- `/dockerctl/comfyui/memoria[/subir|/devolver]`: o limite de RAM do ComfyUI, com o token fixo
  de teste (`DOCKERCTL_TOKEN` do `docker-compose.e2e.yml`);
- controle, só do e2e: `POST /geracao-e2e/gpu {ocupada}`, `POST /geracao-e2e/lento {segundos}`,
  `GET /geracao-e2e/memoria` (os limites depois de cada ação) e `GET /geracao-e2e/pedidos`
  (os prompts recebidos, com a seed e o bloco).
"""

import hmac
import json
import re
import struct
import threading
import time
import uuid
import zlib

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


def shop_tts(metodo: str, caminho: str) -> tuple[int, dict]:
    if metodo == "GET" and caminho == "/health":
        return 200, {"status": "ok", "loaded": False, "voices": [], "vram_free_mb": 14000}
    if metodo == "POST" and caminho == "/unload":
        return 200, {"unloaded": True}
    return 404, {"detail": "Not Found"}


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
    return 404, {"detail": "Not Found"}
