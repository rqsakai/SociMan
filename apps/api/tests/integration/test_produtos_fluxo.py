"""Fluxo do cadastro (spec 012, T020 e T026, US1 e US2): a ficha pelo Claude falso, os recortes
direto na variante, os flats com 2 opções e escolha humana, "Gerar outras" e "Refazer flat",
com o gerador da 021 rodando em teste."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from fakes.comfyui_fake import ComfyFake
from sqlalchemy import select

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.produtos_helpers import (  # noqa: F401 (fixtures)
    claude_fake,
    criar,
    escolher,
    passos,
    perfil,
    rodar_tudo,
    ver,
    versoes,
)
from sociman_api.ia.models import IaChamada, IaDesfecho


def test_ficha_aplicada_preenche_campos_e_cores(client, owner, motores, claude_fake, db):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=2, obs="sem flat")
    assert motores.linha_claude().volta() == "ok"
    p = ver(client, h, p["id"])
    assert p["fichaPor"] == "ia"
    f = p["ficha"]
    assert f["nomeComercial"] == "Short canelado cintura alta"
    assert f["materialEn"] == "ribbed knit" and f["precisaFlat"] is False
    assert f["detalhesVisiveis"] and f["cuidados"]
    assert [(v["corEn"], v["corPt"]) for v in p["variantes"]] == [
        ("black", "preto"), ("heather grey", "cinza mescla")]
    # O registro da 008: a chamada com a geração, o custo e o desfecho.
    ficha_g = passos(p, "produto.ficha")[0]
    row = db.scalar(select(IaChamada).where(IaChamada.geracao_id == ficha_g["id"]))
    assert row.tipo_campo == "produto.ficha" and row.entity_type == "produto"
    assert row.entity_id is not None and str(row.entity_id) == p["id"]
    assert row.custo_usd is not None and row.desfecho == IaDesfecho.aplicada
    # A versão do produto com a geração (autor = quem pediu).
    hist = versoes(client, h, p["id"])
    assert hist[0]["details"]["geracao_id"] == ficha_g["id"]
    assert hist[0]["details"]["automatico"] is True
    assert hist[0]["actor"]["id"] == str(owner[0].id)
    # As fotos foram como blocos de imagem numerados.
    assert claude_fake.imagens == [2]
    # A ficha aplicada pede os recortes (antes da GPU, SC-002).
    assert len(passos(p, "produto.recorte")) == 2


def test_observacao_errada_mantem_o_que_as_fotos_mostram(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1, obs="shorts jeans")
    motores.linha_claude().volta()
    p = ver(client, h, p["id"])
    assert p["ficha"]["materialEn"] == "ribbed knit"
    assert any("jeans" in c for c in p["ficha"]["cuidados"])
    assert "<instrucao>shorts jeans</instrucao>" in "\n".join(
        b.get("text", "") for b in claude_fake.bodies[0]["messages"][0]["content"])


def test_roupa_com_2_variantes_recortes_flats_e_escolha(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=2)
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    recortes = passos(p, "produto.recorte")
    assert len(recortes) == 2 and {r["status"] for r in recortes} == {"escolhido"}
    assert all(v["recorte"] for v in p["variantes"])
    flats = passos(p, "produto.flat")
    assert len(flats) == 2 and {f["status"] for f in flats} == {"revisao"}
    assert p["status"] == "gerando"
    # O bloco keyframe recebeu a instrução do flat e o recorte; o cutout, a original.
    blocos = [x.bloco for x in motores.comfy.prompts.values()]
    assert blocos.count("cutout") == 2 and blocos.count("keyframe") == 4
    # Escolher a opção 2 da 1ª variante: a variante recebe o flat e a geração.
    v0 = p["variantes"][0]
    f0 = next(f for f in flats if f["varianteId"] == v0["id"])
    escolher(client, h, p, f0["id"], numero=2)
    p = ver(client, h, p["id"])
    v0 = p["variantes"][0]
    assert v0["flat"] and v0["flatGeracaoId"] == f0["id"]
    assert p["status"] == "gerando"  # falta a outra variante
    assert versoes(client, h, p["id"])[0]["details"]["geracao_id"] == f0["id"]
    f1 = next(f for f in flats if f["varianteId"] == p["variantes"][1]["id"])
    escolher(client, h, p, f1["id"], numero=1)
    p = ver(client, h, p["id"])
    assert p["status"] == "revisao" and p["pendencias"] == []


def test_gerar_outras_mantem_o_flat_vigente(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    f = passos(p, "produto.flat")[0]
    escolher(client, h, p, f["id"], numero=1)
    p = ver(client, h, p["id"])
    flat_antes = p["variantes"][0]["flat"]["imageId"]
    # Refazer flat depois de escolhido: geração nova, o flat atual fica até a nova escolha.
    r = client.post(f"/api/produtos/{p['id']}/variantes/{p['variantes'][0]['id']}/refazer-flat",
                    headers=h, json={"version": p["version"]})
    assert r.status_code == 201, r.text
    nova = r.json()
    rodar_tudo(motores)
    g = client.get(f"/api/geracoes/{nova['id']}", headers=h).json()
    assert g["status"] == "revisao"
    seeds_antigas = {c["seed"] for c in client.get(
        f"/api/geracoes/{f['id']}", headers=h).json()["candidatos"]}
    assert not seeds_antigas & {c["seed"] for c in g["candidatos"]}
    # Com opções esperando escolha, refazer manda usar "Gerar outras".
    p = ver(client, h, p["id"])
    r = client.post(f"/api/produtos/{p['id']}/variantes/{p['variantes'][0]['id']}/refazer-flat",
                    headers=h, json={"version": p["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "estado_invalido"
    r = client.post(f"/api/geracoes/{g['id']}/gerar-outras", headers=h,
                    json={"version": g["version"]})
    assert r.status_code == 201, r.text
    assert client.get(f"/api/geracoes/{g['id']}", headers=h).json()["status"] == "descartada"
    p = ver(client, h, p["id"])
    assert p["variantes"][0]["flat"]["imageId"] == flat_antes


def test_sem_flat_vai_direto_para_revisao(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=2, obs="sem flat")
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    assert passos(p, "produto.flat") == []
    assert p["status"] == "revisao" and p["pendencias"] == []


def test_fake_do_comfy_recebe_a_instrucao_do_flat(client, owner, motores, claude_fake):
    h = owner[1]
    criar(client, h, perfil(client, h), n_fotos=1)
    rodar_tudo(motores)
    flat = next(x for x in motores.comfy.prompts.values() if x.bloco == "keyframe")
    assert "flat-lay" in str(flat.params)
    assert isinstance(motores.comfy, ComfyFake)
