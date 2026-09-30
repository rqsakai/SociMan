"""US4 (T043 da 008): o campo `ia` na criação e na edição do destino (research R10), agora
pelas rotas da spec 014 (`/api/conteudos/{id}/destinos`, `/api/destinos/{id}`,
`/api/agendamentos`) e com o alvo `conteudo` (R12).

As chamadas são semeadas direto em `ia_chamadas` (sem o Claude): aqui só interessa o que o
save faz com o `ia`.
"""

import uuid

import pytest
from fakes.anthropic_fake import anthropic_fake, texto  # noqa: F401
from sqlalchemy import select

from integration.postagem_helpers import (  # noqa: F401
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.history import EntityVersion
from sociman_api.ia.cliente import get_ia_client
from sociman_api.ia.models import IaChamada, IaDesfecho
from sociman_api.main import app
from sociman_api.perfis.models import Platform
from sociman_api.postagem.models import Postagem


@pytest.fixture
def cenario(client, db, membro):  # noqa: F811
    user, h = membro
    perfil = criar_perfil(client, h)
    tiktok = criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd")
    youtube = criar_conta(client, h, perfil["id"], "youtube", "tavernanerdyt")
    corte = criar_corte(db, perfil["id"])
    return {"user": user, "h": h, "perfil": perfil, "tiktok": tiktok, "youtube": youtube,
            "corte": corte}


def _chamada(db, c, tipo_campo, proposta, *, conta="tiktok", postagem_id=None) -> uuid.UUID:
    conta_ = c[conta]
    row = IaChamada(
        tipo_campo=tipo_campo, perfil_id=uuid.UUID(c["perfil"]["id"]),
        entity_type="postagem" if postagem_id else "corte",
        entity_id=uuid.UUID(postagem_id) if postagem_id else c["corte"].id,
        corte_id=c["corte"].id, conteudo_id=c["corte"].id, conta_id=uuid.UUID(conta_["id"]),
        plataforma=Platform(conta_["platform"]), proposta=proposta,
        model="claude-sonnet-5-5", prompt_version="ia/1", duration_ms=800,
    )
    db.add(row)
    db.commit()
    return row.id


def _row(db, cid) -> IaChamada:
    db.expire_all()
    return db.get(IaChamada, cid)


def _ultima_versao(db, postagem_id) -> EntityVersion:
    db.expire_all()
    return db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "postagem",
        EntityVersion.entity_id == uuid.UUID(postagem_id),
    ).order_by(EntityVersion.version.desc()).limit(1)).one()


def _ia(tipo, cid) -> list[dict]:
    return [{"tipoCampo": tipo, "chamadaId": str(cid)}]


def test_criar_so_com_o_titulo_e_ia(client, db, cenario):
    c = cenario
    cid = _chamada(db, c, "postagem.titulo", {"texto": "Você usa isso errado"})
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], "titulo": "Você usa isso errado",
                          "ia": _ia("postagem.titulo", cid)})
    assert r.status_code == 201, r.text
    p = r.json()["destino"]
    assert p["version"] == 1 and p["descricao"] == "" and p["hashtags"] == []

    v = _ultima_versao(db, p["id"])
    assert v.action == "created" and v.actor_user_id == c["user"].id
    assert v.details == {"ia": [{"campo": "titulo", "tipoCampo": "postagem.titulo",
                                 "chamadaId": str(cid), "desfecho": "aplicada"}]}
    row = _row(db, cid)
    assert row.desfecho == IaDesfecho.aplicada and row.aplicada_versao == 1
    assert db.get(Postagem, uuid.UUID(p["id"])).sugestao_id == cid


def test_editar_parcial_aplicada_e_editada(client, db, cenario):
    c = cenario
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], "titulo": "Antes"})
    p = r.json()["destino"]

    desc = _chamada(db, c, "postagem.descricao", {"texto": "Descrição nova"},
                    postagem_id=p["id"])
    r = client.patch(f"/api/destinos/{p['id']}", headers=c["h"],
                     json={"version": p["version"], "descricao": "Descrição nova",
                           "ia": _ia("postagem.descricao", desc)})
    assert r.status_code == 200, r.text
    p = r.json()["destino"]
    assert p["titulo"] == "Antes"
    assert _row(db, desc).desfecho == IaDesfecho.aplicada
    assert _ultima_versao(db, p["id"]).changed_fields == ["descricao"]

    tags = _chamada(db, c, "postagem.hashtags", {"itens": ["#dica", "#tech", "#nerd"]})
    r = client.patch(f"/api/destinos/{p['id']}", headers=c["h"],
                     json={"version": p["version"], "hashtags": ["#dica", "#tech"],
                           "ia": _ia("postagem.hashtags", tags)})
    assert r.status_code == 200, r.text
    row = _row(db, tags)
    assert row.desfecho == IaDesfecho.editada
    assert row.aplicada_versao == r.json()["destino"]["version"]


def test_textos_juntos_gravam_sugestao_id(client, db, cenario):
    c = cenario
    proposta = {"titulo": "T", "descricao": "D", "hashtags": ["#a1", "#b2", "#c3"]}
    cid = _chamada(db, c, "postagem.textos", proposta)
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], **proposta,
                          "ia": _ia("postagem.textos", cid)})
    assert r.status_code == 201, r.text
    p = r.json()["destino"]
    assert db.get(Postagem, uuid.UUID(p["id"])).sugestao_id == cid
    entrada = _ultima_versao(db, p["id"]).details["ia"][0]
    assert entrada["campo"] == "titulo,descricao,hashtags"
    assert entrada["desfecho"] == "aplicada"


def test_alvo_de_outra_conta_ignorado(client, db, cenario):
    c = cenario
    cid = _chamada(db, c, "postagem.titulo", {"texto": "X"}, conta="youtube")
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], "titulo": "X",
                          "ia": _ia("postagem.titulo", cid)})
    assert r.status_code == 201, r.text
    p = r.json()["destino"]
    assert _ultima_versao(db, p["id"]).details == {}
    assert _row(db, cid).desfecho == IaDesfecho.sem_acao
    assert db.get(Postagem, uuid.UUID(p["id"])).sugestao_id is None


# ---- gerar (US4) com o Claude falso, e aplicar pelo save ----

@pytest.fixture
def fake(anthropic_fake):  # noqa: F811
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    return anthropic_fake


def _gerar(client, c, tipo, alvo, **extra):
    body = {"tipoCampo": tipo, "perfilId": c["perfil"]["id"], "alvo": alvo,
            "sessaoId": str(uuid.uuid4())} | extra
    r = client.post("/api/ia/gerar", headers=c["h"], json=body)
    assert r.status_code == 200, r.text
    return r.json()["chamada"]


def _alvo_corte(c, conta="tiktok") -> dict:
    return {"entityType": "corte", "entityId": str(c["corte"].id), "contaId": c[conta]["id"]}


def test_titulo_mais_polemico_com_contexto_da_006_e_aplicar(client, db, cenario, fake):
    c = cenario
    c["corte"].transcript = "hoje o atalho é ctrl+shift+t"
    db.commit()
    fake.responder(texto("Você usa o atalho ERRADO"))
    ch = _gerar(client, c, "postagem.titulo", _alvo_corte(c),
                valorAtual={"texto": "Atalho"}, instrucao="mais polêmico")
    assert ch["proposta"]["texto"] == "Você usa o atalho ERRADO"
    user = fake.bodies[0]["messages"][0]["content"]
    assert "<dados_terceiros" in user and "ctrl+shift+t" in user
    assert "TikTok" in user and "mais polêmico" in user

    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], "titulo": ch["proposta"]["texto"],
                          "ia": _ia("postagem.titulo", ch["id"])})
    assert r.status_code == 201, r.text
    p = r.json()["destino"]
    assert _ultima_versao(db, p["id"]).details["ia"][0]["desfecho"] == "aplicada"
    assert _row(db, uuid.UUID(ch["id"])).desfecho == IaDesfecho.aplicada


def test_descricao_na_postagem_leva_os_outros_campos(client, db, cenario, fake):
    c = cenario
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["youtube"]["id"], "titulo": "Atalho secreto do Chrome"})
    p = r.json()["destino"]
    ch = _gerar(client, c, "postagem.descricao", {"entityType": "postagem", "entityId": p["id"]})
    user = fake.bodies[0]["messages"][0]["content"]
    assert "Atalho secreto do Chrome" in user and "YouTube Shorts" in user
    r = client.patch(f"/api/destinos/{p['id']}", headers=c["h"],
                     json={"version": p["version"], "descricao": ch["proposta"]["texto"] + "!",
                           "ia": _ia("postagem.descricao", ch["id"])})
    assert r.status_code == 200, r.text
    assert _row(db, uuid.UUID(ch["id"])).desfecho == IaDesfecho.editada


def test_textos_juntos_pelo_gerar(client, db, cenario, fake):
    c = cenario
    ch = _gerar(client, c, "postagem.textos", _alvo_corte(c))
    prop = ch["proposta"]
    assert prop["titulo"] and 3 <= len(prop["hashtags"]) <= 8
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], "titulo": prop["titulo"],
                          "descricao": prop["descricao"], "hashtags": prop["hashtags"],
                          "ia": _ia("postagem.textos", ch["id"])})
    assert r.status_code == 201, r.text
    p = r.json()["destino"]
    db.expire_all()
    assert db.get(Postagem, uuid.UUID(p["id"])).sugestao_id == uuid.UUID(ch["id"])
    assert _row(db, uuid.UUID(ch["id"])).desfecho == IaDesfecho.aplicada


# ---- spec 014 (T037): alvo `conteudo`, `conteudo_id` gravado, vídeo próprio, agendar com ia ----

def _alvo_conteudo(c, conteudo_id, conta="tiktok") -> dict:
    return {"entityType": "conteudo", "entityId": str(conteudo_id), "contaId": c[conta]["id"]}


def test_alvo_conteudo_antes_do_destino_e_agendar_com_ia(client, db, cenario, fake, dono):  # noqa: F811
    c = cenario
    ch = _gerar(client, c, "postagem.titulo", _alvo_conteudo(c, c["corte"].id))
    row = _row(db, uuid.UUID(ch["id"]))
    assert row.entity_type == "conteudo" and row.conteudo_id == c["corte"].id
    assert row.corte_id == c["corte"].id and row.conta_id == uuid.UUID(c["tiktok"]["id"])
    assert ch["alvo"]["contaId"] == c["tiktok"]["id"]

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    quando = (datetime.now(ZoneInfo("America/Sao_Paulo")) + timedelta(days=1)).replace(
        hour=19, minute=0, second=0, microsecond=0)
    r = client.post("/api/agendamentos", headers=dono[1], json={
        "conteudoId": str(c["corte"].id), "contaId": c["tiktok"]["id"],
        "plannedAt": quando.isoformat(), "modo": "lembrete",
        "textos": {"titulo": ch["proposta"]["texto"], "descricao": "Legenda"},  # 015 (T101)
        "ia": _ia("postagem.titulo", ch["id"])})
    assert r.status_code == 201, r.text
    d = r.json()["destino"]
    v = _ultima_versao(db, d["id"])
    assert v.details["acao"] == "agendado"
    assert v.details["ia"][0]["desfecho"] == "aplicada"
    assert _row(db, uuid.UUID(ch["id"])).desfecho == IaDesfecho.aplicada


def test_alvo_corte_continua_e_grava_conteudo_id(client, db, cenario, fake):
    c = cenario
    ch = _gerar(client, c, "postagem.titulo", _alvo_corte(c))
    assert _row(db, uuid.UUID(ch["id"])).conteudo_id == c["corte"].id


def test_alvo_postagem_grava_conteudo_id_e_sessao_sobrevive(client, db, cenario, fake):
    c = cenario
    sessao = str(uuid.uuid4())
    antes = _gerar(client, c, "postagem.titulo", _alvo_conteudo(c, c["corte"].id),
                   sessaoId=sessao)
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"]})
    p = r.json()["destino"]
    ch = _gerar(client, c, "postagem.titulo", {"entityType": "postagem", "entityId": p["id"]},
                sessaoId=sessao, anteriores=[antes["id"]])
    row = _row(db, uuid.UUID(ch["id"]))
    assert row.entity_type == "postagem" and row.conteudo_id == c["corte"].id
    assert row.anteriores == [uuid.UUID(antes["id"])]


def test_video_proprio_sem_transcricao(client, db, cenario, fake):
    c = cenario
    proprio = Conteudo(id=uuid.uuid4(), perfil_id=uuid.UUID(c["perfil"]["id"]),
                       origem=ConteudoOrigem.video_proprio, titulo="Unboxing do teclado",
                       video_key=f"conteudos/{uuid.uuid4()}/video.mp4",
                       video_content_type="video/mp4", poster_key="p.jpg", duration_ms=42000,
                       width=1080, height=1920)
    db.add(proprio)
    db.commit()
    ch = _gerar(client, c, "postagem.titulo", _alvo_conteudo(c, proprio.id))
    user = fake.bodies[0]["messages"][0]["content"]
    assert "Unboxing do teclado" in user and "vídeo próprio" in user
    assert "<dados_terceiros" not in user  # sem corte: nada de terceiros, nem transcrição
    row = _row(db, uuid.UUID(ch["id"]))
    assert row.conteudo_id == proprio.id and row.corte_id is None
    assert "transcricao" in row.contexto_faltante
    # o alvo `corte` com o id de um vídeo próprio não existe
    r = client.post("/api/ia/gerar", headers=c["h"], json={
        "tipoCampo": "postagem.titulo", "perfilId": c["perfil"]["id"],
        "alvo": _alvo_corte(c) | {"entityId": str(proprio.id)}, "sessaoId": str(uuid.uuid4())})
    assert r.status_code == 404
