"""O `dockerctl` (spec 021, T036; contracts/dockerctl.md): a allowlist, o token, o corpo fixo do
`update`, o 409 `nao_coube` e o 404.

O `docker/dockerctl/server.py` não faz parte do pacote da API: o teste o importa pelo caminho
(na stack efêmera, `./docker/dockerctl` é montado só leitura em `/dockerctl`; fora do container,
vale o caminho do repositório). O Docker é um `http.server` num socket Unix temporário, que
guarda o `HostConfig.Memory` e registra cada pedido.
"""

import importlib.util
import json
import shutil
import socketserver
import tempfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

GiB = 1024**3
TOKEN = "token-de-teste-dockerctl"
_AQUI = Path(__file__).resolve()
CANDIDATOS = (Path("/dockerctl/server.py"),
              *(p / "docker" / "dockerctl" / "server.py" for p in _AQUI.parents[3:4]))


def _carregar() -> ModuleType:
    caminho = next((p for p in CANDIDATOS if p.is_file()), None)
    if caminho is None:
        pytest.skip("docker/dockerctl/server.py não está visível (rode com npm run test:api)")
    spec = importlib.util.spec_from_file_location("dockerctl_server", caminho)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


srv_mod = _carregar()


class DockerFalso:
    """A API do Docker num socket Unix: inspect e update de um container só."""

    def __init__(self, caminho: str, container: str = "comfyui"):
        self.container = container
        self.memoria = 12 * GiB
        self.swap = 12 * GiB
        self.recusar_update = 0  # quantos `update` respondem 500 (o cgroup não reduziu)
        self.pedidos: list[tuple[str, str, Any]] = []
        dono = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def _json(self, status: int, dados: Any) -> None:
                corpo = json.dumps(dados).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_GET(self) -> None:
                dono.pedidos.append(("GET", self.path, None))
                if self.path == f"/v1.47/containers/{dono.container}/json":
                    self._json(200, {"Name": f"/{dono.container}",
                                     "HostConfig": {"Memory": dono.memoria,
                                                    "MemorySwap": dono.swap}})
                else:
                    self._json(404, {"message": "no such container"})

            def do_POST(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                corpo = json.loads(self.rfile.read(n)) if n else None
                dono.pedidos.append(("POST", self.path, corpo))
                if self.path != f"/v1.47/containers/{dono.container}/update":
                    self._json(404, {"message": "page not found"})
                    return
                if dono.recusar_update > 0:
                    dono.recusar_update -= 1
                    self._json(500, {"message": "Cannot update container: memory limit too low"})
                    return
                dono.memoria, dono.swap = corpo["Memory"], corpo["MemorySwap"]
                self._json(200, {"Warnings": []})

        self.servidor = socketserver.ThreadingUnixStreamServer(caminho, H)
        self.servidor.daemon_threads = True
        threading.Thread(target=self.servidor.serve_forever, kwargs={"poll_interval": 0.05},
                         daemon=True).start()

    def parar(self) -> None:
        self.servidor.shutdown()
        self.servidor.server_close()


def _env(sock: str, **extra: str) -> dict[str, str]:
    return {"DOCKERCTL_TOKEN": TOKEN, "DOCKERCTL_SOCKET": sock, **extra}


@pytest.fixture
def ambiente() -> Iterator[tuple[DockerFalso, httpx.Client, list[str]]]:
    pasta = tempfile.mkdtemp(prefix="dctl")  # caminho curto: socket Unix tem limite de 108
    sock = f"{pasta}/docker.sock"
    docker = DockerFalso(sock)
    cfg = srv_mod.carregar_config(_env(sock))
    srv = srv_mod.criar_servidor(cfg, ("127.0.0.1", 0))
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                     daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    logs: list[str] = []
    original = srv_mod._log
    srv_mod._log = lambda *a: (logs.append(" ".join(map(str, a))), original(*a))
    with httpx.Client(base_url=base, timeout=5) as http:
        try:
            yield docker, http, logs
        finally:
            srv_mod._log = original
            srv.shutdown()
            srv.server_close()
            docker.parar()
            shutil.rmtree(pasta, ignore_errors=True)


AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_ler_subir_e_devolver_com_corpo_fixo(ambiente) -> None:
    docker, http, _ = ambiente
    r = http.get("/comfyui/memoria", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"memoria_bytes": 12 * GiB, "memoria_swap_bytes": 12 * GiB,
                        "estado": "normal"}

    # o corpo do pedido é ignorado: nem container nem valor vêm de fora
    r = http.post("/comfyui/memoria/subir", headers=AUTH,
                  json={"Memory": 1, "container": "outro", "Privileged": True})
    assert r.status_code == 200
    assert r.json()["estado"] == "job"
    assert r.json()["memoria_bytes"] == 28 * GiB

    r = http.post("/comfyui/memoria/devolver", headers=AUTH, content=b"lixo")
    assert r.json() == {"memoria_bytes": 12 * GiB, "memoria_swap_bytes": 12 * GiB,
                        "estado": "normal"}

    updates = [(p, c) for m, p, c in docker.pedidos if m == "POST"]
    assert updates == [("/v1.47/containers/comfyui/update",
                        {"Memory": 28 * GiB, "MemorySwap": 28 * GiB}),
                       ("/v1.47/containers/comfyui/update",
                        {"Memory": 12 * GiB, "MemorySwap": 12 * GiB})]
    # do Docker, só inspect e update deste container
    assert {(m, p) for m, p, _ in docker.pedidos} == {
        ("GET", "/v1.47/containers/comfyui/json"),
        ("POST", "/v1.47/containers/comfyui/update")}


def test_estado_outro(ambiente) -> None:
    docker, http, _ = ambiente
    docker.memoria = 16 * GiB
    assert http.get("/comfyui/memoria", headers=AUTH).json()["estado"] == "outro"


@pytest.mark.parametrize("cab", [None, "Bearer errado", f"Bearer {TOKEN}x", TOKEN,
                                 f"bearer {TOKEN}", f"Bearer  {TOKEN}"])
def test_token_errado_401_sem_tocar_no_docker(ambiente, cab) -> None:
    docker, http, logs = ambiente
    headers = {"Authorization": cab} if cab else {}
    for metodo, caminho in (("GET", "/comfyui/memoria"), ("POST", "/comfyui/memoria/subir"),
                            ("POST", "/comfyui/memoria/devolver")):
        r = http.request(metodo, caminho, headers=headers)
        assert r.status_code == 401
    assert docker.pedidos == []
    assert docker.memoria == 12 * GiB
    assert all(TOKEN not in linha for linha in logs)


@pytest.mark.parametrize("metodo,caminho", [
    ("POST", "/comfyui/memoria"),
    ("GET", "/comfyui/memoria/subir"),
    ("PUT", "/comfyui/memoria/subir"),
    ("DELETE", "/comfyui/memoria"),
    ("PATCH", "/comfyui/memoria/devolver"),
    ("OPTIONS", "/comfyui/memoria"),
    ("GET", "/"),
    ("GET", "/comfyui/memoria/"),
    ("GET", "/comfyui/memoria?container=outro"),
    ("POST", "/containers/comfyui/update"),
    ("POST", "/v1.47/containers/create"),
    ("GET", "/comfyui/../containers/json"),
])
def test_fora_da_allowlist_404_com_log(ambiente, metodo, caminho) -> None:
    docker, http, logs = ambiente
    r = http.request(metodo, caminho, headers=AUTH)
    assert r.status_code == 404
    assert docker.pedidos == []
    assert logs and "404" in logs[-1]


def test_devolver_recusado_pelo_docker_409_nao_coube(ambiente) -> None:
    docker, http, logs = ambiente
    http.post("/comfyui/memoria/subir", headers=AUTH)
    docker.recusar_update = 1
    r = http.post("/comfyui/memoria/devolver", headers=AUTH)
    assert r.status_code == 409
    assert r.json() == {"erro": "nao_coube"}
    assert docker.memoria == 28 * GiB
    assert "nao_coube" in logs[-1]
    # na 2ª tentativa coube
    assert http.post("/comfyui/memoria/devolver", headers=AUTH).json()["estado"] == "normal"


def test_log_por_acao_sem_token(ambiente, capsys) -> None:
    _, http, _ = ambiente
    http.post("/comfyui/memoria/subir", headers=AUTH)
    saida = capsys.readouterr().out
    linha = next(x for x in saida.splitlines() if "acao=subir" in x)
    assert f"antes={12 * GiB}" in linha and f"depois={28 * GiB}" in linha
    assert "resultado=ok" in linha
    assert TOKEN not in saida


def test_docker_fora_502(ambiente) -> None:
    docker, http, _ = ambiente
    docker.parar()
    r = http.get("/comfyui/memoria", headers=AUTH)
    assert r.status_code == 502
    assert r.json() == {"erro": "docker_fora"}


def test_config_do_ambiente() -> None:
    cfg = srv_mod.carregar_config({"DOCKERCTL_TOKEN": TOKEN})
    assert (cfg.container, cfg.api, cfg.mem_job, cfg.mem_normal) == (
        "comfyui", "v1.47", 30064771072, 12884901888)
    assert cfg.socket_path == "/var/run/docker.sock"
    assert TOKEN not in repr(cfg)
    cfg = srv_mod.carregar_config({"DOCKERCTL_TOKEN": TOKEN, "DOCKERCTL_CONTAINER": "c2",
                                   "DOCKERCTL_DOCKER_API": "v1.45",
                                   "DOCKERCTL_MEM_JOB": "1024m", "DOCKERCTL_MEM_NORMAL": "512m"})
    assert (cfg.container, cfg.api, cfg.mem_job, cfg.mem_normal) == ("c2", "v1.45", GiB,
                                                                     GiB // 2)


@pytest.mark.parametrize("env", [
    {}, {"DOCKERCTL_TOKEN": ""}, {"DOCKERCTL_TOKEN": "   "},
    {"DOCKERCTL_TOKEN": TOKEN, "DOCKERCTL_MEM_JOB": "muito"},
    {"DOCKERCTL_TOKEN": TOKEN, "DOCKERCTL_CONTAINER": "../x"},
    {"DOCKERCTL_TOKEN": TOKEN, "DOCKERCTL_DOCKER_API": "1.47/../../"},
])
def test_sem_token_ou_config_invalida_nao_sobe(env) -> None:
    with pytest.raises(SystemExit) as exc:
        srv_mod.carregar_config(env)
    assert exc.value.code and TOKEN not in str(exc.value.code)


def test_memoria_bytes() -> None:
    assert srv_mod.memoria_bytes("28g") == 30064771072
    assert srv_mod.memoria_bytes("12G") == 12884901888
    assert srv_mod.memoria_bytes("100") == 100
    for ruim in ("", "0", "-1g", "1t", "1.5g"):
        with pytest.raises(ValueError):
            srv_mod.memoria_bytes(ruim)
