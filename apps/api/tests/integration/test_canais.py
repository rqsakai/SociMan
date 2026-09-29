"""Canais-fonte (T023, US1; contracts/http-api.md "Canais")."""

from datetime import UTC, datetime, timedelta

import pytest
from fakes.youtube_fake import CHAVE_TESTE, YoutubeFake, youtube_fake  # noqa: F401
from sqlalchemy import select

from sociman_api.canais.models import CanalFonte, CanalSync
from sociman_api.canais.youtube import get_youtube_client
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.perfis.models import Perfil

PW = "senha-forte-123"
CID = "UCaaaaaaaaaaaaaaaaaaaaaa"
CID2 = "UCbbbbbbbbbbbbbbbbbbbbbb"


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


@pytest.fixture
def fake(youtube_fake: YoutubeFake) -> YoutubeFake:  # noqa: F811
    youtube_fake.add_canal(CID, "The IT Nerd", handle="theitnerd")
    youtube_fake.add_canal(CID2, "Outro Canal", handle="outro")
    app.dependency_overrides[get_youtube_client] = lambda: youtube_fake.client()
    return youtube_fake


@pytest.fixture
def perfis(db):
    a = Perfil(name="A Taverna Nerd", slug="a-taverna-nerd")
    b = Perfil(name="Bits", slug="bits")
    db.add_all([a, b])
    db.commit()
    return a, b


def _err(r) -> dict:
    return r.json()["error"]


def _criar(client, h, cid=CID, perfil_ids=()):
    r = client.post("/api/canais", json={"youtubeChannelId": cid,
                                         "perfilIds": [str(p) for p in perfil_ids]}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["canal"]


def _versions(client, h, canal):
    r = client.get(f"/api/canais/{canal['id']}/versions", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ---- resolver ----

def test_resolver_mostra_previa_sem_gravar(client, db, membro, fake):
    _, h = membro
    r = client.post("/api/canais/resolver", json={"entrada": "https://www.youtube.com/@theitnerd"},
                    headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["custo"] == 1
    assert body["existente"] is None
    cand = body["candidato"]
    assert cand["youtubeChannelId"] == CID
    assert cand["title"] == "The IT Nerd"
    assert cand["handle"] == "theitnerd"
    assert cand["subscribers"] == 45600
    assert cand["avatarUrl"].startswith("/img/")
    assert db.scalar(select(CanalFonte.id)) is None


def test_resolver_ja_cadastrado_traz_existente(client, membro, fake):
    _, h = membro
    canal = _criar(client, h)
    r = client.post("/api/canais/resolver", json={"entrada": "@theitnerd"}, headers=h)
    assert r.json()["existente"] == {"id": canal["id"]}
    antes = len(fake.requests)
    r = client.post("/api/canais/resolver", json={"entrada": CID}, headers=h)
    assert r.json()["existente"] == {"id": canal["id"]}
    assert r.json()["custo"] == 0
    assert len(fake.requests) == antes  # não gasta cota com o que já temos


def test_resolver_entrada_invalida_e_nao_encontrado(client, membro, fake):
    _, h = membro
    r = client.post("/api/canais/resolver", json={"entrada": "https://vimeo.com/1"}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (400, "invalid_channel_input")
    r = client.post("/api/canais/resolver", json={"entrada": "@naoexiste"}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (404, "canal_not_found")


# ---- criar ----

def test_criar_com_sync_pendente_e_perfis(client, db, membro, fake, perfis):
    user, h = membro
    antes = datetime.now(UTC)
    canal = _criar(client, h, perfil_ids=[perfis[0].id])
    assert canal["title"] == "The IT Nerd"
    assert canal["direito"] == "sem_acordo"
    assert canal["sync"]["status"] == "pendente"
    assert canal["sync"]["lidos"] is None
    next_sync = datetime.fromisoformat(canal["sync"]["nextSyncAt"])
    assert antes - timedelta(seconds=5) <= next_sync <= datetime.now(UTC)
    assert [p["slug"] for p in canal["perfis"]] == ["a-taverna-nerd"]
    assert canal["version"] == 1
    assert canal["createdBy"] == {"id": str(user.id), "name": "Membro"}
    assert canal["avatarUrl"].startswith("/img/")
    assert canal["videosConhecidos"] == 0
    [v1] = _versions(client, h, canal)
    assert v1["action"] == "created"
    assert v1["after"]["perfil_ids"] == [str(perfis[0].id)]


def test_criar_duplicado_409_contando_arquivados(client, membro, fake):
    _, h = membro
    canal = _criar(client, h)
    r = client.post("/api/canais", json={"youtubeChannelId": CID}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (409, "canal_exists")
    assert _err(r)["details"] == {"id": canal["id"]}
    r = client.post(f"/api/canais/{canal['id']}/archive", json={"version": 1}, headers=h)
    assert r.status_code == 200
    antes = len(fake.requests)
    r = client.post("/api/canais", json={"youtubeChannelId": CID}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (409, "canal_exists")
    assert len(fake.requests) == antes


def test_criar_valida_formato_e_perfil(client, membro, fake, perfis, db):
    _, h = membro
    r = client.post("/api/canais", json={"youtubeChannelId": "UCcurto"}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (400, "validation_error")
    perfis[1].archived_at = datetime.now(UTC)
    db.commit()
    r = client.post("/api/canais", json={"youtubeChannelId": CID,
                                         "perfilIds": [str(perfis[1].id)]}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (400, "validation_error")


# ---- editar perfis ----

def test_patch_perfis_gera_versao(client, membro, fake, perfis, db):
    _, h = membro
    a, b = perfis
    canal = _criar(client, h, perfil_ids=[a.id])
    r = client.patch(f"/api/canais/{canal['id']}",
                     json={"version": 1, "perfilIds": [str(b.id), str(a.id)]}, headers=h)
    assert r.status_code == 200, r.text
    canal = r.json()["canal"]
    assert canal["version"] == 2
    assert {p["id"] for p in canal["perfis"]} == {str(a.id), str(b.id)}
    v2 = _versions(client, h, canal)[0]
    assert v2["action"] == "updated"
    assert v2["changedFields"] == ["perfil_ids"]
    assert v2["after"]["perfil_ids"] == sorted([str(a.id), str(b.id)])

    r = client.patch(f"/api/canais/{canal['id']}", json={"version": 1, "perfilIds": []},
                     headers=h)
    assert (r.status_code, _err(r)["code"]) == (409, "version_conflict")

    b.archived_at = datetime.now(UTC)
    db.commit()
    r = client.patch(f"/api/canais/{canal['id']}",
                     json={"version": 2, "perfilIds": [str(b.id)]}, headers=h)
    assert r.status_code == 400
    r = client.patch(f"/api/canais/{canal['id']}", json={"version": 2, "title": "x"}, headers=h)
    assert r.status_code == 400  # só perfis são editáveis


def test_filtros_da_lista(client, membro, fake, perfis):
    _, h = membro
    c1 = _criar(client, h, perfil_ids=[perfis[0].id])
    c2 = _criar(client, h, cid=CID2)
    r = client.get("/api/canais", headers=h)
    assert [c["title"] for c in r.json()["items"]] == ["Outro Canal", "The IT Nerd"]
    r = client.get("/api/canais", params={"perfilId": str(perfis[0].id)}, headers=h)
    assert [c["id"] for c in r.json()["items"]] == [c1["id"]]
    r = client.get("/api/canais", params={"q": "outr"}, headers=h)
    assert [c["id"] for c in r.json()["items"]] == [c2["id"]]
    client.post(f"/api/canais/{c2['id']}/archive", json={"version": 1}, headers=h)
    r = client.get("/api/canais", headers=h)
    assert [c["id"] for c in r.json()["items"]] == [c1["id"]]
    r = client.get("/api/canais", params={"archived": "true"}, headers=h)
    assert [c["id"] for c in r.json()["items"]] == [c2["id"]]
    r = client.get(f"/api/canais/{c2['id']}", headers=h)
    assert r.json()["canal"]["archived"] is True


# ---- direito (princípio II) ----

def test_direito_so_o_dono_muda(client, membro, dono, fake):
    _, hm = membro
    user_dono, hd = dono
    canal = _criar(client, hm)
    corpo = {"version": 1, "direito": "proprio", "evidenciaUrl": "https://exemplo.com/acordo",
             "evidenciaNota": "Canal do próprio dono"}
    r = client.put(f"/api/canais/{canal['id']}/direito", json=corpo, headers=hm)
    assert (r.status_code, _err(r)["code"]) == (403, "forbidden")

    r = client.put(f"/api/canais/{canal['id']}/direito", json=corpo, headers=hd)
    assert r.status_code == 200, r.text
    canal = r.json()["canal"]
    assert canal["direito"] == "proprio"
    assert canal["direitoEvidenciaUrl"] == "https://exemplo.com/acordo"
    assert canal["version"] == 2
    v = _versions(client, hd, canal)[0]
    assert v["actor"] == {"id": str(user_dono.id), "name": "Dono"}
    assert v["before"]["direito"] == "sem_acordo"
    assert v["after"]["direito"] == "proprio"
    assert set(v["changedFields"]) == {"direito", "direito_evidencia_url",
                                       "direito_evidencia_nota"}


def test_direito_valida_evidencia(client, dono, fake):
    _, h = dono
    canal = _criar(client, h)
    url = f"/api/canais/{canal['id']}/direito"
    r = client.put(url, json={"version": 1, "direito": "parceiro", "evidenciaUrl": "ftp://x"},
                   headers=h)
    assert r.status_code == 400
    r = client.put(url, json={"version": 1, "direito": "parceiro", "evidenciaNota": "x" * 2001},
                   headers=h)
    assert r.status_code == 400
    r = client.put(url, json={"version": 1, "direito": "nenhum"}, headers=h)
    assert r.status_code == 400


# ---- arquivar, restaurar e reverter ----

def test_archive_restore(client, membro, fake, db):
    _, h = membro
    canal = _criar(client, h)
    r = client.post(f"/api/canais/{canal['id']}/archive", json={"version": 1}, headers=h)
    assert r.json()["canal"]["archived"] is True
    r = client.post(f"/api/canais/{canal['id']}/archive", json={"version": 2}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (409, "conflict")
    r = client.post(f"/api/canais/{canal['id']}/restore", json={"version": 2}, headers=h)
    assert r.status_code == 200
    assert r.json()["canal"]["archived"] is False
    assert [v["action"] for v in _versions(client, h, canal)] == \
        ["restored", "archived", "created"]


def test_revert_so_o_dono_recria_ligacoes_e_ignora_titulo(client, membro, dono, fake, perfis,
                                                         db):
    _, hm = membro
    _, hd = dono
    a, b = perfis
    canal = _criar(client, hm, perfil_ids=[a.id])
    client.patch(f"/api/canais/{canal['id']}", json={"version": 1, "perfilIds": [str(b.id)]},
                 headers=hm)
    client.put(f"/api/canais/{canal['id']}/direito",
               json={"version": 2, "direito": "parceiro"}, headers=hd)
    # A sync troca o título (estado de job, sem versão).
    row = db.get(CanalFonte, canal["id"])
    row.title = "Nome Novo"
    db.commit()

    r = client.post(f"/api/canais/{canal['id']}/revert", json={"version": 3, "toVersion": 1},
                    headers=hm)
    assert r.status_code == 403
    r = client.post(f"/api/canais/{canal['id']}/revert", json={"version": 3, "toVersion": 1},
                    headers=hd)
    assert r.status_code == 200, r.text
    out = r.json()["canal"]
    assert out["version"] == 4
    assert out["direito"] == "sem_acordo"
    assert [p["id"] for p in out["perfis"]] == [str(a.id)]
    assert out["title"] == "Nome Novo"
    v4 = _versions(client, hd, out)[0]
    assert v4["action"] == "reverted"
    assert v4["details"] == {"from_version": 1}


# ---- integração ----

def test_sem_chave_503(client, membro, youtube_fake):  # noqa: F811
    _, h = membro
    app.dependency_overrides[get_youtube_client] = lambda: youtube_fake.client(key="")
    r = client.post("/api/canais/resolver", json={"entrada": "@theitnerd"}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (503, "youtube_unconfigured")
    assert _err(r)["message"] == "A chave da API do YouTube não está configurada"
    r = client.post("/api/canais", json={"youtubeChannelId": CID}, headers=h)
    assert r.status_code == 503


def test_cota_esgotada_429(client, membro, youtube_fake):  # noqa: F811
    _, h = membro
    youtube_fake.add_canal(CID, handle="theitnerd")
    app.dependency_overrides[get_youtube_client] = lambda: youtube_fake.client(quota_daily=1)
    client.post("/api/canais/resolver", json={"entrada": "@theitnerd"}, headers=h)
    r = client.post("/api/canais/resolver", json={"entrada": "@theitnerd"}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (429, "youtube_quota")
    assert "volta às" in _err(r)["message"]


def test_chave_invalida_502_sem_vazar(client, membro, fake):
    _, h = membro
    fake.erro_proximo("keyInvalid")
    r = client.post("/api/canais/resolver", json={"entrada": "@theitnerd"}, headers=h)
    assert (r.status_code, _err(r)["code"]) == (502, "youtube_error")
    assert CHAVE_TESTE not in r.text
    assert _err(r)["message"].startswith("Chave do YouTube inválida")


def test_sincronizar_agora(client, membro, fake, db):
    _, h = membro
    canal = _criar(client, h)
    row = db.get(CanalFonte, canal["id"])
    row.next_sync_at = datetime.now(UTC) + timedelta(hours=1)
    row.sync_status = CanalSync.ok
    db.commit()
    r = client.post(f"/api/canais/{canal['id']}/sincronizar", headers=h)
    assert r.status_code == 200, r.text
    assert datetime.fromisoformat(r.json()["canal"]["sync"]["nextSyncAt"]) <= datetime.now(UTC)
    assert r.json()["canal"]["version"] == 1  # estado de job: sem versão
    assert db.scalar(select(EntityVersion.id).where(EntityVersion.version == 2)) is None

    row = db.get(CanalFonte, canal["id"])
    db.refresh(row)
    row.sync_status = CanalSync.sincronizando
    db.commit()
    r = client.post(f"/api/canais/{canal['id']}/sincronizar", headers=h)
    assert (r.status_code, _err(r)["code"]) == (409, "sync_running")
