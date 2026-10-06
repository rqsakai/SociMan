"""Cenas (spec 010, T014, T022, T025): criar e ler com o prompt ao vivo, ingredientes e avisos;
posse dos assets; lista com filtros e cursor; duplicar, arquivar, reverter; "onde é usado"."""

# ruff: noqa: F811 — fixtures importadas de `cenas_helpers`

import time
import uuid

from sqlalchemy import select

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    ACHADINHOS,
    _buckets,
    acao,
    base,
    corpo_cena,
    criar_cena,
    get,
    member,
    montar_perfil,
    owner,
    patch,
)
from sociman_api.cenas.models import Cena
from sociman_api.history import EntityVersion


def test_criar_com_todos_os_campos(client, base):
    h = base["h"]
    cena = criar_cena(client, h, base, textoTela="R$ 49,90", camera="eye level", notas="n")
    assert cena["status"] == "rascunho" and cena["version"] == 1
    p = cena["prompt"]
    assert p["congelado"] is False and p["texto"].startswith(ACHADINHOS)
    assert [x["parte"] for x in p["partes"]] == ["avatar", "regras", "acao", "cenario", "camera",
                                                 "estilo", "fala", "audio"]
    assert "R$ 49,90" not in p["texto"]
    assert "exactly as in the reference image" in p["texto"]
    assert [i["papel"] for i in cena["ingredientes"]] == ["avatar", "produto", "cenario"]
    assert cena["ingredientes"][0]["arquivoId"] == base["look"]["id"]
    assert all(i["downloadUrl"].startswith("/api/midia/") for i in cena["ingredientes"])
    assert cena["avatar"]["nome"] == "Achadinhos" and cena["autor"]["nome"] == "Dono"
    assert get(client, h, cena["id"])["prompt"]["texto"] == p["texto"]


def test_historico_created(client, db, base):
    cena = criar_cena(client, base["h"], base)
    rows = list(db.scalars(select(EntityVersion).where(EntityVersion.entity_id
                                                       == uuid.UUID(cena["id"]))))
    assert [(r.entity_type, r.action) for r in rows] == [("cena", "created")]


def test_avisos_no_get(client, base):
    cena = criar_cena(client, base["h"], base, fala="um milagre " * 9, duracaoS=6,
                      produtoImagemId=None)
    codigos = {a["codigo"] for a in cena["avisos"]}
    assert {"fala_longa", "duracao_modo", "produto_sem_foto", "proibida"} <= codigos


def test_assets_de_outro_perfil_ou_arquivo_errado(client, base):
    h = base["h"]
    outro = montar_perfil(client, h, "outro", proibida=None)
    for campo, valor in (("avatarId", outro["avatar"]["id"]), ("cenarioId",
                                                               outro["cenario"]["id"]),
                         ("produtoImagemId", outro["produto"]["id"]),
                         ("avatarId", base["cenario"]["id"])):
        r = client.post(f"/api/perfis/{base['perfil']['id']}/cenas", headers=h,
                        json=corpo_cena(base, **{campo: valor, "avatarArquivoId": None}))
        assert r.status_code == 422, (campo, r.text)
        assert r.json()["error"]["code"] == "cena_invalida"
    r = client.post(f"/api/perfis/{base['perfil']['id']}/cenas", headers=h,
                    json=corpo_cena(base, avatarArquivoId=base["cenario_file"]["id"]))
    assert r.status_code == 422 and r.json()["error"]["details"]["field"] == "avatarArquivoId"


def test_conflito_de_versao(client, base):
    h = base["h"]
    cena = criar_cena(client, h, base)
    patch(client, h, cena, nome="Outro nome")
    r = client.patch(f"/api/cenas/{cena['id']}", headers=h,
                     json={"version": cena["version"], "nome": "De novo"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


def test_lista_filtros_e_cursor(client, base):
    h = base["h"]
    pid = base["perfil"]["id"]
    a = criar_cena(client, h, base, nome="Panela vapor", tags=["abertura"])
    b = criar_cena(client, h, base, nome="Mostra a tampa", avatarId=None, avatarArquivoId=None,
                   fala="Olha o preço", tags=["fecho"], produtoNome="Açucareiro",
                   produtoImagemId=None)
    c = criar_cena(client, h, base, nome="Câmera na mão", cenarioId=None)
    acao(client, h, c, "pronta")

    def ids(**q):
        r = client.get(f"/api/perfis/{pid}/cenas", headers=h, params=q)
        assert r.status_code == 200, r.text
        return {i["id"] for i in r.json()["items"]}

    assert ids() == {a["id"], b["id"], c["id"]}
    assert ids(status="pronta") == {c["id"]}
    assert ids(avatarId=base["avatar"]["id"]) == {a["id"], c["id"]}
    assert ids(cenarioId=base["cenario"]["id"]) == {a["id"], b["id"]}
    assert ids(produtoImagemId=base["produto"]["id"]) == {a["id"], c["id"]}
    assert ids(tag="fecho") == {b["id"]}
    assert ids(q="camera") == {c["id"]}  # sem acento
    assert ids(q="PRECO") == {b["id"]}  # na fala
    assert ids(q="acucareiro") == {b["id"]}  # no produto
    assert ids(q="steam") == {a["id"], b["id"], c["id"]}  # na ação
    pagina = client.get(f"/api/perfis/{pid}/cenas", headers=h, params={"limit": 2}).json()
    assert len(pagina["items"]) == 2 and pagina["nextCursor"]
    resto = client.get(f"/api/perfis/{pid}/cenas", headers=h,
                       params={"limit": 2, "cursor": pagina["nextCursor"]}).json()
    assert len(resto["items"]) == 1 and resto["nextCursor"] is None
    item = next(i for i in pagina["items"] + resto["items"] if i["id"] == a["id"])
    assert item["avatar"]["nome"] == "Achadinhos" and item["thumbUrl"]


def test_duplicar_arquivar_restaurar(client, db, base):
    h = base["h"]
    cena = acao(client, h, criar_cena(client, h, base), "pronta")
    copia = acao(client, h, cena, "duplicar", status=201)
    assert copia["nome"] == "Achadinhos abre a panela (cópia)"
    assert copia["status"] == "rascunho" and copia["tomadas"] == 0 and copia["usos"] == []
    assert copia["duplicadaDe"] == cena["id"]
    row = db.scalar(select(EntityVersion).where(EntityVersion.entity_id
                                                == uuid.UUID(copia["id"])))
    assert row.details == {"duplicadaDe": cena["id"]}
    arq = acao(client, h, copia, "arquivar")
    assert arq["arquivada"] is True
    assert acao(client, h, arq, "arquivar", status=409)["error"]["code"] == "arquivada"
    patch(client, h, arq, status=409, nome="x")
    assert acao(client, h, arq, "restaurar")["arquivada"] is False


def test_revert_dono_membro(client, base, member):
    h = base["h"]
    cena = criar_cena(client, h, base)
    pronta = acao(client, h, cena, "pronta")
    texto = pronta["prompt"]["texto"]
    editada = patch(client, h, pronta, acao="waves")
    assert editada["status"] == "rascunho"
    r = client.post(f"/api/cenas/{cena['id']}/revert", headers=member[1],
                    json={"version": editada["version"], "toVersion": 2})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_dono"
    r = client.post(f"/api/cenas/{cena['id']}/revert", headers=h,
                    json={"version": editada["version"], "toVersion": 2})
    assert r.status_code == 200, r.text
    volta = r.json()
    assert volta["status"] == "pronta" and volta["prompt"]["congelado"] is True
    assert volta["prompt"]["texto"] == texto and volta["acao"] == cena["acao"]


def test_usos_do_asset_nao_bloqueiam(client, base):
    h = base["h"]
    criar_cena(client, h, base)
    criar_cena(client, h, base, nome="Outra")
    r = client.get(f"/api/assets/{base['avatar']['id']}", headers=h)
    usos = [u for u in r.json()["usos"] if u["origem"] == "cena"]
    assert [u["rotulo"] for u in usos] == ["2 cenas"]
    assert usos[0]["bloqueia"] is False and "aba=cenas" in usos[0]["href"]
    produto = client.get(f"/api/assets/{base['produto']['id']}", headers=h).json()
    assert any(u["origem"] == "cena" for u in produto["usos"])
    asset = r.json()["asset"]
    r = client.post(f"/api/assets/{asset['id']}/archive", headers=h,
                    json={"version": asset["version"]})
    assert r.status_code == 200, r.text


def test_desempenho_200_cenas(client, db, base):
    """SC-006: 200 cenas, lista filtrada < 500 ms; detalhe < 200 ms (T047)."""
    pid = uuid.UUID(base["perfil"]["id"])
    one = criar_cena(client, base["h"], base)
    modelo = db.get(Cena, uuid.UUID(one["id"]))
    for i in range(199):
        db.add(Cena(id=uuid.uuid4(), perfil_id=pid, nome=f"Cena {i}", acao=f"acts {i}",
                    avatar_id=modelo.avatar_id, cenario_id=modelo.cenario_id,
                    tags=["lote"] if i % 2 else []))
    db.commit()
    h = base["h"]
    client.get(f"/api/perfis/{pid}/cenas", headers=h)  # aquece
    t0 = time.perf_counter()
    r = client.get(f"/api/perfis/{pid}/cenas", headers=h,
                   params={"tag": "lote", "avatarId": str(modelo.avatar_id), "limit": 100})
    lista = time.perf_counter() - t0
    assert r.status_code == 200 and len(r.json()["items"]) == 99
    t0 = time.perf_counter()
    get(client, h, one["id"])
    detalhe = time.perf_counter() - t0
    assert lista < 0.5, lista
    assert detalhe < 0.2, detalhe
