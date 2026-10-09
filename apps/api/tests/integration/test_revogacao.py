"""Revogação de consentimento (spec 025, T033, FR-033a; exceção 2 da 4.3.0): só o dono humano,
com confirmação; os arquivos e as linhas da pessoa apagados; as gerações com mídia nula e o
`escolhido_id` íntegro; os textos das chamadas e das versões antigas redigidos; o evento com as
contagens; restaurar e reverter recusados; as cenas da 010 listadas e intactas no prompt."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

from sqlalchemy import select, text

from integration.geracao_helpers import _buckets, member, motores, owner  # noqa: F401
from integration.padrao_helpers import (
    avatar,
    com_claude,
    consentimento,
    img,
    passo_e_escolha,
    perfil,
    ver,
)
from integration.test_vozes import _aprovada
from sociman_api import history, storage
from sociman_api.auth.models import SecurityEvent
from sociman_api.db import get_engine
from sociman_api.errors import ApiError
from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaChamada


def _sql(sql: str, **p):
    with get_engine().begin() as conn:
        return conn.execute(text(sql), p)


def _existe(key: str, bucket: str = "imagens") -> bool:
    try:
        storage.stat(key, bucket=bucket)
        return True
    except Exception:  # noqa: BLE001 — NoSuchKey
        return False


def _pessoa_real(client, h, motores, pid: str) -> dict:
    """Avatar de pessoa real com a foto de origem enviada, o frontal gerado e a checagem."""
    a = avatar(client, h, pid, "Ana real")
    a = consentimento(client, h, a["id"], a["version"])["asset"]
    r = client.post(f"/api/assets/{a['id']}/arquivos", headers=h,
                    data={"role": "kit", "slot": "rosto_origem", "origem": "pessoa_real"},
                    files={"file": ("ana.jpg", img(), "image/jpeg")})
    assert r.status_code == 201, r.text
    passo_e_escolha(client, h, motores, pid, a["id"], "avatar.rosto_frontal",
                    instrucao="soft smile")
    a = ver(client, h, a["id"])
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "prompt": "Adult woman, curly hair"})
    assert r.status_code == 200
    return r.json()["asset"]


def test_foto_de_pessoa_real_exige_consentimento(client, owner):
    h = owner[1]
    a = avatar(client, h, perfil(client, h))
    r = client.post(f"/api/assets/{a['id']}/arquivos", headers=h,
                    data={"role": "kit", "slot": "rosto_origem", "origem": "pessoa_real"},
                    files={"file": ("ana.jpg", img(), "image/jpeg")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "consentimento_ausente"
    out = consentimento(client, h, a["id"], a["version"])["asset"]
    assert out["origem"] == "pessoa_real" and out["consentimento"]["temProva"] is False
    hist = client.get(f"/api/assets/{a['id']}/versions", headers=h).json()["items"]
    assert hist[0]["action"] == "consentimento" and hist[0]["actor"]["id"] == str(owner[0].id)


def test_so_dono_humano_e_com_confirmacao(client, owner, member, motores, mcp_habilitado):
    from integration.mcp_helpers import bearer, criar_cliente, ligar

    h = owner[1]
    pid = perfil(client, h)
    a = _pessoa_real(client, h, motores, pid)
    url = f"/api/assets/{a['id']}/consentimento/revogar"
    r = client.post(url, headers=member[1], json={"version": a["version"], "confirmo": True})
    assert r.status_code == 403
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, escopo="propostas")
    r = client.post(url, headers=bearer(token), json={"version": a["version"], "confirmo": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.post(url, headers=h, json={"version": a["version"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "confirmacao_obrigatoria"


def test_revogar_avatar_apaga_arquivos_e_redige_o_historico(client, owner, motores, db):
    h = owner[1]
    pid = perfil(client, h)
    com_claude(motores)
    a = _pessoa_real(client, h, motores, pid)
    keys = [k for (k,) in _sql("SELECT i.object_key FROM images i JOIN asset_files f ON "
                               "f.image_id = i.id WHERE f.asset_id = :a", a=a["id"])]
    cand_keys = [k for (k,) in _sql(
        "SELECT i.object_key FROM geracao_candidatos c JOIN geracoes g ON g.id = c.geracao_id "
        "JOIN images i ON i.id = c.image_id WHERE g.alvo_id = :a", a=a["id"])]
    assert keys and cand_keys
    # Uma cena da 010 que usa o avatar, com um look enviado à mão apontado.
    r = client.post(f"/api/assets/{a['id']}/arquivos", headers=h,
                    data={"role": "referencia", "look": "Casa"},
                    files={"file": ("look.jpg", img(), "image/jpeg")})
    assert r.status_code == 201, r.text
    look = r.json()["file"]
    keys.append(_sql("SELECT object_key FROM images WHERE id = :i",
                     i=look["image"]["id"]).scalar())
    a = r.json()["asset"]
    cena = client.post(f"/api/perfis/{pid}/cenas", headers=h, json={
        "nome": "Com a Ana", "acao": "smiles", "avatarId": a["id"],
        "avatarArquivoId": look["id"]})
    assert cena.status_code == 201, cena.text
    cena = cena.json()
    previa = client.get(f"/api/assets/{a['id']}/consentimento/previa-revogacao", headers=h)
    assert previa.status_code == 200 and previa.json()["cenasAfetadas"][0]["id"] == cena["id"]

    r = client.post(f"/api/assets/{a['id']}/consentimento/revogar", headers=h,
                    json={"version": a["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["asset"]["revogado"] and out["asset"]["archived"]
    assert out["asset"]["files"] == [] and out["asset"]["prompt"] is None
    assert out["apagados"]["imagens"] >= 3
    # Os objetos saíram do MinIO (depois do commit) e as linhas do banco.
    assert not any(_existe(k) for k in keys + cand_keys)
    assert _sql("SELECT count(*) FROM asset_files WHERE asset_id = :a", a=a["id"]).scalar() == 0
    # As gerações: mídia nula, `params` sem texto, o escolhido íntegro.
    for status, inst, escolhido in _sql(
            "SELECT status, params->>'instrucao', escolhido_id FROM geracoes WHERE alvo_id = :a",
            a=a["id"]):
        assert inst is None
        if status == "escolhido":
            assert escolhido is not None
    assert _sql("SELECT count(*) FROM geracao_candidatos c JOIN geracoes g ON "
                "g.id = c.geracao_id WHERE g.alvo_id = :a AND (c.image_id IS NOT NULL OR "
                "c.image_par_id IS NOT NULL)", a=a["id"]).scalar() == 0
    # O histórico: nenhuma versão com o prompt, e o registro do consentimento mantido.
    db.expire_all()
    versoes = list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_id == uuid.UUID(a["id"]), EntityVersion.entity_type == "asset")))
    assert versoes and all(v.details.get("redigida") for v in versoes)
    for v in versoes:
        for snap in (v.before, v.after):
            if snap:
                assert snap.get("prompt") is None and snap.get("identidade") is None
                assert (snap.get("consentimento") or {}).get("prova") is None
    ultima = max(versoes, key=lambda v: v.version)
    assert ultima.action == "revoked" and ultima.after["consentimento"]["nome"] == "Ana Souza"
    assert ultima.after["consentimento"]["revogado_em"]
    # As chamadas de IA do alvo sem texto (custo mantido).
    for row in db.scalars(select(IaChamada).where(IaChamada.entity_id == uuid.UUID(a["id"]))):
        assert row.instrucao == "" and row.proposta is None and row.custo_usd is not None
    # O evento, sem nome nem texto da pessoa.
    ev = db.scalar(select(SecurityEvent).where(SecurityEvent.type == "eliminacao_lgpd"))
    assert ev.details["excecao"] == "lgpd_revogacao" and ev.details["versoesLimpas"] >= 3
    assert "Ana" not in str(ev.details)
    # Restaurar, reverter e gerar recusados.
    a2 = out["asset"]
    r = client.post(f"/api/assets/{a2['id']}/restore", headers=h,
                    json={"version": a2["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "consentimento_revogado"
    r = client.post(f"/api/assets/{a2['id']}/revert", headers=h,
                    json={"version": a2["version"], "toVersion": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "consentimento_revogado"
    # A cena continua, com o prompt e sem o ponteiro do arquivo apagado.
    c = client.get(f"/api/cenas/{cena['id']}", headers=h).json()
    assert c["avatarId"] == a["id"] and c["avatarArquivoId"] is None


def test_revert_para_versao_redigida_recusado():
    """O `history.version_state` recusa qualquer versão redigida (mesmo de entidade viva)."""
    import pytest

    from sociman_api.db import get_sessionmaker

    eid = uuid.uuid4()
    _sql("INSERT INTO entity_versions (entity_type, entity_id, version, action, actor_kind, "
         "after, changed_fields, details) VALUES ('asset', :e, 1, 'created', 'user', "
         "'{}'::jsonb, '{}', '{\"redigida\": {\"motivo\": \"lgpd_revogacao\"}}'::jsonb)", e=eid)
    db = get_sessionmaker()()
    try:
        with pytest.raises(ApiError) as exc:
            history.version_state(db, "asset", eid, 1)
        assert exc.value.code == "versao_redigida"
    finally:
        db.close()


def test_revogar_voz_apaga_audios(client, owner, motores, db):
    h = owner[1]
    pid = perfil(client, h)
    v, _ = _aprovada(client, h, motores, pid)
    chaves = [k for (k,) in _sql("SELECT object_key FROM audios WHERE id IN (:g, :r)",
                                 g=v["gravacao"]["id"], r=v["referencia"]["id"])]
    r = client.post(f"/api/vozes/{v['id']}/consentimento/revogar", headers=h,
                    json={"version": v["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    out = r.json()["voz"]
    assert out["revogada"] and out["archived"] and out["referencia"] is None
    assert out["gravacao"] is None and out["refTexto"] is None
    assert not any(_existe(k, bucket="audios") for k in chaves)
    db.expire_all()
    for ver_ in db.scalars(select(EntityVersion).where(
            EntityVersion.entity_id == uuid.UUID(v["id"]))):
        for snap in (ver_.before, ver_.after):
            if snap:
                assert snap.get("ref_texto") is None
    r = client.post(f"/api/vozes/{v['id']}/restore", headers=h, json={"version": out["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "consentimento_revogado"


def test_revogar_voz_de_outro_perfil_lista_o_avatar_e_apaga(client, owner, motores):
    """Spec 029 (T028a): a voz de B é a padrão de um avatar de A; a revogação continua apagando
    tudo e lista o avatar afetado do outro perfil."""
    h = owner[1]
    pa, pb = perfil(client, h, slug="perfil-a"), perfil(client, h, slug="perfil-b")
    v, _ = _aprovada(client, h, motores, pb)
    a = avatar(client, h, pa, "Ana de A")
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "vozId": v["id"]})
    assert r.status_code == 200, r.text
    chaves = [k for (k,) in _sql("SELECT object_key FROM audios WHERE id IN (:g, :r)",
                                 g=v["gravacao"]["id"], r=v["referencia"]["id"])]
    r = client.post(f"/api/vozes/{v['id']}/consentimento/revogar", headers=h,
                    json={"version": v["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["avataresAfetados"]] == [a["id"]]
    assert not any(_existe(k, bucket="audios") for k in chaves)
