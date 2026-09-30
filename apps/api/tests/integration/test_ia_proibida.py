"""Aplicar sem editar uma proposta com palavra proibida é recusado (spec 017, T031; Q2 = A,
research R7): 400 `ia_proibida` só para o campo salvo igual à proposta; campo editado passa
(desfecho `editada`). As chamadas vêm do Claude falso com o guia salvo."""

import uuid

from fakes.anthropic_fake import anthropic_fake, texto  # noqa: F401

from integration.guia_ia_helpers import (  # noqa: F401
    alvo_corte,
    avatar,
    cena,
    fake,
    gerar,
    guia_perfil,
)
from integration.postagem_helpers import dono  # noqa: F401
from sociman_api.ia.models import IaChamada, IaDesfecho


def _ia(tipo, ch) -> list[dict]:
    return [{"tipoCampo": tipo, "chamadaId": ch["id"]}]


def _chamada_com_proibida(client, c, fake) -> dict:  # noqa: F811
    guia_perfil(client, c, proibidas=["clickbait"])
    fake.responder("proibida_postagem", "proibida_postagem")
    ch = gerar(client, c, "postagem.textos", alvo_corte(c))
    assert ch["proibidas"] == ["clickbait"]
    return ch


def _criar_destino(client, c, ch, **mudar):
    prop = ch["proposta"]
    body = {"contaId": c["tiktok"]["id"], "titulo": prop["titulo"],
            "descricao": prop["descricao"], "hashtags": prop["hashtags"],
            "ia": _ia("postagem.textos", ch)} | mudar
    return client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"], json=body)


def _desfecho(db, ch) -> IaDesfecho:
    db.expire_all()
    return db.get(IaChamada, uuid.UUID(ch["id"])).desfecho


def test_titulo_igual_a_proposta_e_recusado(client, db, cena, fake):  # noqa: F811
    c = cena
    ch = _chamada_com_proibida(client, c, fake)
    r = _criar_destino(client, c, ch)
    assert r.status_code == 400, r.text
    erro = r.json()["error"]
    assert erro["code"] == "ia_proibida"
    assert erro["details"] == {"palavras": ["clickbait"], "campos": ["titulo"]}
    assert _desfecho(db, ch) == IaDesfecho.sem_acao


def test_so_a_descricao_editada_e_o_titulo_intacto_continua_recusado(client, db, cena, fake):  # noqa: F811
    c = cena
    ch = _chamada_com_proibida(client, c, fake)
    r = _criar_destino(client, c, ch, descricao="Descrição reescrita pela equipe.")
    assert r.status_code == 400 and r.json()["error"]["details"]["campos"] == ["titulo"]


def test_titulo_editado_mesmo_com_a_palavra_passa_como_editada(client, db, cena, fake):  # noqa: F811
    c = cena
    ch = _chamada_com_proibida(client, c, fake)
    r = _criar_destino(client, c, ch, titulo="Sem clickbait: o truque do teclado")
    assert r.status_code == 201, r.text
    assert _desfecho(db, ch) == IaDesfecho.editada


def test_sem_o_campo_ia_o_save_passa(client, db, cena, fake):  # noqa: F811
    """O texto humano é decisão humana (R13): sem `ia`, nada confere proibidas."""
    c = cena
    ch = _chamada_com_proibida(client, c, fake)
    prop = ch["proposta"]
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["tiktok"]["id"], "titulo": prop["titulo"]})
    assert r.status_code == 201, r.text


def test_campo_visual_sem_edicao_e_recusado(client, db, cena, fake):  # noqa: F811
    c = cena
    a = avatar(client, c)
    guia_perfil(client, c, proibidas=["logo"])
    fake.responder(texto("A woman with a logo shirt."), texto("A woman with a logo shirt."))
    ch = gerar(client, c, "avatar.descricao_prompt", {"entityType": "asset", "entityId": a["id"]})
    assert ch["proibidas"] == ["logo"]
    r = client.patch(f"/api/assets/{a['id']}", headers=c["h"],
                     json={"version": a["version"], "prompt": ch["proposta"]["texto"],
                           "ia": _ia("avatar.descricao_prompt", ch)})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["details"] == {"palavras": ["logo"], "campos": ["prompt"]}


def test_chamada_sem_proibidas_segue_a_008(client, db, cena, fake):  # noqa: F811
    c = cena
    fake.responder("postagem_sem_fixas")
    ch = gerar(client, c, "postagem.textos", alvo_corte(c))
    assert ch["proibidas"] == []
    r = _criar_destino(client, c, ch)
    assert r.status_code == 201, r.text
    assert _desfecho(db, ch) == IaDesfecho.aplicada
    # um `ia` que não casa continua ignorado (o save nunca falha por causa dele)
    r = client.post(f"/api/conteudos/{c['corte'].id}/destinos", headers=c["h"],
                    json={"contaId": c["youtube"]["id"], "titulo": "Outro",
                          "ia": [{"tipoCampo": "postagem.textos",
                                  "chamadaId": str(uuid.uuid4())}]})
    assert r.status_code == 201, r.text
