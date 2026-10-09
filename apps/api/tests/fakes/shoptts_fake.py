"""shop-tts falso (spec 021, T013, research R13): exatamente o contrato `v2` de
`specs/021-geracao-local/contracts/shop-tts.md` (mais o `DELETE /v2/voices/{nome}` da 025), num
`httpx.MockTransport` com estado, para o cliente de `geracao/shoptts.py`.

Uso: `from fakes.shoptts_fake import shoptts_fake  # noqa: F401` e `shoptts_fake.cliente()` (o
`ShopTtsClient("http://shop-tts:8200")` com o transporte falso).

Rotas:
- `GET /health` → `{status, loaded, voices, vram_free_mb}`; `GET /voices` → `nome → {file, text,
  sha256}` (começa com `animada`, `calma` e `explicativa`, como o serviço real); `POST /unload`;
- `POST /v2/voices/register` (multipart `arquivo`, `nome`, `tom`, `n` ≤ 3) e
  `POST /v2/voices/design` (JSON `nome`, `descricao`, `texto?`, `n` ≤ 3, `seed`) → `Lote` com
  `candidatos` [{n, arquivo: "candidato_N.wav", teste: "teste_N.wav", segundos, similaridade,
  transcricao, janela: {inicio_s, fim_s}}] (o register traz também a `analise`; arquivo `.ogg`/
  `.opus`/`.m4a` ganha o aviso de áudio comprimido);
- `POST /v2/voices/import` (multipart `nome`, `ref` = WAV mono 24 kHz, `ref_texto`, `meta` JSON)
  → `{nome, sha256, importada_em}`; a voz entra no `GET /voices` com o `sha256` da referência;
- `POST /v2/tts` (frases em `frase_NN.wav`) e `POST /v2/tts_paragraph` (`narracao.wav` e os
  tempos de cada frase): o `TTSRequest` do serviço **sem** `out_dir` (com ele → 422);
- `GET /v2/lotes/{lote}/{arquivo}` → WAV sintético válido (mono, 24 kHz, 16 bits, tom de 440 Hz,
  a duração do `segundos` do lote), que o ffprobe aceita; `DELETE /v2/lotes/{lote}` → 204 (o id
  vai para `lotes_apagados` e os arquivos somem); `DELETE /v2/voices/{nome}` → 204, ou 404 se a
  voz não existe (`vozes_apagadas`).

Nomes de voz: `[a-z0-9_]{2,40}` (o `_nome_ok` do serviço); fora disso → 422. Voz desconhecida
no `tts` → 404.

Falhas: `fora = True` (conexão recusada: `httpx.ConnectError`), `erro_5xx = True` e
`sem_memoria = N` (as próximas N chamadas que usam a GPU, register, design, tts e
tts_paragraph, respondem 503 "GPU sem memória livre"). `similaridade` (padrão 0.97) e
`segundos` (padrão 1.0) mudam os números dos lotes seguintes.

`requests` guarda cada pedido como `Pedido(metodo, caminho, corpo)` (JSON, ou os campos de texto
do multipart com os arquivos pelo nome); `lotes` guarda o `Lote` e os bytes de cada arquivo;
`importadas` guarda cada import (`nome`, `ref_texto`, `meta`, `sha256`, `ref` em bytes).
"""

import hashlib
import io
import json
import math
import re
import struct
import uuid
import wave
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, NamedTuple

import httpx
import pytest

from fakes import _multipart
from sociman_api.geracao.shoptts import ShopTtsClient

BASE = "http://shop-tts:8200"
TAXA = 24000
_NOME_VOZ = re.compile(r"^[a-z0-9_]{2,40}$")
_NOME_ARQ = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
COMPRIMIDOS = (".ogg", ".opus", ".m4a", ".mp3")


class Pedido(NamedTuple):
    metodo: str
    caminho: str
    corpo: Any


def wav_sintetico(segundos: float = 1.0, frequencia: float = 440.0, taxa: int = TAXA) -> bytes:
    """WAV PCM mono 16 bits de um tom (o `wave` da stdlib; o ffprobe lê sem reclamar)."""
    n = max(1, int(segundos * taxa))
    quadros = b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * frequencia * i
                                                               / taxa)))
                       for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(quadros)
    return buf.getvalue()


def _wav_mono_24k(dados: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(dados), "rb") as w:
            return w.getnchannels() == 1 and w.getframerate() == TAXA and w.getnframes() > 0
    except (wave.Error, EOFError):
        return False


@dataclass
class LoteFake:
    id: str
    corpo: dict[str, Any]
    arquivos: dict[str, bytes] = field(default_factory=dict)


class ShopTtsFake:
    def __init__(self) -> None:
        self.requests: list[Pedido] = []
        self.vozes: dict[str, dict[str, Any]] = {}
        for nome, texto in (("animada", "Oi, gente! Olha só o que eu achei hoje."),
                            ("calma", "Hoje eu quero te mostrar uma coisa com calma."),
                            ("explicativa", "Vou te explicar como funciona, passo a passo.")):
            ref = wav_sintetico(1.0)
            self.vozes[nome] = {"file": f"/vozes/ref_{nome}.wav", "text": texto,
                                "sha256": hashlib.sha256(ref).hexdigest()}
        self.lotes: dict[str, LoteFake] = {}
        self.lotes_apagados: list[str] = []
        self.vozes_apagadas: list[str] = []
        self.importadas: list[dict[str, Any]] = []
        self.loaded = False
        self.unloads = 0
        self.vram_free_mb: int | None = 12000
        self.similaridade = 0.97
        self.segundos = 1.0
        self.fora = False
        self.erro_5xx = False
        self.sem_memoria = 0
        self.transport = httpx.MockTransport(self._handle)

    # ---- para os testes ----

    def cliente(self) -> ShopTtsClient:
        return ShopTtsClient(BASE, transport=self.transport)

    def pedidos(self) -> list[tuple[str, str]]:
        return [(p.metodo, p.caminho) for p in self.requests]

    def ultimo_lote(self) -> LoteFake:
        return list(self.lotes.values())[-1]

    # ---- servidor ----

    @staticmethod
    def _json(status: int, data: Any) -> httpx.Response:
        return httpx.Response(status, json=data)

    @classmethod
    def _422(cls, msg: str) -> httpx.Response:
        return cls._json(422, {"detail": msg})

    def _registrar(self, request: httpx.Request) -> dict[str, _multipart.Parte]:
        partes = _multipart.ler(request)
        corpo: Any = None
        if partes:
            corpo = {n: (p.arquivo if p.arquivo is not None else p.texto)
                     for n, p in partes.items()}
        elif request.content:
            try:
                corpo = json.loads(request.content)
            except ValueError:
                corpo = request.content
        self.requests.append(Pedido(request.method, request.url.path, corpo))
        return partes

    def _handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        partes = self._registrar(request)
        if self.fora:
            raise httpx.ConnectError("conexão recusada", request=request)
        if self.erro_5xx:
            return self._json(500, {"detail": "Internal Server Error"})
        metodo, path = request.method, request.url.path
        gpu = {"/v2/voices/register", "/v2/voices/design", "/v2/tts", "/v2/tts_paragraph"}
        if metodo == "POST" and path in gpu and self.sem_memoria > 0:
            self.sem_memoria -= 1
            return self._json(503, {"detail": "GPU sem memória livre"})
        if metodo == "GET" and path == "/health":
            return self._json(200, {"status": "ok", "loaded": self.loaded,
                                    "voices": list(self.vozes),
                                    "vram_free_mb": self.vram_free_mb})
        if metodo == "GET" and path == "/voices":
            return self._json(200, self.vozes)
        if metodo == "POST" and path == "/unload":
            self.loaded = False
            self.unloads += 1
            return self._json(200, {"unloaded": True})
        if metodo == "POST" and path == "/v2/voices/register":
            return self._register(partes)
        if metodo == "POST" and path == "/v2/voices/design":
            return self._design(json.loads(request.content or b"{}"))
        if metodo == "POST" and path == "/v2/voices/import":
            return self._import(partes)
        if metodo == "POST" and path in ("/v2/tts", "/v2/tts_paragraph"):
            return self._tts(json.loads(request.content or b"{}"),
                             paragrafo=path.endswith("paragraph"))
        partes_path = path.strip("/").split("/")
        if partes_path[:2] == ["v2", "lotes"] and len(partes_path) == 4 and metodo == "GET":
            return self._baixar(partes_path[2], partes_path[3])
        if partes_path[:2] == ["v2", "lotes"] and len(partes_path) == 3 and metodo == "DELETE":
            return self._apagar_lote(partes_path[2])
        if partes_path[:2] == ["v2", "voices"] and len(partes_path) == 3 and metodo == "DELETE":
            return self._apagar_voz(partes_path[2])
        return self._json(404, {"detail": "Not Found"})

    # -- lotes --

    def _novo_lote(self, corpo: dict[str, Any], arquivos: dict[str, bytes]) -> httpx.Response:
        self.loaded = True
        lote = LoteFake(id=uuid.uuid4().hex, corpo=corpo, arquivos=arquivos)
        corpo["lote_id"] = lote.id
        self.lotes[lote.id] = lote
        return self._json(200, corpo)

    def _candidatos(self, n: int, transcricao: str) -> tuple[list[dict[str, Any]],
                                                              dict[str, bytes]]:
        cands, arquivos = [], {}
        for k in range(1, n + 1):
            inicio = round(0.5 + 9.0 * (k - 1), 2)
            cands.append({"n": k, "arquivo": f"candidato_{k}.wav", "teste": f"teste_{k}.wav",
                          "segundos": self.segundos,
                          "similaridade": round(self.similaridade - 0.01 * (k - 1), 3),
                          "transcricao": transcricao,
                          "janela": {"inicio_s": inicio, "fim_s": round(inicio + 8.5, 2)}})
            arquivos[f"candidato_{k}.wav"] = wav_sintetico(self.segundos, 220.0 + 20 * k)
            arquivos[f"teste_{k}.wav"] = wav_sintetico(self.segundos, 330.0 + 20 * k)
        return cands, arquivos

    @staticmethod
    def _n(valor: Any) -> int | None:
        try:
            n = int(valor)
        except (TypeError, ValueError):
            return None
        return n if 1 <= n <= 3 else None

    def _register(self, partes: dict[str, _multipart.Parte]) -> httpx.Response:
        arq = partes.get("arquivo")
        if arq is None or not arq.dados:
            return self._422("arquivo é obrigatório")
        if len(arq.dados) > 25 * 1024 * 1024:
            return self._json(413, {"detail": "arquivo acima de 25 MB"})
        nome = partes["nome"].texto if "nome" in partes else ""
        if not _NOME_VOZ.match(nome):
            return self._422("nome inválido")
        if "tom" not in partes or not partes["tom"].texto:
            return self._422("tom é obrigatório")
        n = self._n(partes["n"].texto if "n" in partes else None)
        if n is None:
            return self._422("n deve ser de 1 a 3")
        comprimido = (arq.arquivo or "").lower().endswith(COMPRIMIDOS)
        transcricao = "Oi, gente! Hoje eu vou mostrar um achadinho incrível para vocês."
        cands, arquivos = self._candidatos(n, transcricao)
        aviso = ("O áudio parece comprimido (WhatsApp); grave de novo pela interface de "
                 "áudio se der")
        avisos = [aviso] if comprimido else []
        corpo = {"analise": {"codec": "opus" if comprimido else "pcm_s16le",
                             "bitrate": 32000 if comprimido else 384000,
                             "sample_rate": 48000 if comprimido else TAXA,
                             "piso_ruido_dbfs": -58.0, "snr_db": 36.5, "clipping_pct": 0.0,
                             "duracao_s": 21.4, "avisos": avisos},
                 "transcricao": transcricao, "candidatos": cands}
        return self._novo_lote(corpo, arquivos)

    def _design(self, corpo_in: dict[str, Any]) -> httpx.Response:
        if not _NOME_VOZ.match(str(corpo_in.get("nome") or "")):
            return self._422("nome inválido")
        if not str(corpo_in.get("descricao") or "").strip():
            return self._422("descricao é obrigatória")
        n = self._n(corpo_in.get("n"))
        if n is None:
            return self._422("n deve ser de 1 a 3")
        if not isinstance(corpo_in.get("seed"), int):
            return self._422("seed é obrigatória")
        texto = corpo_in.get("texto") or "Oi! Essa é a minha voz, prazer em te conhecer."
        cands, arquivos = self._candidatos(n, texto)
        return self._novo_lote({"transcricao": texto, "candidatos": cands}, arquivos)

    def _import(self, partes: dict[str, _multipart.Parte]) -> httpx.Response:
        nome = partes["nome"].texto if "nome" in partes else ""
        if not _NOME_VOZ.match(nome):
            return self._422("nome inválido")
        ref = partes.get("ref")
        if ref is None or not _wav_mono_24k(ref.dados):
            return self._422("ref deve ser um WAV mono de 24 kHz")
        ref_texto = partes["ref_texto"].texto if "ref_texto" in partes else ""
        if not ref_texto.strip():
            return self._422("ref_texto é obrigatório")
        try:
            meta = json.loads(partes["meta"].texto) if "meta" in partes else {}
        except ValueError:
            return self._422("meta deve ser JSON")
        sha = hashlib.sha256(ref.dados).hexdigest()
        agora = datetime.now(UTC).isoformat(timespec="seconds")
        self.vozes[nome] = {"file": f"/vozes/ref_{nome}.wav", "text": ref_texto, "sha256": sha}
        self.importadas.append({"nome": nome, "ref_texto": ref_texto, "meta": meta,
                                "sha256": sha, "ref": ref.dados})
        return self._json(200, {"nome": nome, "sha256": sha, "importada_em": agora})

    def _tts(self, corpo_in: dict[str, Any], *, paragrafo: bool) -> httpx.Response:
        if "out_dir" in corpo_in:
            return self._422("out_dir não existe no v2")
        frases = corpo_in.get("sentences")
        if not isinstance(frases, list) or not frases or not all(
                isinstance(f, str) and f.strip() for f in frases):
            return self._422("sentences deve ser uma lista de textos")
        voz = corpo_in.get("voice", "animada")
        if voz not in self.vozes:
            return self._json(404, {"detail": f"voz desconhecida: {voz}"})
        seed = int(corpo_in.get("seed", 1))
        minimo = float(corpo_in.get("min_similarity", 0.95))
        ok = self.similaridade >= minimo
        if paragrafo:
            total = round(self.segundos * len(frases), 2)
            tempos = [{"index": i, "text": f, "start": round(self.segundos * (i - 1), 2),
                       "end": round(self.segundos * i, 2)} for i, f in enumerate(frases, 1)]
            corpo = {"voice": voz, "arquivo": "narracao.wav", "frases": tempos,
                     "sample_rate": TAXA, "seconds": total, "similarity": self.similaridade,
                     "seed": seed, "transcript": " ".join(frases), "ok": ok}
            return self._novo_lote(corpo, {"narracao.wav": wav_sintetico(total)})
        saida, arquivos = [], {}
        for i, f in enumerate(frases, 1):
            nome = f"frase_{i:02d}.wav"
            saida.append({"index": i, "text": f, "arquivo": nome,
                          "similarity": self.similaridade, "seconds": self.segundos,
                          "seed": seed, "transcript": f, "ok": ok})
            arquivos[nome] = wav_sintetico(self.segundos, 300.0 + 10 * i)
        corpo = {"voice": voz, "sample_rate": TAXA,
                 "total_seconds": round(self.segundos * len(frases), 2), "frases": saida}
        return self._novo_lote(corpo, arquivos)

    def _baixar(self, lote_id: str, arquivo: str) -> httpx.Response:
        if not (_NOME_ARQ.match(lote_id) and _NOME_ARQ.match(arquivo)) or ".." in (
                lote_id + arquivo):
            return self._json(400, {"detail": "caminho inválido"})
        lote = self.lotes.get(lote_id)
        if lote is None or arquivo not in lote.arquivos:
            return self._json(404, {"detail": "Not Found"})
        return httpx.Response(200, content=lote.arquivos[arquivo],
                              headers={"content-type": "audio/wav"})

    def _apagar_lote(self, lote_id: str) -> httpx.Response:
        if not _NOME_ARQ.match(lote_id) or ".." in lote_id:
            return self._json(400, {"detail": "caminho inválido"})
        self.lotes_apagados.append(lote_id)
        self.lotes.pop(lote_id, None)
        return httpx.Response(204)

    def _apagar_voz(self, nome: str) -> httpx.Response:
        if not _NOME_VOZ.match(nome):
            return self._422("nome inválido")
        if self.vozes.pop(nome, None) is None:
            return self._json(404, {"detail": "voz não existe"})
        self.vozes_apagadas.append(nome)
        return httpx.Response(204)


@pytest.fixture
def shoptts_fake() -> ShopTtsFake:
    return ShopTtsFake()
