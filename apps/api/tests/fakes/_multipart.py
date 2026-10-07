"""Leitura de `multipart/form-data` para os fakes (spec 021: ComfyUI e shop-tts), só com a stdlib
(`email`), sem depender do `python-multipart` do servidor."""

from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import HTTP

import httpx


@dataclass(frozen=True)
class Parte:
    nome: str
    arquivo: str | None  # o `filename` (None = campo de texto)
    tipo: str
    dados: bytes

    @property
    def texto(self) -> str:
        return self.dados.decode()


def ler(request: httpx.Request) -> dict[str, Parte]:
    """As partes do corpo por nome; vazio se não for multipart."""
    tipo = request.headers.get("content-type", "")
    if not tipo.startswith("multipart/form-data"):
        return {}
    msg = BytesParser(policy=HTTP).parsebytes(
        f"Content-Type: {tipo}\r\n\r\n".encode() + request.content)
    partes: dict[str, Parte] = {}
    for p in msg.iter_parts():
        nome = p.get_param("name", header="content-disposition")
        if not nome:
            continue
        partes[str(nome)] = Parte(str(nome), p.get_filename(), p.get_content_type(),
                                  p.get_payload(decode=True) or b"")
    return partes
