"""Temas do perfil (spec 023, T022; FR-001, FR-002, FR-007): CRUD com histórico, nome único sem
acento, máximo de 30, juntar e reverter, arquivar (reclassificar), a versão da taxonomia, a
proposta da IA (nada salvo) e o membro que só lê."""

import uuid

from fakes.anthropic_fake import anthropic_fake  # noqa: F401
from sqlalchemy import func, select

from integration.analytics_helpers import cena  # noqa: F401
from integration.aprendizado_helpers import ap, err, fake, membro  # noqa: F401
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado.models import Classificacao, Origem, Tema
from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaChamada, IaDesfecho


def _versoes(db, entity_type, entity_id) -> list[EntityVersion]:
    db.expire_all()
    return list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == entity_type,
        EntityVersion.entity_id == uuid.UUID(str(entity_id))).order_by(EntityVersion.version)))


def _class(db, video_id) -> Classificacao:
    db.expire_all()
    return db.scalar(select(Classificacao).where(Classificacao.video_id == video_id))


def test_criar_editar_e_nome_repetido_sem_acento(ap):  # noqa: F811
    t = ap.tema("Animação", ["Animação", "  desenho ", "animacao"])
    assert t["palavrasChave"] == ["animacao", "desenho"] and t["version"] == 1
    r = ap.client.post(f"{ap.url}/temas", headers=ap.h, json={"nome": "animacao"})
    assert r.status_code == 409 and err(r) == "tema_repetido"
    r = ap.client.patch(f"/api/aprendizado/temas/{t['id']}", headers=ap.h,
                        json={"version": 1, "descricao": "Desenhos e anime"})
    assert r.status_code == 200 and r.json()["version"] == 2
    r = ap.client.patch(f"/api/aprendizado/temas/{t['id']}", headers=ap.h,
                        json={"version": 1, "nome": "Outro"})
    assert r.status_code == 409 and err(r) == "version_conflict"
    lista = ap.get("temas")
    assert [x["nome"] for x in lista["items"]] == ["Animação"]
    assert lista["taxonomiaVersao"] == 2
    assert [v.action for v in _versoes(ap.db, "aprendizado_tema", t["id"])] == [
        "created", "updated"]
    r = ap.client.post(f"{ap.url}/temas", headers=ap.h,
                       json={"nome": "X", "palavrasChave": ["a"]})
    assert r.status_code == 400  # palavra com menos de 2 caracteres


def test_31o_tema_recusado(ap):  # noqa: F811
    r = ap.client.post(f"{ap.url}/temas/lote", headers=ap.h,
                       json={"temas": [{"nome": f"Tema {i}"} for i in range(K.MAX_TEMAS)]})
    assert r.status_code == 201, r.text
    r = ap.client.post(f"{ap.url}/temas", headers=ap.h, json={"nome": "Mais um"})
    assert r.status_code == 409 and err(r) == "temas_no_maximo"
    r = ap.client.post(f"{ap.url}/temas/lote", headers=ap.h, json={"temas": [{"nome": "A"}]})
    assert r.status_code == 409 and err(r) == "temas_no_maximo"


def test_juntar_e_reverter_movem_as_classificacoes(ap):  # noqa: F811
    marvel, mcu = ap.tema("Marvel"), ap.tema("MCU")
    v1, v2 = ap.post(dias=3), ap.post(dias=4)
    ap.classificar(v1, "MCU")
    ap.classificar(v2, "Marvel")
    c2 = _class(ap.db, v2)
    c2.secundarios = [uuid.UUID(mcu["id"])]
    ap.db.commit()
    r = ap.client.post(f"/api/aprendizado/temas/{mcu['id']}/juntar", headers=ap.h,
                       json={"version": 1, "destinoId": marvel["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["movidas"] == 1 and body["origem"]["archived"]
    assert body["origem"]["juntadoEmId"] == marvel["id"] and body["destino"]["nPosts"] == 2
    assert str(_class(ap.db, v1).tema_id) == marvel["id"]
    assert _class(ap.db, v2).secundarios == []  # o secundário virou o principal
    versao = ap.get("temas")["taxonomiaVersao"]

    r = ap.client.post(f"/api/aprendizado/temas/{mcu['id']}/revert", headers=ap.h,
                       json={"version": body["origem"]["version"], "toVersion": 1})
    assert r.status_code == 200, r.text
    assert not r.json()["archived"] and r.json()["juntadoEmId"] is None
    assert str(_class(ap.db, v1).tema_id) == mcu["id"]
    assert _class(ap.db, v2).secundarios == [uuid.UUID(mcu["id"])]
    assert ap.get("temas")["taxonomiaVersao"] == versao + 1
    acoes = [v.action for v in _versoes(ap.db, "aprendizado_classificacao", _class(ap.db, v1).id)]
    assert acoes[-2:] == ["updated", "updated"]


def test_arquivar_manda_para_sem_tema_e_restaurar_devolve(ap):  # noqa: F811
    t = ap.tema("Games")
    v_ia, v_dono = ap.post(dias=3), ap.post(dias=4)
    ap.classificar(v_ia, "Games")
    ap.classificar(v_dono, "Games", origem=Origem.dono)
    r = ap.client.post(f"/api/aprendizado/temas/{t['id']}/archive", headers=ap.h,
                       json={"version": 1})
    assert r.status_code == 200 and r.json()["archived"]
    c_ia, c_dono = _class(ap.db, v_ia), _class(ap.db, v_dono)
    assert c_ia.tema_id is None and c_ia.reclassificar
    assert c_dono.tema_id is None and not c_dono.reclassificar and c_dono.origem == Origem.dono
    assert ap.get("temas")["items"] == [] and len(ap.get("temas", arquivados=True)["items"]) == 1
    r = ap.client.post(f"/api/aprendizado/temas/{t['id']}/restore", headers=ap.h,
                       json={"version": 2})
    assert r.status_code == 200, r.text
    assert str(_class(ap.db, v_ia).tema_id) == t["id"] and not _class(ap.db, v_ia).reclassificar
    assert str(_class(ap.db, v_dono).tema_id) == t["id"]


def test_membro_so_le(ap, membro):  # noqa: F811
    t = ap.tema("Marvel")
    _, hm = membro
    assert ap.get("temas", h=hm)["items"][0]["id"] == t["id"]
    for metodo, url, corpo in (
            ("post", f"{ap.url}/temas", {"nome": "X"}),
            ("post", f"{ap.url}/temas/lote", {"temas": [{"nome": "X"}]}),
            ("patch", f"/api/aprendizado/temas/{t['id']}", {"version": 1, "nome": "Y"}),
            ("post", f"/api/aprendizado/temas/{t['id']}/archive", {"version": 1}),
            ("post", f"{ap.url}/taxonomia/propor", {})):
        r = ap.client.request(metodo, url, headers=hm, json=corpo)
        assert r.status_code == 403 and err(r) == "somente_dono", (url, r.text)
    r = ap.client.get(f"/api/aprendizado/temas/{t['id']}/versions", headers=hm)
    assert r.status_code == 200 and r.json()["items"][0]["action"] == "created"


def test_proposta_da_ia_nao_salva_e_o_lote_marca_a_chamada(ap, fake):  # noqa: F811
    ap.post(dias=3, legenda="Vingadores #marvel #marvel #geek")
    r = ap.client.post(f"{ap.url}/taxonomia/propor", headers=ap.h, json={"instrucao": ""})
    assert r.status_code == 200, r.text
    prop = r.json()
    assert 3 <= len(prop["temas"]) <= 15 and prop["custoUsd"] is not None
    assert ap.db.scalar(select(func.count()).select_from(Tema)) == 0
    chamada = ap.db.get(IaChamada, uuid.UUID(prop["chamadaId"]))
    assert chamada.tipo_campo == "aprendizado.taxonomia" and chamada.desfecho == IaDesfecho.sem_acao
    assert '<post id="' in fake.bodies[0]["messages"][0]["content"]
    temas = prop["temas"]
    r = ap.client.post(f"{ap.url}/temas/lote", headers=ap.h,
                       json={"temas": temas, "chamadaId": prop["chamadaId"]})
    assert r.status_code == 201, r.text
    ap.db.expire_all()
    assert ap.db.get(IaChamada, chamada.id).desfecho == IaDesfecho.aplicada
    [v] = _versoes(ap.db, "aprendizado_tema", r.json()["items"][0]["id"])
    assert v.details["ia"][0]["chamadaId"] == prop["chamadaId"]


def test_proposta_sem_chave_grava_o_erro(ap):  # noqa: F811
    from sociman_api.ia.cliente import get_ia_client
    from sociman_api.main import app

    app.dependency_overrides[get_ia_client] = lambda: None
    r = ap.client.post(f"{ap.url}/taxonomia/propor", headers=ap.h, json={})
    assert r.status_code == 503 and err(r) == "claude_unconfigured"
    [row] = ap.db.scalars(select(IaChamada)).all()
    assert row.erro_code == "unconfigured" and row.desfecho == IaDesfecho.erro
