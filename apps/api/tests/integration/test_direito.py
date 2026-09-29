"""Guarda do princípio II (direito primeiro, R12 da spec 006, que absorveu a 008).

- só o dono muda o direito do canal (membro → 403), com versão (autor, antes e depois);
- enviar `sem_acordo` ou avulso sem `confirmarAviso` → 409 `aviso_direito` e nada enviado; com a
  confirmação (dono ou membro, Q3 = A) → 200, e a versão do envio registra direito, fonte, autor
  e data;
- `proprio` não pede aviso;
- o direito não altera a pontuação nem bloqueia o envio.
"""

import dataclasses
import inspect
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from integration.postagem_helpers import criar_perfil, dono, membro  # noqa: F401
from sociman_api.canais import score
from sociman_api.canais.models import CanalDireito, CanalFonte, CanalPerfil, VideoFonte
from sociman_api.envios.models import Envio, EnvioStatus


def _canal(db, perfil_id, direito: CanalDireito = CanalDireito.sem_acordo) -> CanalFonte:
    suf = uuid.uuid4().hex[:22]
    canal = CanalFonte(youtube_channel_id=f"UC{suf}", title="The IT Nerd",
                       uploads_playlist_id=f"UU{suf}", direito=direito)
    db.add(canal)
    db.flush()
    db.add(CanalPerfil(canal_id=canal.id, perfil_id=uuid.UUID(perfil_id)))
    db.commit()
    return canal


def _video(db, canal: CanalFonte, pontos: str = "70.0") -> VideoFonte:
    vid = uuid.uuid4().hex[:11]
    video = VideoFonte(canal_id=canal.id, youtube_video_id=vid, title="10 atalhos",
                       published_at=datetime.now(UTC) - timedelta(days=2), duration_s=600,
                       next_metrics_at=datetime.now(UTC) + timedelta(hours=1),
                       score=Decimal(pontos), score_reason="Novo", recomendavel=True)
    db.add(video)
    db.commit()
    return video


@pytest.fixture
def base(client, db, dono):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    return {"h": h, "perfil": perfil}


def _selecionar(client, h, perfil_id, **body):
    r = client.post(f"/api/perfis/{perfil_id}/envios", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["envio"]


def _enviar(client, h, envio, **extra):
    return client.post("/api/envios/enviar", headers=h,
                       json={"items": [{"envioId": envio["id"], "version": envio["version"]}],
                             **extra})


# ---- direito do canal: só o dono ----

def test_membro_nao_muda_o_direito(client, db, base, membro):  # noqa: F811
    canal = _canal(db, base["perfil"]["id"])
    r = client.put(f"/api/canais/{canal.id}/direito", headers=membro[1],
                   json={"version": canal.version, "direito": "proprio"})
    assert r.status_code == 403
    db.refresh(canal)
    assert canal.direito == CanalDireito.sem_acordo


def test_dono_muda_o_direito_com_versao(client, db, base, dono):  # noqa: F811
    canal = _canal(db, base["perfil"]["id"])
    r = client.put(f"/api/canais/{canal.id}/direito", headers=base["h"],
                   json={"version": canal.version, "direito": "parceiro",
                         "evidenciaUrl": "https://exemplo.com/acordo",
                         "evidenciaNota": "Acordo por e-mail"})
    assert r.status_code == 200, r.text
    assert r.json()["canal"]["direito"] == "parceiro"
    [ultima, *_] = client.get(f"/api/canais/{canal.id}/versions",
                              headers=base["h"]).json()["items"]
    assert ultima["actor"]["id"] == str(dono[0].id)
    assert ultima["before"]["direito"] == "sem_acordo"
    assert ultima["after"]["direito"] == "parceiro"
    assert "direito" in ultima["changedFields"]


# ---- aviso ao enviar ----

@pytest.mark.parametrize("quem", ["dono", "membro"])
def test_sem_acordo_exige_aviso_e_registra_o_envio(client, db, base, dono, membro, quem):  # noqa: F811
    user, h = {"dono": dono, "membro": membro}[quem]
    canal = _canal(db, base["perfil"]["id"])
    video = _video(db, canal)
    envio = _selecionar(client, h, base["perfil"]["id"], videoFonteId=str(video.id))

    r = _enviar(client, h, envio)
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "aviso_direito" and "responsabilidade" in err["message"]
    assert err["details"]["envioIds"] == [envio["id"]]
    assert db.get(Envio, uuid.UUID(envio["id"])).status == EnvioStatus.selecionado  # nada saiu

    antes = datetime.now(UTC)
    r = _enviar(client, h, envio, confirmarAviso=True)
    assert r.status_code == 200, r.text  # o direito não bloqueia (Q3 = A)
    assert r.json()["items"][0]["status"] == "na_fila"
    [v, *_] = client.get(f"/api/envios/{envio['id']}/versions", headers=h).json()["items"]
    assert v["actor"]["id"] == str(user.id)
    assert datetime.fromisoformat(v["occurredAt"]) >= antes - timedelta(seconds=5)
    assert v["after"]["direito_no_envio"] == "sem_acordo"
    assert v["after"]["aviso_confirmado"] is True
    assert v["after"]["source_url"].endswith(video.youtube_video_id)
    assert v["after"]["canal_fonte_id"] == str(canal.id)


def test_avulso_exige_aviso(client, db, base):
    h = base["h"]
    envio = _selecionar(client, h, base["perfil"]["id"], url="https://vimeo.com/12345",
                        titulo="Palestra")
    r = _enviar(client, h, envio)
    assert r.status_code == 409 and r.json()["error"]["code"] == "aviso_direito"
    r = _enviar(client, h, envio, confirmarAviso=True)
    assert r.status_code == 200, r.text
    [v, *_] = client.get(f"/api/envios/{envio['id']}/versions", headers=h).json()["items"]
    assert v["after"]["direito_no_envio"] == "avulso"
    assert v["after"]["source_url"] == "https://vimeo.com/12345"


def test_proprio_nao_pede_aviso(client, db, base):
    canal = _canal(db, base["perfil"]["id"], CanalDireito.proprio)
    video = _video(db, canal)
    envio = _selecionar(client, base["h"], base["perfil"]["id"], videoFonteId=str(video.id))
    r = _enviar(client, base["h"], envio)
    assert r.status_code == 200, r.text
    [v, *_] = client.get(f"/api/envios/{envio['id']}/versions",
                         headers=base["h"]).json()["items"]
    assert v["after"]["direito_no_envio"] == "proprio"
    assert v["after"]["aviso_confirmado"] is False


# ---- o direito não entra na pontuação ----

def test_pontuacao_nao_conhece_o_direito():
    campos = {f.name for f in dataclasses.fields(score.Entrada)}
    assert not any("direito" in c for c in campos)
    assert not any("direito" in p for p in inspect.signature(score.calcular).parameters)


def test_mudar_o_direito_nao_muda_o_score_exibido(client, db, base):
    canal = _canal(db, base["perfil"]["id"])
    video = _video(db, canal, "70.0")
    params = {"perfilId": base["perfil"]["id"], "recomendaveis": "false"}

    def _score():
        r = client.get("/api/videos-fonte", headers=base["h"], params=params)
        assert r.status_code == 200, r.text
        [item] = [i for i in r.json()["items"] if i["id"] == str(video.id)]
        return item["score"]

    antes = _score()
    r = client.put(f"/api/canais/{canal.id}/direito", headers=base["h"],
                   json={"version": canal.version, "direito": "proprio"})
    assert r.status_code == 200, r.text
    assert _score() == antes == 70.0
