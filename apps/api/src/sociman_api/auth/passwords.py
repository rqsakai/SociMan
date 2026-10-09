"""Hash e política de senha (research.md R1, FR-007/FR-008)."""

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from sociman_api.config import get_settings
from sociman_api.errors import ApiError

# Parâmetros do volans e mínimo da OWASP: Argon2id, m=19 MiB, t=2, p=1.
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16)

# Senhas óbvias recusadas mesmo quando passam no tamanho mínimo. Comparação em minúsculas.
# Lista do volans (packages/contract/src/password.ts) ampliada com as mais comuns dos vazamentos;
# as curtas já caem no tamanho mínimo, mas ficam aqui caso o mínimo seja reduzido.
COMMON_PASSWORDS = frozenset({
    # volans
    "12345678", "123456789", "1234567890", "password", "password1", "password123", "senha1234",
    "12341234", "qwertyui", "qwerty123", "11111111", "00000000", "abcd1234", "iloveyou",
    "sunshine", "football", "baseball", "princess", "dragon123", "letmein1", "welcome1",
    "admin123", "mudar123", "brasil123",
    # mais comuns (vazamentos públicos, com variantes de 12+ caracteres)
    "123456", "12345", "1234567", "qwerty", "abc123", "111111", "123123", "admin", "letmein",
    "welcome", "monkey", "dragon", "master", "login", "passw0rd", "starwars", "whatever",
    "trustno1", "shadow", "superman", "michael", "jennifer", "hunter2", "batman", "charlie",
    "donald", "freedom", "qazwsx", "zaq12wsx", "1q2w3e4r", "1q2w3e4r5t", "1qaz2wsx", "654321",
    "666666", "121212", "7777777", "987654321", "112233", "aa123456", "senha", "senha123",
    "mudar@123", "brasil", "flamengo", "corinthians", "palmeiras", "saopaulo", "gremio",
    "cruzeiro", "vasco", "botafogo", "santos", "internacional", "minhasenha", "trocarsenha",
    "123456789012", "1234567890ab", "12345678910", "123456789123", "1234567891011",
    "111111111111", "000000000000", "123123123123", "121212121212", "abcdefghijkl",
    "abcdef123456", "abc123456789", "qwertyuiop12", "qwertyuiopas", "qwerty123456",
    "1q2w3e4r5t6y", "1qaz2wsx3edc", "q1w2e3r4t5y6", "zaq1zaq1zaq1", "asdfghjkl123",
    "passwordpassword", "password1234", "password12345", "password123!", "password@123",
    "senhasenha12", "senha1234567", "senha123456789", "minhasenha123", "mudar1234567",
    "trocar123456", "iloveyou1234", "welcome12345", "letmein12345", "administrator",
    "admin1234567", "admin@123456", "adminadmin12", "changeme1234", "sociman12345",
    "brasil123456", "flamengo1234", "corinthians1", "palmeiras123", "football1234",
    "baseball1234", "sunshine1234", "princess1234", "superman1234", "starwars1234",
    "dragon123456", "master123456", "monkey123456", "shadow123456", "michael12345",
})


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_policy(password: str, current: str | None = None) -> None:
    """Levanta 400 `validation_error` se a senha nova não cumpre a política.

    `current` é a senha atual em texto (troca de senha): a nova não pode ser igual.
    """
    settings = get_settings()
    if len(password) < settings.password_min_length:
        raise _invalid(f"A senha precisa ter pelo menos {settings.password_min_length} caracteres")
    if len(password) > settings.password_max_length:
        raise _invalid(f"A senha pode ter no máximo {settings.password_max_length} caracteres")
    if password.lower() in COMMON_PASSWORDS:
        raise _invalid("Essa senha é muito comum. Escolha outra")
    if current is not None and password == current:
        raise _invalid("A nova senha precisa ser diferente da atual")


def _invalid(message: str) -> ApiError:
    return ApiError(400, "validation_error", message)


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("sociman-equalize-timing")


def equalize_timing() -> None:
    """Gasta o mesmo tempo de um verify quando o e-mail não existe (sem vazar quais existem)."""
    verify_password("sociman-equalize-timing-wrong", _dummy_hash())
