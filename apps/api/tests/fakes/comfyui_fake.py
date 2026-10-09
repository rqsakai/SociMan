"""ComfyUI falso (spec 021, T012, research R13): um `httpx.MockTransport` com estado para o
cliente de `geracao/comfyui.py`. Os testes nunca chamam o ComfyUI real.

Uso: `from fakes.comfyui_fake import comfy_fake  # noqa: F401` e `comfy_fake.cliente()` (o
`ComfyClient("http://comfyui:8188")` com o transporte falso), ou `transport=comfy_fake.transport`
nas fábricas `get_comfy_client`.

A API padrão que o cliente usa (contracts/comfyui.md):
- `GET /system_stats`: VRAM programável em **bytes** (`vram_free`, `torch_vram_total`,
  `vram_total`);
- `POST /upload/image` (multipart `image`, `subfolder`, `type`, `overwrite`): guarda os bytes em
  `uploads["<subfolder>/<nome>"]` e responde `{name, subfolder, type}`;
- `POST /prompt {prompt, client_id}`: reconhece o bloco pelos nós (os 4 de `geracao/workflows/`)
  e confere o contrato `params.json`: `image` precisa apontar para uma imagem enviada,
  `image_optional` ou foi enviada ou o nó saiu inteiro (sem link pendurado), `value` tem o tipo
  do padrão (texto não vazio). Recusa como o ComfyUI (400 `prompt_outputs_failed_validation`,
  guardado em `recusados`); aceito, guarda em `prompts` e devolve `prompt_id`;
- `GET /history/{id}`: `{}` ("rodando") por `voltas` chamadas, depois o resultado com
  `outputs.<nó>.images` (o nó de saída do contrato);
- `GET /view?filename&subfolder&type`: o PNG sintético do tamanho do workflow (`width`/`height`
  do contrato; sem eles, 768×1344), com a seed escrita na imagem e no texto `seed` do PNG
  (`ComfyFake.seed_do_png(dados)` lê de volta);
- `POST /free` (corpos em `frees`), `POST /interrupt` (`interrupcoes`; o prompt que está rodando
  termina com `execution_interrupted`), `GET /queue` (`queue_running` com
  `[numero, prompt_id, workflow, extra, saídas]`) e `POST /queue {delete: [...]}` (`apagados`).

Falhas: `fora = True` (conexão recusada em tudo: `httpx.ConnectError`), `erro_5xx = True`,
`falhar_proximo("oom" | "vazia", vezes=1)` ou `falhar_sempre = "oom" | "vazia"`: `oom` termina a
execução com `status_str: "error"` e `torch.OutOfMemoryError`; `vazia` termina em `success`
sem imagens.

`requests` guarda cada pedido como `Pedido(metodo, caminho, corpo)`: JSON decodificado, os
campos de texto do multipart (com `image` = nome do arquivo) ou a query do GET.
"""

import copy
import io
import itertools
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import httpx
import pytest
from PIL import Image, ImageDraw, PngImagePlugin

from fakes import _multipart
from sociman_api.geracao.comfyui import BLOCOS, ComfyClient, carregar_bloco

BASE = "http://comfyui:8188"
GiB = 1024**3
W_PADRAO, H_PADRAO = 768, 1344


class Pedido(NamedTuple):
    metodo: str
    caminho: str
    corpo: Any


@dataclass
class PromptFake:
    id: str
    numero: int
    bloco: str
    workflow: dict[str, Any]
    voltas: int
    falha: str | None
    estado: str = "fila"  # fila | pronto | interrompido | apagado
    saida: dict[str, str] | None = None
    params: dict[str, Any] = field(default_factory=dict)


def _ids_opcionais(contrato: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for spec in contrato["params"].values():
        if spec["kind"] == "image_optional":
            ids.add(spec["node"])
            ids.update(spec.get("drop", []))
    return ids


def _links(no: dict[str, Any]) -> list[str]:
    return [v[0] for v in no.get("inputs", {}).values()
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)]


class ComfyFake:
    def __init__(self) -> None:
        self.requests: list[Pedido] = []
        self.vram_total = 16 * GiB
        self.vram_free = 14 * GiB
        self.torch_vram_total = 0
        self.uploads: dict[str, bytes] = {}
        self.prompts: dict[str, PromptFake] = {}
        self.recusados: list[str] = []
        self.saidas: dict[tuple[str, str, str], bytes] = {}
        self.frees: list[dict[str, Any]] = []
        self.interrupcoes = 0
        self.apagados: list[str] = []
        self.voltas = 1
        self.fora = False
        self.erro_5xx = False
        self.falhar_sempre: str | None = None
        self._falhas: list[str] = []
        self._numero = itertools.count(1)
        self._contador = itertools.count(1)
        self._blocos = {b: carregar_bloco(b) for b in BLOCOS}
        self.transport = httpx.MockTransport(self._handle)

    # ---- para os testes ----

    def cliente(self) -> ComfyClient:
        return ComfyClient(BASE, transport=self.transport)

    def falhar_proximo(self, falha: str, vezes: int = 1) -> None:
        if falha not in ("oom", "vazia"):
            raise ValueError(falha)
        self._falhas.extend([falha] * vezes)

    def pedidos(self) -> list[tuple[str, str]]:
        return [(p.metodo, p.caminho) for p in self.requests]

    def ultimo(self) -> PromptFake:
        return max(self.prompts.values(), key=lambda p: p.numero)

    @staticmethod
    def seed_do_png(dados: bytes) -> int:
        with Image.open(io.BytesIO(dados)) as im:
            return int(im.text["seed"])  # type: ignore[attr-defined]

    # ---- servidor ----

    @staticmethod
    def _json(status: int, data: Any) -> httpx.Response:
        return httpx.Response(status, json=data)

    def _registrar(self, request: httpx.Request) -> None:
        corpo: Any = None
        if request.method == "GET":
            corpo = dict(request.url.params) or None
        elif request.content:
            partes = _multipart.ler(request)
            if partes:
                corpo = {n: (p.arquivo if p.arquivo is not None else p.texto)
                         for n, p in partes.items()}
            else:
                try:
                    corpo = json.loads(request.content)
                except ValueError:
                    corpo = request.content
        self.requests.append(Pedido(request.method, request.url.path, corpo))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self._registrar(request)
        if self.fora:
            raise httpx.ConnectError("conexão recusada", request=request)
        if self.erro_5xx:
            return self._json(500, {"error": "Internal Server Error"})
        metodo, path = request.method, request.url.path
        if metodo == "GET" and path == "/system_stats":
            return self._system_stats()
        if metodo == "POST" and path == "/upload/image":
            return self._upload(request)
        if metodo == "POST" and path == "/prompt":
            return self._prompt(json.loads(request.content))
        if metodo == "GET" and path.startswith("/history/"):
            return self._history(path.removeprefix("/history/"))
        if metodo == "GET" and path == "/view":
            p = request.url.params
            return self._view(p.get("filename", ""), p.get("subfolder", ""),
                              p.get("type", "output"))
        if metodo == "GET" and path == "/queue":
            return self._queue()
        if metodo == "POST" and path == "/queue":
            return self._queue_post(json.loads(request.content or b"{}"))
        if metodo == "POST" and path == "/interrupt":
            return self._interrupt()
        if metodo == "POST" and path == "/free":
            self.frees.append(json.loads(request.content or b"{}"))
            return httpx.Response(200)
        return self._json(404, {"error": "Not Found"})

    def _system_stats(self) -> httpx.Response:
        return self._json(200, {
            "system": {"os": "posix", "comfyui_version": "0.3.x", "python_version": "3.12"},
            "devices": [{"name": "cuda:0 NVIDIA GeForce RTX 5060 Ti : cudaMallocAsync",
                         "type": "cuda", "index": 0, "vram_total": self.vram_total,
                         "vram_free": self.vram_free, "torch_vram_total": self.torch_vram_total,
                         "torch_vram_free": self.torch_vram_total}]})

    def _upload(self, request: httpx.Request) -> httpx.Response:
        partes = _multipart.ler(request)
        img = partes.get("image")
        if img is None or not img.arquivo:
            return self._json(400, {"error": "image is required"})
        sub = partes["subfolder"].texto if "subfolder" in partes else ""
        tipo = partes["type"].texto if "type" in partes else "input"
        chave = f"{sub}/{img.arquivo}" if sub else img.arquivo
        self.uploads[chave] = img.dados
        return self._json(200, {"name": img.arquivo, "subfolder": sub, "type": tipo})

    # -- /prompt --

    def _reconhecer(self, wf: dict[str, Any]) -> str | None:
        enviados = {(nid, no.get("class_type")) for nid, no in wf.items()}
        for bloco, (api, contrato) in self._blocos.items():
            assinatura = {(nid, no["class_type"]) for nid, no in api.items()}
            obrigatorios = {(nid, api[nid]["class_type"]) for nid in api
                            if nid not in _ids_opcionais(contrato)}
            if enviados <= assinatura and obrigatorios <= enviados:
                return bloco
        return None

    def _validar(self, bloco: str, wf: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        contrato = self._blocos[bloco][1]
        erros: list[str] = []
        params: dict[str, Any] = {}
        for nome, spec in contrato["params"].items():
            no = wf.get(spec["node"])
            if no is None:
                if spec["kind"] != "image_optional":
                    erros.append(f"{nome}: o nó {spec['node']} sumiu")
                continue
            valor = no.get("inputs", {}).get(spec["input"])
            params[nome] = valor
            if spec["kind"] in ("image", "image_optional"):
                if valor not in self.uploads:
                    erros.append(f"{nome}: a imagem {valor!r} não foi enviada")
            elif valor is None:
                erros.append(f"{nome}: sem valor")
            elif type(valor) is not type(spec["default"]):
                erros.append(f"{nome}: tipo {type(valor).__name__}, esperado "
                             f"{type(spec['default']).__name__}")
            elif isinstance(valor, str) and not valor.strip():
                erros.append(f"{nome}: texto vazio")
        for nid, no in wf.items():
            for alvo in _links(no):
                if alvo not in wf:
                    erros.append(f"nó {nid} aponta para o nó {alvo}, que não existe")
        return erros, params

    def _prompt(self, corpo: dict[str, Any]) -> httpx.Response:
        wf = corpo.get("prompt")
        if not isinstance(wf, dict):
            return self._json(400, {"error": {"type": "invalid_prompt",
                                              "message": "no prompt"}, "node_errors": {}})
        bloco = self._reconhecer(wf)
        erros, params = (["bloco desconhecido"], {}) if bloco is None else self._validar(bloco,
                                                                                         wf)
        if erros:
            self.recusados.extend(erros)
            return self._json(400, {
                "error": {"type": "prompt_outputs_failed_validation",
                          "message": "Prompt outputs failed validation",
                          "details": "; ".join(erros)},
                "node_errors": {}})
        falha = self._falhas.pop(0) if self._falhas else self.falhar_sempre
        p = PromptFake(id=str(uuid.uuid4()), numero=next(self._numero), bloco=bloco or "",
                       workflow=copy.deepcopy(wf), voltas=self.voltas, falha=falha,
                       params=params)
        self.prompts[p.id] = p
        return self._json(200, {"prompt_id": p.id, "number": p.numero, "node_errors": {}})

    # -- execução --

    def _rodando(self) -> PromptFake | None:
        vivos = [p for p in self.prompts.values() if p.estado == "fila"]
        return min(vivos, key=lambda p: p.numero) if vivos else None

    def _tamanho(self, p: PromptFake) -> tuple[int, int]:
        w, h = p.params.get("width"), p.params.get("height")
        return (int(w), int(h)) if isinstance(w, int) and isinstance(h, int) else (W_PADRAO,
                                                                                    H_PADRAO)

    def _png(self, p: PromptFake) -> bytes:
        seed = int(p.params.get("seed") or 0)
        w, h = self._tamanho(p)
        cor = ((seed * 67) % 256, (seed * 131) % 256, (seed * 199) % 256)
        im = Image.new("RGB", (w, h), cor)
        ImageDraw.Draw(im).text((16, 16), f"{p.bloco} seed={seed}", fill=(255, 255, 255))
        info = PngImagePlugin.PngInfo()
        info.add_text("seed", str(seed))
        info.add_text("bloco", p.bloco)
        buf = io.BytesIO()
        im.save(buf, format="PNG", pnginfo=info)
        return buf.getvalue()

    def _concluir(self, p: PromptFake) -> None:
        p.estado = "pronto"
        if p.falha:
            return
        prefixo = str(p.params.get("prefix") or "ComfyUI")
        sub, _, base = prefixo.rpartition("/")
        nome = f"{base}_{next(self._contador):05d}_.png"
        p.saida = {"filename": nome, "subfolder": sub, "type": "output"}
        self.saidas[(sub, nome, "output")] = self._png(p)

    def _history(self, prompt_id: str) -> httpx.Response:
        p = self.prompts.get(prompt_id)
        if p is None or p.estado == "apagado":
            return self._json(200, {})
        if p.estado == "fila":
            # Só o 1º da fila anda (gasta as `voltas`); os de trás esperam, como no ComfyUI.
            if self._rodando() is not p:
                return self._json(200, {})
            if p.voltas > 0:
                p.voltas -= 1
                return self._json(200, {})
            self._concluir(p)
        return self._json(200, {p.id: self._resultado(p)})

    def _resultado(self, p: PromptFake) -> dict[str, Any]:
        no_saida = next(o["node"] for o in self._blocos[p.bloco][1]["outputs"].values()
                        if o["kind"] == "image")
        if p.estado == "interrompido":
            return {"prompt": [p.numero, p.id, p.workflow, {}, [no_saida]], "outputs": {},
                    "status": {"status_str": "error", "completed": False, "messages": [
                        ["execution_start", {"prompt_id": p.id}],
                        ["execution_interrupted", {"prompt_id": p.id, "node_id": no_saida,
                                                   "node_type": "KSampler"}]]}}
        if p.falha == "oom":
            return {"prompt": [p.numero, p.id, p.workflow, {}, [no_saida]], "outputs": {},
                    "status": {"status_str": "error", "completed": False, "messages": [
                        ["execution_start", {"prompt_id": p.id}],
                        ["execution_error", {
                            "prompt_id": p.id, "node_id": no_saida, "node_type": "KSampler",
                            "exception_type": "torch.OutOfMemoryError",
                            "exception_message": ("Allocation on device 0 would exceed "
                                                  "allowed memory. (out of memory)")}]]}}
        imagens = [p.saida] if p.saida else []
        return {"prompt": [p.numero, p.id, p.workflow, {}, [no_saida]],
                "outputs": {no_saida: {"images": imagens}} if imagens else {},
                "status": {"status_str": "success", "completed": True, "messages": [
                    ["execution_start", {"prompt_id": p.id}],
                    ["execution_success", {"prompt_id": p.id}]]}}

    def _view(self, filename: str, subfolder: str, tipo: str) -> httpx.Response:
        dados = self.saidas.get((subfolder, filename, tipo))
        if dados is None:
            return self._json(404, {"error": "file not found"})
        return httpx.Response(200, content=dados, headers={"content-type": "image/png"})

    def _queue(self) -> httpx.Response:
        vivos = sorted((p for p in self.prompts.values() if p.estado == "fila"),
                       key=lambda p: p.numero)

        def item(p: PromptFake) -> list[Any]:
            return [p.numero, p.id, p.workflow, {"client_id": "fake"}, []]

        return self._json(200, {"queue_running": [item(p) for p in vivos[:1]],
                                "queue_pending": [item(p) for p in vivos[1:]]})

    def _queue_post(self, corpo: dict[str, Any]) -> httpx.Response:
        rodando = self._rodando()
        for pid in corpo.get("delete", []):
            self.apagados.append(pid)
            p = self.prompts.get(pid)
            if p is not None and p.estado == "fila" and p is not rodando:
                p.estado = "apagado"  # como o ComfyUI: só sai da fila o que não está rodando
        if corpo.get("clear"):
            for p in self.prompts.values():
                if p.estado == "fila" and p is not rodando:
                    p.estado = "apagado"
        return httpx.Response(200)

    def _interrupt(self) -> httpx.Response:
        self.interrupcoes += 1
        p = self._rodando()
        if p is not None:
            p.estado = "interrompido"
        return httpx.Response(200)


@pytest.fixture
def comfy_fake() -> ComfyFake:
    return ComfyFake()
