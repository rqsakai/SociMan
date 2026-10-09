"""Poda e conferência de dados pessoais de terceiros no bruto e nos eventos (FR-029).

A lista fechada `CHAVES_PESSOAIS` espelha a do coletor (`contracts/coletor.md`, "Privacidade"):
o coletor poda antes de enviar e o servidor repete a poda e **recusa** o item se ainda sobrar
alguma chave (`bruto_pessoal`). O @ público do criador (`uniqueId`/`handle`/`autorHandle`) e o
`autorRef` da avaliação são as únicas exceções na checagem: o `autorRef` serve só para o hash
com pepper e **não fica no bruto gravado** (`anonimizar` troca por `[hash]`, SC-006). URLs com
`?` perdem a query.
"""

import re
from typing import Any

# No **bruto** (o JSON da rede), `name`, `profile` e `address` são de pessoa: saem podados.
CHAVES_PESSOAIS = frozenset({
    "nickname", "nick_name", "nickName", "user_name", "userName", "username", "display_name",
    "displayName", "name", "avatar", "avatar_url", "avatarUrl", "avatar_thumb", "avatarThumb",
    "avatar_larger", "avatar_medium", "profile", "bio", "signature", "email", "phone",
    "telefone", "mobile", "address", "endereco", "sec_uid", "secUid", "user", "author",
    "cookie", "cookies", "token", "sessionid", "session_id",
})
# Nos **campos** normalizados (o nosso esquema, `contracts/coletor.md`), `nome` é de atributo,
# loja e categoria, nunca de pessoa: a lista é a mesma sem os nomes genéricos.
CHAVES_PESSOAIS_CAMPOS = CHAVES_PESSOAIS - {"name", "profile", "address", "endereco"}
EXCECOES = frozenset({"unique_id", "uniqueId", "handle", "autorHandle", "autor_handle",
                      "autorRef", "autor_ref"})
PODADO = "[podado]"
# Pseudônimos que o servidor consome (viram hash) e não guarda: nem no bruto, nem nos campos.
CHAVES_PSEUDONIMAS = frozenset({"autorRef", "autor_ref"})
ANONIMIZADO = "[hash]"
_QUERY = re.compile(r"\?.*$")


def podar(valor: Any, _caminho: str = "") -> Any:
    """Troca por `[podado]` toda chave da lista, em qualquer profundidade, e tira a query das
    URLs. Devolve um novo objeto (o original não muda)."""
    if isinstance(valor, dict):
        out: dict[str, Any] = {}
        for k, v in valor.items():
            if k in CHAVES_PESSOAIS and k not in EXCECOES:
                out[k] = PODADO
            else:
                out[k] = podar(v, f"{_caminho}.{k}" if _caminho else k)
        return out
    if isinstance(valor, list):
        return [podar(v, f"{_caminho}[{i}]") for i, v in enumerate(valor)]
    if isinstance(valor, str) and valor.startswith(("http://", "https://")) and "?" in valor:
        return _QUERY.sub("", valor)
    return valor


def anonimizar(valor: Any) -> Any:
    """Troca por `[hash]` toda chave pseudônima (`autorRef`), em qualquer profundidade; o resto
    fica. Roda depois da poda, antes de gravar o bruto e os campos das avaliações."""
    if isinstance(valor, dict):
        return {k: (ANONIMIZADO if k in CHAVES_PSEUDONIMAS and v not in (None, ANONIMIZADO)
                    else anonimizar(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [anonimizar(v) for v in valor]
    return valor


def chave_pessoal(valor: Any, _caminho: str = "",
                  chaves: frozenset[str] = CHAVES_PESSOAIS) -> str | None:
    """O caminho da primeira chave pessoal **com valor** (não podada), ou None. Para os
    `campos` normalizados use `chaves=CHAVES_PESSOAIS_CAMPOS`."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            caminho = f"{_caminho}.{k}" if _caminho else k
            if k in chaves and k not in EXCECOES and v != PODADO:
                return caminho
            achado = chave_pessoal(v, caminho, chaves)
            if achado:
                return achado
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            achado = chave_pessoal(v, f"{_caminho}[{i}]", chaves)
            if achado:
                return achado
    return None
