"""Enviar ao OpenShorts (T044; R6, princípio II, contracts/http-api.md "Envios")."""

import uuid

from integration import envios_helpers
from integration.envios_helpers import (
    criar_canal,
    criar_video,
    enviar,
    envio_row,
    selecionado,
)
from sociman_api.canais.models import CanalDireito
from sociman_api.envios.models import EnvioStatus

# Fixtures compartilhadas (atribuídas, e não importadas, para o ruff não acusar F811).
member = envios_helpers.member
owner = envios_helpers.owner
perfil = envios_helpers.perfil

def _versions(client, h, envio_id: str) -> list[dict]:
    return client.get(f"/api/envios/{envio_id}/versions", headers=h).json()["items"]


def test_sem_acordo_sem_confirmacao_nao_envia_nenhum(client, owner, perfil, db):
    _, h = owner
    proprio = selecionado(client, h, perfil["id"], criar_video(criar_canal(CanalDireito.proprio)))
    sem = selecionado(client, h, perfil["id"], criar_video(criar_canal(CanalDireito.sem_acordo)))
    avulso = selecionado(client, h, perfil["id"], url="https://vimeo.com/1")

    r = enviar(client, h, [proprio, sem, avulso])
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "aviso_direito"
    assert err["message"] == "O direito autoral deste vídeo é de sua responsabilidade"
    assert sorted(err["details"]["envioIds"]) == sorted([sem["id"], avulso["id"]])
    for e in (proprio, sem, avulso):  # tudo ou nada
        row = envio_row(db, e["id"])
        assert row.status == EnvioStatus.selecionado and row.version == 1


def test_membro_confirma_o_aviso_e_envia(client, owner, member, perfil, db):
    user, h = member
    canal = criar_canal(CanalDireito.sem_acordo, "Canal alheio")
    e = selecionado(client, owner[1], perfil["id"], criar_video(canal, title="Entrevista"))

    r = enviar(client, h, [e], confirmarAviso=True)
    assert r.status_code == 200, r.text
    (out,) = r.json()["items"]
    assert out["status"] == "na_fila" and out["direitoNoEnvio"] == "sem_acordo"
    assert out["sentAt"] is not None and out["version"] == 2
    assert out["config"] == {"clipMinS": 15, "clipMaxS": 60, "quantidade": None,
                             "layout": "auto", "formato": "vertical", "legenda": "kit",
                             "marcaAutomatica": False, "kitVersion": 0}

    row = envio_row(db, e["id"])
    assert row.aviso_confirmado is True and row.direito_no_envio.value == "sem_acordo"
    # a seção openshorts.subtitle do kit fica só no servidor
    assert row.config["subtitle"]["font_name"] and row.config["subtitle"]["style"]
    assert "subtitle" not in out["config"]

    v = _versions(client, h, e["id"])[0]
    assert v["action"] == "updated" and v["actor"]["id"] == str(user.id)
    assert v["after"]["direito_no_envio"] == "sem_acordo"
    assert v["after"]["aviso_confirmado"] is True and v["after"]["status"] == "na_fila"
    assert v["after"]["source_url"] == row.source_url
    assert v["details"] == {"acao": "enviar", "duplicado": False,
                            "canal_direito_atual": "sem_acordo",
                            "aviso_confirmado_por": str(user.id)}


def test_proprio_nao_pede_aviso(client, owner, perfil):
    _, h = owner
    e = selecionado(client, h, perfil["id"], criar_video(criar_canal(CanalDireito.proprio)))
    r = enviar(client, h, [e])
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["direitoNoEnvio"] == "proprio"
    v = _versions(client, h, e["id"])[0]
    assert v["after"]["aviso_confirmado"] is False
    assert "aviso_confirmado_por" not in v["details"]


def test_avulso_registra_direito_avulso(client, owner, perfil):
    _, h = owner
    e = selecionado(client, h, perfil["id"], url="https://vimeo.com/1", titulo="Palestra")
    r = enviar(client, h, [e], confirmarAviso=True)
    assert r.status_code == 200 and r.json()["items"][0]["direitoNoEnvio"] == "avulso"
    v = _versions(client, h, e["id"])[0]
    assert v["details"]["canal_direito_atual"] is None


def test_config_padroes_do_perfil_mais_override(client, owner, perfil, db):
    _, h = owner
    r = client.put(f"/api/perfis/{perfil['id']}/padroes-corte", headers=h, json={
        "version": 0, "clipMinS": 20, "clipMaxS": 90, "quantidade": 4, "layout": "split",
        "formato": "square", "legenda": "gerador", "marcaAutomatica": True,
        "contaPadraoId": None})
    assert r.status_code == 200, r.text
    e = selecionado(client, h, perfil["id"], criar_video(criar_canal(CanalDireito.proprio)))
    r = enviar(client, h, [e], config={"clipMaxS": 120, "quantidade": None})
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["config"] == {
        "clipMinS": 20, "clipMaxS": 120, "quantidade": None, "layout": "split",
        "formato": "square", "legenda": "gerador", "marcaAutomatica": True, "kitVersion": 0}
    assert "subtitle" not in envio_row(db, e["id"]).config  # legenda do gerador

    # mudar o padrão depois não afeta o envio
    client.put(f"/api/perfis/{perfil['id']}/padroes-corte", headers=h, json={
        "version": 1, "clipMinS": 30, "clipMaxS": 90, "quantidade": 4, "layout": "split",
        "formato": "square", "legenda": "gerador", "marcaAutomatica": True,
        "contaPadraoId": None})
    assert envio_row(db, e["id"]).config["clip_min_s"] == 20


def test_config_invalida(client, owner, perfil, db):
    _, h = owner
    e = selecionado(client, h, perfil["id"], criar_video(criar_canal(CanalDireito.proprio)))
    r = enviar(client, h, [e], config={"clipMinS": 50, "clipMaxS": 52})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "invalid_config" and err["details"]["field"] == "clipMaxS"
    r = enviar(client, h, [e], config={"layout": "grade"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_config"
    assert envio_row(db, e["id"]).status == EnvioStatus.selecionado


def test_ja_enviado_pede_confirmacao_de_duplicado(client, owner, perfil):
    _, h = owner
    video = criar_video(criar_canal(CanalDireito.proprio))
    e1 = selecionado(client, h, perfil["id"], video)
    assert enviar(client, h, [e1]).status_code == 200
    r = client.post(f"/api/perfis/{perfil['id']}/envios", headers=h,
                    json={"videoFonteId": str(video.id), "confirmarDuplicado": True})
    e2 = r.json()["envio"]

    r = enviar(client, h, [e2])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_sent"
    assert r.json()["error"]["details"]["envioId"] == e1["id"]
    r = enviar(client, h, [e2], confirmarDuplicado=True)
    assert r.status_code == 200, r.text
    v = _versions(client, h, e2["id"])[0]
    assert v["details"]["duplicado"] is True


def test_conflitos(client, owner, perfil):
    _, h = owner
    canal = criar_canal(CanalDireito.proprio)
    e = selecionado(client, h, perfil["id"], criar_video(canal))
    r = client.post("/api/envios/enviar", headers=h,
                    json={"items": [{"envioId": e["id"], "version": 5}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    assert enviar(client, h, [e]).status_code == 200
    r = client.post("/api/envios/enviar", headers=h,
                    json={"items": [{"envioId": e["id"], "version": 2}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    r = client.post("/api/envios/enviar", headers=h,
                    json={"items": [{"envioId": str(uuid.uuid4()), "version": 1}]})
    assert r.status_code == 404
    r = client.post("/api/envios/enviar", headers=h, json={"items": []})
    assert r.status_code == 400
    many = [{"envioId": str(uuid.uuid4()), "version": 1} for _ in range(21)]
    assert client.post("/api/envios/enviar", headers=h, json={"items": many}).status_code == 400


def test_video_ficou_indisponivel(client, owner, perfil, db):
    _, h = owner
    video = criar_video(criar_canal(CanalDireito.proprio))
    e = selecionado(client, h, perfil["id"], video)
    from sociman_api.canais.models import VideoFonte

    db.get(VideoFonte, video.id).disponivel = False
    db.commit()
    r = enviar(client, h, [e])
    assert r.status_code == 409 and r.json()["error"]["code"] == "video_unavailable"


def _falhar(db, envio_id: str, code: str = "openshorts_failed", job: str | None = None) -> None:
    row = envio_row(db, envio_id)
    row.status = EnvioStatus.falhou
    row.error_code = code
    row.error_message = "falhou"
    row.openshorts_job_id = job
    db.commit()


def test_confirmar_qualidade(client, owner, perfil, db):
    _, h = owner
    canal = criar_canal(CanalDireito.proprio)
    e1 = enviar(client, h, [selecionado(client, h, perfil["id"], criar_video(canal))]).json()
    e2 = enviar(client, h, [selecionado(client, h, perfil["id"], criar_video(canal))]).json()
    e1, e2 = e1["items"][0], e2["items"][0]
    r = client.post(f"/api/envios/{e1['id']}/confirmar-qualidade", headers=h,
                    json={"version": 2, "enviar": True})
    assert r.status_code == 409  # ainda em na_fila

    for e in (e1, e2):
        row = envio_row(db, e["id"])
        row.status = EnvioStatus.confirmar_qualidade
        db.commit()
    r = client.post(f"/api/envios/{e1['id']}/confirmar-qualidade", headers=h,
                    json={"version": 2, "enviar": True})
    assert r.status_code == 200, r.text
    assert r.json()["envio"]["status"] == "na_fila"
    assert envio_row(db, e1["id"]).force_low_quality is True

    r = client.post(f"/api/envios/{e2['id']}/confirmar-qualidade", headers=h,
                    json={"version": 2, "enviar": False})
    assert r.status_code == 200
    assert r.json()["envio"]["status"] == "descartado" and r.json()["envio"]["archived"]
    assert _versions(client, h, e2["id"])[0]["details"] == {"acao": "descartar"}


def test_retry(client, owner, perfil, db):
    _, h = owner
    canal = criar_canal(CanalDireito.proprio)
    e = enviar(client, h, [selecionado(client, h, perfil["id"], criar_video(canal))])
    e = e.json()["items"][0]
    r = client.post(f"/api/envios/{e['id']}/retry", json={"version": 2}, headers=h)
    assert r.status_code == 409

    _falhar(db, e["id"], job="job-velho")
    r = client.post(f"/api/envios/{e['id']}/retry", json={"version": 2}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["envio"]["status"] == "na_fila" and r.json()["envio"]["errorMessage"] is None
    row = envio_row(db, e["id"])
    assert row.openshorts_job_id is None
    assert _versions(client, h, e["id"])[0]["details"] == {"acao": "tentar_de_novo"}

    # falha na importação com o job ainda lá: "Importar de novo"
    _falhar(db, e["id"], code="import_failed", job="job-1")
    r = client.post(f"/api/envios/{e['id']}/retry", json={"version": 3}, headers=h)
    assert r.status_code == 200 and r.json()["envio"]["status"] == "importando"
    assert envio_row(db, e["id"]).openshorts_job_id == "job-1"
