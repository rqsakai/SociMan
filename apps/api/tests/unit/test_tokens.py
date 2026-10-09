import threading

import pytest

from sociman_api.auth import tokens
from sociman_api.config import Settings


@pytest.fixture
def settings():
    return Settings(jwt_secret="s" * 40, refresh_grace=60, refresh_ttl=7 * 24 * 3600)


@pytest.fixture
def clock(monkeypatch):
    now = {"ms": tokens._now_ms()}
    monkeypatch.setattr(tokens, "_now_ms", lambda: now["ms"])
    return now


def test_create_family_e_access(r, settings):
    access, refresh, fam = tokens.create_family("user-1", r=r, settings=settings)
    assert refresh.startswith(f"{fam}.")
    assert r.hget(f"rt:{fam}", "tokenHash") != refresh  # só o hash é guardado
    assert fam in r.smembers("uf:user-1")
    claims = tokens.decode_access(access, settings=settings)
    assert claims["sub"] == "user-1"
    assert claims["fam"] == fam
    assert claims["iss"] == "sociman-auth"
    assert claims["aud"] == "sociman"
    assert tokens.family_alive(fam, r=r)
    assert tokens.remaining_ttl(fam, r=r) > 7 * 24 * 3600 - 5


def test_decode_access_recusa_lixo_e_outro_segredo(settings):
    assert tokens.decode_access("lixo", settings=settings) is None
    other = Settings(jwt_secret="o" * 40)
    access = tokens.sign_access("user-1", "fam-1", other)
    assert tokens.decode_access(access, settings=settings) is None


def test_decode_access_expirado_so_com_allow_expired(settings):
    old = Settings(jwt_secret=settings.jwt_secret, access_ttl=-120)
    access = tokens.sign_access("user-1", "fam-1", old)
    assert tokens.decode_access(access, settings=settings) is None
    claims = tokens.decode_access(access, allow_expired=True, settings=settings)
    assert claims["fam"] == "fam-1"


def test_rotacao_gira_o_token(r, settings):
    _, refresh, fam = tokens.create_family("user-1", r=r, settings=settings)
    res = tokens.rotate(refresh, r=r, settings=settings)
    assert res.ok
    assert res.user_id == "user-1"
    assert res.fam == fam
    assert res.refresh != refresh
    assert tokens.decode_access(res.access, settings=settings)["fam"] == fam
    res2 = tokens.rotate(res.refresh, r=r, settings=settings)
    assert res2.ok


def test_token_invalido(r, settings):
    assert tokens.rotate("semponto", r=r, settings=settings).reason == "invalid"
    assert tokens.rotate("fam-inexistente.abc", r=r, settings=settings).reason == "invalid"


def test_anterior_na_carencia_passa_sem_estender(r, settings, clock):
    _, t0, fam = tokens.create_family("user-1", r=r, settings=settings)
    t1 = tokens.rotate(t0, r=r, settings=settings)
    assert t1.ok
    before = r.hgetall(f"rt:{fam}")
    clock["ms"] += 30_000
    again = tokens.rotate(t0, r=r, settings=settings)
    assert again.ok
    assert again.concurrent
    assert r.hgetall(f"rt:{fam}") == before  # nem rotação nova, nem carência estendida
    assert tokens.family_alive(fam, r=r)


def test_concorrente_recebe_o_mesmo_token_atual(r, settings):
    # Cookie do navegador inteiro: as duas abas precisam acabar com o MESMO token, senão o último
    # Set-Cookie a chegar pode ser um token já fora da família (reuso na renovação seguinte).
    _, t0, fam = tokens.create_family("user-1", r=r, settings=settings)
    a = tokens.rotate(t0, r=r, settings=settings)
    b = tokens.rotate(t0, r=r, settings=settings)
    assert a.ok and b.ok
    assert not a.concurrent and b.concurrent
    assert b.refresh == a.refresh
    assert b.access != "" and tokens.decode_access(b.access, settings=settings)["fam"] == fam
    # o token devolvido às duas segue a família normalmente
    assert tokens.rotate(a.refresh, r=r, settings=settings).ok
    assert tokens.family_alive(fam, r=r)


def test_selo_nao_abre_sem_o_token_anterior(r, settings):
    _, t0, fam = tokens.create_family("user-1", r=r, settings=settings)
    t1 = tokens.rotate(t0, r=r, settings=settings)
    sealed = r.hget(f"rt:{fam}", "nextSealed")
    assert sealed and t1.refresh not in sealed
    assert tokens._unseal(sealed, t0, fam) == t1.refresh
    assert tokens._unseal(sealed, t1.refresh, fam) is None
    assert tokens._unseal(sealed, t0, "outra-fam") is None


def test_anterior_fora_da_carencia_e_reuso(r, settings, clock):
    _, t0, fam = tokens.create_family("user-1", r=r, settings=settings)
    assert tokens.rotate(t0, r=r, settings=settings).ok
    clock["ms"] += 61_000
    res = tokens.rotate(t0, r=r, settings=settings)
    assert not res.ok
    assert res.reason == "reused"
    assert not tokens.family_alive(fam, r=r)
    assert fam not in r.smembers("uf:user-1")


def test_token_de_duas_geracoes_atras_e_reuso(r, settings):
    _, t0, fam = tokens.create_family("user-1", r=r, settings=settings)
    t1 = tokens.rotate(t0, r=r, settings=settings)
    assert tokens.rotate(t1.refresh, r=r, settings=settings).ok
    assert tokens.rotate(t0, r=r, settings=settings).reason == "reused"
    assert not tokens.family_alive(fam, r=r)


def test_rotacoes_concorrentes_nao_derrubam_a_familia(r, settings):
    _, t0, fam = tokens.create_family("user-1", r=r, settings=settings)
    barrier = threading.Barrier(8)
    results = []

    def worker():
        barrier.wait()
        results.append(tokens.rotate(t0, r=r, settings=settings))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(res.ok for res in results), results
    assert len({res.refresh for res in results}) == 1  # uma rotação só; o resto é concorrente
    assert sum(not res.concurrent for res in results) == 1
    assert tokens.family_alive(fam, r=r)


def test_expiracao_absoluta_nao_e_estendida(r, clock):
    s = Settings(jwt_secret="s" * 40, refresh_ttl=100, refresh_grace=60)
    _, t0, fam = tokens.create_family("user-1", r=r, settings=s)
    expires = r.hget(f"rt:{fam}", "expiresAt")
    clock["ms"] += 50_000
    t1 = tokens.rotate(t0, r=r, settings=s)
    assert t1.ok
    assert t1.remaining_seconds == 50
    assert r.hget(f"rt:{fam}", "expiresAt") == expires
    assert r.pttl(f"rt:{fam}") <= 50_000
    assert tokens.remaining_ttl(fam, r=r) == 50
    clock["ms"] += 51_000
    assert tokens.rotate(t1.refresh, r=r, settings=s).reason == "invalid"
    assert not tokens.family_alive(fam, r=r)


def test_revoke_family(r, settings):
    _, refresh, fam = tokens.create_family("user-1", r=r, settings=settings)
    tokens.revoke_family(fam, r=r)
    assert not tokens.family_alive(fam, r=r)
    assert fam not in r.smembers("uf:user-1")
    assert tokens.rotate(refresh, r=r, settings=settings).reason == "invalid"
    assert tokens.remaining_ttl(fam, r=r) == 0


def test_revoke_all_for_user_com_except_fam(r, settings):
    fams = [tokens.create_family("user-1", r=r, settings=settings)[2] for _ in range(3)]
    other = tokens.create_family("user-2", r=r, settings=settings)[2]
    tokens.revoke_all_for_user("user-1", except_fam=fams[0], r=r)
    assert tokens.family_alive(fams[0], r=r)
    assert not tokens.family_alive(fams[1], r=r)
    assert not tokens.family_alive(fams[2], r=r)
    assert r.smembers("uf:user-1") == {fams[0]}
    assert tokens.family_alive(other, r=r)
    tokens.revoke_all_for_user("user-1", r=r)
    assert not tokens.family_alive(fams[0], r=r)
    assert not r.exists("uf:user-1")
