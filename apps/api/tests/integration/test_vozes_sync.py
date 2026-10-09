"""Sincronização das vozes com o shop-tts (spec 025, T027, R12, R22): importa com o `tts_id` e o
`sha256` conferido; com o shop-tts fora, "pendente" e nova tentativa depois da espera; a
referência nova reimporta; a revogada sai do shop-tts (idempotente); e a limpeza de 90 dias não
toca a gravação nem a referência."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import hashlib

from sqlalchemy import text

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import perfil, ver_voz
from integration.test_vozes import _aprovada
from sociman_api.auth.deps import CLI
from sociman_api.db import get_engine, get_sessionmaker
from sociman_api.geracao import limpeza
from sociman_api.geracao.vozes_sync import Sync


def _volta(sync: Sync, motores, agora: float = 0.0) -> int:
    db = get_sessionmaker()()
    try:
        return sync.volta(db, motores.tts.cliente(), agora=agora)
    finally:
        db.close()


def test_importa_confere_e_reimporta(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    v, _ = _aprovada(client, h, motores, pid)
    sync = Sync()
    assert _volta(sync, motores) == 1
    v2 = ver_voz(client, h, v["id"])
    assert v2["sincronizacao"] == "ok" and v2["sincronizadaEm"] is not None
    imp = motores.tts.importadas[-1]
    assert imp["nome"] == v["ttsId"] and imp["ref_texto"] == v["refTexto"]
    assert imp["meta"]["sociman_voz_id"] == v["id"]
    assert imp["sha256"] == hashlib.sha256(imp["ref"]).hexdigest()
    assert _volta(sync, motores) == 0  # nada mais a fazer


def test_shoptts_fora_fica_pendente_e_tenta_depois(client, owner, motores):
    h = owner[1]
    v, _ = _aprovada(client, h, motores, perfil(client, h))
    motores.tts.fora = True
    sync = Sync()
    assert _volta(sync, motores, agora=0) == 0
    assert ver_voz(client, h, v["id"])["sincronizacao"] == "pendente"
    motores.tts.fora = False
    assert _volta(sync, motores, agora=1) == 0  # ainda na espera (30 s)
    assert _volta(sync, motores, agora=31) == 1
    assert ver_voz(client, h, v["id"])["sincronizacao"] == "ok"


def test_revogada_sai_do_shoptts(client, owner, motores):
    h = owner[1]
    v, _ = _aprovada(client, h, motores, perfil(client, h))
    sync = Sync()
    _volta(sync, motores)
    v = ver_voz(client, h, v["id"])
    r = client.post(f"/api/vozes/{v['id']}/consentimento/revogar", headers=h,
                    json={"version": v["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    assert r.json()["voz"]["sincronizacao"] == "removendo"
    assert _volta(sync, motores) == 1
    assert v["ttsId"] in motores.tts.vozes_apagadas
    assert ver_voz(client, h, v["id"])["sincronizadaEm"] is None
    assert _volta(sync, motores) == 0  # idempotente


def test_limpeza_nao_toca_gravacao_nem_referencia(client, owner, motores, db):
    h = owner[1]
    v, _ = _aprovada(client, h, motores, perfil(client, h))
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE geracoes SET finished_at = now() - interval '91 days' "
                          "WHERE finished_at IS NOT NULL"))
    limpeza.limpar(db, CLI)
    db.expire_all()
    v = ver_voz(client, h, v["id"])
    assert v["referencia"] is not None and v["gravacao"] is not None
