"""Limpeza de 90 dias com produtos (spec 012, T028, R12): as opções não escolhidas de flat saem;
o flat escolhido, os recortes e as originais ficam, inclusive a imagem de uma variante
arquivada que não passou pelo `escolhido` (provedor `produtos/uso.py`)."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from sqlalchemy import select, text

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.produtos_helpers import (  # noqa: F401 (fixtures)
    claude_fake,
    criar,
    escolher,
    passos,
    perfil,
    rodar_tudo,
    ver,
)
from sociman_api import storage
from sociman_api.auth.deps import CLI
from sociman_api.auth.models import SecurityEvent
from sociman_api.db import get_engine
from sociman_api.geracao import limpeza


def _sql(sql: str, **p):
    with get_engine().begin() as conn:
        return conn.execute(text(sql), p)


def _existe(key: str) -> bool:
    try:
        storage.stat(key)
        return True
    except Exception:  # noqa: BLE001 — NoSuchKey
        return False


def _chave(image_id: str) -> str:
    return _sql("SELECT object_key FROM images WHERE id = :i", i=image_id).scalar()


def test_limpa_opcoes_de_flat_e_mantem_o_que_o_produto_usa(client, owner, motores,
                                                           claude_fake, db):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=2)
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    flats = {f["varianteId"]: f for f in passos(p, "produto.flat")}
    v0, v1 = p["variantes"]
    escolher(client, h, p, flats[v0["id"]]["id"], numero=1)
    p = ver(client, h, p["id"])
    escolher(client, h, p, flats[v1["id"]]["id"], numero=2)
    p = ver(client, h, p["id"])
    # A variante 2 arquivada aponta para a opção NÃO escolhida da 1ª variante (fora do
    # `escolhido`): só o provedor do produto a protege.
    g0 = client.get(f"/api/geracoes/{flats[v0['id']]['id']}", headers=h).json()
    nao_escolhida = next(c for c in g0["candidatos"] if c["numero"] == 2)["imagem"]["imageId"]
    r = client.post(f"/api/produtos/{p['id']}/variantes/{v1['id']}/arquivar", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 200, r.text
    _sql("UPDATE produto_variantes SET flat_image_id = :img WHERE id = :v",
         img=nao_escolhida, v=v1["id"])
    g1 = client.get(f"/api/geracoes/{flats[v1['id']]['id']}", headers=h).json()
    descartavel = next(c for c in g1["candidatos"] if c["numero"] == 1)["imagem"]["imageId"]
    chaves = {"original": _chave(v0["original"]["imageId"]),
              "recorte": _chave(v0["recorte"]["imageId"]),
              "flat": _chave(p["variantes"][0]["flat"]["imageId"]),
              "arquivada": _chave(nao_escolhida), "descartavel": _chave(descartavel)}
    _sql("UPDATE geracoes SET finished_at = now() - interval '91 days' "
         "WHERE finished_at IS NOT NULL")

    r = limpeza.limpar(db, CLI)
    assert r.candidatos == 1 and r.mantidos == 1
    assert not _existe(chaves.pop("descartavel"))
    assert all(_existe(k) for k in chaves.values())
    eventos = db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "eliminacao_candidatos")).all()
    assert eventos and all(e.details["excecao"] == "candidatos_90d" for e in eventos)
    # A folha continua com o flat escolhido da variante ativa.
    p = ver(client, h, p["id"])
    assert p["variantes"][0]["flat"]["imageId"]
