"""Raízes da agência e varredura segura (research R1 e R2).

As duas raízes (`AGENCIA_SHARED_DIR`, `AGENCIA_CLIPES_DIR`) são montagens só leitura no container.
A varredura usa `os.walk(followlinks=False)`: um link simbólico só vale se o destino continuar
dentro da raiz; pasta-link nunca é seguida. Passou de `ENTRADAS_MAX`, a leitura inteira é recusada
(413). Este módulo só abre arquivos para leitura; o conteúdo de um arquivo fora do mapeamento
nunca é aberto (quem decide é `mapa.classificar`, antes de ler).
"""

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sociman_api.config import get_settings
from sociman_api.errors import ApiError

Raiz = Literal["shared", "clipes"]
RAIZES: tuple[Raiz, ...] = ("shared", "clipes")

ENTRADAS_MAX = 2000
MD_MAX = 2 * 1024 * 1024
IMG_MAX = 20 * 1024 * 1024  # o mesmo da biblioteca (007)
BLOCO = 1024 * 1024

INDISPONIVEL = "A pasta da agência não está disponível"
GRANDE = f"A pasta da agência tem mais de {ENTRADAS_MAX} arquivos; nada foi lido"


@dataclass(frozen=True)
class Arquivo:
    raiz: Raiz
    rel: str  # caminho relativo à raiz, com "/"
    path: Path
    bytes: int

    @property
    def id(self) -> str:
        """`shared:perfis/x/perfil.md` (o `arquivo` dos itens)."""
        return f"{self.raiz}:{self.rel}"


@dataclass
class Varredura:
    arquivos: list[Arquivo] = field(default_factory=list)
    links_fora: list[str] = field(default_factory=list)  # ids dos links para fora da raiz


def raiz_path(raiz: Raiz) -> Path:
    s = get_settings()
    return Path(s.agencia_shared_dir if raiz == "shared" else s.agencia_clipes_dir)


def disponivel(raiz: Raiz) -> tuple[bool, str | None]:
    """(disponível, motivo). `shared` vazia também é indisponível (montagem errada)."""
    root = raiz_path(raiz)
    try:
        if not root.is_dir():
            return False, "pasta não encontrada"
        if raiz == "shared" and not any(root.iterdir()):
            return False, "pasta vazia"
    except OSError:
        return False, "pasta sem permissão de leitura"
    return True, None


def exigir(raiz: Raiz) -> Path:
    ok, motivo = disponivel(raiz)
    if not ok:
        raise ApiError(503, "agencia_pasta_indisponivel", f"{INDISPONIVEL} ({raiz}: {motivo})",
                       details={"raiz": raiz, "motivo": motivo})
    return raiz_path(raiz)


def varrer(raiz: Raiz) -> Varredura:
    """Todos os arquivos da raiz (sem abrir nenhum). 503 sem a pasta; 413 acima do limite."""
    root = exigir(raiz)
    real_root = root.resolve()
    out = Varredura()
    entradas = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        base = Path(dirpath)
        for nome in sorted(filenames) + [d for d in dirnames if (base / d).is_symlink()]:
            entradas += 1
            if entradas > ENTRADAS_MAX:
                raise ApiError(413, "agencia_pasta_grande", GRANDE,
                               details={"raiz": raiz, "limite": ENTRADAS_MAX})
            p = base / nome
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                try:
                    destino = p.resolve(strict=True)
                except (OSError, RuntimeError):
                    out.links_fora.append(f"{raiz}:{rel}")
                    continue
                if not destino.is_relative_to(real_root) or not destino.is_file():
                    out.links_fora.append(f"{raiz}:{rel}")
                    continue
            try:
                tamanho = p.stat().st_size
            except OSError:
                continue
            out.arquivos.append(Arquivo(raiz, rel, p, tamanho))
    return out


def ler_bytes(arq: Arquivo, limite: int) -> bytes | None:
    """O conteúdo inteiro, ou None se passar do limite (o item vira "fora")."""
    if arq.bytes > limite:
        return None
    with arq.path.open("rb") as f:
        data = f.read(limite + 1)
    return None if len(data) > limite else data


def sha256_arquivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while bloco := f.read(BLOCO):
            h.update(bloco)
    return h.hexdigest()


_CACHE_SHA: dict[tuple[str, int, int], str] = {}


def sha256_cache(path: Path) -> str:
    """Para o estado da tela (FR-028): reusa o hash enquanto tamanho e mtime não mudam."""
    st = path.stat()
    chave = (str(path), st.st_size, st.st_mtime_ns)
    if chave not in _CACHE_SHA:
        _CACHE_SHA[chave] = sha256_arquivo(path)
    return _CACHE_SHA[chave]
