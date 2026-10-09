"""Cliente do ComfyUI e o porte do `run_block` do pipeline (research R3, R6 e R9;
contracts/comfyui.md).

Lista fechada (`ALLOWED`, como o cliente da publicação da 015): só a API padrão que o pipeline usa
(`/system_stats`, `/upload/image`, `/prompt`, `/history/{id}`, `/view`, `/queue`, `/interrupt` e
`/free`). Qualquer outro caminho é recusado antes de sair. Timeout de 10 s por chamada; a opção
inteira tem o teto `GERACAO_COMFYUI_TETO_S` (depois, `servico_fora`).

`run_bloco` preenche um dos 4 blocos copiados (`workflows/`, com o manifesto) pelo contrato
`params.json`, igual ao `run_block`: `image` sobe a imagem pelo `/upload/image` (subpasta
`sociman`), `image_optional` ausente tira o nó e religa (`drop`, `consumers`, `rewire`) e os demais
vão em `inputs`. Depois `POST /prompt`, polling do `/history` a cada 2 s (o `heartbeat` também
diz se a geração foi cancelada: aí `/interrupt` se o prompt é o que está rodando, e
`/queue delete`), o `/view` da 1ª saída e `POST /free` sem descarregar os modelos.

Os erros saem já traduzidos em `MotorErro` (R8): conexão, timeout e 5xx → `servico_fora`;
`OutOfMemoryError` na execução → `sem_memoria`; o resto → `internal`, com o detalhe só no log.
"""

import copy
import io
import json
import logging
import time
import uuid
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps

from sociman_api.config import get_settings
from sociman_api.geracao.erros import MotorErro

log = logging.getLogger("sociman.gerador")

WORKFLOWS = Path(__file__).resolve().parent / "workflows"
BLOCOS = ("cena", "keyframe", "retrato", "cutout")
ALLOWED: tuple[tuple[str, str], ...] = (
    ("GET", "/system_stats"),
    ("POST", "/upload/image"),
    ("POST", "/prompt"),
    ("GET", "/history/"),
    ("GET", "/view"),
    ("GET", "/queue"),
    ("POST", "/queue"),
    ("POST", "/interrupt"),
    ("POST", "/free"),
)
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
POLL_S = 2.0
SUBPASTA = "sociman"
W, H = 768, 1344
GB = 1024**3


class Cancelada(Exception):
    """A geração foi cancelada (ou deixou de ser deste processamento) no meio do bloco."""


def _allowed(method: str, path: str) -> bool:
    for m, prefix in ALLOWED:
        if m != method:
            continue
        if prefix.endswith("/") and path.startswith(prefix) and len(path) > len(prefix):
            return True
        if path == prefix:
            return True
    return False


class ComfyClient:
    """`transport` só nos testes (o fake `tests/fakes/comfyui_fake.py`)."""

    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=TIMEOUT, transport=transport)

    def __repr__(self) -> str:
        return f"ComfyClient({self.base_url!r})"

    def close(self) -> None:
        self._http.close()

    def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        if not _allowed(method, path):
            raise ValueError(f"ComfyUI: {method} {path} fora da lista fechada")
        try:
            resp = self._http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise MotorErro("servico_fora", detalhe=f"{method} {path}: {exc!r}") from exc
        if resp.status_code >= 500:
            raise MotorErro("servico_fora", detalhe=f"{method} {path}: {resp.status_code}")
        if resp.status_code >= 400:
            raise MotorErro("internal",
                            detalhe=f"{method} {path}: {resp.status_code} {resp.text[:500]}")
        return resp

    def system_stats(self) -> dict[str, Any]:
        return self._req("GET", "/system_stats").json()

    def vram_disponivel_gb(self) -> float:
        """`vram_free + torch_vram_total` do 1º dispositivo (o cache do ComfyUI conta, R3)."""
        dev = (self.system_stats().get("devices") or [{}])[0]
        return (int(dev.get("vram_free") or 0) + int(dev.get("torch_vram_total") or 0)) / GB

    def upload_image(self, nome: str, data: bytes) -> str:
        resp = self._req("POST", "/upload/image",
                         files={"image": (nome, data, "image/png")},
                         data={"subfolder": SUBPASTA, "type": "input", "overwrite": "true"})
        j = resp.json()
        return f"{j['subfolder']}/{j['name']}" if j.get("subfolder") else j["name"]

    def prompt(self, api: dict[str, Any]) -> str:
        return self._req("POST", "/prompt",
                         json={"prompt": api, "client_id": str(uuid.uuid4())}).json()["prompt_id"]

    def history(self, prompt_id: str) -> dict[str, Any] | None:
        return self._req("GET", f"/history/{prompt_id}").json().get(prompt_id)

    def view(self, filename: str, subfolder: str, tipo: str) -> bytes:
        return self._req("GET", "/view", params={"filename": filename, "subfolder": subfolder,
                                                 "type": tipo}).content

    def queue(self) -> dict[str, Any]:
        return self._req("GET", "/queue").json()

    def interrupt(self) -> None:
        self._req("POST", "/interrupt", json={})

    def queue_delete(self, prompt_ids: list[str]) -> None:
        self._req("POST", "/queue", json={"delete": prompt_ids})

    def free(self, unload_models: bool) -> None:
        self._req("POST", "/free", json={"unload_models": unload_models, "free_memory": True})


def get_comfy_client(transport: httpx.BaseTransport | None = None) -> ComfyClient:
    return ComfyClient(get_settings().comfyui_url, transport=transport)


# ---- blocos ----

@lru_cache
def _bloco_arquivos(bloco: str) -> tuple[str, str]:
    if bloco not in BLOCOS:
        raise ValueError(f"bloco desconhecido: {bloco}")
    return ((WORKFLOWS / f"{bloco}.api.json").read_text(),
            (WORKFLOWS / f"{bloco}.params.json").read_text())


def carregar_bloco(bloco: str) -> tuple[dict[str, Any], dict[str, Any]]:
    api, contrato = _bloco_arquivos(bloco)
    return json.loads(api), json.loads(contrato)


def preencher(bloco: str, params: dict[str, Any], upload: Callable[[str, bytes], str]
              ) -> tuple[dict[str, Any], dict[str, Any]]:
    """O workflow pronto para o `/prompt` (porte do `run_block`). `params[nome]` de imagem são
    bytes, que sobem por `upload(nome, data)`. Devolve (workflow, contrato)."""
    api, contrato = carregar_bloco(bloco)
    api = copy.deepcopy(api)
    for nome, spec in contrato["params"].items():
        valor = params.get(nome)
        if spec["kind"] in ("image", "image_optional", "audio"):
            if valor is None:
                if spec["kind"] == "image":
                    raise MotorErro("entrada_invalida",
                                    detalhe=f"{bloco}: falta a imagem obrigatória {nome!r}")
                api.pop(spec["node"], None)
                for nid in spec.get("drop", []):
                    api.pop(nid, None)
                for nid, inp in spec.get("consumers", []):
                    if nid in api:
                        api[nid]["inputs"].pop(inp, None)
                rw = spec.get("rewire", {})
                for n in api.values():
                    for k, v in n["inputs"].items():
                        if isinstance(v, list) and len(v) == 2 and v[0] in rw:
                            n["inputs"][k] = [rw[v[0]], v[1]]
                continue
            valor = upload(nome, valor)
        if valor is not None:
            api[spec["node"]]["inputs"][spec["input"]] = valor
    return api, contrato


def _erro_execucao(status: dict[str, Any]) -> MotorErro:
    mensagens = status.get("messages", [])
    if any(m[0] == "execution_interrupted" for m in mensagens):
        # Interrompido por outro processo (o pipeline do host, a UI do ComfyUI): o motor estava
        # de pé e a entrada é boa, então volta à fila com espera (R8), como um serviço fora.
        return MotorErro("servico_fora", detalhe="execução interrompida fora do SociMan")
    err = next((m[1] for m in mensagens if m[0] == "execution_error"), {})
    tipo = str(err.get("exception_type") or "")
    detalhe = f"{err.get('node_type')} {tipo}: {str(err.get('exception_message'))[:400]}"
    if "OutOfMemory" in tipo or "out of memory" in detalhe.lower():
        return MotorErro("sem_memoria", detalhe=detalhe)
    return MotorErro("internal", detalhe=detalhe)


def _parar(client: ComfyClient, prompt_id: str) -> None:
    """Cancelada: interrompe se o prompt é o que está rodando e tira da fila do ComfyUI."""
    try:
        fila = client.queue()
        rodando = {item[1] for item in fila.get("queue_running", []) if len(item) > 1}
        if prompt_id in rodando:
            client.interrupt()
        client.queue_delete([prompt_id])
    except MotorErro:
        log.warning("não foi possível interromper o prompt %s no ComfyUI", prompt_id)


def run_bloco(client: ComfyClient, bloco: str, params: dict[str, Any],
              heartbeat: Callable[[], bool], *, nome_base: str, teto_s: float | None = None,
              poll_s: float = POLL_S, sleep: Callable[[float], None] = time.sleep,
              relogio: Callable[[], float] = time.monotonic) -> bytes:
    """Roda um bloco e devolve os bytes da 1ª imagem de saída. `heartbeat()` False = cancelada
    (levanta `Cancelada` depois de parar o ComfyUI)."""
    teto = teto_s if teto_s is not None else get_settings().geracao_comfyui_teto_s

    def upload(nome: str, data: bytes) -> str:
        return client.upload_image(f"{nome_base}_{nome}.png", data)

    api, contrato = preencher(bloco, params, upload)
    prompt_id = client.prompt(api)
    inicio = relogio()
    while True:
        if not heartbeat():
            _parar(client, prompt_id)
            raise Cancelada
        h = client.history(prompt_id)
        if h is not None:
            break
        if relogio() - inicio > teto:
            _parar(client, prompt_id)
            raise MotorErro("servico_fora", detalhe=f"{bloco}: passou do teto de {teto:.0f} s")
        sleep(poll_s)
    status = h.get("status") or {}
    if status.get("status_str") != "success":
        raise _erro_execucao(status)
    dados = None
    for o in contrato["outputs"].values():
        if o["kind"] != "image":
            continue
        files = (h.get("outputs") or {}).get(o["node"], {}).get("images") or []
        if files:
            f = files[0]
            dados = client.view(f["filename"], f.get("subfolder", ""), f.get("type", "output"))
            break
    try:
        client.free(unload_models=False)
    except MotorErro:
        log.warning("POST /free do ComfyUI falhou no fim do bloco %s", bloco)
    if not dados:
        raise MotorErro("internal", "O motor não devolveu imagem", detalhe=f"{bloco}: sem saída")
    return dados


def normalizar_9x16(data: bytes) -> bytes:
    """Corta no centro para 9:16 e redimensiona para 768×1344 (o `fit_9x16` do pipeline), em
    memória, como PNG."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            out = ImageOps.fit(im, (W, H), Image.LANCZOS)
    except Exception as exc:  # imagem ilegível que o motor devolveu
        raise MotorErro("entrada_invalida", "O motor devolveu uma imagem inválida",
                        detalhe=repr(exc)) from exc
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
