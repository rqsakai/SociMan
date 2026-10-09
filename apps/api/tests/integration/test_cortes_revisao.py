"""Revisão dos clipes do OpenShorts (T056; FR-013, contracts/http-api.md "Cortes").

Os cortes em `revisao` entram direto pelo modelo (o vídeo não é lido por estas rotas).
"""

import uuid
from decimal import Decimal

import pytest

from integration import envios_helpers
from sociman_api.config import get_settings
from sociman_api.cortes import queue
from sociman_api.cortes.models import Corte, CorteOrigem, CorteStatus
from sociman_api.db import get_sessionmaker
from sociman_api.envios.models import Envio, EnvioOrigem

# Fixtures compartilhadas (atribuídas, e não importadas, para o ruff não acusar F811).
member = envios_helpers.member
owner = envios_helpers.owner
perfil = envios_helpers.perfil

def _envio(perfil_id: str) -> uuid.UUID:
    with get_sessionmaker()() as s:
        e = Envio(perfil_id=uuid.UUID(perfil_id), origem=EnvioOrigem.avulso_link,
                  source_url="https://vimeo.com/1", source_title="Palestra")
        s.add(e)
        s.commit()
        return e.id


def _corte(perfil_id: str, envio_id: uuid.UUID, idx: int, hook: str = "Olha isso",
           status: CorteStatus = CorteStatus.revisao, width: int = 1080) -> str:
    with get_sessionmaker()() as s:
        cid = uuid.uuid4()
        kit = {} if status != CorteStatus.revisao else None
        c = Corte(id=cid, perfil_id=uuid.UUID(perfil_id), hook_text=hook, status=status,
                  kit_version=None if kit is None else 0, kit_tokens=kit,
                  origem=CorteOrigem.openshorts, envio_id=envio_id, clip_index=idx,
                  original_filename=f"clipe-{idx + 1}.mp4",
                  original_key=f"perfis/{perfil_id}/cortes/{cid}/original.mp4",
                  original_content_type="video/mp4", original_bytes=1000, duration_ms=20_000,
                  width=width, height=width * 16 // 9, fps=Decimal(30), video_codec="h264",
                  audio_codec="aac", original_sha256="0" * 64)
        s.add(c)
        s.commit()
        return str(cid)


@pytest.fixture
def clipes(perfil) -> list[str]:
    envio_id = _envio(perfil["id"])
    return [_corte(perfil["id"], envio_id, i, hook=f"Gancho {i + 1}") for i in range(3)]


def _get(client, h, corte_id: str) -> dict:
    return client.get(f"/api/cortes/{corte_id}", headers=h).json()["corte"]


def _aplicar(client, h, *pares: tuple[str, int]):
    return client.post("/api/cortes/aplicar-marca", headers=h,
                       json={"items": [{"corteId": c, "version": v} for c, v in pares]})


# ---- gancho ----

def test_editar_gancho_em_revisao(client, member, clipes):
    user, h = member
    r = client.patch(f"/api/cortes/{clipes[0]}", headers=h,
                     json={"version": 1, "hookText": "  Novo gancho  "})
    assert r.status_code == 200, r.text
    c = r.json()["corte"]
    assert c["hookText"] == "Novo gancho" and c["version"] == 2 and c["kitVersion"] is None
    v = client.get(f"/api/cortes/{clipes[0]}/versions", headers=h).json()["items"][0]
    assert v["action"] == "updated" and v["changedFields"] == ["hook_text"]
    assert v["actor"]["id"] == str(user.id)

    r = client.patch(f"/api/cortes/{clipes[0]}", headers=h,
                     json={"version": 1, "hookText": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


@pytest.mark.parametrize("hook", ["", "   ", "x" * 121])
def test_gancho_invalido(client, owner, clipes, hook):
    r = client.patch(f"/api/cortes/{clipes[0]}", headers=owner[1],
                     json={"version": 1, "hookText": hook})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_hook"


def test_gancho_que_passa_de_3_linhas(client, owner, perfil):
    corte = _corte(perfil["id"], _envio(perfil["id"]), 0, width=240)
    texto = " ".join(["Palavrona"] * 12)
    r = client.patch(f"/api/cortes/{corte}", headers=owner[1],
                     json={"version": 1, "hookText": texto})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_hook"


def test_editar_fora_de_revisao_da_409(client, owner, perfil):
    corte = _corte(perfil["id"], _envio(perfil["id"]), 0, status=CorteStatus.na_fila)
    r = client.patch(f"/api/cortes/{corte}", headers=owner[1],
                     json={"version": 1, "hookText": "Outro"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


# ---- aplicar marca ----

def test_aplicar_marca_em_lote(client, owner, perfil, clipes):
    _, h = owner
    kit = client.get(f"/api/perfis/{perfil['id']}/kit", headers=h).json()["kit"]
    body = {k: kit[k] for k in ("version", "palette", "caption", "hook", "watermark",
                                "endCard", "catchphrases", "series")}
    assert client.put(f"/api/perfis/{perfil['id']}/kit", json=body, headers=h).status_code == 200

    r = _aplicar(client, h, (clipes[2], 1), (clipes[0], 1))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [c["id"] for c in items] == [clipes[2], clipes[0]]
    assert all(c["status"] == "na_fila" and c["kitVersion"] == 1 and c["version"] == 2
               for c in items)
    assert items[0]["queuePosition"] is not None
    v = client.get(f"/api/cortes/{clipes[0]}/versions", headers=h).json()["items"][0]
    assert v["details"] == {"acao": "aplicar_marca"}
    assert v["after"]["status"] == "na_fila" and v["after"]["kit_version"] == 1
    assert _get(client, h, clipes[1])["status"] == "revisao"

    with get_sessionmaker()() as s:
        tokens = s.get(Corte, uuid.UUID(clipes[0])).kit_tokens
    assert tokens["hook"]["fonte"]["padrao"] == "noto-serif-bold"

    # de novo: já não está em revisão (tudo ou nada: o clipe 1 também não muda)
    r = _aplicar(client, h, (clipes[1], 1), (clipes[0], 2))
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert _get(client, h, clipes[1])["status"] == "revisao"


def test_aplicar_marca_gancho_vazio(client, owner, perfil):
    _, h = owner
    envio_id = _envio(perfil["id"])
    ok = _corte(perfil["id"], envio_id, 0)
    vazio = _corte(perfil["id"], envio_id, 1, hook="")
    r = _aplicar(client, h, (ok, 1), (vazio, 1))
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "invalid_hook" and err["details"] == {"corteId": vazio}
    assert _get(client, h, ok)["status"] == "revisao"


def test_aplicar_marca_limites_e_versao(client, owner, clipes):
    _, h = owner
    many = [{"corteId": str(uuid.uuid4()), "version": 1} for _ in range(31)]
    assert client.post("/api/cortes/aplicar-marca", headers=h,
                       json={"items": many}).status_code == 400
    assert client.post("/api/cortes/aplicar-marca", headers=h,
                       json={"items": []}).status_code == 400
    r = _aplicar(client, h, (clipes[0], 7))
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    assert _aplicar(client, h, (str(uuid.uuid4()), 1)).status_code == 404


def test_aplicar_marca_sem_hd(client, owner, clipes, monkeypatch, tmp_path):
    _, h = owner
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = _aplicar(client, h, (clipes[0], 1))
    assert r.status_code == 503
    monkeypatch.undo()
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    assert _aplicar(client, h, (clipes[0], 1)).status_code == 507
    monkeypatch.undo()
    assert _get(client, h, clipes[0])["status"] == "revisao"


# ---- arquivar ----

def test_arquivar_e_restaurar(client, owner, perfil, clipes):
    _, h = owner
    r = client.post(f"/api/cortes/{clipes[0]}/archive", json={"version": 1}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["corte"]["archived"] is True and r.json()["corte"]["version"] == 2
    assert client.post(f"/api/cortes/{clipes[0]}/archive", json={"version": 2},
                       headers=h).status_code == 409
    assert _aplicar(client, h, (clipes[0], 2)).status_code == 409

    url = f"/api/perfis/{perfil['id']}/cortes"
    ativos = client.get(url, headers=h).json()["items"]
    assert clipes[0] not in {c["id"] for c in ativos} and len(ativos) == 2
    arquivados = client.get(url, params={"archived": "true"}, headers=h).json()["items"]
    assert [c["id"] for c in arquivados] == [clipes[0]]

    r = client.post(f"/api/cortes/{clipes[0]}/restore", json={"version": 2}, headers=h)
    assert r.status_code == 200 and r.json()["corte"]["archived"] is False
    assert client.post(f"/api/cortes/{clipes[0]}/restore", json={"version": 3},
                       headers=h).status_code == 409
    actions = [v["action"] for v in
               client.get(f"/api/cortes/{clipes[0]}/versions", headers=h).json()["items"]]
    assert actions == ["restored", "archived"]


def test_arquivar_processando_da_409(client, owner, perfil):
    corte = _corte(perfil["id"], _envio(perfil["id"]), 0, status=CorteStatus.processando)
    r = client.post(f"/api/cortes/{corte}/archive", json={"version": 1}, headers=owner[1])
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


def test_filtros_da_lista(client, owner, perfil, clipes):
    _, h = owner
    url = f"/api/perfis/{perfil['id']}/cortes"
    outro_envio = _envio(perfil["id"])
    _corte(perfil["id"], outro_envio, 0)
    assert len(client.get(url, params={"origem": "openshorts"}, headers=h).json()["items"]) == 4
    assert client.get(url, params={"origem": "upload"}, headers=h).json()["items"] == []
    r = client.get(url, params={"envioId": str(outro_envio)}, headers=h)
    assert len(r.json()["items"]) == 1
    r = client.get(url, params={"status": "revisao"}, headers=h)
    assert len(r.json()["items"]) == 4


def test_worker_continua_pegando_so_na_fila(client, owner, clipes):
    assert queue.claim() is None  # três em revisão, nenhum na fila
    r = _aplicar(client, owner[1], (clipes[1], 1))
    assert r.status_code == 200
    job = queue.claim()
    assert job is not None and str(job.id) == clipes[1]
    assert queue.claim() is None
