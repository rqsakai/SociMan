"""Fila das gerações (spec 021, T018, R2): ordem de pedido, um job de GPU por vez (índice),
`requeue_stale`, os fins "é meu" e o gancho `ao_mudar_estado` em toda transição."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    acao,
    detalhe,
    montar,
    owner,
    pedir,
)
from sociman_api.db import get_engine
from sociman_api.geracao import aplicadores, fila
from sociman_api.geracao.models import GeracaoMotor, GeracaoStatus

GPU = {GeracaoMotor.comfyui, GeracaoMotor.tts}


def _sql(sql: str, **p):
    with get_engine().begin() as conn:
        return conn.execute(text(sql), p)


def test_ordem_de_pedido_e_um_de_gpu_por_vez(client, owner):
    h = owner[1]
    b = montar(client, h)
    ids = [pedir(client, h, b)["id"] for _ in range(3)]
    primeira = fila.proxima(GPU)
    assert str(primeira.id) == ids[0]
    job = fila.claim(primeira.id)
    assert job.attempts == 1
    # A 2ª, com a 1ª rodando, não é pega (o índice único recusa).
    assert fila.claim(uuid.UUID(ids[1])) is None
    with pytest.raises(IntegrityError):
        _sql("UPDATE geracoes SET status = 'rodando' WHERE id = :i", i=ids[1])
    assert fila.para_revisao(job)
    assert str(fila.proxima(GPU).id) == ids[1]


def _abandonar(gid) -> None:
    _sql("UPDATE geracoes SET heartbeat_at = now() - interval '5 minutes' WHERE id = :i", i=gid)


def test_requeue_stale_devolve_sem_gastar_e_na_terceira_falha(client, owner):
    h = owner[1]
    b = montar(client, h)
    gid = uuid.UUID(pedir(client, h, b)["id"])
    for vez in (1, 2, 3):
        job = fila.claim(gid)
        assert job is not None and job.attempts == 1  # a interrupção não gastou a tentativa
        _abandonar(gid)
        assert fila.requeue_stale() == 1
        assert _sql("SELECT interrupcoes FROM geracoes WHERE id = :i", i=gid).scalar() == vez
    g = detalhe(client, h, str(gid))
    assert g["status"] == "falhou" and g["erro"]["code"] == "internal"
    assert "3 vezes" in g["erro"]["message"]
    g = acao(client, h, g, "tentar-de-novo")
    assert _sql("SELECT interrupcoes FROM geracoes WHERE id = :i", i=gid).scalar() == 0


def test_duas_esperas_por_memoria_e_uma_interrupcao_nao_falham(client, owner):
    """FR-018 × FR-023: as esperas por memória e as interrupções têm orçamentos separados."""
    h = owner[1]
    b = montar(client, h)
    gid = uuid.UUID(pedir(client, h, b)["id"])
    for _ in range(2):
        job = fila.claim(gid)
        fila.para_espera(job, "sem_memoria", "x", timedelta(seconds=0))
    job = fila.claim(gid)
    assert job.attempts == 3
    _abandonar(gid)
    fila.requeue_stale()
    g = detalhe(client, h, str(gid))
    assert g["status"] == "na_fila" and g["attempts"] == 2
    # Ainda há orçamento: a próxima espera por memória é a 3ª, não a última.
    job = fila.claim(gid)
    assert job.attempts == 3
    fila.para_espera(job, "sem_memoria", "x", timedelta(seconds=0))
    assert detalhe(client, h, str(gid))["status"] == "na_fila"


def test_fim_e_meu_nao_sobrescreve_cancelada(client, owner):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b)
    job = fila.claim(uuid.UUID(g["id"]))
    g = detalhe(client, h, g["id"])
    assert acao(client, h, g, "cancelar")["status"] == "cancelada"
    assert not fila.heartbeat(job, 50)
    assert not fila.para_revisao(job)
    assert not fila.para_falhou(job, "internal", "x")
    assert not fila.para_espera(job, "sem_memoria", "x", timedelta(seconds=30))
    assert detalhe(client, h, g["id"])["status"] == "cancelada"


class _Espiao(aplicadores.CenarioCena):
    def __init__(self, falhar_em: GeracaoStatus | None = None):
        self.vistos: list[tuple[str | None, str]] = []
        self.falhar_em = falhar_em

    def ao_mudar_estado(self, db, geracao, de, para):
        if para == self.falhar_em:
            raise RuntimeError("gancho recusou")
        self.vistos.append((de.value if de else None, para.value))


def test_gancho_em_cada_transicao_e_excecao_desfaz(client, owner, monkeypatch):
    h = owner[1]
    b = montar(client, h)
    espiao = _Espiao()
    monkeypatch.setitem(aplicadores.APLICADORES, "cenario.cena", espiao)
    g = pedir(client, h, b)
    job = fila.claim(uuid.UUID(g["id"]))
    fila.para_espera(job, "sem_memoria", "x", timedelta(seconds=0))
    job = fila.claim(uuid.UUID(g["id"]))
    fila.para_falhou(job, "internal", "x")
    g = detalhe(client, h, g["id"])
    g = acao(client, h, g, "tentar-de-novo")
    acao(client, h, g, "cancelar")
    assert espiao.vistos == [(None, "na_fila"), ("na_fila", "rodando"), ("rodando", "na_fila"),
                             ("na_fila", "rodando"), ("rodando", "falhou"),
                             ("falhou", "na_fila"), ("na_fila", "cancelada")]
    # Uma exceção no gancho desfaz a transição inteira.
    monkeypatch.setitem(aplicadores.APLICADORES, "cenario.cena",
                        _Espiao(falhar_em=GeracaoStatus.rodando))
    g2 = pedir(client, h, b)
    with pytest.raises(RuntimeError):
        fila.claim(uuid.UUID(g2["id"]))
    assert detalhe(client, h, g2["id"])["status"] == "na_fila"
    assert detalhe(client, h, g2["id"])["attempts"] == 0


def test_abertas_do_alvo(client, owner):
    h = owner[1]
    b = montar(client, h)
    a1 = pedir(client, h, b)
    a2 = pedir(client, h, b)
    acao(client, h, detalhe(client, h, a2["id"]), "cancelar")
    from sociman_api.db import get_sessionmaker
    from sociman_api.geracao.models import GeracaoAlvo

    with get_sessionmaker()() as db:
        abertas = fila.abertas_do_alvo(db, GeracaoAlvo.asset, uuid.UUID(b["cenario"]["id"]))
        assert [str(g.id) for g in abertas] == [a1["id"]]
        assert fila.abertas_do_alvo(db, GeracaoAlvo.asset, uuid.UUID(b["cenario"]["id"]),
                                    exceto=uuid.UUID(a1["id"])) == []
