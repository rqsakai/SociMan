"""Gerar e descartar (spec 008, T016; US1, R5, R9): contexto enviado ao Claude falso, validações,
"Outra versão" por sessão, sugestões com seleção, e gerar **não cria versão** (princípio VII)."""

import uuid
from datetime import UTC, datetime

import pytest
from fakes.anthropic_fake import anthropic_fake, itens, texto  # noqa: F401
from sqlalchemy import func, select

from sociman_api.assets.models import Asset
from sociman_api.history import EntityVersion
from sociman_api.ia.cliente import get_ia_client
from sociman_api.ia.models import IaChamada, IaDesfecho
from sociman_api.ia.tipos import TIPOS
from sociman_api.main import app
from sociman_api.marca.models import BrandKit

PW = "senha-forte-123"
PROMPT = "A cheerful woman in her 30s, curly black hair, round glasses."


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


@pytest.fixture
def fake(anthropic_fake):  # noqa: F811
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    return anthropic_fake


def _perfil(client, h, slug="achadinhos", **extra) -> dict:
    body = {"name": slug.title(), "slug": slug, "niche": "casa", "bio": "Achados baratos"}
    r = client.post("/api/perfis", headers=h, json=body | extra)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _asset(client, h, perfil, **body) -> dict:
    r = client.post(f"/api/perfis/{perfil['id']}/assets", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def _kit(client, h, perfil, **sections) -> dict:
    kit = client.get(f"/api/perfis/{perfil['id']}/kit", headers=h).json()["kit"]
    keys = ("version", "palette", "caption", "hook", "watermark", "endCard", "catchphrases",
            "series")
    r = client.put(f"/api/perfis/{perfil['id']}/kit", headers=h,
                   json={k: kit[k] for k in keys} | sections)
    assert r.status_code == 200, r.text
    return r.json()["kit"]


@pytest.fixture
def cena(client, dono, fake):
    _, h = dono
    perfil = _perfil(client, h)
    kit = _kit(client, h, perfil, catchphrases=["Olha isso!"], series=["Achado do dia"])
    avatar = _asset(client, h, perfil, tipo="avatar", name="Ana", prompt=PROMPT,
                    voiceTone="Animada e direta", imageRules="Sempre de óculos")
    cenario = _asset(client, h, perfil, tipo="cenario", name="Cozinha",
                     prompt="A bright kitchen")
    sticker = _asset(client, h, perfil, tipo="sticker", name="Seta", description="Seta rosa")
    return {"h": h, "perfil": perfil, "kit": kit, "avatar": avatar, "cenario": cenario,
            "sticker": sticker}


def _gerar(client, h, tipo, perfil, alvo, valor=None, instrucao="", sessao=None, **extra):
    body = {"tipoCampo": tipo, "perfilId": perfil["id"], "alvo": alvo,
            "valorAtual": valor or {}, "instrucao": instrucao,
            "sessaoId": str(sessao or uuid.uuid4()), **extra}
    return client.post("/api/ia/gerar", headers=h, json=body)


def _alvo(cena, tipo) -> dict:
    entidade = TIPOS[tipo].entidade
    if entidade == "perfil":
        return {"entityType": "perfil", "entityId": cena["perfil"]["id"]}
    if entidade == "kit":
        return {"entityType": "kit", "entityId": None}
    chave = {"cenario.prompt_ambiente": "cenario", "asset.nome": "sticker",
             "asset.descricao": "sticker"}.get(tipo, "avatar")
    return {"entityType": "asset", "entityId": cena[chave]["id"]}


def _v(valor: dict | None) -> dict | None:
    """`Valor` sem as chaves nulas (a API devolve as cinco)."""
    return {k: v for k, v in valor.items() if v is not None} if valor else valor


def _versoes(db) -> int:
    return db.scalar(select(func.count()).select_from(EntityVersion))


TIPOS_US1 = [t for t in TIPOS if TIPOS[t].entidade in ("asset", "perfil", "kit")]


@pytest.mark.parametrize("tipo", TIPOS_US1)
def test_gerar_manda_o_contexto_certo_e_nao_cria_versao(client, db, cena, fake, tipo):
    assert len(TIPOS_US1) == 9
    t = TIPOS[tipo]
    valor = {"itens": ["Olha isso!"]} if t.formato == "sugestoes" else {"texto": "Valor atual"}
    if t.formato == "sugestoes":
        fake.responder(itens("Sugestão nova 1", "Sugestão nova 2"))
    antes = _versoes(db)
    r = _gerar(client, cena["h"], tipo, cena["perfil"], _alvo(cena, tipo), valor,
               "mais curto")
    assert r.status_code == 200, r.text
    ch = r.json()["chamada"]
    assert ch["tipoCampo"] == tipo and ch["desfecho"] == "sem_acao" and ch["proposta"]
    assert _v(ch["entrada"]) == valor and ch["instrucao"] == "mais curto"
    assert ch["custoUsd"] > 0 and ch["regrasVersion"] == 0

    body = fake.bodies[-1]
    system = " ".join(b["text"] for b in body["system"])
    user = body["messages"][0]["content"]
    assert t.padrao in body["system"][1]["text"]  # as regras em vigor (padrão)
    assert "Achadinhos" in body["system"][2]["text"] and "Olha isso!" in system  # perfil + kit
    assert "<instrucao>\nmais curto\n</instrucao>" in user
    assert "<valor_atual>" in user
    if tipo.startswith("avatar."):
        assert "<persona>" not in user  # o próprio avatar entra como entidade
        assert "Tipo do asset: avatar" in user
    else:
        assert "<persona>\nNome: Ana" in user
    if t.entidade == "asset" and tipo != "avatar.descricao_prompt" and tipo.startswith("avatar"):
        assert PROMPT in user  # os outros campos do mesmo avatar
    if tipo == "kit.bordoes":
        assert "Achado do dia" in user  # o outro campo do kit
    assert _versoes(db) == antes  # gerar não cria versão em nenhuma entidade (VII)


def test_campo_vazio_pede_criacao_do_zero(client, cena, fake):
    r = _gerar(client, cena["h"], "perfil.bio", cena["perfil"], _alvo(cena, "perfil.bio"),
               {"texto": "   "})
    assert r.status_code == 200
    assert "crie o texto do zero" in fake.bodies[-1]["messages"][0]["content"]


def test_gerar_nao_muda_o_asset(client, db, cena, fake):
    r = _gerar(client, cena["h"], "avatar.tom_de_voz", cena["perfil"],
               _alvo(cena, "avatar.tom_de_voz"), {"texto": "x"})
    assert r.status_code == 200
    asset = db.get(Asset, uuid.UUID(cena["avatar"]["id"]))
    assert asset.voice_tone == "Animada e direta" and asset.version == 1


def test_outra_versao_manda_as_anteriores_da_sessao(client, cena, fake):
    sessao = uuid.uuid4()
    alvo = _alvo(cena, "perfil.bio")
    fake.responder(texto("Primeira versão da bio"), texto("Segunda versão"))
    a = _gerar(client, cena["h"], "perfil.bio", cena["perfil"], alvo, sessao=sessao).json()
    r = _gerar(client, cena["h"], "perfil.bio", cena["perfil"], alvo, sessao=sessao,
               anteriores=[a["chamada"]["id"]])
    assert r.status_code == 200, r.text
    user = fake.bodies[-1]["messages"][0]["content"]
    assert "<propostas_anteriores>" in user and "Primeira versão da bio" in user
    assert r.json()["chamada"]["sessaoId"] == str(sessao)


def test_anteriores_invalidas(client, cena, membro, fake):
    h = cena["h"]
    sessao = uuid.uuid4()
    alvo = _alvo(cena, "perfil.bio")
    a = _gerar(client, h, "perfil.bio", cena["perfil"], alvo, sessao=sessao).json()["chamada"]
    casos = [
        {"sessao": uuid.uuid4()},  # outra sessão
        {"sessao": sessao, "tipo": "avatar.tom_de_voz"},  # outro tipo e alvo
    ]
    for caso in casos:
        tipo = caso.get("tipo", "perfil.bio")
        r = _gerar(client, h, tipo, cena["perfil"], _alvo(cena, tipo), sessao=caso["sessao"],
                   anteriores=[a["id"]])
        assert r.status_code == 400 and r.json()["error"]["code"] == "ia_anteriores_invalidas"
    # Outro autor, mesma sessão.
    r = _gerar(client, membro[1], "perfil.bio", cena["perfil"], alvo, sessao=sessao,
               anteriores=[a["id"]])
    assert r.status_code == 400 and r.json()["error"]["code"] == "ia_anteriores_invalidas"
    # Id que não existe.
    r = _gerar(client, h, "perfil.bio", cena["perfil"], alvo, sessao=sessao,
               anteriores=[str(uuid.uuid4())])
    assert r.status_code == 400


def test_selecao_so_nas_sugestoes(client, cena, fake):
    r = _gerar(client, cena["h"], "perfil.bio", cena["perfil"], _alvo(cena, "perfil.bio"),
               selecao={"aceitos": ["x"], "rejeitados": []})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_ia"
    r = _gerar(client, cena["h"], "kit.series", cena["perfil"], _alvo(cena, "kit.series"),
               selecao={"aceitos": ["x" * 61], "rejeitados": []})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_ia"


def test_sugestoes_removem_repetidas_e_guardam_a_selecao(client, db, cena, fake):
    fake.responder(itens("Olha isso!", "Partiu!", "Nem vem", "Bora lá", "bora lá"))
    r = _gerar(client, cena["h"], "kit.bordoes", cena["perfil"], _alvo(cena, "kit.bordoes"),
               {"itens": ["Olha isso!"]},
               selecao={"aceitos": ["Partiu!"], "rejeitados": ["Nem vem"]})
    assert r.status_code == 200, r.text
    ch = r.json()["chamada"]
    assert _v(ch["proposta"]) == {"itens": ["Bora lá"]}
    assert any("já vistas" in a for a in ch["avisos"])
    assert any("repetida" in a for a in ch["avisos"])
    assert ch["aceitos"] == ["Partiu!"] and ch["rejeitados"] == ["Nem vem"]
    kit_id = db.scalar(select(BrandKit.id).where(
        BrandKit.perfil_id == uuid.UUID(cena["perfil"]["id"])))
    assert ch["alvo"]["entityId"] == str(kit_id)  # o SPA manda null; vale o kit salvo
    user = fake.bodies[-1]["messages"][0]["content"]
    assert "<ja_aceitos>\n- Partiu!" in user and "<rejeitados>\n- Nem vem" in user


def test_alvo_de_outro_perfil_tipo_incompativel_e_valor_grande(client, cena, fake):
    h = cena["h"]
    outro = _perfil(client, h, "outro")
    r = _gerar(client, h, "avatar.tom_de_voz", outro, _alvo(cena, "avatar.tom_de_voz"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_ia"
    r = _gerar(client, h, "avatar.tom_de_voz", cena["perfil"],
               {"entityType": "asset", "entityId": cena["cenario"]["id"]})
    assert r.status_code == 400 and "cenario" in r.json()["error"]["message"]
    r = _gerar(client, h, "avatar.tom_de_voz", cena["perfil"],
               _alvo(cena, "avatar.tom_de_voz"), {"texto": "a" * 751})  # 1,5 × 500
    assert r.status_code == 400
    r = _gerar(client, h, "avatar.tom_de_voz", cena["perfil"],
               _alvo(cena, "avatar.tom_de_voz"), {"texto": "a" * 750})
    assert r.status_code == 200
    r = _gerar(client, h, "perfil.bio", cena["perfil"], _alvo(cena, "perfil.bio"),
               {"itens": ["x"]})
    assert r.status_code == 400  # formato errado para o tipo
    r = _gerar(client, h, "perfil.bio", cena["perfil"],
               {"entityType": "perfil", "entityId": outro["id"]})
    assert r.status_code == 400
    r = _gerar(client, h, "avatar.tom_de_voz", cena["perfil"],
               {"entityType": "asset", "entityId": str(uuid.uuid4())})
    assert r.status_code == 404


def test_entidade_arquivada_409(client, db, cena, fake):
    asset = db.get(Asset, uuid.UUID(cena["sticker"]["id"]))
    asset.archived_at = datetime.now(UTC)
    db.commit()
    r = _gerar(client, cena["h"], "asset.nome", cena["perfil"], _alvo(cena, "asset.nome"))
    assert r.status_code == 409


def test_perfil_sem_kit_e_sem_avatar(client, dono, fake):
    _, h = dono
    perfil = _perfil(client, h, "vazio", bio="")
    r = _gerar(client, h, "perfil.bio", perfil,
               {"entityType": "perfil", "entityId": perfil["id"]})
    assert r.status_code == 200, r.text
    ch = r.json()["chamada"]
    assert {"kit", "persona"} <= set(ch["contextoFaltante"])
    assert any("kit salvo" in a for a in ch["avisos"]) and any("avatar" in a for a in ch["avisos"])
    assert "Contexto que não existe: kit, persona" in fake.bodies[-1]["messages"][0]["content"]
    # Kit nunca salvo: o alvo do kit fica sem id.
    r = _gerar(client, h, "kit.series", perfil, {"entityType": "kit", "entityId": None})
    assert r.status_code == 200 and r.json()["chamada"]["alvo"]["entityId"] is None


def test_descartar_so_o_autor_e_idempotente(client, db, cena, membro, fake):
    h = cena["h"]
    alvo = _alvo(cena, "perfil.bio")
    ch = _gerar(client, h, "perfil.bio", cena["perfil"], alvo).json()["chamada"]
    url = f"/api/ia/chamadas/{ch['id']}/descartar"
    assert client.post(url, headers=membro[1]).status_code == 403
    assert client.post(url, headers=h).status_code == 204
    assert client.post(url, headers=h).status_code == 204
    row = db.get(IaChamada, uuid.UUID(ch["id"]))
    assert row.desfecho == IaDesfecho.descartada and row.desfecho_por is not None
    # Aplicada, editada e erro não mudam.
    for desfecho in (IaDesfecho.aplicada, IaDesfecho.editada):
        outra = _gerar(client, h, "perfil.bio", cena["perfil"], alvo).json()["chamada"]
        row = db.get(IaChamada, uuid.UUID(outra["id"]))
        row.desfecho = desfecho
        db.commit()
        assert client.post(f"/api/ia/chamadas/{outra['id']}/descartar",
                           headers=h).status_code == 204
        db.refresh(row)
        assert row.desfecho == desfecho
    fake.responder("timeout")
    assert _gerar(client, h, "perfil.bio", cena["perfil"], alvo).status_code == 504
    erro = db.scalar(select(IaChamada).where(IaChamada.desfecho == IaDesfecho.erro))
    assert client.post(f"/api/ia/chamadas/{erro.id}/descartar", headers=h).status_code == 204
    db.refresh(erro)
    assert erro.desfecho == IaDesfecho.erro
    r = client.post(f"/api/ia/chamadas/{uuid.uuid4()}/descartar", headers=h)
    assert r.status_code == 404
