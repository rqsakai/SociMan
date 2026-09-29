"""Plataformas de mídia social: link, @ e slug (research R8 e R9).

Funções puras; quem converte `ValueError` em `ApiError(400, …)` é o service.
"""

import re
import unicodedata
from dataclasses import dataclass

from sociman_api.perfis.models import Platform

HANDLE_RE = re.compile(r"^[a-z0-9._-]{1,60}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SLUG_MAX = 60


@dataclass(frozen=True)
class PlatformInfo:
    label: str
    url_template: str | None  # "{h}" = handle; None em "outra"
    url_re: re.Pattern[str] | None  # grupo "h" = handle


def _url_re(hosts: str, prefix: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(?:https?://)?(?:(?:www|m|web|mobile)\.)?(?:{hosts})/{prefix}(?P<h>[^/?#\s]+)/?"
        r"(?:[?#].*)?$",
        re.IGNORECASE,
    )


PLATFORMS: dict[Platform, PlatformInfo] = {
    Platform.tiktok: PlatformInfo(
        "TikTok", "https://www.tiktok.com/@{h}", _url_re(r"tiktok\.com", "@")
    ),
    Platform.youtube: PlatformInfo(
        "YouTube", "https://www.youtube.com/@{h}", _url_re(r"youtube\.com", "@")
    ),
    Platform.instagram: PlatformInfo(
        "Instagram", "https://www.instagram.com/{h}", _url_re(r"instagram\.com", "@?")
    ),
    Platform.kwai: PlatformInfo("Kwai", "https://www.kwai.com/@{h}", _url_re(r"kwai\.com", "@")),
    Platform.facebook: PlatformInfo(
        "Facebook", "https://www.facebook.com/{h}", _url_re(r"facebook\.com|fb\.com", "")
    ),
    Platform.x: PlatformInfo("X", "https://x.com/{h}", _url_re(r"x\.com|twitter\.com", "@?")),
    Platform.outra: PlatformInfo("Outra", None, None),
}


def normalize_handle(raw: str) -> str:
    """`" @ Meus.Queridinhos "` → `"meus.queridinhos"`. ValueError se sobrar caractere inválido."""
    handle = re.sub(r"\s+", "", raw).lstrip("@").lower()
    if not HANDLE_RE.match(handle):
        raise ValueError("@ inválido: use só letras, números, ponto, hífen e sublinhado (até 60)")
    return handle


def handle_from_url(platform: Platform, url: str) -> str | None:
    """O @ de um link colado da plataforma, já normalizado; None se o link não bate."""
    info = PLATFORMS[platform]
    if info.url_re is None:
        return None
    match = info.url_re.match(url.strip())
    if not match:
        return None
    try:
        return normalize_handle(match["h"])
    except ValueError:
        return None


def url_for(platform: Platform, handle: str) -> str | None:
    """Link do perfil na plataforma; None em "outra" (lá o link é obrigatório e digitado)."""
    template = PLATFORMS[platform].url_template
    return template.format(h=handle) if template else None


def suggest_slug(name: str) -> str:
    """`"Achadinhos da Lú!"` → `"achadinhos-da-lu"`: sem acento, minúsculo, hífens, até 60.

    Pode sair com menos de 2 caracteres (ex.: nome só com símbolos); o service valida.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug[:SLUG_MAX].rstrip("-")
