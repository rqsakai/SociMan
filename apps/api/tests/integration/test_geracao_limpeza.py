"""Limpeza de 90 dias (spec 021, T057, SC-006; exceção 1 da constitution 4.3.0)."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import uuid

import pytest
from sqlalchemy import select, text

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
)
from sociman_api import storage
from sociman_api.auth.deps import CLI
from sociman_api.auth.models import SecurityEvent
from sociman_api.db import get_engine
from sociman_api.geracao import limpeza
from sociman_api.main import app


def _sql(sql: str, **p):
    with get_engine().begin() as conn:
        return conn.execute(text(sql), p)


def _envelhecer(gid: str, dias: int) -> None:
    _sql("UPDATE geracoes SET finished_at = now() - make_interval(days => :d) WHERE id = :i",
         d=dias, i=gid)


def _existe(key: str) -> bool:
    try:
        storage.stat(key)
        return True
    except Exception:  # noqa: BLE001 — NoSuchKey
        return False


def _keys(gid: str) -> dict[str, list[str]]:
    rows = _sql("SELECT c.id, i.object_key, p.object_key FROM geracao_candidatos c "
                "LEFT JOIN images i ON i.id = c.image_id "
                "LEFT JOIN images p ON p.id = c.image_par_id WHERE c.geracao_id = :g",
                g=gid).all()
    return {str(cid): [k for k in (a, b) if k] for cid, a, b in rows}


def _escolhida(client, h, motores, b) -> dict:
    g = pedir(client, h, b)
    rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    alvo = asset(client, h, b["cenario"]["id"])
    r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                    json={"candidatoId": g["candidatos"][1]["id"], "version": g["version"],
                          "alvoVersion": alvo["version"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_89_e_91_dias_em_cada_estado_final(client, owner, motores, db):
    h = owner[1]
    b = montar(client, h)
    escolhida = _escolhida(client, h, motores, b)
    antiga_revisao = pedir(client, h, b)
    rodar_gpu(motores)
    cancelada = acao(client, h, detalhe(client, h, pedir(client, h, b)["id"]), "cancelar")
    descartada = pedir(client, h, b)
    rodar_gpu(motores)
    acao(client, h, detalhe(client, h, descartada["id"]), "gerar-outras", status=201)
    rodar_gpu(motores)
    falhou = pedir(client, h, b)
    motores.comfy.falhar_proximo("vazia", vezes=1)
    rodar_gpu(motores, voltas=1)
    _sql("UPDATE geracoes SET status = 'falhou', error_code = 'internal', error_message = 'x', "
         "finished_at = now() WHERE id = :i AND status <> 'falhou'", i=falhou["id"])
    recente = _escolhida(client, h, motores, b)
    for g in (escolhida, cancelada, descartada, falhou):
        _envelhecer(g["id"], 91)
    _envelhecer(recente["id"], 89)
    _sql("UPDATE geracoes SET created_at = now() - interval '200 days' WHERE id = :i",
         i=antiga_revisao["id"])
    antes_escolhida = _keys(escolhida["id"])
    antes_descartada = _keys(descartada["id"])
    antes_recente = _keys(recente["id"])
    antes_revisao = _keys(antiga_revisao["id"])

    # --dry-run não apaga nada.
    seco = limpeza.limpar(db, CLI, dry_run=True)
    # escolhida: 1 não escolhida; cancelada na fila: 0; descartada: 2; falhou com 1 de 2: 1.
    assert seco.geracoes == 4 and seco.candidatos == 1 + 0 + 2 + 1
    assert _keys(escolhida["id"]) == antes_escolhida

    r = limpeza.limpar(db, limpeza.AGENDADOR)
    assert r.geracoes == 4 and r.candidatos == 4 and r.imagens == 4 and r.bytes > 0
    # O escolhido intacto; a não escolhida apagada (linha e objeto).
    depois = _keys(escolhida["id"])
    assert list(depois) == [escolhida["escolhidoId"]]
    assert _existe(depois[escolhida["escolhidoId"]][0])
    perdidas = [k for cid, ks in antes_escolhida.items() if cid != escolhida["escolhidoId"]
                for k in ks]
    assert perdidas and not any(_existe(k) for k in perdidas)
    assert _keys(descartada["id"]) == {} and not any(_existe(k) for ks in
                                                     antes_descartada.values() for k in ks)
    assert _keys(recente["id"]) == antes_recente
    assert _keys(antiga_revisao["id"]) == antes_revisao
    g = detalhe(client, h, escolhida["id"])
    assert g["limpaEm"] is not None and len(g["candidatos"]) == 1
    eventos = db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "eliminacao_candidatos")).all()
    assert len(eventos) == 4
    ev = next(e for e in eventos if e.details["geracaoId"] == escolhida["id"])
    assert ev.actor_kind == "system:agendador" and ev.outcome == "ok"
    assert ev.details["excecao"] == "candidatos_90d" and ev.details["candidatos"] == 1
    assert ev.occurred_at is not None
    # Idempotente.
    assert limpeza.limpar(db, limpeza.AGENDADOR).geracoes == 0


def test_arquivo_em_uso_fica_e_conta_mantidos(client, owner, motores, db):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b)
    rodar_gpu(motores)
    g = acao(client, h, detalhe(client, h, g["id"]), "cancelar")
    # A imagem da opção 1 também está num arquivo de asset (reuso fora do escolhido).
    img_id = g["candidatos"][0]["imagem"]["imageId"]
    _sql("INSERT INTO asset_files (id, asset_id, image_id, role, position) VALUES "
         "(:i, :a, :img, 'referencia', 9)", i=uuid.uuid4(), a=b["cenario"]["id"], img=img_id)
    _envelhecer(g["id"], 91)
    r = limpeza.limpar(db)
    assert r.mantidos == 1 and r.candidatos == 1
    assert list(_keys(g["id"])) == [g["candidatos"][0]["id"]]
    ev = db.scalar(select(SecurityEvent).where(SecurityEvent.type == "eliminacao_candidatos"))
    assert ev.details["mantidos"] == 1


def test_objetos_so_depois_do_commit(client, owner, motores, db, monkeypatch):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b)
    rodar_gpu(motores)
    g = acao(client, h, detalhe(client, h, g["id"]), "cancelar")
    _envelhecer(g["id"], 91)
    chamadas = []

    def apagar(key, *, bucket, excecao):
        n = _sql("SELECT count(*) FROM images WHERE object_key = :k", k=key).scalar()
        chamadas.append((key, n, excecao))
    monkeypatch.setattr(storage, "apagar_por_excecao", apagar)
    limpeza.limpar(db)
    assert len(chamadas) == 2 and all(n == 0 and e == "candidatos_90d" for _, n, e in chamadas)


def test_midia_nula_da_revogacao_e_pulada(client, owner, motores, db):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b)
    rodar_gpu(motores)
    g = acao(client, h, detalhe(client, h, g["id"]), "cancelar")
    _sql("ALTER TABLE geracao_candidatos DISABLE TRIGGER geracao_candidatos_midia")
    _sql("UPDATE geracao_candidatos SET image_id = NULL, metricas = '{}' WHERE geracao_id = :g",
         g=g["id"])
    _sql("ALTER TABLE geracao_candidatos ENABLE TRIGGER geracao_candidatos_midia")
    _envelhecer(g["id"], 91)
    r = limpeza.limpar(db)
    assert r.geracoes == 1 and r.candidatos == 0
    assert len(_keys(g["id"])) == 2


def test_nenhuma_rota_dispara_a_limpeza():
    textos = " ".join(f"{p} {op.get('operationId', '')}" for p, v in app.openapi()["paths"].items()
                      for op in v.values()).lower()
    assert "limp" not in textos and "elimin" not in textos


@pytest.mark.parametrize("dry", [True, False])
def test_cli(client, owner, motores, dry):
    from typer.testing import CliRunner

    from sociman_api.cli import app as cli

    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b)
    rodar_gpu(motores)
    acao(client, h, detalhe(client, h, g["id"]), "cancelar")
    _envelhecer(g["id"], 91)
    args = ["geracoes", "limpar"] + (["--dry-run"] if dry else [])
    res = CliRunner().invoke(cli, args)
    assert res.exit_code == 0, res.output
    assert ("seriam apagadas: 2" if dry else "apagadas: 2") in res.output
    assert len(_keys(g["id"])) == (2 if dry else 0)
