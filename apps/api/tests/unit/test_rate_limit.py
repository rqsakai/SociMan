import pytest

from sociman_api.auth import rate_limit
from sociman_api.errors import ApiError


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    # início de uma janela de 15 min: o teste não cruza a borda do bucket
    monkeypatch.setattr(rate_limit, "_now", lambda: 900.0 * 2_000_000 + 1)


def test_decimo_primeiro_login_da_conta_da_429(r):
    for _ in range(10):
        rate_limit.check("login", "10.0.0.1", "Dono@Casa.local", r=r)
    with pytest.raises(ApiError) as exc:
        rate_limit.check("login", "10.0.0.2", "dono@casa.local", r=r)
    assert exc.value.status == 429
    assert exc.value.code == "rate_limited"
    retry = int(exc.value.headers["Retry-After"])
    assert 0 < retry <= 15 * 60
    assert "15 minutos" in exc.value.message


def test_contas_diferentes_nao_interferem(r):
    for _ in range(10):
        rate_limit.check("login", "10.0.0.1", "a@casa.local", r=r)
    rate_limit.check("login", "10.0.0.1", "b@casa.local", r=r)


def test_limite_por_ip(r):
    for i in range(30):
        rate_limit.check("login", "10.0.0.9", f"u{i}@casa.local", r=r)
    with pytest.raises(ApiError):
        rate_limit.check("login", "10.0.0.9", "novo@casa.local", r=r)


def test_chaves_tem_ttl_da_janela(r):
    rate_limit.check("forgot", "10.0.0.1", "a@casa.local", r=r)
    keys = r.keys("rl:forgot:*")
    assert len(keys) == 2
    assert all(0 < r.ttl(k) <= 3600 for k in keys)


def test_change_so_conta_por_conta(r):
    for _ in range(10):
        rate_limit.check("change", "10.0.0.1", "user-1", r=r)
    assert r.keys("rl:change:ip:*") == []
    with pytest.raises(ApiError):
        rate_limit.check("change", "10.0.0.1", "user-1", r=r)
