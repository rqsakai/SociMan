"""`GET /api/integracoes` (T072, R15): estado de YouTube, OpenShorts e Claude, e a cota do dia,
sem nenhum valor de chave na resposta."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr

from integration.postagem_helpers import dono  # noqa: F401
from sociman_api import integracoes
from sociman_api.canais import youtube
from sociman_api.canais.models import CanalFonte, CanalSync, YoutubeCota
from sociman_api.config import get_settings

CHAVE_YT = "chave-youtube-de-teste"
CHAVE_CLAUDE = "chave-claude-de-teste"


@pytest.fixture(autouse=True)
def _sem_cache():
    integracoes.limpar_cache()
    yield
    integracoes.limpar_cache()


@pytest.fixture
def chaves(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "youtube_api_key", SecretStr(CHAVE_YT))
    monkeypatch.setattr(s, "anthropic_api_key", SecretStr(CHAVE_CLAUDE))


@pytest.fixture
def sem_chaves(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "youtube_api_key", SecretStr(""))
    monkeypatch.setattr(s, "anthropic_api_key", SecretStr(""))


def _get(client, h):
    r = client.get("/api/integracoes", headers=h)
    assert r.status_code == 200, r.text
    return r


def test_sem_chaves_ausente(client, dono, sem_chaves, monkeypatch):  # noqa: F811
    monkeypatch.setattr(integracoes, "_openshorts_ok", lambda: False)
    body = _get(client, dono[1]).json()
    assert body["youtube"] == "ausente" and body["claude"] == "ausente"
    assert body["openshorts"] == "fora"


def test_com_chaves_ok_e_sem_valores(client, dono, chaves, monkeypatch):  # noqa: F811
    monkeypatch.setattr(integracoes, "_openshorts_ok", lambda: True)
    r = _get(client, dono[1])
    body = r.json()
    assert (body["youtube"], body["claude"], body["openshorts"]) == ("ok", "ok", "ok")
    assert CHAVE_YT not in r.text and CHAVE_CLAUDE not in r.text


def test_youtube_invalida_pelo_erro_de_chave_do_canal(client, db, dono, chaves,  # noqa: F811
                                                      monkeypatch):
    monkeypatch.setattr(integracoes, "_openshorts_ok", lambda: True)
    canal = CanalFonte(youtube_channel_id="UC" + "a" * 22, title="Canal",
                       uploads_playlist_id="UU" + "a" * 22, sync_status=CanalSync.erro,
                       sync_error=f"{youtube.PREFIXO_CHAVE_INVALIDA}: confira a YOUTUBE_API_KEY")
    db.add(canal)
    db.commit()
    assert _get(client, dono[1]).json()["youtube"] == "invalida"
    # Canal arquivado não conta.
    canal.archived_at = datetime.now(UTC)
    db.commit()
    assert _get(client, dono[1]).json()["youtube"] == "ok"


def test_outro_erro_de_sync_nao_e_chave_invalida(client, db, dono, chaves,  # noqa: F811
                                                 monkeypatch):
    monkeypatch.setattr(integracoes, "_openshorts_ok", lambda: True)
    db.add(CanalFonte(youtube_channel_id="UC" + "b" * 22, title="Canal",
                      uploads_playlist_id="UU" + "b" * 22, sync_status=CanalSync.erro,
                      sync_error="O YouTube não respondeu"))
    db.commit()
    assert _get(client, dono[1]).json()["youtube"] == "ok"


def test_cota_do_dia_do_pacifico_e_renovacao_em_app_tz(client, db, dono, sem_chaves,  # noqa: F811
                                                       monkeypatch):
    monkeypatch.setattr(integracoes, "_openshorts_ok", lambda: False)
    hoje_la = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    db.add(YoutubeCota(dia=hoje_la, unidades=1234))
    db.commit()
    cota = _get(client, dono[1]).json()["cotaYoutube"]
    assert cota["usadas"] == 1234 and cota["limite"] == get_settings().yt_quota_daily
    renova = datetime.fromisoformat(cota["renovaEm"])
    assert renova.utcoffset() == datetime.now(ZoneInfo("America/Sao_Paulo")).utcoffset()
    local_la = renova.astimezone(ZoneInfo("America/Los_Angeles"))
    assert (local_la.hour, local_la.minute) == (0, 0)
    assert renova > datetime.now(UTC)


def test_cota_sem_linha_zero(db):
    cota = integracoes.cota_youtube(db, datetime(2026, 9, 29, 12, tzinfo=UTC))
    assert cota.usadas == 0
    # 12:00 UTC = 05:00 no Pacífico (PDT): renova à meia-noite de 30/09 PDT = 04:00 em SP.
    assert cota.renova_em.isoformat() == "2026-09-30T04:00:00-03:00"


def test_openshorts_cache_de_30s(monkeypatch):
    chamadas = []

    def _ok():
        chamadas.append(1)
        return True

    monkeypatch.setattr(integracoes, "_openshorts_ok", _ok)
    assert integracoes.openshorts_status(agora=100.0) == "ok"
    assert integracoes.openshorts_status(agora=129.0) == "ok"
    assert len(chamadas) == 1
    assert integracoes.openshorts_status(agora=131.0) == "ok"
    assert len(chamadas) == 2


def test_openshorts_falha_vira_fora(monkeypatch):
    class _Quebrado:
        def health(self, timeout=None):
            raise ConnectionError("recusado")

    import sociman_api.envios as envios_pkg

    fake_mod = type("M", (), {"get_openshorts_client": staticmethod(lambda: _Quebrado())})
    monkeypatch.setitem(__import__("sys").modules, "sociman_api.envios.openshorts", fake_mod)
    monkeypatch.setattr(envios_pkg, "openshorts", fake_mod, raising=False)
    assert integracoes._openshorts_ok() is False


def test_exige_login(client):
    assert client.get("/api/integracoes").status_code == 401
