"""Postagens por conta de destino e calendário (T064, US5, R10). Nada é publicado."""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from integration.postagem_helpers import (  # noqa: F401
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.cortes.models import CorteStatus
from sociman_api.history import EntityVersion
from sociman_api.marca.models import BrandKit
from sociman_api.postagem.models import Postagem

SP = ZoneInfo("America/Sao_Paulo")


def _amanha(hora: int = 19) -> datetime:
    return (datetime.now(SP) + timedelta(days=1)).replace(hour=hora, minute=0, second=0,
                                                         microsecond=0)


@pytest.fixture
def cenario(client, db, dono):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    tiktok = criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd")
    youtube = criar_conta(client, h, perfil["id"], "youtube", "tavernanerdyt")
    corte = criar_corte(db, perfil["id"])
    return {"h": h, "perfil": perfil, "tiktok": tiktok, "youtube": youtube, "corte": corte}


def _criar(client, c, conta="tiktok", **body):
    body.setdefault("contaId", c[conta]["id"])
    return client.post(f"/api/cortes/{c['corte'].id}/postagens", headers=c["h"], json=body)


def test_criar_rascunho_e_agendado(client, cenario):
    c = cenario
    r = _criar(client, c, titulo="  Atalho secreto  ", hashtags=["Dica", "#tecnologia"])
    assert r.status_code == 201, r.text
    p = r.json()["postagem"]
    assert p["estado"] == "rascunho" and p["plannedAt"] is None
    assert p["titulo"] == "Atalho secreto" and p["hashtags"] == ["#Dica", "#tecnologia"]
    assert p["conta"] == {"id": c["tiktok"]["id"], "platform": "tiktok", "platformName": "",
                          "handle": "tavernanerd"}
    assert p["version"] == 1 and p["lembrado"] is False and p["archived"] is False

    quando = _amanha()
    r = _criar(client, c, conta="youtube", plannedAt=quando.isoformat())
    assert r.status_code == 201, r.text
    p = r.json()["postagem"]
    assert p["estado"] == "agendado"
    assert datetime.fromisoformat(p["plannedAt"]) == quando
    assert p["plannedAt"].endswith("-03:00")  # devolvido em APP_TZ


def test_hora_sem_offset_e_local(client, cenario):
    quando = _amanha(8).replace(tzinfo=None)
    r = _criar(client, cenario, plannedAt=quando.isoformat())
    assert r.status_code == 201, r.text
    assert datetime.fromisoformat(r.json()["postagem"]["plannedAt"]) == quando.replace(
        tzinfo=SP)


def test_duas_contas_postagens_independentes(client, cenario):
    """US5-5 (Q2 = A): cada conta com textos, data e "Postado" próprios."""
    c = cenario
    a = _criar(client, c, titulo="No TikTok").json()["postagem"]
    b = _criar(client, c, conta="youtube", titulo="No YouTube",
               plannedAt=_amanha().isoformat()).json()["postagem"]
    r = client.post(f"/api/postagens/{a['id']}/postado", headers=c["h"],
                    json={"version": 1, "postedUrl": "https://www.tiktok.com/@x/video/1"})
    assert r.status_code == 200, r.text
    assert r.json()["postagem"]["estado"] == "postado"
    assert r.json()["postagem"]["postedAt"] is not None
    outra = client.get(f"/api/postagens/{b['id']}", headers=c["h"]).json()["postagem"]
    assert outra["estado"] == "agendado" and outra["titulo"] == "No YouTube"
    lista = client.get(f"/api/cortes/{c['corte'].id}/postagens", headers=c["h"]).json()
    assert {p["titulo"] for p in lista["items"]} == {"No TikTok", "No YouTube"}


def test_postagem_exists_so_entre_ativas(client, cenario):
    c = cenario
    p = _criar(client, c).json()["postagem"]
    r = _criar(client, c)
    assert r.status_code == 409 and r.json()["error"]["code"] == "postagem_exists"
    assert client.post(f"/api/postagens/{p['id']}/archive", headers=c["h"],
                       json={"version": 1}).status_code == 200
    novo = _criar(client, c)
    assert novo.status_code == 201, novo.text
    # Restaurar a arquivada viraria a segunda ativa: 409.
    r = client.post(f"/api/postagens/{p['id']}/restore", headers=c["h"], json={"version": 2})
    assert r.status_code == 409 and r.json()["error"]["code"] == "postagem_exists"


def test_conta_precisa_ser_do_perfil_e_ativa(client, db, cenario):
    c = cenario
    outro = criar_perfil(client, c["h"], "Outro")
    conta_outro = criar_conta(client, c["h"], outro["id"])
    r = _criar(client, c, contaId=conta_outro["id"])
    assert r.status_code == 400 and "perfil do corte" in r.json()["error"]["message"]
    client.post(f"/api/contas/{c['youtube']['id']}/archive", headers=c["h"], json={"version": 1})
    r = _criar(client, c, conta="youtube")
    assert r.status_code == 400 and "arquivada" in r.json()["error"]["message"]


def test_agendar_exige_corte_pronto(client, db, cenario):
    c = cenario
    revisao = criar_corte(db, c["perfil"]["id"], CorteStatus.revisao, hook_text="")
    url = f"/api/cortes/{revisao.id}/postagens"
    r = client.post(url, headers=c["h"], json={"contaId": c["tiktok"]["id"],
                                               "plannedAt": _amanha().isoformat()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "corte_not_ready"
    # Rascunho em revisão pode.
    r = client.post(url, headers=c["h"], json={"contaId": c["tiktok"]["id"], "titulo": "x"})
    assert r.status_code == 201, r.text
    p = r.json()["postagem"]
    r = client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                     json={"version": 1, "plannedAt": _amanha().isoformat()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "corte_not_ready"


def test_planned_in_past_com_tolerancia(client, cenario):
    c = cenario
    r = _criar(client, c, plannedAt=(datetime.now(UTC) - timedelta(minutes=5)).isoformat())
    assert r.status_code == 400 and r.json()["error"]["code"] == "planned_in_past"
    r = _criar(client, c, plannedAt=(datetime.now(UTC) - timedelta(seconds=20)).isoformat())
    assert r.status_code == 201, r.text  # dentro da tolerância de 1 min


@pytest.mark.parametrize(("hashtags", "ok"), [
    (["#a", "#b", "#c", "#d", "#e", "#f", "#g", "#h"], True),
    (["#a", "#b", "#c", "#d", "#e", "#f", "#g", "#h", "#i"], False),
    (["#com espaço"], False),
    (["#pontuação!"], False),
    (["#" + "x" * 51], False),
    (["#ação_2"], True),
    ([], True),
])
def test_limites_das_hashtags(client, cenario, hashtags, ok):
    r = _criar(client, cenario, hashtags=hashtags)
    assert (r.status_code == 201) is ok, r.text
    if not ok:
        assert r.json()["error"]["code"] == "validation_error"


def test_limites_de_titulo_e_descricao(client, cenario):
    assert _criar(client, cenario, titulo="x" * 101).status_code == 400
    assert _criar(client, cenario, descricao="x" * 2001).status_code == 400
    assert _criar(client, cenario, titulo="x" * 100, descricao="y" * 2000).status_code == 201


def test_patch_remarca_volta_a_rascunho_e_zera_lembrete(client, db, cenario):
    c = cenario
    p = _criar(client, c, plannedAt=_amanha().isoformat()).json()["postagem"]
    db.query(Postagem).filter_by(id=p["id"]).update({"lembrado_em": datetime.now(UTC)})
    db.commit()
    assert client.get(f"/api/postagens/{p['id']}", headers=c["h"]).json()["postagem"][
        "lembrado"] is True
    r = client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                     json={"version": 1, "plannedAt": _amanha(21).isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["postagem"]["lembrado"] is False
    r = client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                     json={"version": 2, "titulo": "Só o título"})
    assert r.json()["postagem"]["estado"] == "agendado"  # plannedAt ausente não muda
    r = client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                     json={"version": 3, "plannedAt": None})
    assert r.json()["postagem"]["estado"] == "rascunho"
    assert r.json()["postagem"]["plannedAt"] is None
    r = client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                     json={"version": 3, "titulo": "velha"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


def test_postado_por_qualquer_usuario_e_depois_nao_edita(client, cenario, membro):  # noqa: F811
    c = cenario
    user, hm = membro
    p = _criar(client, c).json()["postagem"]
    r = client.post(f"/api/postagens/{p['id']}/postado", headers=hm, json={"version": 1})
    assert r.status_code == 200, r.text
    assert r.json()["postagem"]["postedUrl"] is None
    assert r.json()["postagem"]["updatedBy"]["id"] == str(user.id)
    r = client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                     json={"version": 2, "titulo": "depois"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    r = client.post(f"/api/postagens/{p['id']}/postado", headers=c["h"], json={"version": 2})
    assert r.status_code == 409
    r = client.post(f"/api/postagens/{p['id']}/revert", headers=c["h"],
                    json={"version": 2, "toVersion": 1})
    assert r.status_code == 409  # revert não desfaz postado


def test_postado_url_invalida(client, cenario):
    p = _criar(client, cenario).json()["postagem"]
    r = client.post(f"/api/postagens/{p['id']}/postado", headers=cenario["h"],
                    json={"version": 1, "postedUrl": "javascript:alert(1)"})
    assert r.status_code == 400


def test_versoes_historico_dos_textos(client, db, cenario):
    """US5-2: cada edição fica no histórico, com autor e antes/depois."""
    c = cenario
    p = _criar(client, c, titulo="v1").json()["postagem"]
    client.patch(f"/api/postagens/{p['id']}", headers=c["h"], json={"version": 1, "titulo": "v2"})
    client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                 json={"version": 2, "hashtags": ["#nova"]})
    r = client.get(f"/api/postagens/{p['id']}/versions", headers=c["h"])
    items = r.json()["items"]
    assert [v["action"] for v in items] == ["updated", "updated", "created"]
    assert items[1]["before"]["titulo"] == "v1" and items[1]["after"]["titulo"] == "v2"
    assert items[0]["changedFields"] == ["hashtags"]
    assert items[0]["actor"]["name"] == "Dono"
    # Sem mudança, sem versão nova.
    r = client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                     json={"version": 3, "titulo": "v2"})
    assert r.json()["postagem"]["version"] == 3
    assert db.query(EntityVersion).filter_by(entity_type="postagem").count() == 3


def test_revert_so_dono(client, cenario, membro):  # noqa: F811
    c = cenario
    _, hm = membro
    p = _criar(client, c, titulo="original").json()["postagem"]
    client.patch(f"/api/postagens/{p['id']}", headers=c["h"],
                 json={"version": 1, "titulo": "mudado", "contaId": c["youtube"]["id"]})
    r = client.post(f"/api/postagens/{p['id']}/revert", headers=hm,
                    json={"version": 2, "toVersion": 1})
    assert r.status_code == 403
    r = client.post(f"/api/postagens/{p['id']}/revert", headers=c["h"],
                    json={"version": 2, "toVersion": 1})
    assert r.status_code == 200, r.text
    post = r.json()["postagem"]
    assert post["titulo"] == "original" and post["conta"]["id"] == c["tiktok"]["id"]
    assert post["version"] == 3


def test_archive_restore(client, cenario):
    c = cenario
    p = _criar(client, c).json()["postagem"]
    r = client.post(f"/api/postagens/{p['id']}/archive", headers=c["h"], json={"version": 1})
    assert r.json()["postagem"]["archived"] is True
    assert client.post(f"/api/postagens/{p['id']}/archive", headers=c["h"],
                       json={"version": 2}).status_code == 409
    r = client.post(f"/api/postagens/{p['id']}/restore", headers=c["h"], json={"version": 2})
    assert r.json()["postagem"]["archived"] is False
    ativos = client.get(f"/api/cortes/{c['corte'].id}/postagens?archived=false",
                        headers=c["h"]).json()["items"]
    assert len(ativos) == 1


def test_resumos_por_corte(client, db, cenario):
    from sociman_api.postagem.service import resumos_por_corte

    c = cenario
    _criar(client, c, plannedAt=_amanha().isoformat())
    arq = _criar(client, c, conta="youtube").json()["postagem"]
    client.post(f"/api/postagens/{arq['id']}/archive", headers=c["h"], json={"version": 1})
    out = resumos_por_corte(db, [c["corte"].id])
    [resumo] = out[c["corte"].id]
    assert resumo.plataforma == "tiktok" and resumo.estado == "agendado"


# ---- calendário ----

def test_calendario_por_dia_local_perfil_e_plataforma(client, db, cenario):
    c = cenario
    amanha = _amanha(23)  # 23:00 em SP = 02:00 UTC do dia seguinte: tem de cair no dia local
    _criar(client, c, plannedAt=amanha.isoformat(), titulo="Tarde da noite")
    _criar(client, c, conta="youtube", plannedAt=(amanha + timedelta(days=3)).isoformat())
    outro = criar_perfil(client, c["h"], "Outro")
    conta2 = criar_conta(client, c["h"], outro["id"])
    corte2 = criar_corte(db, outro["id"])
    client.post(f"/api/cortes/{corte2.id}/postagens", headers=c["h"],
                json={"contaId": conta2["id"], "plannedAt": amanha.isoformat()})

    dia = amanha.date().isoformat()
    r = client.get("/api/calendario", headers=c["h"], params={"de": dia, "ate": dia})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 2
    it = next(i for i in items if i["titulo"] == "Tarde da noite")
    assert it["corte"]["id"] == str(c["corte"].id) and it["corte"]["status"] == "pronto"
    assert it["perfil"]["name"] == "A Taverna Nerd" and it["conta"]["platform"] == "tiktok"

    r = client.get("/api/calendario", headers=c["h"],
                   params={"de": dia, "ate": dia, "perfilId": c["perfil"]["id"]})
    assert [i["titulo"] for i in r.json()["items"]] == ["Tarde da noite"]
    fim = (amanha + timedelta(days=5)).date().isoformat()
    r = client.get("/api/calendario", headers=c["h"],
                   params={"de": dia, "ate": fim, "plataforma": "youtube"})
    assert [i["conta"]["platform"] for i in r.json()["items"]] == ["youtube"]


def test_calendario_sem_data(client, db, cenario):
    c = cenario
    livre = criar_corte(db, c["perfil"]["id"], openshorts_title="Clipe livre")
    criar_corte(db, c["perfil"]["id"], CorteStatus.revisao, hook_text="")  # não está pronto
    _criar(client, c, plannedAt=_amanha().isoformat())  # c["corte"] tem agendada
    dia = datetime.now(SP).date().isoformat()
    r = client.get("/api/calendario", headers=c["h"], params={"de": dia, "ate": dia})
    sem = r.json()["semData"]
    assert [s["corteId"] for s in sem] == [str(livre.id)]
    assert sem[0]["titulo"] == "Clipe livre"


def test_calendario_cor_do_perfil_pela_paleta(client, db, cenario):
    """R14: a cor do perfil é a 1ª cor da paleta do kit; sem kit salvo, `cor` vem null."""
    c = cenario
    livre = criar_corte(db, c["perfil"]["id"], openshorts_title="Clipe livre")
    _criar(client, c, plannedAt=_amanha().isoformat())
    dia = _amanha().date().isoformat()
    hoje = datetime.now(SP).date().isoformat()

    r = client.get("/api/calendario", headers=c["h"], params={"de": hoje, "ate": dia})
    assert r.json()["items"][0]["perfil"]["cor"] is None
    assert r.json()["semData"][0]["perfilCor"] is None

    db.add(BrandKit(perfil_id=uuid.UUID(c["perfil"]["id"]),
                    palette=[{"chave": "rosa", "nome": "Rosa", "valor": "#ff5fa2"},
                             {"chave": "preto", "nome": "Preto", "valor": "#000000"}],
                    caption={}, hook={}, watermark={}, end_card={}))
    db.commit()
    r = client.get("/api/calendario", headers=c["h"], params={"de": hoje, "ate": dia})
    assert r.json()["items"][0]["perfil"]["cor"] == "#FF5FA2"
    sem = r.json()["semData"]
    assert [s["corteId"] for s in sem] == [str(livre.id)] and sem[0]["perfilCor"] == "#FF5FA2"


@pytest.mark.parametrize("params", [
    {"de": "2026-10-10", "ate": "2026-10-01"},
    {"de": "2026-10-01", "ate": "2026-12-15"},
    {"de": "2026-10-01"},
])
def test_calendario_intervalo_invalido(client, cenario, params):
    r = client.get("/api/calendario", headers=cenario["h"], params=params)
    assert r.status_code == 400
