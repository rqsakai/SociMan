"""Cliente HTTP da TikTok (research R4, R16.3 e R21 da spec 015; princípio I).

O **único** arquivo de `src/` que cita o endereço da API da TikTok (guarda R16.1: exceção por
pasta, `publicacao/tiktok/`). Lista fechada `ALLOWED`: exatamente os pedidos de R21 mais a
`LEITURA_016` (spec 016: `video/list` e `video/query`, só leitura). Cada pedido
passa por `_conferir`, que recusa o resto com `PedidoProibido`:
- os caminhos da API (OAuth, `user/info`, `creator_info`, os dois `init` e `status/fetch`);
- `PUT` das partes só para `https://` em host `*.tiktokapis.com` (ou os hosts de
  `TIKTOK_UPLOAD_HOSTS`, só em teste);
- `GET` do avatar só em `*.tiktokcdn.com`/`*.tiktokcdn-us.com`, só imagem, até 1 MB.

Segredos (princípio V): nenhum log de corpo nem de URL de upload (o `upload_url` leva o
`upload_token`); o log registra só método, caminho e status. Todo texto de erro passa por
`redact()`. O logger do `httpx` (que imprime a URL) fica em WARNING.

Erros tipados, que a trilha e as conexões traduzem:
- `ConexaoPerdida`: o refresh não vale mais (`invalid_grant`): a conta precisa reconectar;
- `ConexaoIndisponivel`: o pedido não chegou (conexão recusada) ou a TikTok respondeu 5xx;
- `SemResposta`: o pedido saiu e a resposta não veio (timeout de leitura, conexão caída no
  meio). No `init`, a TikTok **pode** ter criado algo (fase `incerta`, R8);
- `RecusaRede(codigo)`: a TikTok recusou (`error.code` da API ou `error` do OAuth).

O transporte entra por injeção (`get_tiktok_client(transport=...)`): os testes usam
`tests/fakes/tiktok_fake.py` e nunca chamam a TikTok real.
"""

import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from sociman_api.config import get_settings
from sociman_api.publicacao import executor
from sociman_api.publicacao.executor import RedeErro

log = logging.getLogger("sociman.tiktok")
# O httpx registra a URL completa (com o `upload_token`) em INFO: nunca pode chegar ao log.
logging.getLogger("httpx").setLevel(logging.WARNING)

API_URL = "https://open.tiktokapis.com"
AUTORIZAR_URL = "https://www.tiktok.com/v2/auth/authorize/"
UPLOAD_SUFIXO = ".tiktokapis.com"
CDN_SUFIXOS = (".tiktokcdn.com", ".tiktokcdn-us.com")
AVATAR_MAX_BYTES = 1024 * 1024

# Marcadores dos pedidos fora da API (a URL vem da própria TikTok).
UPLOAD = "<upload_url>"
AVATAR = "<avatar>"

R21 = frozenset({
    ("POST", "/v2/oauth/token/"),
    ("POST", "/v2/oauth/revoke/"),
    ("GET", "/v2/user/info/"),
    ("POST", "/v2/post/publish/creator_info/query/"),
    ("POST", "/v2/post/publish/inbox/video/init/"),
    ("POST", "/v2/post/publish/video/init/"),
    ("POST", "/v2/post/publish/status/fetch/"),
    ("PUT", UPLOAD),
    ("GET", AVATAR),
})
# Spec 016 (R2): leitura das métricas (a `user/info` e o `status/fetch` já estavam no R21).
LEITURA_016 = frozenset({
    ("POST", "/v2/video/list/"),
    ("POST", "/v2/video/query/"),
})
# As listas só crescem por spec.
ALLOWED = R21 | LEITURA_016
INIT_INBOX = "/v2/post/publish/inbox/video/init/"

TIMEOUT = httpx.Timeout(20.0, connect=5.0)
PARTE_TIMEOUT = httpx.Timeout(120.0, connect=5.0)

_SEGREDOS = ("access_token", "refresh_token", "code_verifier", "client_secret", "upload_token",
             "code")
_REDACT = [
    # chave=valor (query string, form) e "chave": "valor" / 'chave': 'valor' (JSON, repr)
    re.compile(rf"(\b{nome}=)[^&\s\"'<>]+") for nome in _SEGREDOS
] + [
    re.compile(rf"""((["']){nome}\2\s*:\s*(["']))[^"']*""") for nome in _SEGREDOS
]


def redact(texto: str) -> str:
    """Troca o valor de `access_token`, `refresh_token`, `code`, `code_verifier`,
    `client_secret` e `upload_token` por `***`."""
    for padrao in _REDACT:
        texto = padrao.sub(r"\1***", texto)
    return texto


# ---- erros (os tipos genéricos de `publicacao/executor.py`, com o texto já sem segredo) ----

class TikTokErro(RedeErro):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(redact(mensagem), status)


class PedidoProibido(TikTokErro, executor.PedidoProibido):
    """Pedido fora do `ALLOWED` ou para host não permitido (princípio I)."""


class ConexaoPerdida(TikTokErro, executor.ConexaoPerdida):
    """O refresh foi revogado ou venceu (`invalid_grant`): a conta precisa reconectar."""


class ConexaoIndisponivel(TikTokErro, executor.ConexaoIndisponivel):
    """O pedido não chegou à TikTok, ou ela respondeu 5xx: tentar na próxima volta."""


class SemResposta(TikTokErro, executor.SemResposta):
    """O pedido saiu e a resposta não veio: a TikTok pode ter processado."""


class RecusaRede(executor.RecusaRede):
    """A TikTok recusou. `codigo` é o `error.code` (API) ou o `error` (OAuth), cru."""

    def __init__(self, codigo: str, mensagem: str = "", status: int | None = None,
                 log_id: str | None = None):
        super().__init__(codigo, redact(mensagem), status, log_id)


# ---- cliente ----

def _hosts_extras(valor: str) -> frozenset[str]:
    return frozenset(h.strip().lower() for h in valor.split(",") if h.strip())


class TikTokCliente:
    def __init__(self, transport: httpx.BaseTransport | None = None, api_url: str = "",
                 hosts_extras: Iterable[str] = ()):
        self.api_url = (api_url or API_URL).rstrip("/")
        self.hosts_extras = frozenset(h.lower() for h in hosts_extras)
        self._http = httpx.Client(transport=transport, timeout=TIMEOUT, follow_redirects=False)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ---- conferência ----

    def _host_ok(self, url: str, sufixos: tuple[str, ...]) -> bool:
        partes = urlsplit(url)
        host = (partes.hostname or "").lower()
        if host in self.hosts_extras:  # só em teste (fake da TikTok)
            return partes.scheme in ("https", "http")
        return partes.scheme == "https" and any(host.endswith(s) for s in sufixos)

    def _conferir(self, metodo: str, alvo: str) -> None:
        if (metodo, alvo) not in ALLOWED:
            raise PedidoProibido(f"pedido fora da lista da TikTok: {metodo} {alvo}")

    # ---- execução ----

    def _enviar(self, rotulo: str, pedido: httpx.Request) -> httpx.Response:
        try:
            resp = self._http.send(pedido)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as e:
            log.warning("tiktok %s: sem conexão (%s)", rotulo, type(e).__name__)
            raise ConexaoIndisponivel(f"TikTok fora do ar ({type(e).__name__})") from None
        except httpx.TransportError as e:  # saiu e não voltou (timeout de leitura, queda)
            log.warning("tiktok %s: sem resposta (%s)", rotulo, type(e).__name__)
            raise SemResposta(f"a TikTok não respondeu ({type(e).__name__})") from None
        log.info("tiktok %s: %s", rotulo, resp.status_code)
        return resp

    def _json(self, resp: httpx.Response) -> dict[str, Any]:
        try:
            dados = resp.json()
        except ValueError:
            dados = None
        if not isinstance(dados, dict):
            if resp.status_code >= 500:
                raise ConexaoIndisponivel(f"TikTok respondeu {resp.status_code}",
                                          resp.status_code)
            raise RecusaRede("resposta_invalida", f"HTTP {resp.status_code}", resp.status_code)
        return dados

    def api(self, metodo: str, caminho: str, *, token: str | None = None,
            json: Mapping[str, Any] | None = None, data: Mapping[str, str] | None = None,
            params: Mapping[str, str] | None = None) -> dict[str, Any]:
        """Um pedido da API (`open.tiktokapis.com`). Devolve o JSON; erro vira exceção."""
        self._conferir(metodo, caminho)
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        pedido = self._http.build_request(
            metodo, f"{self.api_url}{caminho}", headers=headers, params=params,
            json=dict(json) if json is not None else None,
            data=dict(data) if data is not None else None)
        resp = self._enviar(f"{metodo} {caminho}", pedido)
        dados = self._json(resp)
        erro = dados.get("error")
        if isinstance(erro, dict):  # API: {"data": …, "error": {"code", "message", "log_id"}}
            codigo = str(erro.get("code") or "")
            if codigo and codigo != "ok":
                if resp.status_code >= 500:
                    raise ConexaoIndisponivel(f"TikTok respondeu {resp.status_code} ({codigo})",
                                              resp.status_code)
                raise RecusaRede(codigo, str(erro.get("message") or ""), resp.status_code,
                                 erro.get("log_id"))
        elif isinstance(erro, str) and erro:  # OAuth: {"error", "error_description"}
            if resp.status_code >= 500:
                raise ConexaoIndisponivel(f"TikTok respondeu {resp.status_code} ({erro})",
                                          resp.status_code)
            descricao = str(dados.get("error_description") or "")
            if erro == "invalid_grant":
                raise ConexaoPerdida(f"autorização da TikTok não vale mais: {descricao}",
                                     resp.status_code)
            raise RecusaRede(erro, descricao, resp.status_code, dados.get("log_id"))
        if resp.status_code >= 500:
            raise ConexaoIndisponivel(f"TikTok respondeu {resp.status_code}", resp.status_code)
        if resp.status_code >= 400:
            raise RecusaRede(f"http_{resp.status_code}", "", resp.status_code)
        return dados

    def put_parte(self, upload_url: str, dados: bytes, inicio: int, total: int) -> int:
        """PUT de uma parte (`bytes inicio-fim/total`). Nunca registra o `upload_url`."""
        self._conferir("PUT", UPLOAD)
        if not self._host_ok(upload_url, (UPLOAD_SUFIXO,)):
            raise PedidoProibido("PUT de parte para host fora da TikTok")
        fim = inicio + len(dados) - 1
        pedido = self._http.build_request("PUT", upload_url, content=dados, headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(len(dados)),
            "Content-Range": f"bytes {inicio}-{fim}/{total}",
        }, timeout=PARTE_TIMEOUT)
        resp = self._enviar(f"PUT parte {inicio}-{fim}/{total}", pedido)
        if resp.status_code >= 500:
            raise ConexaoIndisponivel(f"TikTok respondeu {resp.status_code} na parte",
                                      resp.status_code)
        if resp.status_code >= 400:
            raise RecusaRede(f"http_{resp.status_code}", "parte recusada", resp.status_code)
        return resp.status_code

    def get_avatar(self, url: str) -> tuple[bytes, str]:
        """Baixa o avatar da CDN da TikTok: só imagem, até 1 MB. Devolve (bytes, tipo)."""
        self._conferir("GET", AVATAR)
        if not self._host_ok(url, CDN_SUFIXOS):
            raise PedidoProibido("avatar fora da CDN da TikTok")
        pedido = self._http.build_request("GET", url)
        try:
            resp = self._http.send(pedido, stream=True)
        except httpx.TransportError as e:
            raise ConexaoIndisponivel(f"CDN da TikTok indisponível ({type(e).__name__})") \
                from None
        try:
            tipo = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if resp.status_code != 200 or not tipo.startswith("image/"):
                raise RecusaRede("avatar_invalido", f"HTTP {resp.status_code} {tipo}",
                                 resp.status_code)
            corpo = bytearray()
            for pedaco in resp.iter_bytes():
                corpo += pedaco
                if len(corpo) > AVATAR_MAX_BYTES:
                    raise RecusaRede("avatar_grande", "avatar acima de 1 MB")
            return bytes(corpo), tipo
        finally:
            resp.close()


def get_tiktok_client(transport: httpx.BaseTransport | None = None) -> TikTokCliente:
    """Fábrica (a trilha e as rotas recebem por parâmetro/dependência; os testes injetam o
    transporte do fake). `TIKTOK_API_URL` e `TIKTOK_UPLOAD_HOSTS` vazios = produção."""
    s = get_settings()
    return TikTokCliente(transport=transport, api_url=s.tiktok_api_url,
                         hosts_extras=_hosts_extras(s.tiktok_upload_hosts))
