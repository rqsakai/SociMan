"""Acompanhar, cancelar, tentar de novo e gerar outras (spec 021, T043, US3)."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import uuid

import pytest
from sqlalchemy import text

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    acao,
    asset,
    detalhe,
    montar,
    motores,
    owner,
    pedir,
    rodar_gpu,
    sem_espera,
)
from sociman_api.db import get_engine
from sociman_api.geracao import aplicadores, erros, fila


def _sql(sql: str, **p):
    with get_engine().begin() as conn:
        return conn.execute(text(sql), p)


def test_cancelar_em_cada_estado_nao_final_e_recusas(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    na_fila = pedir(client, h, b)
    assert acao(client, h, na_fila, "cancelar")["status"] == "cancelada"
    rodando = pedir(client, h, b)
    fila.claim(uuid.UUID(rodando["id"]))
    rodando = detalhe(client, h, rodando["id"])
    assert rodando["status"] == "rodando"
    assert acao(client, h, rodando, "cancelar")["status"] == "cancelada"
    revisao = pedir(client, h, b)
    rodar_gpu(motores)
    revisao = detalhe(client, h, revisao["id"])
    alvo_antes = asset(client, h, b["cenario"]["id"])["version"]
    c = acao(client, h, revisao, "cancelar")
    assert c["status"] == "cancelada" and asset(client, h, b["cenario"]["id"])["version"] == \
        alvo_antes
    # Recusas nos finais.
    for nome, codigo in (("cancelar", "geracao_finalizada"), ("tentar-de-novo", "estado_invalido"),
                         ("gerar-outras", "estado_invalido")):
        r = acao(client, h, c, nome, status=409)
        assert r["error"]["code"] == codigo
    # versão velha → version_conflict
    g = pedir(client, h, b)
    r = acao(client, h, g | {"version": 99}, "cancelar", status=409)
    assert r["error"]["code"] == "version_conflict"


def test_tentar_de_novo_so_em_falhou(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    motores.comfy.falhar_sempre = "vazia"  # nenhuma opção → internal
    g = pedir(client, h, b)
    rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "falhou" and g["erro"]["code"] == "internal"
    assert g["erro"]["message"] == "O motor não devolveu nenhuma opção"
    motores.comfy.falhar_sempre = None
    g = acao(client, h, g, "tentar-de-novo")
    assert g["status"] == "na_fila" and g["attempts"] == 0 and g["erro"] is None
    assert g["nextAttemptAt"] is None
    hist = client.get(f"/api/geracoes/{g['id']}/versoes", headers=h).json()["items"]
    assert hist[0]["details"]["erroAnterior"]["code"] == "internal"
    rodar_gpu(motores)
    assert detalhe(client, h, g["id"])["status"] == "revisao"


def test_gerar_outras_seeds_novas_e_gancho_ve_a_nova(client, owner, motores, monkeypatch):
    h = owner[1]
    b = montar(client, h)
    vistas = []

    class _Gancho(aplicadores.CenarioCena):
        def ao_mudar_estado(self, db, geracao, de, para):
            if para.value == "descartada":
                abertas = fila.abertas_do_alvo(db, geracao.alvo_tipo, geracao.alvo_id,
                                               exceto=geracao.id)
                vistas.append([str(a.id) for a in abertas])
    monkeypatch.setitem(aplicadores.APLICADORES, "cenario.cena", _Gancho())
    g = pedir(client, h, b)
    rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    seeds_antigas = {c["seed"] for c in g["candidatos"]}
    nova = acao(client, h, g, "gerar-outras", status=201)
    assert nova["status"] == "na_fila" and nova["deGeracaoId"] == g["id"]
    assert detalhe(client, h, g["id"])["status"] == "descartada"
    assert vistas == [[nova["id"]]]
    rodar_gpu(motores)
    nova = detalhe(client, h, nova["id"])
    assert nova["status"] == "revisao"
    assert not seeds_antigas & {c["seed"] for c in nova["candidatos"]}
    hist = client.get(f"/api/geracoes/{g['id']}/versoes", headers=h).json()["items"]
    assert hist[0]["details"] == {"acao": "gerar_outras", "novaGeracaoId": nova["id"]}


def test_veio_uma_de_duas(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    motores.comfy.falhar_proximo("vazia", vezes=1)
    g = pedir(client, h, b)
    rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "revisao" and g["nCandidatos"] == 1
    assert g["etapaMensagem"] == "Veio 1 de 2"


@pytest.mark.parametrize("codigo", ["sem_memoria", "servico_fora"])
def test_mensagens_por_codigo_e_espera(client, owner, motores, codigo):
    h = owner[1]
    b = montar(client, h)
    if codigo == "sem_memoria":
        motores.comfy.falhar_sempre = "oom"
    else:
        motores.comfy.erro_5xx = True
    g = pedir(client, h, b)
    rodar_gpu(motores, voltas=1)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "na_fila" and g["erro"]["code"] == codigo
    assert g["etapaMensagem"] == erros.MENSAGENS[codigo]
    assert "OutOfMemory" not in str(g)
    # Esgotadas as tentativas → falhou.
    _sql("UPDATE geracoes SET attempts = 6, next_attempt_at = NULL WHERE id = :i", i=g["id"])
    rodar_gpu(motores, voltas=1)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "falhou" and g["erro"]["code"] == codigo


def test_referencia_arquivada_antes_do_job(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b, referencias=[b["foto_image_id"]])
    foto = asset(client, h, b["foto"]["id"])
    r = client.post(f"/api/assets/{foto['id']}/archive", headers=h,
                    json={"version": foto["version"]})
    assert r.status_code == 200, r.text
    rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "falhou" and g["erro"]["code"] == "entrada_invalida"
    assert b["foto_image_id"][:8] in g["erro"]["message"]


def test_hd_sem_sentinela_no_meio_falha_sem_gravar(client, owner, motores, monkeypatch):
    from sociman_api import datadir

    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b)
    real = datadir.status
    estado = {"n": 0}

    def status_falso(*a, **kw):
        estado["n"] += 1
        s = real(*a, **kw)
        return s if estado["n"] <= 1 else datadir.DataDirStatus(False, "sem_sentinela", None,
                                                                None, s.min_free_bytes)
    monkeypatch.setattr(datadir, "status", status_falso)
    rodar_gpu(motores, voltas=1)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "falhou" and g["nCandidatos"] == 0
    assert "HD" in g["erro"]["message"]
