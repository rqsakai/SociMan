"""Servidor falso da rede (HTTP local em thread) para o teste de fluxo com navegador.

Serve páginas HTML **sintéticas** que carregam JSON pelos fragmentos de `INTERCEPTAR` de teste
(`/api-sintetica/...`), imagens PNG de 1 px, uma página de captcha, uma de login (com
redirecionamento), uma "layout mudou" (JSON sem campos) e uma que responde 429. Nunca páginas
reais salvas, nunca a rede real.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tests.fakes import (
    PNG_1PX,
    json_affiliate,
    json_avaliacoes,
    json_produto,
    json_ranking,
)

_PRODUTO = re.compile(r"^/product/(\d{6,})$")
_API_PRODUTO = re.compile(r"^/api-sintetica/product/(\d{6,})$")
_API_AFFILIATE = re.compile(r"^/api-sintetica/affiliate/(\d{6,})$")
_API_REVIEWS = re.compile(r"^/api-sintetica/reviews/(\d{6,})$")
_VAZIO = re.compile(r"^/vazio/(\d+)$")
_API_VAZIO = re.compile(r"^/api-sintetica/vazio/(\d+)$")
_IMG = re.compile(r"^/img/([A-Za-z0-9_.-]+)\.png$")


def _html(titulo: str, corpo: str, scripts: list[str]) -> bytes:
    js = "\n".join(f"fetch('{u}').then(r => r.json()).then(j => window.__j = j);" for u in scripts)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{titulo}</title><meta property="og:title" content="{titulo}"></head>
<body><h1>{titulo}</h1>{corpo}<script>{js}</script></body></html>""".encode()


class _Handler(BaseHTTPRequestHandler):
    servidor: ServidorSintetico

    def log_message(self, fmt: str, *args: Any) -> None:  # silencioso
        pass

    def _responder(
        self, status: int, corpo: bytes, tipo: str, extra: dict[str, str] | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self) -> None:  # noqa: N802 - nome do http.server
        caminho = self.path.split("?")[0]
        self.servidor.acessos.append(caminho)
        base = self.servidor.base
        if m := _PRODUTO.match(caminho):
            pid = m.group(1)
            if pid in self.servidor.redireciona_login:
                self._responder(302, b"", "text/html", {"Location": "/login?next=" + caminho})
                return
            imgs = "".join(
                f'<img src="{base}/img/{n}-{pid}.png">' for n in ("main", "main2", "sku")
            )
            self._responder(
                200,
                _html(
                    f"Shorts {pid}",
                    imgs,
                    [f"/api-sintetica/product/{pid}", f"/api-sintetica/affiliate/{pid}"],
                ),
                "text/html",
            )
        elif m := _API_PRODUTO.match(caminho):
            self._responder(
                200, json.dumps(self._produto(m.group(1), base)).encode(), "application/json"
            )
        elif m := _API_AFFILIATE.match(caminho):
            self._responder(
                200, json.dumps(json_affiliate(m.group(1))).encode(), "application/json"
            )
        elif caminho == "/ranking/cat45":
            imgs = "".join(f'<img src="{base}/img/rank-{i}.png">' for i in range(3))
            self._responder(
                200, _html("Ranking Feminino", imgs, ["/api-sintetica/ranking/cat45"]), "text/html"
            )
        elif caminho == "/api-sintetica/ranking/cat45":
            j = json_ranking(3)
            for i, it in enumerate(j["data"]["items"]):
                it["product"]["image"] = {"url": f"{base}/img/rank-{i}.png"}
                it["product"]["product_url"] = f"{base}/product/72910{i:02d}"
            self._responder(200, json.dumps(j).encode(), "application/json")
        elif m := re.match(r"^/product/(\d{6,})/reviews$", caminho):
            pid = m.group(1)
            self._responder(
                200,
                _html(
                    "Avaliações",
                    f'<img src="{base}/img/av1.png">',
                    [f"/api-sintetica/reviews/{pid}"],
                ),
                "text/html",
            )
        elif m := _API_REVIEWS.match(caminho):
            j = json_avaliacoes(m.group(1))
            j["data"]["reviews"][0]["images"] = [{"url": f"{base}/img/av1.png"}]
            self._responder(200, json.dumps(j).encode(), "application/json")
        elif m := _IMG.match(caminho):
            self._responder(200, PNG_1PX + m.group(1).encode(), "image/png")
        elif caminho.startswith("/verify/"):
            self._responder(
                200, _html("Verificação de segurança", "<p>captcha</p>", []), "text/html"
            )
        elif caminho == "/captcha-produto":
            self._responder(302, b"", "text/html", {"Location": "/verify/abc"})
        elif caminho == "/login":
            self._responder(
                200, _html("Entrar", "<form><button>Entrar</button></form>", []), "text/html"
            )
        elif m := _VAZIO.match(caminho):
            self._responder(
                200,
                _html(
                    f"Página {m.group(1)}", "<p>nada</p>", [f"/api-sintetica/vazio/{m.group(1)}"]
                ),
                "text/html",
            )
        elif _API_VAZIO.match(caminho):
            self._responder(
                200, json.dumps({"data": {"layout": "novo"}}).encode(), "application/json"
            )
        elif caminho.startswith("/erro429/"):
            self._responder(429, _html("Too many requests", "", []), "text/html")
        else:
            self._responder(404, _html("Nao encontrado", "", []), "text/html")

    @staticmethod
    def _produto(pid: str, base: str) -> dict[str, Any]:
        j = json_produto(pid)
        p = j["data"]["product"]
        p["images"] = [
            {"url_list": [f"{base}/img/main-{pid}.png"]},
            {"url_list": [f"{base}/img/main2-{pid}.png"]},
        ]
        p["skus"][0]["image"] = {"url_list": [f"{base}/img/sku-{pid}.png"]}
        return j


class ServidorSintetico:
    def __init__(self) -> None:
        handler = type("HandlerLigado", (_Handler,), {"servidor": self})
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self.acessos: list[str] = []
        self.redireciona_login: set[str] = set()

    @property
    def porta(self) -> int:
        return self._httpd.server_address[1]

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.porta}"

    def __enter__(self) -> ServidorSintetico:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
