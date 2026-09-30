"""Cifra dos segredos da publicação: AES-256-GCM (research R4 da spec 015, princípio V).

- Chave `SOCIMAN_TOKENS_KEY` (32 bytes em base64url, no `.env` da raiz, só na `api` e no
  `agendador`). `SOCIMAN_TOKENS_KEY_ANTERIOR`, opcional, só decifra (rotação).
- Formato gravado: `nonce(12) ‖ AES-GCM(texto)`, com nonce aleatório por cifragem.
- **AAD** = `"{id}:{campo}"` (`access`, `refresh`, `upload`): um valor copiado para outra linha
  ou outro campo não decifra.
- `key_id` = os 8 primeiros hex do SHA-256 da chave, gravado por linha; quem decifra com a chave
  anterior regrava com a atual (`precisa_recifrar`).

A chave nunca aparece em `repr`, log nem mensagem de erro. Os textos decifrados só existem em
variável local dentro de `publicacao/`.
"""

import base64
import binascii
import hashlib
import os
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from sociman_api.config import get_settings

NONCE_BYTES = 12
CAMPOS = ("access", "refresh", "upload")


class CifraErro(Exception):
    """Base dos erros da cifra. A mensagem nunca leva a chave nem o texto."""


class ChaveAusente(CifraErro):
    def __init__(self) -> None:
        super().__init__("SOCIMAN_TOKENS_KEY não configurada: a publicação fica desligada")


class ChaveInvalida(CifraErro):
    def __init__(self, nome: str) -> None:
        super().__init__(f"{nome} inválida: esperado 32 bytes em base64url")


class ChaveDesconhecida(CifraErro):
    """O `key_id` da linha não é o da chave atual nem o da anterior."""

    def __init__(self, key_id: str) -> None:
        super().__init__(f"nenhuma chave configurada decifra key_id {key_id}")


class DecifraFalhou(CifraErro):
    """Tag inválida: AAD trocado, dado corrompido ou chave errada."""

    def __init__(self) -> None:
        super().__init__("não foi possível decifrar (AAD, chave ou dado não conferem)")


@dataclass(frozen=True)
class _Chave:
    key_id: str
    bruta: bytes = field(repr=False)


def key_id(bruta: bytes) -> str:
    return hashlib.sha256(bruta).hexdigest()[:8]


def aad(entidade_id: object, campo: str) -> str:
    if campo not in CAMPOS:
        raise ValueError(f"campo de cifra desconhecido: {campo}")
    return f"{entidade_id}:{campo}"


def _carregar(valor: str, nome: str) -> _Chave | None:
    valor = valor.strip()
    if not valor:
        return None
    try:
        bruta = base64.urlsafe_b64decode(valor + "=" * (-len(valor) % 4))
    except (binascii.Error, ValueError):
        raise ChaveInvalida(nome) from None
    if len(bruta) != 32:
        raise ChaveInvalida(nome)
    return _Chave(key_id(bruta), bruta)


def _atual() -> _Chave:
    chave = _carregar(get_settings().sociman_tokens_key.get_secret_value(), "SOCIMAN_TOKENS_KEY")
    if chave is None:
        raise ChaveAusente()
    return chave


def _anterior() -> _Chave | None:
    return _carregar(get_settings().sociman_tokens_key_anterior.get_secret_value(),
                     "SOCIMAN_TOKENS_KEY_ANTERIOR")


def chave_configurada() -> bool:
    """A chave atual existe e é válida (sem levantar erro)."""
    try:
        _atual()
    except CifraErro:
        return False
    return True


def key_id_atual() -> str:
    return _atual().key_id


def cifrar(texto: str, aad_: str) -> tuple[bytes, str]:
    """`(nonce ‖ cifrado, key_id)` com a chave atual."""
    chave = _atual()
    nonce = os.urandom(NONCE_BYTES)
    dados = AESGCM(chave.bruta).encrypt(nonce, texto.encode(), aad_.encode())
    return nonce + dados, chave.key_id


def decifrar(dados: bytes, aad_: str, key_id_linha: str | None = None) -> str:
    """Decifra com a chave do `key_id` da linha (atual ou anterior). Sem `key_id` (o
    `upload_url` da tentativa), tenta a atual e depois a anterior."""
    atual = _atual()
    anterior = _anterior()
    candidatas = [c for c in (atual, anterior) if c is not None]
    if key_id_linha is not None:
        candidatas = [c for c in candidatas if c.key_id == key_id_linha]
        if not candidatas:
            raise ChaveDesconhecida(key_id_linha)
    nonce, cifrado = bytes(dados[:NONCE_BYTES]), bytes(dados[NONCE_BYTES:])
    for chave in candidatas:
        try:
            return AESGCM(chave.bruta).decrypt(nonce, cifrado, aad_.encode()).decode()
        except InvalidTag:
            continue
    raise DecifraFalhou()


def precisa_recifrar(key_id_linha: str) -> bool:
    """A linha foi cifrada com outra chave (a anterior): regravar com a atual."""
    return key_id_linha != _atual().key_id
