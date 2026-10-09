"""HD de dados (spec 004, R5; constitution 2.1.0, armazenamento).

Tudo o que é pesado fica em `SOCIMAN_DATA_DIR`, no HD. Antes de gravar (no MinIO ou em `work/`),
confere o sentinela `.sociman-volume`: sem ele, o HD pode estar desmontado e a pasta seria criada
no NVMe. Confere também o piso de espaço livre (`DATA_MIN_FREE_GB`). Este módulo nunca cria
`SOCIMAN_DATA_DIR` nem pastas acima dele.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sociman_api.config import get_settings
from sociman_api.errors import ApiError

SENTINEL = ".sociman-volume"
GB = 1024**3

Reason = Literal["ok", "sem_sentinela", "pouco_espaco"]


@dataclass(frozen=True)
class DataDirStatus:
    available: bool
    reason: Reason
    free_bytes: int | None
    total_bytes: int | None
    min_free_bytes: int


def _min_free_bytes(min_free_gb: float | None = None) -> int:
    gb = get_settings().data_min_free_gb if min_free_gb is None else min_free_gb
    return int(gb * GB)


def status(min_free_gb: float | None = None) -> DataDirStatus:
    root = Path(get_settings().data_dir)
    floor = _min_free_bytes(min_free_gb)
    if not (root / SENTINEL).is_file():
        return DataDirStatus(False, "sem_sentinela", None, None, floor)
    st = os.statvfs(root)
    free, total = st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize
    reason: Reason = "ok" if free >= floor else "pouco_espaco"
    return DataDirStatus(reason == "ok", reason, free, total, floor)


def ensure_writable(n_bytes: int = 0, min_free_gb: float | None = None) -> None:
    """Levanta 503 sem o sentinela e 507 se, depois de gravar `n_bytes`, sobrar menos que o piso."""
    s = status(min_free_gb)
    if s.reason == "sem_sentinela":
        raise ApiError(503, "storage_unavailable", "O HD de dados não está disponível")
    if s.free_bytes is None or s.free_bytes - n_bytes < s.min_free_bytes:
        raise ApiError(507, "storage_full", "Pouco espaço no HD de dados")


def pin_tempdir() -> None:
    """Fixa o `TMPDIR` (spool de upload no HD) sem o recuo do `tempfile` para `/tmp`.

    O `tempfile` troca um `TMPDIR` inexistente por `/tmp` em silêncio e guarda a escolha; com o
    HD fora na subida da API, os uploads iriam para o NVMe. Fixado, o spool falha em vez disso.
    """
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        tempfile.tempdir = tmpdir
