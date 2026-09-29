"""Guarda do princípio I da constitution: nenhum agente publica em rede social.

As próximas specs só ampliam as listas abaixo; nunca as reduzem.
O princípio II (direito primeiro) ganha teste próprio na spec 008.
"""

import re
import tomllib
from pathlib import Path

from sociman_api.main import app

PUBLISH_TERMS = ("publish", "post-to", "upload-to", "share", "tiktok", "youtube", "instagram")
SOCIAL_SDKS = ("tiktok", "google-api-python-client", "instagrapi", "facebook", "tweepy")

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _norm(value: str) -> str:
    # post_to, postTo e post-to caem todos em "post-to".
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    return value.lower().replace("_", "-")


def test_nenhuma_rota_de_publicacao():
    offenders = []
    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            text = f"{_norm(path)} {_norm(op.get('operationId', ''))}"
            hits = [t for t in PUBLISH_TERMS if t in text]
            if hits:
                offenders.append(f"{method.upper()} {path}: {hits}")
    assert not offenders, f"rotas violam o princípio I: {offenders}"


def test_nenhum_sdk_de_rede_social():
    data = tomllib.loads(PYPROJECT.read_text())
    deps = list(data["project"].get("dependencies", []))
    for group in data["project"].get("optional-dependencies", {}).values():
        deps += group
    for group in data.get("dependency-groups", {}).values():
        deps += [d for d in group if isinstance(d, str)]
    offenders = [d for d in deps if any(sdk in d.lower() for sdk in SOCIAL_SDKS)]
    assert not offenders, f"dependências violam o princípio I: {offenders}"
