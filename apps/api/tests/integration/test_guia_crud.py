"""Guia de comunicação do perfil e da conta (spec 017, T017; US1, data-model "Validação no
save", research R2, R5, R6, R7, R11, R12): GET sem guia, criação pelo dono, permissões, limites
campo a campo, proibidas, regra de soma das fixas, validação cruzada e conflitos."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaGuia
from sociman_api.perfis.models import Conta, Perfil, Platform

PW = "senha-forte-123"


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


@pytest.fixture
def perfil(db) -> Perfil:
    p = Perfil(slug=f"taverna-{uuid.uuid4().hex[:6]}", name="A Taverna")
    db.add(p)
    db.commit()
    return p


def _conta(db, perfil: Perfil, platform: Platform = Platform.tiktok,
           handle: str = "atavernanerd", archived: bool = False) -> Conta:
    c = Conta(perfil_id=perfil.id, platform=platform, handle=handle,
              url=f"https://example.com/@{handle}-{platform.value}",
              archived_at=datetime.now(UTC) if archived else None)
    db.add(c)
    db.commit()
    return c


def _put_perfil(client, h, perfil_id, version=0, **campos):
    return client.put(f"/api/perfis/{perfil_id}/guia", headers=h,
                      json={"version": version, "campos": campos})


def _put_conta(client, h, conta_id, version=0, **campos):
    return client.put(f"/api/contas/{conta_id}/guia", headers=h,
                      json={"version": version, "campos": campos})


def _fields(r) -> dict:
    assert r.status_code == 400, r.text
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    return body["details"]["fields"]


def _versoes(db, guia_id) -> int:
    return db.scalar(select(func.count()).select_from(EntityVersion).where(
        EntityVersion.entity_type == "ia_guia", EntityVersion.entity_id == guia_id))


def test_get_sem_guia_devolve_vazio_com_limites(client, membro, perfil):
    r = client.get(f"/api/perfis/{perfil.id}/guia", headers=membro[1])
    assert r.status_code == 200
    g = r.json()["guia"]
    assert g["id"] is None and g["version"] == 0 and g["contaId"] is None
    assert g["campos"]["faca"] == [] and g["campos"]["emojis"] is None
    assert g["campos"]["maxHashtagsFixas"] is None and g["tamanho"] == 0
    assert g["limites"] == {
        "tomMax": 500, "regrasItens": 10, "regraMax": 200, "vocabularioItens": 30,
        "termoMax": 60, "proibidasItens": 30, "emojisItens": 10, "emojiMax": 16,
        "hashtagsFixasPerfil": 5, "hashtagsFixasPadrao": 5, "hashtagsFixasTeto": 8,
        "exemplos": 5, "exemploMax": 500, "totalMax": 4000}
    assert client.get(f"/api/perfis/{perfil.id}/guia/versions",
                      headers=membro[1]).json() == {"items": []}


def test_404(client, dono):
    h = dono[1]
    x = uuid.uuid4()
    for r in (client.get(f"/api/perfis/{x}/guia", headers=h), _put_perfil(client, h, x),
              client.get(f"/api/contas/{x}/guia", headers=h), _put_conta(client, h, x),
              client.get(f"/api/contas/{x}/guia/versions", headers=h)):
        assert r.status_code == 404, r.text


def test_dono_cria_e_membro_so_ve(client, dono, membro, perfil, db):
    r = _put_perfil(client, dono[1], perfil.id, tom="  Nerd e acolhedor ",
                    faca=["Explique o termo", " "], proibidas=["clickbait"], emojis="moderado",
                    hashtagsFixas=["Taverna", "#RPG"],
                    exemplos=[{"tipo": "titulo", "texto": "Rolamos 20!"}])
    assert r.status_code == 200, r.text
    g = r.json()["guia"]
    assert g["version"] == 1 and g["updatedBy"]["name"] == "Dono"
    assert g["campos"]["tom"] == "Nerd e acolhedor" and g["campos"]["faca"] == ["Explique o termo"]
    assert g["campos"]["hashtagsFixas"] == ["#taverna", "#rpg"]
    assert g["tamanho"] == len("Nerd e acolhedor") + len("Explique o termo") + len(
        "clickbait") + len("#taverna") + len("#rpg") + len("Rolamos 20!")
    v = client.get(f"/api/perfis/{perfil.id}/guia/versions", headers=membro[1]).json()["items"]
    assert [(x["version"], x["action"], x["actor"]["name"]) for x in v] == [(1, "created", "Dono")]
    assert v[0]["after"]["hashtags_fixas"] == ["#taverna", "#rpg"]

    r = _put_perfil(client, membro[1], perfil.id, version=1, tom="Outro")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert client.get(f"/api/perfis/{perfil.id}/guia", headers=membro[1]).json()["guia"][
        "campos"]["tom"] == "Nerd e acolhedor"

    # Salvar igual não cria versão; 409 com versão velha.
    igual = _put_perfil(client, dono[1], perfil.id, version=1, **{
        k: v for k, v in g["campos"].items()})
    assert igual.status_code == 200 and igual.json()["guia"]["version"] == 1
    assert _versoes(db, uuid.UUID(g["id"])) == 1
    velho = _put_perfil(client, dono[1], perfil.id, version=0, tom="x")
    assert velho.status_code == 409 and velho.json()["error"]["code"] == "version_conflict"
    assert "Este guia foi alterado por outra pessoa" in velho.json()["error"]["message"]
    r = _put_perfil(client, dono[1], perfil.id, version=1, tom="Sério")
    assert r.json()["guia"]["version"] == 2
    # Limpar = salvar vazio (nova versão); sem DELETE.
    r = _put_perfil(client, dono[1], perfil.id, version=2)
    assert r.status_code == 200 and r.json()["guia"]["version"] == 3
    assert r.json()["guia"]["tamanho"] == 0


def test_salvar_vazio_sem_guia_nao_cria_linha(client, dono, perfil, db):
    r = _put_perfil(client, dono[1], perfil.id, tom="   ")
    assert r.status_code == 200 and r.json()["guia"]["version"] == 0
    assert db.scalar(select(func.count()).select_from(IaGuia)) == 0


def test_limites_campo_a_campo(client, dono, perfil):
    h = dono[1]
    f = _fields(_put_perfil(client, h, perfil.id, tom="x" * 501))
    assert f == {"tom": "no máximo 500 caracteres"}
    f = _fields(_put_perfil(client, h, perfil.id, faca=["a", "b", "c", "d" * 201]))
    assert f == {"faca.3": "no máximo 200 caracteres"}
    f = _fields(_put_perfil(client, h, perfil.id, faca=[f"f{i}" for i in range(11)]))
    assert f == {"faca": "no máximo 10 itens"}
    f = _fields(_put_perfil(client, h, perfil.id, exemplos=[
        {"tipo": "legenda", "texto": f"e{i}"} for i in range(6)]))
    assert f == {"exemplos": "no máximo 5 exemplos"}
    f = _fields(_put_perfil(client, h, perfil.id, exemplos=[
        {"tipo": "legenda", "texto": "ok"}, {"tipo": "titulo", "texto": "y" * 501}]))
    assert f == {"exemplos.1.texto": "no máximo 500 caracteres"}
    f = _fields(_put_perfil(client, h, perfil.id, vocabulario=["Dado", "dádo"]))
    assert f == {"vocabulario.1": "item repetido"}
    f = _fields(_put_perfil(client, h, perfil.id, hashtagsFixas=["#ok", "!!!"]))
    assert f == {"hashtagsFixas.1": "hashtag inválida"}
    r = _put_perfil(client, h, perfil.id, tom="x" * 500,
                    faca=[f"{i}" + "z" * 199 for i in range(10)],
                    exemplos=[{"tipo": "legenda", "texto": f"{i}" + "y" * 499} for i in range(5)])
    assert _fields(r) == {"total": "o guia tem 5000 caracteres; o máximo é 4000"}
    msg = r.json()["error"]["message"]
    assert msg == "O guia tem 1 problema"
    f = _fields(_put_perfil(client, h, perfil.id, maxHashtagsFixas=3))
    assert list(f) == ["maxHashtagsFixas"]
    f = _fields(_put_perfil(client, h, perfil.id, hashtagsFixas=[f"#h{i}" for i in range(6)]))
    assert f == {"hashtagsFixas": "no máximo 5 hashtags fixas"}


def test_proibida_do_perfil_nos_campos_do_proprio_guia_e_da_conta(client, dono, perfil, db):
    h = dono[1]
    f = _fields(_put_perfil(client, h, perfil.id, proibidas=["clickbait"],
                            vocabulario=["CLÍCKBAIT"]))
    assert f == {"vocabulario.0": "usa a palavra proibida 'clickbait'"}
    assert _put_perfil(client, h, perfil.id, proibidas=["clickbait"]).status_code == 200
    conta = _conta(db, perfil)
    r = _put_conta(client, h, conta.id, exemplos=[
        {"tipo": "titulo", "texto": "ok"}, {"tipo": "legenda", "texto": "a"},
        {"tipo": "titulo", "texto": "Puro clickbait!"}])
    assert _fields(r) == {"exemplos.2.texto": "usa a palavra proibida 'clickbait'"}
    # A proibida da própria conta também vale nela.
    r = _put_conta(client, h, conta.id, proibidas=["pix"], hashtagsFixas=["#pix"])
    assert _fields(r) == {"hashtagsFixas.0": "usa a palavra proibida 'pix'"}


def test_soma_das_fixas_na_conta(client, dono, perfil, db):
    h = dono[1]
    assert _put_perfil(client, h, perfil.id, hashtagsFixas=["#taverna"]).status_code == 200
    conta = _conta(db, perfil)
    cinco = [f"#c{i}" for i in range(5)]
    r = _put_conta(client, h, conta.id, hashtagsFixas=cinco)
    assert _fields(r) == {"hashtagsFixas": "perfil e conta somam 6 hashtags fixas; o máximo "
                                           "desta conta é 5 (1 vêm do perfil)"}
    r = _put_conta(client, h, conta.id, hashtagsFixas=cinco, maxHashtagsFixas=6)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["guia"]["campos"]["maxHashtagsFixas"] == 6
    assert body["efetivo"]["maxHashtagsFixas"] == 6
    assert body["efetivo"]["hashtagsFixas"] == ["#taverna", *cinco]
    # A fixa que o perfil já tem não conta duas vezes.
    r = _put_conta(client, h, conta.id, version=1, hashtagsFixas=["#taverna", *cinco[:4]])
    assert r.status_code == 200 and r.json()["efetivo"]["maxHashtagsFixas"] == 5
    f = _fields(_put_conta(client, h, conta.id, version=2, maxHashtagsFixas=9))
    assert f == {"maxHashtagsFixas": "de 0 a 8"}
    f = _fields(_put_conta(client, h, conta.id, version=2,
                           hashtagsFixas=[f"#h{i}" for i in range(9)], maxHashtagsFixas=8))
    assert f == {"hashtagsFixas": "no máximo 8 hashtags fixas"}


def test_perfil_confere_todas_as_contas_nao_arquivadas(client, dono, perfil, db):
    h = dono[1]
    sem_guia = _conta(db, perfil, Platform.instagram, "ataverna")
    youtube = _conta(db, perfil, Platform.youtube, "atavernanerd")
    arquivada = _conta(db, perfil, Platform.kwai, "velha", archived=True)
    assert _put_conta(client, h, youtube.id, maxHashtagsFixas=1).status_code == 200
    assert _put_perfil(client, h, perfil.id, hashtagsFixas=["#taverna"]).status_code == 200
    r = _put_perfil(client, h, perfil.id, version=1, hashtagsFixas=["#taverna", "#rpg"])
    assert r.status_code == 400
    det = r.json()["error"]["details"]
    assert det["fields"] == {}
    assert det["contas"] == [{
        "contaId": str(youtube.id), "rotulo": "YouTube @atavernanerd",
        "campos": ["hashtagsFixas"],
        "mensagem": "A conta YouTube @atavernanerd aceita no máximo 1 hashtags fixas; perfil "
                    "e conta somariam 2"}]
    # Conta sem guia: o máximo é o padrão 5 (o perfil já é limitado a 5).
    assert sem_guia.id not in {c["contaId"] for c in det["contas"]}
    # Arquivada não conta: um máximo 0 nela não bloqueia.
    db.add(IaGuia(perfil_id=perfil.id, conta_id=arquivada.id, max_hashtags_fixas=0))
    db.commit()
    assert _put_conta(client, h, youtube.id, version=1, maxHashtagsFixas=2).status_code == 200
    r = _put_perfil(client, h, perfil.id, version=1, hashtagsFixas=["#taverna", "#rpg"])
    assert r.status_code == 200, r.text


def test_proibida_nova_do_perfil_usada_no_guia_da_conta(client, dono, perfil, db):
    h = dono[1]
    conta = _conta(db, perfil)
    assert _put_conta(client, h, conta.id, vocabulario=["pix", "clickbait"],
                      tom="sem clickbait").status_code == 200
    r = _put_perfil(client, h, perfil.id, proibidas=["Clickbait"])
    assert r.status_code == 400
    det = r.json()["error"]["details"]
    assert det["contas"] == [{
        "contaId": str(conta.id), "rotulo": "TikTok @atavernanerd",
        "campos": ["tom", "vocabulario"],
        "mensagem": "A conta TikTok @atavernanerd usa 'Clickbait' no tom; tire de lá antes; "
                    "A conta TikTok @atavernanerd usa 'Clickbait' no vocabulário; tire de lá "
                    "antes"}]
    assert r.json()["error"]["message"] == "O guia tem 1 problema"


def test_get_da_conta_com_efetivo_e_conflitos(client, dono, membro, perfil, db):
    h = dono[1]
    conta = _conta(db, perfil)
    assert _put_perfil(client, h, perfil.id, emojis="nao", faca=["Seja breve"],
                       proibidas=["clickbait"], emojisPreferidos=["🎲"],
                       hashtagsFixas=["#taverna"]).status_code == 200
    assert _put_conta(client, h, conta.id, emojis="livre", naoFaca=["seja BREVE"],
                      proibidas=["grátis"], hashtagsFixas=["#tiktokrpg"]).status_code == 200
    r = client.get(f"/api/contas/{conta.id}/guia", headers=membro[1])
    assert r.status_code == 200
    body = r.json()
    assert body["guia"]["contaId"] == str(conta.id) and body["guia"]["perfilId"] == str(perfil.id)
    assert body["perfil"]["contaId"] is None and body["perfil"]["version"] == 1
    assert body["efetivo"] == {"proibidas": ["clickbait", "grátis"],
                               "hashtagsFixas": ["#taverna", "#tiktokrpg"], "emojis": "livre",
                               "emojisPreferidos": ["🎲"], "maxHashtagsFixas": 5}
    assert [c["campo"] for c in body["conflitos"]] == ["emojis", "naoFaca"]


def test_estado_invalido_herdado_vira_conflito(client, dono, perfil, db):
    conta = _conta(db, perfil)
    db.add_all([IaGuia(perfil_id=perfil.id, hashtags_fixas=["#a", "#b"]),
                IaGuia(perfil_id=perfil.id, conta_id=conta.id, hashtags_fixas=["#c"],
                       max_hashtags_fixas=2)])
    db.commit()
    body = client.get(f"/api/contas/{conta.id}/guia", headers=dono[1]).json()
    assert body["efetivo"]["hashtagsFixas"] == ["#a", "#b"]
    assert [c["campo"] for c in body["conflitos"]] == ["hashtagsFixas"]


def test_conta_ou_perfil_arquivado_409(client, dono, perfil, db):
    conta = _conta(db, perfil, archived=True)
    r = _put_conta(client, dono[1], conta.id, tom="x")
    assert r.status_code == 409 and r.json()["error"]["message"] == "Esta conta está arquivada"
    assert client.get(f"/api/contas/{conta.id}/guia", headers=dono[1]).status_code == 200
    perfil.archived_at = datetime.now(UTC)
    db.commit()
    r = _put_perfil(client, dono[1], perfil.id, tom="x")
    assert r.status_code == 409 and r.json()["error"]["message"] == "Este perfil está arquivado"


def test_perfil_id_do_guia_da_conta_vem_da_conta(client, dono, perfil, db):
    outro = Perfil(slug=f"outro-{uuid.uuid4().hex[:6]}", name="Outro")
    db.add(outro)
    db.commit()
    conta = _conta(db, outro)
    r = client.put(f"/api/contas/{conta.id}/guia", headers=dono[1],
                   json={"version": 0, "perfilId": str(perfil.id), "campos": {"tom": "x"}})
    assert r.status_code == 200
    assert r.json()["guia"]["perfilId"] == str(outro.id)
    row = db.scalar(select(IaGuia).where(IaGuia.conta_id == conta.id))
    assert row.perfil_id == outro.id
