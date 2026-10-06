"""Imagens do perfil (spec 013, US4, T036): SHA-256 igual não reenvia, poses no mesmo avatar,
sticker com transparência, logo só sem logo, `nao-usar-ainda`, imagem inválida, citada que não
existe e HD indisponível antes de gravar."""

import io

from sqlalchemy import select

from integration.agencia_helpers import (  # noqa: F401
    _buckets,
    agencia,
    confirmar,
    dono,
    importar,
    itens,
    jpg,
    png,
    previa,
    um,
    yt,
)
from sociman_api.assets.models import Asset, AssetTipo, FileRole
from sociman_api.config import get_settings
from sociman_api.perfis.models import Perfil


def _perfil_com_imagem(client, h, dados: bytes) -> dict:
    r = client.post("/api/perfis", headers=h, json={"name": "Taverna Teste",
                                                     "slug": "taverna-teste", "status": "ativo",
                                                     "niche": "RPG e colecionáveis"})
    perfil = r.json()["perfil"]
    r = client.post(f"/api/perfis/{perfil['id']}/assets/arquivo", headers=h,
                    files={"file": ("ja.jpg", io.BytesIO(dados), "image/jpeg")},
                    data={"tipo": "imagem", "name": "Já"})
    assert r.status_code == 201, r.text
    return perfil


def test_igual_poses_sticker_e_tipos(client, db, dono, agencia, yt, s3):  # noqa: F811
    _, h = dono
    ja = jpg((1, 2, 3))
    _perfil_com_imagem(client, h, ja)
    agencia.perfil()
    a = "perfis/taverna-teste/assets/"
    agencia.escrever(a + "foto-perfil.jpg", ja)
    agencia.escrever(a + "avatar-poses/avatar-1-rpg-dnd.jpg", jpg((5, 5, 5)))
    agencia.escrever(a + "avatar-poses/avatar-2-leitura.jpg", jpg((6, 6, 6)))
    agencia.escrever(a + "avatar-5poses.jpg", jpg((7, 7, 7)))
    agencia.escrever(a + "stickers/sticker-crit.png", png(alfa=True))
    agencia.escrever(a + "stickers/sticker-jpg.jpg", jpg((8, 8, 8)))
    agencia.escrever(a + "stickers-CHECKERBOARD-nao-usar-ainda.jpg", jpg((9, 9, 9)))
    agencia.escrever(a + "quebrada.jpg", b"nao e imagem")
    objetos = len(s3.keys())

    p = previa(client, h)

    foto = next(i for i in itens(p, "asset") if i["origem"]["trecho"] == "foto-perfil.jpg")
    assert foto["situacao"] == "igual"
    assert um(p, "arquivo", motivo="nao_usar_ainda")
    q = next(i for i in itens(p, "asset") if i["origem"]["trecho"] == "quebrada.jpg")
    assert (q["situacao"], q["motivo"]) == ("fora", "imagem_invalida") and q["proposto"]["erro"]
    assert len(itens(p, "arquivo_asset", situacao="novo")) == 3
    imp = confirmar(client, h, p)

    assert len(s3.keys()) == objetos + 5  # 3 do avatar + 2 stickers; a igual não reenvia
    assets = {a.name: a for a in db.scalars(select(Asset))}
    avatar = assets["Avatar do perfil"]
    assert avatar.tipo == AssetTipo.avatar
    assert sorted(f.label for f in avatar.active_files(FileRole.pose)) == ["leitura", "rpg dnd"]
    assert len(avatar.active_files(FileRole.referencia)) == 1
    assert assets["sticker-crit"].tipo == AssetTipo.sticker
    assert assets["sticker-jpg"].tipo == AssetTipo.imagem
    assert imp["contagens"]["naoGravado"] == 0
    assert previa(client, h)["contagens"]["novo"] == 0


def test_logo_so_sem_logo(client, db, dono, agencia, yt, s3):  # noqa: F811
    _, h = dono
    agencia.perfil()
    agencia.escrever("perfis/taverna-teste/assets/logo.png", png((90, 60, 30, 255)))
    importar(client, h)
    perfil = db.scalars(select(Perfil)).one()
    assert perfil.logo_image_id is not None
    agencia.escrever("perfis/taverna-teste/assets/logo.png", png((10, 60, 30, 255)))
    p = previa(client, h)
    logo = um(p, "imagem_logo")
    assert (logo["situacao"], logo["motivo"]) == ("diverge", "valor")
    antes = perfil.logo_image_id
    confirmar(client, h, p)  # padrão: manter o SociMan
    db.refresh(perfil)
    assert perfil.logo_image_id == antes


def test_citada_que_nao_existe(client, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil(estilo="trocar por `shared/perfis/taverna-teste/assets/watermark.png`")
    p = previa(client, h)
    c = um(p, "asset", motivo="arquivo_citado_nao_encontrado")
    assert c["origem"]["trecho"] == "watermark.png"


def test_hd_indisponivel_falha_antes_de_gravar(client, db, dono, agencia, yt, s3, tmp_path,  # noqa: F811
                                              monkeypatch):
    _, h = dono
    agencia.perfil()
    agencia.escrever("perfis/taverna-teste/assets/foto.jpg", jpg())
    p = previa(client, h)
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    objetos = len(s3.keys())
    r = client.post("/api/agencia/importacoes", headers=h, json={"previaId": p["previaId"]})
    imp = client.get(f"/api/agencia/importacoes/{r.json()['id']}", headers=h).json()
    assert imp["estado"] == "falhou" and "HD" in imp["erro"]
    assert db.scalar(select(Perfil.id)) is None and len(s3.keys()) == objetos
