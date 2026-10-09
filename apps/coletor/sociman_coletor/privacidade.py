"""Poda de dados pessoais de terceiros no bruto, antes de enviar (FR-021, FR-029).

A lista fechada `CHAVES_PESSOAIS` segue `contracts/coletor.md` ("Privacidade") e é, de propósito,
pelo menos tão ampla quanto a do servidor (`coleta/privacidade.py`), para que nada que passe aqui
seja recusado lá como `bruto_pessoal`. Em qualquer profundidade, a chave vira `"[podado]"`; URLs
com `?` perdem a query; `uid` só é podado dentro de avaliação ou comentário.

Exceções (os únicos dados de terceiros que saem do coletor): o @ público do criador
(`unique_id`/`handle`/`autorHandle`, FR-011) e o `autorRef` da avaliação (o id cru, que o servidor
transforma em hash com o pepper e descarta). Os dois são lidos pelo parser **antes** da poda, nos
`campos`; no bruto, `user` e `author` saem inteiros, como no servidor.
"""

from __future__ import annotations

import re
from typing import Any

CHAVES_PESSOAIS: frozenset[str] = frozenset(
    {
        # do contrato
        "nickname",
        "nick_name",
        "user_name",
        "username",
        "display_name",
        "name",
        "avatar",
        "avatar_url",
        "avatar_thumb",
        "profile",
        "bio",
        "signature",
        "email",
        "phone",
        "mobile",
        "address",
        "sec_uid",
        "user",
        "author",
        # variantes camelCase e as do servidor
        "nickName",
        "userName",
        "displayName",
        "avatarUrl",
        "avatarThumb",
        "avatar_larger",
        "avatar_medium",
        "secUid",
        "telefone",
        "endereco",
        "cookie",
        "cookies",
        "token",
        "sessionid",
        "session_id",
    }
)
# `uid` é pessoal quando está dentro de uma avaliação ou de um comentário.
CHAVES_CONTEXTUAIS: frozenset[str] = frozenset({"uid"})
CONTEXTOS_PESSOAIS = re.compile(r"review|comment|avalia|coment", re.IGNORECASE)
EXCECOES: frozenset[str] = frozenset(
    {
        "unique_id",
        "uniqueId",
        "handle",
        "autorHandle",
        "autor_handle",
        "autorRef",
        "autor_ref",
    }
)
PODADO = "[podado]"
_QUERY = re.compile(r"\?.*$", re.DOTALL)
_URL = ("http://", "https://")


def url_sem_query(valor: str) -> str:
    return _QUERY.sub("", valor)


def _e_pessoal(chave: str, caminho: str) -> bool:
    if chave in EXCECOES:
        return False
    if chave in CHAVES_PESSOAIS:
        return True
    return chave in CHAVES_CONTEXTUAIS and bool(CONTEXTOS_PESSOAIS.search(caminho))


def podar(valor: Any, _caminho: str = "") -> Any:
    """Devolve um novo objeto com as chaves pessoais trocadas por `[podado]` e as URLs sem
    query. O original não muda."""
    if isinstance(valor, dict):
        saida: dict[str, Any] = {}
        for k, v in valor.items():
            chave = str(k)
            caminho = f"{_caminho}.{chave}" if _caminho else chave
            saida[k] = PODADO if _e_pessoal(chave, caminho) else podar(v, caminho)
        return saida
    if isinstance(valor, list):
        return [podar(v, f"{_caminho}[{i}]") for i, v in enumerate(valor)]
    if isinstance(valor, tuple):
        return [podar(v, f"{_caminho}[{i}]") for i, v in enumerate(valor)]
    if isinstance(valor, str) and valor.startswith(_URL) and "?" in valor:
        return url_sem_query(valor)
    return valor


def verificar(valor: Any, _caminho: str = "") -> str | None:
    """O caminho da primeira chave pessoal que ainda tem valor (não `[podado]`), ou None."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            chave = str(k)
            caminho = f"{_caminho}.{chave}" if _caminho else chave
            if _e_pessoal(chave, caminho) and v != PODADO:
                return caminho
            achado = verificar(v, caminho)
            if achado:
                return achado
    elif isinstance(valor, list | tuple):
        for i, v in enumerate(valor):
            achado = verificar(v, f"{_caminho}[{i}]")
            if achado:
                return achado
    return None


# O `detalhe` de um evento aceita só estas chaves (o servidor recusa as da poda: 400).
DETALHE_PERMITIDO: frozenset[str] = frozenset(
    {
        "codigoHttp",
        "contagem",
        "urlSemParametros",
        "tipoTarefa",
        "versaoColetor",
        "chromeVersao",
        "motivo",
        "paginas",
        "imagens",
    }
)


def detalhe_evento(**campos: Any) -> dict[str, Any]:
    """Monta o `detalhe` de um evento só com chaves permitidas; URL sem parâmetros."""
    saida: dict[str, Any] = {}
    for k, v in campos.items():
        if k not in DETALHE_PERMITIDO or v is None:
            continue
        if k == "urlSemParametros" and isinstance(v, str):
            v = url_sem_query(v)
        saida[k] = v
    return saida
