"""Classificação e trilha `aprendizado` (spec 023, T023; FR-003 a FR-006, FR-051): pendentes
(< 24 h fica fora), limite diário contando erros, a correção do dono prevalece, id inválido →
"Sem tema" com sugestão, evidência parcial, classificação automática pausada, trilha ociosa sem
chave e o autor `system:aprendizado`."""

import uuid
from datetime import timedelta

from fakes.anthropic_fake import ID_INVALIDO, anthropic_fake, classificacao  # noqa: F401
from sqlalchemy import func, select

from integration.analytics_helpers import agora, cena  # noqa: F401
from integration.aprendizado_helpers import ap, err, fake, membro  # noqa: F401
from integration.postagem_helpers import criar_corte
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import trilha
from sociman_api.aprendizado.models import Classificacao, Origem
from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaChamada


def _rodar(ap, fake):  # noqa: F811
    trilha.rodar(ap.db, client=fake.ia_client())
    ap.db.expire_all()


def _class(ap, vid) -> Classificacao | None:  # noqa: F811
    ap.db.expire_all()
    return ap.db.scalar(select(Classificacao).where(Classificacao.video_id == vid))


def _chamadas(ap) -> int:  # noqa: F811
    ap.db.expire_all()
    return ap.db.scalar(select(func.count()).select_from(IaChamada).where(
        IaChamada.tipo_campo == "aprendizado.classificacao")) or 0


def test_pendentes_classificados_pela_trilha_com_autor_de_sistema(ap, fake):  # noqa: F811
    marvel = ap.tema("Marvel", ["marvel"])
    ap.tema("Games")
    velho = ap.post(dias=3, legenda="Os Vingadores da Marvel chegaram")
    novo = ap.post(publicado=agora() - timedelta(hours=5), legenda="Marvel de hoje")
    lista = ap.get("classificacoes", pendentes="true")
    assert [i["videoId"] for i in lista["items"]] == [str(velho)] and lista["pendentes"] == 1
    _rodar(ap, fake)
    c = _class(ap, velho)
    assert c is not None and str(c.tema_id) == marvel["id"] and c.origem == Origem.ia
    assert c.evidencia_parcial and c.estilo_gancho.value == "pergunta" and c.chamada_id
    assert _class(ap, novo) is None  # < 24 h
    v = ap.db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "aprendizado_classificacao")).one()
    assert v.actor_kind == "system:aprendizado" and v.actor_user_id is None
    assert "O post não tem corte" in fake.bodies[0]["messages"][0]["content"]
    lista = ap.get("classificacoes")
    assert lista["limiteHoje"] == {"usadas": 1, "limite": K.LIMITE_DIARIO}
    assert lista["items"][1]["temaNome"] == "Marvel"


def test_com_corte_manda_gancho_e_transcricao(ap, fake):  # noqa: F811
    ap.tema("Marvel", ["marvel"])
    vid = ap.post(dias=3, legenda="Post")
    corte = criar_corte(ap.db, ap.perfil_id, transcript="hoje eu falo da Marvel", hook_text="Já viu?")
    ap.c.vincular(vid, corte=corte)
    _rodar(ap, fake)
    texto = fake.bodies[0]["messages"][0]["content"]
    assert '<dados_terceiros tipo="gancho">\nJá viu?' in texto
    assert "hoje eu falo da Marvel" in texto and not _class(ap, vid).evidencia_parcial


def test_limite_diario_conta_os_erros(ap, fake, monkeypatch):  # noqa: F811
    monkeypatch.setattr(K, "LIMITE_DIARIO", 3)
    ap.tema("Marvel")
    ids = [ap.post(dias=d) for d in range(2, 8)]
    fake.responder((400, {"type": "error", "error": {"type": "invalid_request_error",
                                                      "message": "x"}}))
    _rodar(ap, fake)
    assert _chamadas(ap) == 3  # 1 erro + 2 classificadas
    assert sum(_class(ap, v) is not None for v in ids) == 2
    _rodar(ap, fake)
    assert _chamadas(ap) == 3  # o limite do dia acabou
    r = ap.client.post(f"{ap.url}/classificar-pendentes", headers=ap.h, json={})
    assert r.status_code == 202 and r.json() == {"pendentes": 4, "restantesHoje": 0}


def test_para_no_erro_de_disponibilidade(ap, fake):  # noqa: F811
    ap.tema("Marvel")
    for d in range(2, 6):
        ap.post(dias=d)
    fake.responder("timeout")
    _rodar(ap, fake)
    assert _chamadas(ap) == 1


def test_correcao_do_dono_prevalece(ap, fake):  # noqa: F811
    marvel, games = ap.tema("Marvel", ["marvel"]), ap.tema("Games")
    vid = ap.post(dias=3, legenda="Marvel")
    _rodar(ap, fake)
    c = _class(ap, vid)
    r = ap.client.put(f"/api/aprendizado/classificacoes/{vid}", headers=ap.h,
                      json={"version": c.version, "temaId": games["id"],
                            "secundarios": [marvel["id"]], "estiloGancho": "humor"})
    assert r.status_code == 200, r.text
    assert r.json()["origem"] == "dono" and r.json()["temaNome"] == "Games"
    # arquivar o tema e pedir pendentes: a linha do dono não volta para a IA
    ap.client.post(f"/api/aprendizado/temas/{games['id']}/archive", headers=ap.h,
                   json={"version": 1})
    ap.client.post(f"{ap.url}/classificar-pendentes", headers=ap.h, json={})
    antes = _chamadas(ap)
    _rodar(ap, fake)
    assert _chamadas(ap) == antes
    c = _class(ap, vid)
    assert c.origem == Origem.dono and c.tema_id is None
    r = ap.client.put(f"/api/aprendizado/classificacoes/{vid}", headers=ap.h,
                      json={"version": c.version, "temaId": games["id"]})
    assert r.status_code == 400 and err(r) == "tema_invalido"  # arquivado
    # reverter volta à versão da IA
    r = ap.client.post(f"/api/aprendizado/classificacoes/{vid}/revert", headers=ap.h,
                       json={"version": c.version, "toVersion": 1})
    assert r.status_code == 200 and r.json()["origem"] == "ia"
    assert r.json()["temaId"] == marvel["id"]


def test_id_invalido_vira_sem_tema_com_sugestao(ap, fake):  # noqa: F811
    ap.tema("Marvel")
    vid = ap.post(dias=3)
    fake.responder(classificacao(ID_INVALIDO, sugestao="Tokusatsu"))
    _rodar(ap, fake)
    c = _class(ap, vid)
    assert c.tema_id is None and c.sugestao_tema == "Tokusatsu" and c.origem == Origem.ia


def test_classificacao_automatica_pausada_e_pedido(ap, fake):  # noqa: F811
    ap.tema("Marvel")
    vid = ap.post(dias=3)
    prefs = ap.get("preferencias")["perfil"]
    r = ap.client.patch(f"{ap.url}/preferencias", headers=ap.h,
                        json={"version": prefs["version"], "classificacaoAuto": False})
    assert r.status_code == 200 and r.json()["classificacaoAuto"] is False
    _rodar(ap, fake)
    assert _class(ap, vid) is None and _chamadas(ap) == 0
    r = ap.client.post(f"{ap.url}/classificar-pendentes", headers=ap.h, json={})
    assert r.status_code == 202 and r.json()["pendentes"] == 1
    _rodar(ap, fake)
    assert _class(ap, vid) is not None
    ap.post(dias=4)
    _rodar(ap, fake)
    assert _chamadas(ap) == 1  # o pedido foi atendido uma vez


def test_sem_taxonomia_e_sem_chave(ap, fake, monkeypatch):  # noqa: F811
    vid = ap.post(dias=3)
    r = ap.client.post(f"{ap.url}/classificar-pendentes", headers=ap.h, json={})
    assert r.status_code == 409 and err(r) == "sem_taxonomia"
    ap.tema("Marvel")
    trilha.rodar(ap.db)  # sem chave no teste: get_ia_client() = None
    assert _class(ap, vid) is None and _chamadas(ap) == 0
    assert trilha.ociosa() is not None


def test_membro_nao_corrige(ap, membro):  # noqa: F811
    _, hm = membro
    t = ap.tema("Marvel")
    vid = ap.post(dias=3)
    r = ap.client.put(f"/api/aprendizado/classificacoes/{vid}", headers=hm,
                      json={"version": 0, "temaId": t["id"]})
    assert r.status_code == 403 and err(r) == "somente_dono"
    assert ap.get("classificacoes", h=hm)["items"][0]["videoId"] == str(vid)
    r = ap.client.put(f"/api/aprendizado/classificacoes/{uuid.uuid4()}", headers=ap.h,
                      json={"version": 0, "temaId": t["id"]})
    assert r.status_code == 404
