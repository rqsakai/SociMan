"""`reprocessar --desde` do lado da API (FR-012, contracts/coletor.md): o token do coletor lista
e detalha só as próprias rodadas, baixa o bruto pelo link e reenvia os campos renormalizados para
a rodada original (já fechada) com `reprocessadoDe`; sem `reprocessadoDe` a rodada fechada
continua 409; a rodada de outro cliente é 404."""

import gzip
import json
from datetime import UTC, datetime

from fakes.coletor_fake import SP, ColetorFake, criar_cliente_coleta
from sqlalchemy import select, text

from integration.coleta_helpers import coletor, dono, ligado  # noqa: F401
from sociman_api.mercado.models import Ficha, FotoProduto

HOJE = datetime.now(UTC).astimezone(SP).date()


def test_reprocessar_le_so_as_proprias_rodadas_e_reenvia_na_fechada(client, db, ligado, coletor):  # noqa: F811
    coletor.semear(db, produtos=1, dias=1, ranking=False)
    db.commit()
    # Lista e detalhe pelo token do coletor.
    r = client.get("/api/coleta/coletas", headers=coletor.h)
    assert r.status_code == 200, r.text
    rodadas = r.json()["itens"]
    assert len(rodadas) == 1 and rodadas[0]["estado"] == "encerrada"
    cid = rodadas[0]["id"]
    det = client.get(f"/api/coleta/coletas/{cid}", headers=coletor.h)
    assert det.status_code == 200 and det.json()["itens"]
    item = next(i for i in det.json()["itens"] if i["tipo"] == "produto")
    # Outro cliente não vê esta rodada (404) nem a lista dele a traz.
    _, token2 = criar_cliente_coleta(client, ligado, "outro desktop")
    outro = ColetorFake(client, token2)
    assert client.get(f"/api/coleta/coletas/{cid}", headers=outro.h).status_code == 404
    assert client.get("/api/coleta/coletas", headers=outro.h).json()["itens"] == []
    # O bruto da tarefa pelo link e o reenvio renormalizado com `reprocessadoDe`.
    link = client.get(f"/api/coleta/coletas/{cid}/bruto/{item['tarefaId']}", headers=coletor.h)
    assert link.status_code == 200, link.text
    bruto = client.get(link.json()["link"]["url"])
    assert bruto.status_code == 200
    campos = json.loads(gzip.decompress(bruto.content))["campos"]
    campos["ficha"]["titulo"] = "Produto 0 (parser novo)"
    fotos_antes = db.scalar(select(FotoProduto).where(FotoProduto.produto_id.is_not(None)).limit(1))
    n_fotos = db.scalar(text("SELECT count(*) FROM mercado_produto_fotos"))
    reenvio = coletor.item(item["tarefaId"], campos, HOJE)
    reenvio["reprocessadoDe"] = item["id"]
    r = client.post(f"/api/coleta/coletas/{cid}/itens", headers=coletor.h,
                    json={"itens": [reenvio]})
    assert r.status_code == 200, r.text
    res = r.json()["resultados"][0]
    assert res["status"] == "gravado" and res["fichaNova"] is True
    db.expire_all()
    assert db.scalar(text("SELECT count(*) FROM mercado_produto_fotos")) == n_fotos  # foto repetida
    assert db.scalar(select(Ficha).where(Ficha.titulo == "Produto 0 (parser novo)")) is not None
    assert fotos_antes is not None
    # Sem `reprocessadoDe`, a rodada fechada recusa.
    r = client.post(f"/api/coleta/coletas/{cid}/itens", headers=coletor.h,
                    json={"itens": [coletor.item(item["tarefaId"], campos, HOJE)]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "coleta_fechada"
    # Reenviar o mesmo de novo: tudo repetido (idempotente).
    r = client.post(f"/api/coleta/coletas/{cid}/itens", headers=coletor.h,
                    json={"itens": [reenvio]})
    assert r.json()["resultados"][0]["status"] == "repetido"
    # O usuário continua vendo todas as rodadas (as de qualquer cliente).
    assert len(client.get("/api/coleta/coletas", headers=ligado).json()["itens"]) == 1
