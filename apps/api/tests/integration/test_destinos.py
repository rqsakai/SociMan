"""Destinos: aprovação, pedido, recusa, lote e histórico (spec 014, US2, R3 e R5).

Nada é publicado: o destino só registra decisões humanas."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from integration.postagem_helpers import (  # noqa: F401
    acao,
    add_destino,
    aprovado,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.cortes.models import CorteStatus
from sociman_api.history import EntityVersion
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo
from sociman_api.postagem.models import DestinoEstado, Postagem


@pytest.fixture
def c(client, db, dono, membro):  # noqa: F811
    _, h = dono
    _, hm = membro
    perfil = criar_perfil(client, h)
    outro = criar_perfil(client, h, "Queridinhos")
    return {
        "h": h, "hm": hm, "dono": dono[0], "membro": membro[0], "perfil": perfil,
        "tiktok": criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd"),
        "youtube": criar_conta(client, h, perfil["id"], "youtube", "tavernanerdyt"),
        "alheia": criar_conta(client, h, outro["id"], "tiktok", "queridinhos"),
        "corte": criar_corte(db, perfil["id"]),
    }


def _versoes(db, destino_id) -> list[EntityVersion]:
    db.expire_all()
    return list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "postagem",
        EntityVersion.entity_id == uuid.UUID(str(destino_id)),
    ).order_by(EntityVersion.version)))


def _err(r) -> str:
    return r.json()["error"]["code"]


# ---- criar ----

def test_add_destino_pendente(client, c):
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["hm"],
                    json={"contaId": c["tiktok"]["id"], "titulo": " Oi ", "hashtags": ["Dica"]})
    assert r.status_code == 201, r.text
    d = r.json()["destino"]
    assert d["estado"] == "pendente" and d["estadoEfetivo"] == "pronto"
    assert d["conteudoId"] == str(c["corte"].id)
    assert d["titulo"] == "Oi" and d["hashtags"] == ["#Dica"]
    assert d["modo"] == "lembrete" and d["plannedAt"] is None
    assert d["aprovacao"] is None and d["pedido"] is None and d["recusa"] is None
    assert d["conta"]["status"] == "ativa" and d["version"] == 1


def test_add_destino_erros(client, db, c):
    url = f"/api/conteudos/{c['corte'].id}/destinos"
    r = client.post(url, headers=c["h"], json={"contaId": c["alheia"]["id"]})
    assert r.status_code == 400 and _err(r) == "conta_invalida"
    add_destino(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = client.post(url, headers=c["h"], json={"contaId": c["tiktok"]["id"]})
    assert r.status_code == 409 and _err(r) == "destino_exists"
    r = client.post(f"/api/contas/{c['youtube']['id']}/archive", headers=c["h"],
                    json={"version": c["youtube"]["version"]})
    assert r.status_code == 200
    r = client.post(url, headers=c["h"], json={"contaId": c["youtube"]["id"]})
    assert r.status_code == 400 and _err(r) == "conta_invalida"
    arquivado = criar_corte(db, c["perfil"]["id"], archived_at=datetime.now(UTC))
    r = client.post(f"/api/conteudos/{arquivado.id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"]})
    assert r.status_code == 409 and _err(r) == "conflict"
    r = client.post(f"/api/conteudos/{uuid.uuid4()}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"]})
    assert r.status_code == 404


def test_rascunho_em_revisao_permitido_mas_aparece_em_revisao(client, db, c):
    corte = criar_corte(db, c["perfil"]["id"], status=CorteStatus.revisao)
    d = add_destino(client, c["h"], corte.id, c["tiktok"]["id"])
    assert d["estado"] == "pendente" and d["estadoEfetivo"] == "em_revisao"


# ---- pedir, aprovar, recusar ----

def test_membro_pede_dono_aprova(client, db, c):
    d = add_destino(client, c["hm"], c["corte"].id, c["tiktok"]["id"])
    r = acao(client, c["hm"], d, "pedir-aprovacao", nota="Pode ir hoje?")
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["estado"] == "aprovacao_pedida"
    assert d["pedido"]["por"]["id"] == str(c["membro"].id) and d["pedido"]["nota"] == "Pode ir hoje?"

    notas = db.scalars(select(Notificacao).where(
        Notificacao.tipo == NotificacaoTipo.aprovacao_pedida)).all()
    assert {n.user_id for n in notas} == {c["dono"].id}  # só os donos ativos
    n = notas[0]
    assert n.dedupe_key == f"aprovacao_pedida:{d['id']}:{d['version']}"
    assert n.link == f"/app/conteudos/{c['corte'].id}?conta={c['tiktok']['id']}"
    assert n.titulo.startswith("Aprovação pedida: ") and n.titulo.endswith(" no TikTok")

    # membro não aprova (403), dono aprova
    assert acao(client, c["hm"], d, "aprovar").status_code == 403
    r = acao(client, c["h"], d, "aprovar")
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["estado"] == "aprovado" and d["aprovacao"]["por"]["id"] == str(c["dono"].id)
    assert d["pedido"] is None and d["recusa"] is None and d["videoMudou"] is False
    row = db.get(Postagem, uuid.UUID(d["id"]))
    assert row.aprovado_video_ref == c["corte"].result_key

    resp = db.scalars(select(Notificacao).where(
        Notificacao.tipo == NotificacaoTipo.aprovacao_respondida)).all()
    assert [n.user_id for n in resp] == [c["membro"].id]

    acoes = [v.details.get("acao") for v in _versoes(db, d["id"])]
    assert acoes == [None, "aprovacao_pedida", "aprovado"]
    assert [v.actor_user_id for v in _versoes(db, d["id"])][1:] == [c["membro"].id, c["dono"].id]


def test_pedir_so_de_pendente(client, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = acao(client, c["hm"], d, "pedir-aprovacao")
    assert r.status_code == 409 and _err(r) == "conflict"


def test_pedir_e_aprovar_exigem_conteudo_pronto(client, db, c):
    corte = criar_corte(db, c["perfil"]["id"], status=CorteStatus.revisao)
    d = add_destino(client, c["h"], corte.id, c["tiktok"]["id"])
    r = acao(client, c["h"], d, "aprovar")
    assert r.status_code == 409 and _err(r) == "conteudo_nao_pronto"
    assert r.json()["error"]["message"] == "Aplique a marca antes de aprovar"
    r = acao(client, c["hm"], d, "pedir-aprovacao")
    assert r.status_code == 409 and _err(r) == "conteudo_nao_pronto"


def test_recusar_com_motivo(client, db, c):
    d = add_destino(client, c["hm"], c["corte"].id, c["tiktok"]["id"])
    d = acao(client, c["hm"], d, "pedir-aprovacao").json()["destino"]
    r = acao(client, c["h"], d, "recusar")
    assert r.status_code == 400
    r = acao(client, c["h"], d, "recusar", motivo="   ")
    assert r.status_code == 400
    assert acao(client, c["hm"], d, "recusar", motivo="não").status_code == 403
    r = acao(client, c["h"], d, "recusar", motivo="Áudio estourado")
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["estado"] == "pendente" and d["estadoEfetivo"] == "pronto"
    assert d["recusa"]["motivo"] == "Áudio estourado" and d["pedido"] is None
    resp = db.scalars(select(Notificacao).where(
        Notificacao.tipo == NotificacaoTipo.aprovacao_respondida)).all()
    assert [n.user_id for n in resp] == [c["membro"].id]
    assert "Áudio estourado" in resp[0].corpo
    # a recusa fica visível até a próxima aprovação
    d = acao(client, c["h"], d, "aprovar").json()["destino"]
    assert d["recusa"] is None


def test_recusar_aprovado_e_nao_agendado(client, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = acao(client, c["h"], d, "recusar", motivo="mudei de ideia")
    assert r.status_code == 200 and r.json()["destino"]["estado"] == "pendente"


def test_textos_depois_da_aprovacao_nao_desfazem(client, db, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = client.patch(f"/api/destinos/{d['id']}", headers=c["hm"],
                     json={"version": d["version"], "titulo": "Novo", "hashtags": ["a1"]})
    assert r.status_code == 200, r.text
    d2 = r.json()["destino"]
    assert d2["estado"] == "aprovado" and d2["titulo"] == "Novo"
    assert d2["aprovacao"] == d["aprovacao"]
    assert _versoes(db, d["id"])[-1].changed_fields == ["titulo", "hashtags"]
    r = client.patch(f"/api/destinos/{d['id']}", headers=c["hm"],
                     json={"version": d["version"], "titulo": "x"})
    assert r.status_code == 409 and _err(r) == "version_conflict"


def test_postado_so_de_aprovado_ou_agendado(client, c):
    d = add_destino(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    assert acao(client, c["h"], d, "postado").status_code == 409
    d = acao(client, c["h"], d, "aprovar").json()["destino"]
    r = acao(client, c["hm"], d, "postado", postedUrl="https://www.tiktok.com/@x/video/1")
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["estado"] == "postado" and d["postedUrl"].endswith("/1") and d["postedAt"]
    r = client.patch(f"/api/destinos/{d['id']}", headers=c["h"],
                     json={"version": d["version"], "titulo": "x"})
    assert r.status_code == 409 and _err(r) == "conflict"


def test_video_mudou(client, db, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    corte = db.get(type(c["corte"]), c["corte"].id)
    corte.result_key = f"{corte.result_key}.novo"
    db.commit()
    r = client.get(f"/api/destinos/{d['id']}", headers=c["h"])
    assert r.status_code == 200 and r.json()["destino"]["videoMudou"] is True
    r = client.get(f"/api/conteudos/{c['corte'].id}", headers=c["h"])
    if r.status_code == 200:  # rota da trilha A
        assert r.json()["conteudo"]["destinos"][0]["videoMudou"] is True


def test_archive_restore_e_versions(client, db, c):
    d = add_destino(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = acao(client, c["hm"], d, "archive")
    assert r.status_code == 200 and r.json()["destino"]["archived"] is True
    d = r.json()["destino"]
    assert d["estadoEfetivo"] == "arquivado"
    add_destino(client, c["h"], c["corte"].id, c["tiktok"]["id"])  # a arquivada não conta
    r = acao(client, c["hm"], d, "restore")
    assert r.status_code == 409 and _err(r) == "destino_exists"
    r = client.get(f"/api/destinos/{d['id']}/versions", headers=c["hm"])
    assert r.status_code == 200 and [v["action"] for v in r.json()["items"]] == [
        "archived", "created"]


# ---- reversão ----

def test_revert_so_dono_e_nunca_restaura_aprovacao(client, db, c):
    d = add_destino(client, c["h"], c["corte"].id, c["tiktok"]["id"], titulo="v1")
    d = acao(client, c["h"], d, "aprovar").json()["destino"]  # v2
    d = client.patch(f"/api/destinos/{d['id']}", headers=c["h"],
                     json={"version": d["version"], "titulo": "v3"}).json()["destino"]
    d = acao(client, c["h"], d, "recusar", motivo="não").json()["destino"]  # v4: pendente
    d = client.patch(f"/api/destinos/{d['id']}", headers=c["h"],
                     json={"version": d["version"], "titulo": "v5"}).json()["destino"]
    body = {"version": d["version"], "toVersion": 3}
    r = client.post(f"/api/destinos/{d['id']}/revert", headers=c["hm"], json=body)
    assert r.status_code == 403
    r = client.post(f"/api/destinos/{d['id']}/revert", headers=c["h"], json=body)
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["titulo"] == "v3" and d["estado"] == "pendente" and d["aprovacao"] is None


def test_revert_de_versao_da_006_sem_campos_novos(client, db, c):
    d = add_destino(client, c["h"], c["corte"].id, c["tiktok"]["id"], titulo="v1")
    v1 = _versoes(db, d["id"])[0]
    v1.after = {"conta_id": c["tiktok"]["id"], "titulo": "da 006", "descricao": "",
                "hashtags": [], "estado": "rascunho", "planned_at": None, "posted_url": None,
                "archived": False}
    db.commit()
    d = client.patch(f"/api/destinos/{d['id']}", headers=c["h"],
                     json={"version": d["version"], "titulo": "v2"}).json()["destino"]
    r = client.post(f"/api/destinos/{d['id']}/revert", headers=c["h"],
                    json={"version": d["version"], "toVersion": 1})
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["titulo"] == "da 006" and d["estado"] == "pendente" and d["modo"] == "lembrete"


def test_revert_nao_desfaz_postado(client, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    d = acao(client, c["h"], d, "postado").json()["destino"]
    r = client.post(f"/api/destinos/{d['id']}/revert", headers=c["h"],
                    json={"version": d["version"], "toVersion": 1})
    assert r.status_code == 409


# ---- lote ----

def test_lote_aprovar_cria_o_que_falta_e_lista_falhas(client, db, c):
    b = criar_corte(db, c["perfil"]["id"])
    revisao = criar_corte(db, c["perfil"]["id"], status=CorteStatus.revisao)
    existente = add_destino(client, c["h"], b.id, c["tiktok"]["id"])
    ids = [str(c["corte"].id), str(b.id), str(revisao.id), str(uuid.uuid4())]
    body = {"contaId": c["tiktok"]["id"], "conteudoIds": ids}
    assert client.post("/api/destinos/lote/aprovar", headers=c["hm"], json=body).status_code == 403
    r = client.post("/api/destinos/lote/aprovar", headers=c["h"], json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert {d["conteudoId"] for d in out["ok"]} == {str(c["corte"].id), str(b.id)}
    assert all(d["estado"] == "aprovado" for d in out["ok"])
    falhas = {f["conteudoId"]: f["code"] for f in out["falhas"]}
    assert falhas[str(revisao.id)] == "conteudo_nao_pronto"
    assert falhas[ids[3]] == "not_found"
    assert existente["id"] in {d["id"] for d in out["ok"]}
    lotes = {v.details.get("loteId") for d in out["ok"] for v in _versoes(db, d["id"])
             if v.details.get("acao") == "lote"}
    assert len(lotes) == 1 and None not in lotes
    # o conteúdo em revisão não ganhou destino aprovado
    assert db.scalar(select(Postagem).where(Postagem.conteudo_id == revisao.id,
                                            Postagem.estado == DestinoEstado.aprovado)) is None


def test_lote_pedir_aprovacao(client, db, c):
    b = criar_corte(db, c["perfil"]["id"])
    r = client.post("/api/destinos/lote/pedir-aprovacao", headers=c["hm"], json={
        "contaId": c["tiktok"]["id"], "conteudoIds": [str(c["corte"].id), str(b.id)],
        "nota": "semana que vem"})
    assert r.status_code == 200, r.text
    assert [d["estado"] for d in r.json()["ok"]] == ["aprovacao_pedida"] * 2
    assert db.query(Notificacao).filter_by(tipo=NotificacaoTipo.aprovacao_pedida).count() == 2


def test_lote_limites_e_conta_invalida(client, c):
    r = client.post("/api/destinos/lote/aprovar", headers=c["h"], json={
        "contaId": c["tiktok"]["id"], "conteudoIds": [str(uuid.uuid4())] * 101})
    assert r.status_code == 400
    r = client.post("/api/destinos/lote/aprovar", headers=c["h"], json={
        "contaId": c["tiktok"]["id"], "conteudoIds": []})
    assert r.status_code == 400
    r = client.post("/api/destinos/lote/aprovar", headers=c["h"], json={
        "contaId": str(uuid.uuid4()), "conteudoIds": [str(c["corte"].id)]})
    assert r.status_code == 400 and _err(r) == "conta_invalida"


# ---- limites dos textos (da 006) e resumos ----

@pytest.mark.parametrize(("hashtags", "ok"), [
    (["#a", "#b", "#c", "#d", "#e", "#f", "#g", "#h", "#i"], False),
    (["#com espaço"], False),
    (["#pontuação!"], False),
    (["#" + "x" * 51], False),
    (["#ação_2"], True),
    ([], True),
])
def test_limites_das_hashtags(client, c, hashtags, ok):
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], "hashtags": hashtags})
    assert (r.status_code == 201) is ok, r.text
    if not ok:
        assert _err(r) == "validation_error"


def test_limites_de_titulo_e_descricao(client, c):
    url = f"/api/conteudos/{c['corte'].id}/destinos"
    body = {"contaId": c["tiktok"]["id"]}
    assert client.post(url, headers=c["h"], json=body | {"titulo": "x" * 101}).status_code == 400
    assert client.post(url, headers=c["h"],
                       json=body | {"descricao": "x" * 2001}).status_code == 400
    assert client.post(url, headers=c["h"], json=body | {
        "titulo": "x" * 100, "descricao": "y" * 2000}).status_code == 201


def test_patch_nao_muda_conta(client, c):
    d = add_destino(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = client.patch(f"/api/destinos/{d['id']}", headers=c["h"],
                     json={"version": d["version"], "contaId": c["youtube"]["id"]})
    assert r.status_code == 400


def test_postado_url_invalida(client, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = acao(client, c["h"], d, "postado", postedUrl="javascript:alert(1)")
    assert r.status_code == 400


def test_resumos_por_conteudo(client, db, c):
    from sociman_api.postagem.service import resumos_por_conteudo

    aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    arq = add_destino(client, c["h"], c["corte"].id, c["youtube"]["id"])
    acao(client, c["h"], arq, "archive")
    out = resumos_por_conteudo(db, [c["corte"].id])
    [resumo] = out[c["corte"].id]
    assert resumo.conta.platform == "tiktok" and resumo.estado == "aprovado"
    assert resumo.estado_efetivo == "aprovado" and resumo.sem_textos is True
