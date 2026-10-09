"""Legenda da TikTok (spec 015, T101, regra do dono de 2026-09-29): a TikTok não tem título, só
**legenda** = descrição + "\\n\\n" + hashtags (com #), até 2.200 caracteres.

Um lugar só para a regra: o snapshot do Direct Post (`post_info.title`), o `legendaFinal` do
destino (prévia e "Copiar textos") e a validação ao agendar. Fica fora de `publicacao/tiktok/`
porque a central (`postagem/`) também usa, e só `registro.py` importa aquele pacote (R16.2).
"""

from collections.abc import Sequence
from typing import Protocol

from sociman_api.errors import ApiError
from sociman_api.perfis.models import Platform

LIMITE = 2200
OBRIGATORIA = "Descreva o post: na TikTok a legenda (descrição + hashtags) é obrigatória"


class ComTextos(Protocol):
    descricao: str
    hashtags: Sequence[str]


def legenda_tiktok(destino: ComTextos) -> str:
    """descrição + "\\n\\n" + hashtags (sem título)."""
    partes = [p for p in ((destino.descricao or "").strip(),
                          " ".join(destino.hashtags or ()).strip()) if p]
    return "\n\n".join(partes)


def problema(platform: Platform, destino: ComTextos) -> ApiError | None:
    """O erro da legenda num destino TikTok (sem descrição ou longa demais), ou None."""
    if platform != Platform.tiktok:
        return None
    if not (destino.descricao or "").strip():
        return ApiError(400, "legenda_obrigatoria", OBRIGATORIA)
    tamanho = len(legenda_tiktok(destino))
    if tamanho > LIMITE:
        return ApiError(400, "legenda_longa",
                        f"A legenda (descrição + hashtags) tem {tamanho} caracteres; o máximo da "
                        f"TikTok é {LIMITE}", details={"tamanho": tamanho, "limite": LIMITE})
    return None


def exigir(platform: Platform, destino: ComTextos) -> None:
    erro = problema(platform, destino)
    if erro is not None:
        raise erro
