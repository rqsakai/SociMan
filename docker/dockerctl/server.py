"""dockerctl: ajusta a RAM do container do ComfyUI, e só isso (spec 021, research R4;
specs/021-geracao-local/contracts/dockerctl.md).

RISCO DE SEGURANÇA: este processo segura o `docker.sock`, que dá poder total sobre o host. Por
isso ele é mínimo e fechado:
- só a stdlib (`http.server` para ouvir, `http.client` sobre o socket Unix para falar com o
  Docker);
- 3 rotas fixas, sem parâmetro nenhum (`GET /comfyui/memoria`, `POST /comfyui/memoria/subir` e
  `POST /comfyui/memoria/devolver`); qualquer outro método ou caminho → 404, com uma linha no log;
- o corpo do pedido é lido e jogado fora: o container, a versão da API do Docker e os valores
  vêm SÓ do ambiente (`DOCKERCTL_CONTAINER`, `DOCKERCTL_DOCKER_API`, `DOCKERCTL_MEM_JOB` e
  `DOCKERCTL_MEM_NORMAL`);
- do Docker, só `GET /<api>/containers/<container>/json` e
  `POST /<api>/containers/<container>/update` com `{"Memory": X, "MemorySwap": X}`;
- `Authorization: Bearer <DOCKERCTL_TOKEN>` comparado em tempo constante (`hmac.compare_digest`);
  sem `DOCKERCTL_TOKEN` o processo sai com erro e não sobe;
- log em stdout, uma linha por ação (data, ação, antes, depois, resultado). O token nunca aparece.

Reduzir a memória com o container rodando funciona se o uso atual couber; se o Docker recusar a
redução, a resposta é 409 `nao_coube` (o gerador chama `POST /free` no ComfyUI e tenta de novo).
"""

import hmac
import http.client
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ENDERECO = ("0.0.0.0", 8080)
SOCKET_PADRAO = "/var/run/docker.sock"
CORPO_MAX = 64 * 1024  # o corpo é ignorado; acima disso, nem é lido
TIMEOUT_DOCKER_S = 20.0
ROTAS = {
    ("GET", "/comfyui/memoria"): "ler",
    ("POST", "/comfyui/memoria/subir"): "subir",
    ("POST", "/comfyui/memoria/devolver"): "devolver",
}
_MEM = re.compile(r"^\s*(\d+)\s*([bkmg]?)\s*$", re.IGNORECASE)
_UNIDADE = {"": 1, "b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
_NOME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_API = re.compile(r"^v\d+\.\d+$")


def memoria_bytes(valor: str) -> int:
    """`28g` → 30064771072 (unidades binárias, como o `docker update --memory`)."""
    m = _MEM.match(valor or "")
    if not m:
        raise ValueError(f"valor de memória inválido: {valor!r}")
    n = int(m.group(1)) * _UNIDADE[m.group(2).lower()]
    if n <= 0:
        raise ValueError(f"valor de memória inválido: {valor!r}")
    return n


@dataclass(frozen=True)
class Config:
    token: str
    container: str
    api: str
    mem_job: int
    mem_normal: int
    socket_path: str

    def __repr__(self) -> str:  # nunca mostra o token
        return (f"Config(container={self.container!r}, api={self.api!r}, "
                f"mem_job={self.mem_job}, mem_normal={self.mem_normal})")


def carregar_config(env: dict[str, str] | None = None) -> Config:
    """Lê o ambiente. Sem token (ou com valor inválido), sai com erro: o serviço não sobe."""
    env = os.environ if env is None else env
    token = env.get("DOCKERCTL_TOKEN", "")
    if not token.strip():
        raise SystemExit("dockerctl: DOCKERCTL_TOKEN vazio; o serviço não sobe")
    container = env.get("DOCKERCTL_CONTAINER", "comfyui")
    api = env.get("DOCKERCTL_DOCKER_API", "v1.47")
    if not _NOME.match(container):
        raise SystemExit("dockerctl: DOCKERCTL_CONTAINER inválido")
    if not _API.match(api):
        raise SystemExit("dockerctl: DOCKERCTL_DOCKER_API inválido (ex.: v1.47)")
    try:
        mem_job = memoria_bytes(env.get("DOCKERCTL_MEM_JOB", "28g"))
        mem_normal = memoria_bytes(env.get("DOCKERCTL_MEM_NORMAL", "12g"))
    except ValueError as exc:
        raise SystemExit(f"dockerctl: {exc}") from exc
    return Config(token=token, container=container, api=api, mem_job=mem_job,
                  mem_normal=mem_normal,
                  socket_path=env.get("DOCKERCTL_SOCKET", SOCKET_PADRAO))


# ---- Docker (socket Unix) ----

class DockerFora(Exception):
    """Sem resposta do Docker (socket ausente, recusado ou resposta ilegível)."""


class _ConexaoUnix(http.client.HTTPConnection):
    def __init__(self, caminho: str):
        super().__init__("localhost", timeout=TIMEOUT_DOCKER_S)
        self._caminho = caminho

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT_DOCKER_S)
        s.connect(self._caminho)
        self.sock = s


def _docker(cfg: Config, metodo: str, sufixo: str, corpo: dict[str, int] | None = None
            ) -> tuple[int, bytes]:
    caminho = f"/{cfg.api}/containers/{cfg.container}/{sufixo}"
    conn = _ConexaoUnix(cfg.socket_path)
    try:
        dados = json.dumps(corpo).encode() if corpo is not None else None
        cab = {"Content-Type": "application/json"} if dados is not None else {}
        conn.request(metodo, caminho, body=dados, headers=cab)
        resp = conn.getresponse()
        return resp.status, resp.read()
    except (OSError, http.client.HTTPException) as exc:
        raise DockerFora(type(exc).__name__) from exc
    finally:
        conn.close()


def ler_memoria(cfg: Config) -> tuple[int, int]:
    status, corpo = _docker(cfg, "GET", "json")
    if status != 200:
        raise DockerFora(f"inspect {status}")
    try:
        hc = json.loads(corpo)["HostConfig"]
        return int(hc.get("Memory") or 0), int(hc.get("MemorySwap") or 0)
    except (ValueError, KeyError, TypeError) as exc:
        raise DockerFora("inspect ilegível") from exc


def atualizar_memoria(cfg: Config, valor: int) -> int:
    """O status do `update` (o corpo é fixo; nada do pedido entra aqui)."""
    status, _ = _docker(cfg, "POST", "update", {"Memory": valor, "MemorySwap": valor})
    return status


def estado(cfg: Config, memoria: int) -> str:
    if memoria == cfg.mem_normal:
        return "normal"
    if memoria == cfg.mem_job:
        return "job"
    return "outro"


# ---- HTTP ----

def _log(acao: str, antes: Any, depois: Any, resultado: str) -> None:
    agora = datetime.now(UTC).isoformat(timespec="seconds")
    print(f"{agora} acao={acao} antes={antes} depois={depois} resultado={resultado}",
          flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "dockerctl"
    sys_version = ""

    @property
    def cfg(self) -> Config:
        return self.server.cfg  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        """Sem o log de acesso padrão: cada ação já tem a sua linha (e nada de cabeçalho)."""

    def _descartar_corpo(self) -> None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if 0 < n <= CORPO_MAX:
            self.rfile.read(n)
        elif n > CORPO_MAX:
            self.close_connection = True

    def _responder(self, status: int, dados: dict[str, Any]) -> None:
        corpo = json.dumps(dados).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)
        self.close_connection = True

    def _token_ok(self) -> bool:
        cab = self.headers.get("Authorization") or ""
        esperado = f"Bearer {self.cfg.token}".encode()
        return hmac.compare_digest(cab.encode("utf-8", "replace"), esperado)

    def _atender(self) -> None:
        self._descartar_corpo()
        caminho = self.path.split("?", 1)[0]
        acao = ROTAS.get((self.command, caminho))
        if acao is None or caminho != self.path:
            _log("negado", "-", "-", f"404 {self.command} {caminho[:80]!r}")
            self._responder(404, {"erro": "nao_encontrado"})
            return
        if not self._token_ok():
            _log(acao, "-", "-", "401")
            self._responder(401, {"erro": "token"})
            return
        try:
            self._acao(acao)
        except DockerFora as exc:
            _log(acao, "-", "-", f"502 docker_fora ({exc})")
            self._responder(502, {"erro": "docker_fora"})

    def _acao(self, acao: str) -> None:
        cfg = self.cfg
        antes, _ = ler_memoria(cfg)
        if acao != "ler":
            alvo = cfg.mem_job if acao == "subir" else cfg.mem_normal
            status = atualizar_memoria(cfg, alvo)
            if not 200 <= status < 300:
                depois, _ = ler_memoria(cfg)
                if acao == "devolver":
                    _log(acao, antes, depois, f"409 nao_coube (docker {status})")
                    self._responder(409, {"erro": "nao_coube"})
                else:
                    _log(acao, antes, depois, f"502 docker_recusou (docker {status})")
                    self._responder(502, {"erro": "docker_recusou"})
                return
        depois, swap = ler_memoria(cfg)
        _log(acao, antes, depois, "ok")
        self._responder(200, {"memoria_bytes": depois, "memoria_swap_bytes": swap,
                              "estado": estado(cfg, depois)})

    do_GET = do_POST = _atender

    def _nao_existe(self) -> None:
        self._descartar_corpo()
        _log("negado", "-", "-", f"404 {self.command} {self.path.split('?', 1)[0][:80]!r}")
        self._responder(404, {"erro": "nao_encontrado"})

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _nao_existe


def criar_servidor(cfg: Config, endereco: tuple[str, int] = ENDERECO) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(endereco, Handler)
    srv.cfg = cfg  # type: ignore[attr-defined]
    return srv


def main() -> None:
    cfg = carregar_config()
    srv = criar_servidor(cfg)
    print(f"dockerctl ouvindo em {ENDERECO[0]}:{ENDERECO[1]} ({cfg!r})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr, flush=True)
            sys.exit(1)
        raise
