"""Poda do bruto: chaves pessoais em várias profundidades saem; `verificar` acusa o que restou;
`autorRef` e `autorHandle` passam (fixtures sintéticas)."""

import copy

from sociman_coletor import privacidade
from sociman_coletor.privacidade import PODADO, podar, verificar

from .fakes import json_avaliacoes, json_videos

FIXTURE = {
    "data": {
        "product": {
            "product_id": "7291001",
            "title": "Shorts",
            "shop": {
                "shop_id": "l1",
                "shop_name": "Loja",
                "name": "Dono da loja",
                "phone": "11 9",
                "email": "a@b.c",
                "address": {"street": "x"},
            },
            "images": [{"url_list": ["https://img.sintetica.test/a.png?sig=abc&exp=1"]}],
        },
        "reviews": [
            {
                "review_id": "r1",
                "text": "bom",
                "uid": "123",
                "user": {
                    "uid": "123",
                    "nickname": "Fulana",
                    "avatar_thumb": {"url_list": ["x"]},
                    "sec_uid": "s",
                    "signature": "bio",
                },
                "replies": [{"comment": {"author": {"nick_name": "Beltrano"}, "uid": "9"}}],
            },
        ],
        "videos": [
            {
                "video_id": "v1",
                "author": {"unique_id": "fulana.achados", "nickname": "F", "avatar_larger": "x"},
                "autorHandle": "fulana.achados",
            },
        ],
        "meta": {
            "cookies": "a=b",
            "token": "t",
            "sessionid": "s",
            "mobile": "9",
            "display_name": "x",
            "userName": "y",
            "profile": {"bio": "z"},
        },
        "lista": [[{"username": "deep"}], {"n": [{"avatar_url": "u"}]}],
    },
    "sku_name": "Bege / M",
    "uid": "fora de review: fica",
}


def test_poda_em_todas_as_profundidades_e_nao_muda_o_original():
    original = copy.deepcopy(FIXTURE)
    podado = podar(FIXTURE)
    assert FIXTURE == original
    p = podado["data"]["product"]
    assert p["shop"]["name"] == PODADO and p["shop"]["phone"] == PODADO
    assert p["shop"]["email"] == PODADO and p["shop"]["address"] == PODADO
    assert p["shop"]["shop_name"] == "Loja"  # nome de loja não é de pessoa
    assert p["images"][0]["url_list"][0] == "https://img.sintetica.test/a.png"
    r = podado["data"]["reviews"][0]
    assert r["user"] == PODADO
    assert r["uid"] == PODADO  # uid dentro de review
    assert r["text"] == "bom"
    assert r["replies"][0]["comment"]["author"] == PODADO
    assert r["replies"][0]["comment"]["uid"] == PODADO
    v = podado["data"]["videos"][0]
    assert v["author"] == PODADO
    assert v["autorHandle"] == "fulana.achados"  # o @ público passa (FR-011)
    m = podado["data"]["meta"]
    assert all(
        m[k] == PODADO
        for k in ("cookies", "token", "sessionid", "mobile", "display_name", "userName", "profile")
    )
    assert podado["data"]["lista"][0][0]["username"] == PODADO
    assert podado["data"]["lista"][1]["n"][0]["avatar_url"] == PODADO
    assert podado["sku_name"] == "Bege / M"
    assert podado["uid"] == "fora de review: fica"  # `uid` só é pessoal em review/comment


def test_verificar_acusa_o_que_restou_e_aceita_o_podado():
    assert verificar(FIXTURE) is not None
    podado = podar(FIXTURE)
    assert verificar(podado) is None
    podado["data"]["reviews"][0]["user"] = {"nickname": "voltou"}
    assert verificar(podado) == "data.reviews[0].user"
    assert verificar({"a": [{"b": {"email": "x"}}]}) == "a[0].b.email"


def test_autor_ref_e_autor_handle_passam():
    campos = {
        "itens": [
            {"redeAvaliacaoId": "a", "autorRef": "6812001", "texto": "ok"},
            {
                "redeVideoId": "v",
                "autorHandle": "fulana",
                "autor_handle": "f",
                "unique_id": "u",
                "uniqueId": "u",
                "handle": "h",
            },
        ]
    }
    assert podar(campos) == campos
    assert verificar(campos) is None


def test_fixtures_da_rede_saem_limpas():
    for bruto in (json_avaliacoes(), json_videos()):
        assert verificar(bruto) is not None
        p = podar(bruto)
        assert verificar(p) is None
    p = podar(json_avaliacoes())
    assert p["data"]["reviews"][0]["user"] == PODADO
    assert p["data"]["reviews"][0]["text"].startswith("Tecido")


def test_lista_do_contrato_esta_coberta():
    contrato = {
        "nickname",
        "nick_name",
        "user_name",
        "username",
        "display_name",
        "name",
        "avatar",
        "avatar_url",
        "avatar_thumb",
        "profile",
        "bio",
        "signature",
        "email",
        "phone",
        "mobile",
        "address",
        "sec_uid",
        "user",
        "author",
    }
    assert contrato <= privacidade.CHAVES_PESSOAIS
    assert "uid" in privacidade.CHAVES_CONTEXTUAIS


def test_detalhe_evento_so_chaves_permitidas():
    d = privacidade.detalhe_evento(
        codigoHttp=429,
        urlSemParametros="https://h/p?x=1",
        tipoTarefa="produto",
        nickname="x",
        cookie="y",
        contagem=None,
    )
    assert d == {"codigoHttp": 429, "urlSemParametros": "https://h/p", "tipoTarefa": "produto"}
