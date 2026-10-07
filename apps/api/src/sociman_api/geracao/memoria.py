"""RAM do container do ComfyUI: 28 GB só durante o job `comfyui` (research R4, FR-021).

Cliente do `dockerctl` (o único container com o socket do Docker; contracts/dockerctl.md), com
lista fechada de 3 ações sem parâmetros e `Authorization: Bearer ${DOCKERCTL_TOKEN}`. O token
nunca aparece em log, erro nem `repr`. `subir` e `devolver` conferem o valor lido depois: se
não bateu, levantam `MemoriaErro` (o gerador trava a linha GPU até ler 12 GB de novo).
"""

from dataclasses import dataclass
from typing import Literal

import httpx

from sociman_api.config import get_settings

ALLOWED: tuple[tuple[str, str], ...] = (
    ("GET", "/comfyui/memoria"),
    ("POST", "/comfyui/memoria/subir"),
    ("POST", "/comfyui/memoria/devolver"),
)
TIMEOUT = httpx.Timeout(30.0, connect=5.0)

EstadoMemoria = Literal["normal", "job", "outro"]


class MemoriaErro(Exception):
    """`motivo`: `fora` (sem resposta), `token` (401), `nao_coube` (o Docker não reduziu: o uso
    atual não cabe em 12 GB) ou `nao_conferiu` (o valor lido depois não é o pedido)."""

    def __init__(self, motivo: str, detalhe: str = ""):
        super().__init__(f"{motivo}: {detalhe}" if detalhe else motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class Memoria:
    memoria_bytes: int
    memoria_swap_bytes: int
    estado: EstadoMemoria


class MemoriaClient:
    def __init__(self, base_url: str, token: str, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._http = httpx.Client(base_url=self.base_url, timeout=TIMEOUT, transport=transport)

    def __repr__(self) -> str:  # nunca mostra o token
        return f"MemoriaClient({self.base_url!r})"

    def close(self) -> None:
        self._http.close()

    def _req(self, method: str, path: str) -> Memoria:
        if (method, path) not in ALLOWED:
            raise ValueError(f"dockerctl: {method} {path} fora da lista fechada")
        try:
            resp = self._http.request(method, path,
                                      headers={"Authorization": f"Bearer {self._token}"})
        except httpx.HTTPError as exc:
            raise MemoriaErro("fora", repr(exc)) from exc
        if resp.status_code == 401:
            raise MemoriaErro("token", "o dockerctl recusou o token")
        if resp.status_code == 409:
            raise MemoriaErro("nao_coube", resp.text[:200])
        if resp.status_code >= 400:
            raise MemoriaErro("fora", f"{resp.status_code}")
        try:
            j = resp.json()
            estado = j["estado"]
            if estado not in ("normal", "job", "outro"):
                raise ValueError(estado)
            return Memoria(int(j["memoria_bytes"]), int(j["memoria_swap_bytes"]), estado)
        except (ValueError, KeyError, TypeError) as exc:  # 200 com corpo fora do contrato
            raise MemoriaErro("fora", f"resposta inválida do dockerctl: {exc!r}") from exc

    def ler(self) -> Memoria:
        return self._req("GET", "/comfyui/memoria")

    def subir(self) -> Memoria:
        m = self._req("POST", "/comfyui/memoria/subir")
        if m.estado != "job":
            raise MemoriaErro("nao_conferiu", f"depois de subir: {m.estado}")
        return m

    def devolver(self) -> Memoria:
        m = self._req("POST", "/comfyui/memoria/devolver")
        if m.estado != "normal":
            raise MemoriaErro("nao_conferiu", f"depois de devolver: {m.estado}")
        return m


def configurado() -> bool:
    return bool(get_settings().dockerctl_token.get_secret_value())


def get_memoria_client(transport: httpx.BaseTransport | None = None) -> MemoriaClient | None:
    """None sem `DOCKERCTL_TOKEN`: o gerador não roda jobs `comfyui` (R4)."""
    s = get_settings()
    token = s.dockerctl_token.get_secret_value()
    if not token:
        return None
    return MemoriaClient(s.dockerctl_url, token, transport=transport)
