"""Persona da fábrica (spec 013, US5, T039): vai para o perfil que já tem a imagem; sem perfil
padrão, exige a escolha; campos diferentes divergem campo a campo; cenários como assets."""

import io

from sqlalchemy import select

from integration.agencia_helpers import (  # noqa: F401
    _buckets,
    agencia,
    confirmar,
    dono,
    importar,
    itens,
    png,
    previa,
    um,
    yt,
)
from sociman_api.assets.models import Asset, AssetTipo, FileRole


def _perfil(client, h, slug):
    r = client.post("/api/perfis", headers=h, json={"name": slug.title(), "slug": slug})
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def test_persona_no_perfil_que_ja_tem_a_imagem(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    imagem = png((10, 200, 10, 255))
    _perfil(client, h, "outro-teste")
    achados = _perfil(client, h, "achados-teste")
    r = client.post(f"/api/perfis/{achados['id']}/assets", headers=h, json={
        "tipo": "avatar", "name": "Achadinha", "prompt": "A cheerful pin-up woman.",
        "voiceTone": "Outro tom"})  # sem regras de imagem
    asset = r.json()["asset"]
    r = client.post(f"/api/assets/{asset['id']}/arquivos", headers=h,
                    files={"file": ("a.png", io.BytesIO(imagem), "image/png")},
                    data={"role": "referencia"})
    assert r.status_code in (200, 201), r.text
    agencia.persona(dados=imagem)

    p = previa(client, h)

    assert p["persona"] == {"perfilPadrao": "achados-teste", "exigePerfil": False}
    av = um(p, "asset", perfilSlug="achados-teste", situacao="diverge")
    assert av["atual"] == {"voice_tone": "Outro tom", "image_rules": ""}  # só o que difere
    assert av["proposto"]["voice_tone"].startswith("Tom: animado")
    assert um(p, "arquivo_asset")["situacao"] == "igual"
    cen = next(i for i in itens(p, "asset") if i["origem"]["trecho"].startswith("Cenário"))
    assert cen["situacao"] == "novo"
    confirmar(client, h, p, [{"n": av["n"], "usar": "markdown"}])
    assets = {a.name: a for a in db.scalars(select(Asset))}
    assert assets["Achadinha"].voice_tone.startswith("Tom: animado")
    assert assets["Cozinha retrô"].tipo == AssetTipo.cenario
    assert assets["Cozinha retrô"].prompt == "1950s kitchen."
    assert str(assets["Cozinha retrô"].perfil_id) == achados["id"]


def test_sem_perfil_padrao_exige_escolha(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    _perfil(client, h, "achados-teste")
    agencia.persona()
    p = previa(client, h)
    assert p["persona"] == {"perfilPadrao": None, "exigePerfil": True}
    assert all(i["exigePerfil"] for i in itens(p, "asset") + itens(p, "arquivo_asset"))
    r = client.post("/api/agencia/importacoes", headers=h, json={"previaId": p["previaId"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "escolha_invalida"

    imp = confirmar(client, h, p, personaPerfil="achados-teste")
    assert imp["estado"] == "concluida"
    avatar = db.scalars(select(Asset).where(Asset.tipo == AssetTipo.avatar)).one()
    assert avatar.prompt == "A cheerful pin-up woman."
    refs = avatar.active_files(FileRole.referencia)
    assert len(refs) == 1 and refs[0].look == "Cozinha, corpo inteiro"
    # reimportar: a persona agora tem perfil padrão e está igual
    p2 = previa(client, h)
    assert p2["persona"]["perfilPadrao"] == "achados-teste"
    assert p2["contagens"]["novo"] == 0
