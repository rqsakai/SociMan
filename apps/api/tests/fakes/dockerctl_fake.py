"""`dockerctl` falso (spec 021, T014, research R13; contracts/dockerctl.md): um
`httpx.MockTransport` com o limite de RAM do container do ComfyUI, para o cliente de
`geracao/memoria.py`.

Uso: `from fakes.dockerctl_fake import dockerctl_fake  # noqa: F401` e `dockerctl_fake.cliente()`
(o `MemoriaClient("http://dockerctl:8080", TOKEN)` com o transporte falso). O token é fixo e de
teste (`TOKEN`); `cliente(token="outro")` testa o 401.

Estado: `memoria` (bytes; começa em `NORMAL` = 12 GiB; `JOB` = 28 GiB) e `historico` (o valor
depois de cada ação, inclusive `ler`). As 3 rotas do contrato (`GET /comfyui/memoria`,
`POST /comfyui/memoria/subir`, `POST /comfyui/memoria/devolver`); o resto → 404.

Falhas:
- `fora = True`: conexão recusada em tudo (`httpx.ConnectError`; o cliente levanta `fora`);
- `nao_volta = True`: o `devolver` responde 200, mas o valor continua o de antes (o cliente
  levanta `nao_conferiu`);
- `nao_coube = N`: os próximos N `devolver` respondem 409 `nao_coube`, sem mudar o valor;
- token errado ou ausente → 401 (o cliente levanta `token`).

`requests` guarda `Pedido(metodo, caminho, autorizado)`: nunca o token.
"""

import hmac
from typing import NamedTuple

import httpx
import pytest

from sociman_api.geracao.memoria import MemoriaClient

BASE = "http://dockerctl:8080"
TOKEN = "token-de-teste-dockerctl"  # fixo e óbvio: só existe nos testes
NORMAL = 12 * 1024**3  # 12884901888
JOB = 28 * 1024**3  # 30064771072


class Pedido(NamedTuple):
    metodo: str
    caminho: str
    autorizado: bool


class DockerctlFake:
    def __init__(self, memoria: int = NORMAL) -> None:
        self.memoria = memoria
        self.historico: list[int] = []
        self.requests: list[Pedido] = []
        self.fora = False
        self.nao_volta = False
        self.nao_coube = 0
        self.transport = httpx.MockTransport(self._handle)

    # ---- para os testes ----

    def cliente(self, token: str = TOKEN) -> MemoriaClient:
        return MemoriaClient(BASE, token, transport=self.transport)

    def pedidos(self) -> list[tuple[str, str]]:
        return [(p.metodo, p.caminho) for p in self.requests]

    def acoes(self) -> list[str]:
        """As ações autorizadas, em ordem: "ler", "subir", "devolver"."""
        nomes = {"/comfyui/memoria": "ler", "/comfyui/memoria/subir": "subir",
                 "/comfyui/memoria/devolver": "devolver"}
        return [nomes.get(p.caminho, p.caminho) for p in self.requests if p.autorizado]

    # ---- servidor ----

    def _estado(self) -> str:
        return "normal" if self.memoria == NORMAL else "job" if self.memoria == JOB else "outro"

    def _resposta(self) -> httpx.Response:
        self.historico.append(self.memoria)
        return httpx.Response(200, json={"memoria_bytes": self.memoria,
                                         "memoria_swap_bytes": self.memoria,
                                         "estado": self._estado()})

    def _handle(self, request: httpx.Request) -> httpx.Response:
        cab = request.headers.get("authorization", "")
        autorizado = hmac.compare_digest(cab.encode(), f"Bearer {TOKEN}".encode())
        self.requests.append(Pedido(request.method, request.url.path, autorizado))
        if self.fora:
            raise httpx.ConnectError("conexão recusada", request=request)
        rota = (request.method, request.url.path)
        if rota not in {("GET", "/comfyui/memoria"), ("POST", "/comfyui/memoria/subir"),
                        ("POST", "/comfyui/memoria/devolver")}:
            return httpx.Response(404, json={"erro": "nao_encontrado"})
        if not autorizado:
            return httpx.Response(401, json={"erro": "token"})
        if rota[1] == "/comfyui/memoria/subir":
            self.memoria = JOB
        elif rota[1] == "/comfyui/memoria/devolver":
            if self.nao_coube > 0:
                self.nao_coube -= 1
                self.historico.append(self.memoria)
                return httpx.Response(409, json={"erro": "nao_coube"})
            if not self.nao_volta:
                self.memoria = NORMAL
        return self._resposta()


@pytest.fixture
def dockerctl_fake() -> DockerctlFake:
    return DockerctlFake()
