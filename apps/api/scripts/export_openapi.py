"""Grava o OpenAPI do app em packages/contract/openapi.json (research.md R7).

Roda no host, sem Docker nem Postgres: só importa o `app` e chama `app.openapi()`.
Uso: uv run --directory apps/api python scripts/export_openapi.py
"""

import json
from pathlib import Path

from sociman_api.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT = REPO_ROOT / "packages" / "contract" / "openapi.json"


def main() -> None:
    spec = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False)
    OUT.write_text(spec + "\n", encoding="utf-8")
    print(f"OpenAPI gravado em {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
