"""Credencial do coletor de mercado (spec 026, FR-024): `scol_<id>_<segredo>`, guardada só como
SHA-256. Cópia do molde `mcp/credenciais.py` com outro prefixo e outra tabela.

- `<id>`: 8 caracteres base32 minúsculos, único e salvo em claro (identifica o cliente no log);
- `<segredo>`: 32 bytes aleatórios em base64url sem padding (43 caracteres).

256 bits aleatórios dispensam hash lento: SHA-256 e `hmac.compare_digest`. O `<id>` inexistente
segue o mesmo caminho com um hash fictício, para o tempo não revelar se o cliente existe. O
`check:secrets` do repositório reconhece o formato.
"""

import base64
import hashlib
import hmac
import re
import secrets
from typing import Any, Protocol

from sqlalchemy import select

from sociman_api.coleta.models import ColetaCliente

PREFIXO = "scol_"
FORMATO = re.compile(r"^scol_([a-z2-7]{8})_([A-Za-z0-9_-]{43})$")
_HASH_FICTICIO = hashlib.sha256(b"scol-cliente-inexistente").digest()


class _Sessao(Protocol):
    def scalar(self, statement: Any) -> Any: ...


class Segredo(str):
    """O token como `str` com `repr` mascarado (nunca cai num log ou numa falha de teste)."""

    def __repr__(self) -> str:
        return "'scol_***'"


def novo_token_id() -> str:
    return base64.b32encode(secrets.token_bytes(5)).decode().lower()  # 5 bytes = 8 caracteres


def montar(token_id: str) -> Segredo:
    segredo = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    return Segredo(f"{PREFIXO}{token_id}_{segredo}")


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def gerar() -> tuple[Segredo, str, bytes]:
    """`(token, token_id, hash)`. O token só existe na resposta que o mostra ao dono."""
    token_id = novo_token_id()
    token = montar(token_id)
    return token, token_id, hash_token(token)


def e_token(token: str | None) -> bool:
    return bool(token) and token.startswith(PREFIXO)


def token_id_de(token: str) -> str | None:
    """O `<id>` de um token bem formado (sem conferir o segredo), ou None."""
    m = FORMATO.match(token)
    return m.group(1) if m else None


def conferir(token: str, esperado: bytes) -> bool:
    return hmac.compare_digest(hash_token(token), bytes(esperado))


def verificar(db: _Sessao, token: str) -> ColetaCliente | None:
    """O cliente dono do token, em tempo constante; None se o token não confere.

    Não olha situação nem vencimento (isso é do portão): só a credencial.
    """
    token_id = token_id_de(token)
    cliente = None
    if token_id is not None:
        cliente = db.scalar(select(ColetaCliente).where(ColetaCliente.token_id == token_id))
    esperado = cliente.token_hash if cliente is not None else _HASH_FICTICIO
    ok = conferir(token, esperado)
    return cliente if ok and cliente is not None else None
