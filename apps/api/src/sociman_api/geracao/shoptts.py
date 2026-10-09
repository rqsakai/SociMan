"""Cliente do shop-tts, contrato `v2` (contracts/shop-tts.md; dependência externa X2).

O serviço fica no `../comfyui-docker/tts_service/` e muda para o `v2` **antes da 025** (D3): na
021 o motor `tts` é testado só contra o fake (`tests/fakes/shoptts_fake.py`). No `v2` a entrada
chega como arquivo (multipart) e a saída sai como arquivo para baixar e apagar
(`/v2/lotes/{lote}/{arquivo}` e `DELETE /v2/lotes/{lote}`).

Lista fechada (`ALLOWED`): `/health`, `/voices`, `/unload`, os `/v2/*` do contrato e o
`DELETE /v2/voices/{nome}` da 025 (a 021 já fecha a lista com ela; quem usa é a 025). Os nomes
de lote, arquivo e voz só passam com `[A-Za-z0-9_.-]` e sem `..`.

Erros já traduzidos em `MotorErro` (R8): 503 ("GPU sem memória livre") → `sem_memoria`;
conexão, timeout e 5xx → `servico_fora`; 422 (o serviço recusou a entrada) → `entrada_invalida`;
os demais 4xx → `internal`. O nome de voz segue a regra do serviço (`[a-z0-9_]{2,40}`); apagar uma
voz que o serviço não tem mais (404) é sucesso (idempotente, shop-tts-025.md).
"""

import json
import re
from typing import Any

import httpx

from sociman_api.config import get_settings
from sociman_api.geracao.erros import MotorErro

ALLOWED: tuple[tuple[str, str], ...] = (
    ("GET", "/health"),
    ("GET", "/voices"),
    ("POST", "/unload"),
    ("POST", "/v2/voices/register"),
    ("POST", "/v2/voices/design"),
    ("POST", "/v2/voices/import"),
    ("POST", "/v2/tts"),
    ("POST", "/v2/tts_paragraph"),
    ("GET", "/v2/lotes/"),
    ("DELETE", "/v2/lotes/"),
    ("DELETE", "/v2/voices/"),  # 025 (shop-tts-025.md)
)
TIMEOUT = httpx.Timeout(600.0, connect=5.0)  # cadastrar e narrar levam minutos na GPU
_NOME = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")  # lote e arquivo
_VOZ = re.compile(r"^[a-z0-9_]{2,40}$")  # o `_nome_ok` do serviço


def _allowed(method: str, path: str) -> bool:
    for m, prefix in ALLOWED:
        if m != method:
            continue
        if prefix.endswith("/") and path.startswith(prefix) and len(path) > len(prefix):
            return True
        if path == prefix:
            return True
    return False


def _nome(valor: str) -> str:
    if not _NOME.match(valor) or ".." in valor:
        raise MotorErro("entrada_invalida", detalhe=f"nome inválido no shop-tts: {valor[:40]!r}")
    return valor


def _voz(valor: str) -> str:
    if not _VOZ.match(valor):
        raise MotorErro("entrada_invalida", detalhe=f"nome de voz inválido: {valor[:40]!r}")
    return valor


SEM_V2 = ("O shop-tts não tem o contrato v2 (as rotas /v2): atualize o serviço antes de gerar "
          "voz. Tentar de novo não resolve.")


def _rota_inexistente(resp: httpx.Response) -> bool:
    """404 do roteador (`{"detail": "Not Found"}`), não da regra do serviço (voz desconhecida)."""
    try:
        return resp.json().get("detail") == "Not Found"
    except ValueError:
        return False


class ShopTtsClient:
    """`transport` só nos testes."""

    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=TIMEOUT, transport=transport)

    def __repr__(self) -> str:
        return f"ShopTtsClient({self.base_url!r})"

    def close(self) -> None:
        self._http.close()

    def _req(self, method: str, path: str, ok_404: bool = False, **kw: Any) -> httpx.Response:
        if not _allowed(method, path):
            raise ValueError(f"shop-tts: {method} {path} fora da lista fechada")
        try:
            resp = self._http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise MotorErro("servico_fora", detalhe=f"{method} {path}: {exc!r}") from exc
        if resp.status_code == 503:
            raise MotorErro("sem_memoria", detalhe=f"{method} {path}: 503")
        if resp.status_code >= 500:
            raise MotorErro("servico_fora", detalhe=f"{method} {path}: {resp.status_code}")
        if resp.status_code == 404 and ok_404:
            return resp
        if resp.status_code == 404 and path.startswith("/v2/") and _rota_inexistente(resp):
            # O serviço não tem a rota (shop-tts antigo, sem o contrato v2): tentar de novo não
            # adianta, e a tela precisa dizer o que fazer.
            raise MotorErro("internal", mensagem=SEM_V2, detalhe=f"{method} {path}: 404 sem a rota")
        if resp.status_code == 422:
            raise MotorErro("entrada_invalida",
                            detalhe=f"{method} {path}: 422 {resp.text[:300]}")
        if resp.status_code >= 400:
            raise MotorErro("internal",
                            detalhe=f"{method} {path}: {resp.status_code} {resp.text[:300]}")
        return resp

    # ---- sem mudança ----

    def health(self) -> dict[str, Any]:
        return self._req("GET", "/health").json()

    def voices(self) -> dict[str, Any]:
        return self._req("GET", "/voices").json()

    def unload(self) -> None:
        self._req("POST", "/unload")

    # ---- v2 ----

    def register(self, arquivo: bytes, nome_arquivo: str, *, nome: str, tom: str, n: int
                 ) -> dict[str, Any]:
        return self._req("POST", "/v2/voices/register",
                         files={"arquivo": (nome_arquivo, arquivo)},
                         data={"nome": _voz(nome), "tom": tom, "n": str(n)}).json()

    def design(self, *, nome: str, descricao: str, n: int, seed: int,
               texto: str | None = None) -> dict[str, Any]:
        corpo: dict[str, Any] = {"nome": _voz(nome), "descricao": descricao, "n": n,
                                 "seed": seed}
        if texto:
            corpo["texto"] = texto
        return self._req("POST", "/v2/voices/design", json=corpo).json()

    def importar(self, *, nome: str, ref: bytes, ref_texto: str, meta: dict[str, Any]
                 ) -> dict[str, Any]:
        return self._req("POST", "/v2/voices/import",
                         files={"ref": ("ref.wav", ref, "audio/wav")},
                         data={"nome": _voz(nome), "ref_texto": ref_texto,
                               "meta": json.dumps(meta)}).json()

    def tts(self, corpo: dict[str, Any]) -> dict[str, Any]:
        return self._req("POST", "/v2/tts", json=corpo).json()

    def tts_paragraph(self, corpo: dict[str, Any]) -> dict[str, Any]:
        return self._req("POST", "/v2/tts_paragraph", json=corpo).json()

    def baixar(self, lote_id: str, arquivo: str) -> bytes:
        return self._req("GET", f"/v2/lotes/{_nome(lote_id)}/{_nome(arquivo)}").content

    def apagar_lote(self, lote_id: str) -> None:
        self._req("DELETE", f"/v2/lotes/{_nome(lote_id)}")

    def apagar_voz(self, nome: str) -> None:  # 025: 404 = já removida (idempotente)
        self._req("DELETE", f"/v2/voices/{_voz(nome)}", ok_404=True)


def get_shoptts_client(transport: httpx.BaseTransport | None = None) -> ShopTtsClient:
    return ShopTtsClient(get_settings().shop_tts_url, transport=transport)
