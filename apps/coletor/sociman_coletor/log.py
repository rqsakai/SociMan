"""Logs sem dado pessoal (FR-021; contracts/coletor.md, "Privacidade e logs").

Só `tarefaId`, tipo, `redeProdutoId`, códigos, contagens, durações e URLs sem parâmetros. O
`FiltroPrivacidade` recusa qualquer linha com `scol_`, `Cookie`, `sessionid`, `@` seguido de letra
ou texto com mais de 200 caracteres: a linha some e, no lugar, sai um aviso curto com o motivo.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

TAMANHO_MAX = 200
PADROES_RECUSADOS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("token", re.compile(r"scol_")),
    ("cookie", re.compile(r"cookie", re.IGNORECASE)),
    ("sessao", re.compile(r"sessionid|session_id", re.IGNORECASE)),
    ("arroba", re.compile(r"@[A-Za-z]")),
    ("query", re.compile(r"https?://[^\s]*\?")),
)

NOME = "sociman_coletor"


def motivo_recusa(texto: str) -> str | None:
    """Por que a linha não pode sair, ou None quando pode."""
    if len(texto) > TAMANHO_MAX:
        return "tamanho"
    for nome, padrao in PADROES_RECUSADOS:
        if padrao.search(texto):
            return nome
    return None


class _SaidaPadrao(logging.StreamHandler):
    """Escreve no `sys.stderr` **corrente** (o systemd, ou a captura do pytest da vez)."""

    def __init__(self) -> None:
        super().__init__(sys.stderr)

    @property
    def stream(self):  # type: ignore[override]
        return sys.stderr

    @stream.setter
    def stream(self, _valor) -> None:
        pass


class FiltroPrivacidade(logging.Filter):
    """Deixa passar só linhas limpas. A recusada vira `linha recusada pelo filtro: <motivo>`."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            texto = record.getMessage()
        except Exception:  # noqa: BLE001 - formato quebrado também não sai
            return False
        motivo = motivo_recusa(texto)
        if motivo is None:
            return True
        record.msg = "linha recusada pelo filtro de privacidade: %s"
        record.args = (motivo,)
        return True


def url_sem_query(url: str) -> str:
    """Só esquema, host e caminho; nada de query nem fragmento."""
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))


def configurar(nivel: str = "INFO", arquivo: Path | None = None, destino=None) -> logging.Logger:
    """Logger `sociman_coletor` com o filtro em todo handler (stderr e, se houver, arquivo)."""
    logger = logging.getLogger(NOME)
    logger.setLevel(getattr(logging, nivel.upper(), logging.INFO))
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
    formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    filtro = FiltroPrivacidade()
    saida = logging.StreamHandler(destino) if destino is not None else _SaidaPadrao()
    saida.setFormatter(formato)
    saida.addFilter(filtro)
    logger.addHandler(saida)
    if arquivo is not None:
        try:
            arquivo = arquivo.expanduser()
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(arquivo, encoding="utf-8")
            fh.setFormatter(formato)
            fh.addFilter(filtro)
            logger.addHandler(fh)
        except OSError:
            logger.warning("arquivo de log indisponivel; so stderr")
    return logger


def obter(sub: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{NOME}.{sub}" if sub else NOME)
