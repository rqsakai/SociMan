"""Resumo do AI Studio (spec 029, T013): `GET /api/estudio/resumo` conta os itens ativos de cada
tipo no filtro de perfil base (todos, `sem` ou um perfil), sem os arquivados."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

from sqlalchemy import text

from integration.estudio_helpers import item, listar, perfil
from integration.geracao_helpers import _buckets, member, owner  # noqa: F401 (fixtures)

ZERO = {"avatares": 0, "cenarios": 0, "assets": 0, "cenas": 0, "produtos": 0, "vozes": 0}


def _cena(db, perfil_id: str | None, arquivada: bool = False) -> None:
    db.execute(text("INSERT INTO cenas (id, perfil_id, nome, acao, archived_at) "
                    "VALUES (:id, :p, 'Cena', 'mostra o produto', "
                    "CASE WHEN :arq THEN now() END)"),
               {"id": uuid.uuid4(), "p": perfil_id, "arq": arquivada})
    db.commit()


def test_resumo_por_perfil_base(client, owner, member, db):
    h = owner[1]
    a, b = perfil(client, h, "perfil-a"), perfil(client, h, "perfil-b")
    item(client, h, "avatar", a)
    item(client, h, "avatar", None)
    item(client, h, "cenario", b, prompt="retro kitchen")
    item(client, h, "imagem", a)
    item(client, h, "sticker", None)
    item(client, h, "fundo", a)
    item(client, h, "produto", a)
    item(client, h, "produto", None)
    item(client, h, "voz", b, name="Voz B")
    _cena(db, a)
    _cena(db, None)
    _cena(db, a, arquivada=True)
    arq = item(client, h, "avatar", a, name="Arquivado")
    r = client.post(f"/api/assets/{arq['id']}/archive", headers=h,
                    json={"version": arq["version"]})
    assert r.status_code == 200, r.text

    assert listar(client, h, "estudio/resumo") == {
        "avatares": 2, "cenarios": 1, "assets": 3, "cenas": 2, "produtos": 2, "vozes": 1}
    assert listar(client, h, "estudio/resumo", perfilId=a) == ZERO | {
        "avatares": 1, "assets": 2, "cenas": 1, "produtos": 1}
    assert listar(client, h, "estudio/resumo", perfilId=b) == ZERO | {
        "cenarios": 1, "vozes": 1}
    assert listar(client, h, "estudio/resumo", perfilId="sem") == ZERO | {
        "avatares": 1, "assets": 1, "cenas": 1, "produtos": 1}
    # O membro também lê; um perfil que não existe é 400.
    assert listar(client, member[1], "estudio/resumo", perfilId=a)["avatares"] == 1
    r = listar(client, h, "estudio/resumo", status=400, perfilId=str(uuid.uuid4()))
    assert r["error"]["code"] == "perfil_invalido"
