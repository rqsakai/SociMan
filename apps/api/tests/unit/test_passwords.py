import pytest

from sociman_api.auth import passwords
from sociman_api.errors import ApiError


def test_hash_e_verify():
    h = passwords.hash_password("uma senha bem longa")
    assert h.startswith("$argon2id$")
    assert passwords.verify_password("uma senha bem longa", h)
    assert not passwords.verify_password("outra senha qualquer", h)
    assert not passwords.verify_password("uma senha bem longa", "lixo")
    assert not passwords.needs_rehash(h)


def test_politica_tamanho_minimo():
    with pytest.raises(ApiError) as exc:
        passwords.validate_password_policy("a" * 5 + "bcdefg")  # 11
    assert exc.value.status == 400
    assert exc.value.code == "validation_error"
    passwords.validate_password_policy("xk7-pq2-mv9z")  # 12


def test_politica_tamanho_maximo():
    passwords.validate_password_policy("x" * 128)
    with pytest.raises(ApiError):
        passwords.validate_password_policy("x" * 129)


@pytest.mark.parametrize("pw", ["123456789012", "PasswordPassword", "QWERTY123456"])
def test_politica_recusa_senha_comum(pw):
    with pytest.raises(ApiError) as exc:
        passwords.validate_password_policy(pw)
    assert "comum" in exc.value.message


def test_politica_recusa_igual_a_atual():
    with pytest.raises(ApiError) as exc:
        passwords.validate_password_policy("xk7-pq2-mv9z", current="xk7-pq2-mv9z")
    assert "diferente" in exc.value.message
    passwords.validate_password_policy("xk7-pq2-mv9z", current="outra-senha-velha")


def test_equalize_timing_nao_levanta():
    passwords.equalize_timing()
    passwords.equalize_timing()
