"""Agendador (spec 006, R1, T018): advisory lock, trilhas independentes e encerramento limpo."""

import threading
import time
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import text

from sociman_api import agendador as agendador_mod
from sociman_api.agendador import LOCK_KEY, Agendador, Trilha
from sociman_api.db import get_engine


def _contador() -> tuple[list[int], Callable]:
    voltas: list[int] = []

    def rodar(_db) -> int:
        voltas.append(1)
        return 1

    return voltas, rodar


def _esperar(cond: Callable[[], bool], timeout: float = 5.0) -> bool:
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


class _Rodando:
    """Um agendador numa thread, parado e aguardado no fim do teste."""

    def __init__(self, ag: Agendador):
        self.ag = ag
        self.stop = threading.Event()
        self.thread = threading.Thread(target=ag.run, args=(self.stop,), daemon=True)
        self.thread.start()

    def parar(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), "o agendador não parou"


@pytest.fixture
def rodar() -> Iterator[Callable[[Agendador], _Rodando]]:
    ativos: list[_Rodando] = []

    def _start(ag: Agendador) -> _Rodando:
        r = _Rodando(ag)
        ativos.append(r)
        return r

    yield _start
    for r in ativos:
        r.parar()


def _ag(*trilhas: Trilha) -> Agendador:
    return Agendador(trilhas=trilhas, engine=get_engine(), espera_lock_s=0.05, vigia_s=0.05)


def _lock_livre() -> bool:
    with get_engine().connect() as conn:
        ok = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
        if ok:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
        return bool(ok)


def test_lock_impede_a_segunda_instancia(rodar):
    voltas_a, rodar_a = _contador()
    voltas_b, rodar_b = _contador()
    a = rodar(_ag(Trilha("a", 0.01, rodar_a)))
    assert _esperar(a.ag.com_lock.is_set)
    assert _esperar(lambda: len(voltas_a) > 0)

    b = rodar(_ag(Trilha("b", 0.01, rodar_b)))
    time.sleep(0.4)
    assert not b.ag.com_lock.is_set()
    assert voltas_b == [], "a segunda instância trabalhou sem o lock"

    a.parar()  # a primeira solta o lock; a segunda assume
    assert _esperar(b.ag.com_lock.is_set)
    assert _esperar(lambda: len(voltas_b) > 0)


def test_excecao_numa_trilha_nao_para_as_outras(rodar):
    def ruim(_db) -> int:
        raise RuntimeError("falha de propósito")

    voltas_boa, boa = _contador()
    r = rodar(_ag(Trilha("ruim", 0.01, ruim), Trilha("boa", 0.01, boa)))
    assert _esperar(lambda: len(voltas_boa) >= 5)
    laco_ruim = next(laco for laco in r.ag.lacos if laco.trilha.nome == "ruim")
    assert _esperar(lambda: laco_ruim.erros >= 3)
    assert laco_ruim.is_alive(), "a trilha com erro deveria continuar tentando"


def test_encerramento_limpo_solta_o_lock(rodar):
    _voltas, rodar_ok = _contador()
    r = rodar(_ag(Trilha("ok", 0.01, rodar_ok)))
    assert _esperar(r.ag.com_lock.is_set)
    assert not _lock_livre()
    r.parar()
    assert all(not laco.is_alive() for laco in r.ag.lacos)
    assert _lock_livre()


def test_trilha_ociosa_nao_roda(rodar):
    voltas, rodar_x = _contador()
    r = rodar(_ag(Trilha("x", 0.01, rodar_x, lambda: "sem chave")))
    assert _esperar(lambda: r.ag.lacos and r.ag.lacos[0].voltas >= 3)
    assert voltas == []


def test_volta_com_erro_faz_rollback(rodar, db):
    """O que a trilha escreveu antes de levantar não fica no banco."""
    db.execute(text("CREATE TABLE IF NOT EXISTS _agendador_teste (n int)"))
    db.commit()
    try:
        def escreve_e_falha(sess) -> int:
            sess.execute(text("INSERT INTO _agendador_teste VALUES (1)"))
            raise RuntimeError("depois de escrever")

        r = rodar(_ag(Trilha("w", 0.01, escreve_e_falha)))
        assert _esperar(lambda: r.ag.lacos and r.ag.lacos[0].erros >= 2)
        r.parar()
        assert db.execute(text("SELECT count(*) FROM _agendador_teste")).scalar() == 0
    finally:
        db.rollback()
        db.execute(text("DROP TABLE IF EXISTS _agendador_teste"))
        db.commit()


def test_trilhas_padrao_e_ociosidade(monkeypatch):
    nomes = [t.nome for t in agendador_mod.trilhas_padrao()]
    assert nomes == ["sync", "openshorts", "importacao", "lembretes", "publicacao",  # + 015
                     "metricas", "aprendizado", "geracao_limpeza"]  # + 016, + 023, + 021

    trilhas = {t.nome: t for t in agendador_mod.trilhas_padrao()}
    # Stack de teste sem YOUTUBE_API_KEY: a sync fica ociosa com motivo claro, sem vazar valor.
    assert "YOUTUBE_API_KEY" in (trilhas["sync"].ociosa() or "")
    assert trilhas["openshorts"].ociosa() is None
    assert trilhas["importacao"].ociosa() is None  # o HD de teste tem o sentinela

    class _SemHd:
        reason = "sem_sentinela"

    monkeypatch.setattr(agendador_mod.datadir, "status", lambda: _SemHd())
    assert "sentinela" in (trilhas["importacao"].ociosa() or "")


def test_trilha_publicacao_ociosa_na_ordem(monkeypatch):
    """Spec 015 (R6): servidor desligado, depois a chave dos tokens, depois o HD."""
    from pydantic import SecretStr

    from sociman_api.config import get_settings

    trilha = {t.nome: t for t in agendador_mod.trilhas_padrao()}["publicacao"]
    s = get_settings()
    monkeypatch.setattr(s, "publicacao_habilitada", False)
    assert "PUBLICACAO_HABILITADA" in (trilha.ociosa() or "")
    monkeypatch.setattr(s, "publicacao_habilitada", True)
    assert trilha.ociosa() is None  # a stack de teste tem a chave e o HD
    chave = s.sociman_tokens_key
    monkeypatch.setattr(s, "sociman_tokens_key", SecretStr(""))
    motivo = trilha.ociosa() or ""
    assert "SOCIMAN_TOKENS_KEY" in motivo and "=" not in motivo

    class _SemHd:
        reason = "sem_sentinela"

    monkeypatch.setattr(s, "sociman_tokens_key", chave)
    monkeypatch.setattr(agendador_mod.datadir, "status", lambda: _SemHd())
    assert "sentinela" in (trilha.ociosa() or "")


def test_trilha_metricas_ociosa_e_independente_da_publicacao(monkeypatch):
    """Spec 016 (R3, T031): ociosa com `METRICAS_COLETA_HABILITADA=false`, sem o app da TikTok
    ou sem a chave dos tokens; **ativa** com a publicação desligada e o botão desligado."""
    from pydantic import SecretStr

    from sociman_api.config import get_settings

    trilha = {t.nome: t for t in agendador_mod.trilhas_padrao()}["metricas"]
    s = get_settings()
    monkeypatch.setattr(s, "tiktok_client_key", SecretStr("chave-de-teste"))
    monkeypatch.setattr(s, "tiktok_client_secret", SecretStr("segredo-de-teste"))
    monkeypatch.setattr(s, "publicacao_habilitada", False)  # o botão já nasce desligado

    class _SemHd:
        reason = "sem_sentinela"

    monkeypatch.setattr(agendador_mod.datadir, "status", lambda: _SemHd())
    assert trilha.ociosa() is None  # só lê: não depende da publicação nem do HD

    monkeypatch.setattr(s, "metricas_coleta_habilitada", False)
    assert "METRICAS_COLETA_HABILITADA" in (trilha.ociosa() or "")
    monkeypatch.setattr(s, "metricas_coleta_habilitada", True)

    chave = s.sociman_tokens_key
    monkeypatch.setattr(s, "sociman_tokens_key", SecretStr(""))
    motivo = trilha.ociosa() or ""
    assert "SOCIMAN_TOKENS_KEY" in motivo and "=" not in motivo
    monkeypatch.setattr(s, "sociman_tokens_key", chave)

    monkeypatch.setattr(s, "tiktok_client_key", SecretStr(""))
    assert "app da TikTok" in (trilha.ociosa() or "")
