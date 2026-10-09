"""T020 (FR-027..FR-032, SC-004): a ingestão pela API com o coletor falso: rodada, lote,
idempotência, ficha por conteúdo, imagens deduplicadas e validadas, poda do bruto, HD ausente,
dia e turno do servidor, eventos e fechamento."""

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
from fakes.coletor_fake import SP, ColetorFake, bruto, coletado_em, png, sha
from sqlalchemy import func, select, text

from integration.coleta_helpers import coletor, criar_cliente_coleta, dono, ligado  # noqa: F401
from sociman_api import datadir
from sociman_api.coleta.models import Evento
from sociman_api.mercado.models import (
    Avaliacao,
    ColetaItem,
    Ficha,
    FotoProduto,
    Imagem,
    Interesse,
    Produto,
    ProdutoImagem,
    Tarefa,
    VideoProduto,
)
from sociman_api.notificacoes.models import Notificacao

HOJE = datetime.now(UTC).astimezone(SP).date()


def _n(db, modelo, *where) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo).where(*where))


def _tarefa_produto(fake: ColetorFake, db, i: int = 0, dia=HOJE, **extra) -> str:
    return fake.tarefa(db, "produto", f"produto:{fake.produto_id(i)}", fake.url_produto(i), dia,
                       **extra)


def test_abrir_rodada_uma_por_cliente(client, db, coletor):  # noqa: F811
    c = coletor.abrir()
    assert c["estado"] == "ativa" and c["protocolo"] == 1
    r = client.post("/api/coleta/coletas", headers=coletor.h,
                    json={"versaoColetor": "0.1.0", "protocolo": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "coleta_em_andamento"
    assert r.json()["error"]["details"]["coletaId"] == c["id"]
    coletor.fechar()
    assert coletor.abrir()["id"] != c["id"]


def test_fila_reserva_e_lote_gravado_repetido(client, db, coletor):  # noqa: F811
    tid = _tarefa_produto(coletor, db)
    fila = coletor.fila()
    assert [t["tarefaId"] for t in fila["tarefas"]] == [tid]
    assert fila["tarefas"][0]["reservadaAte"] is not None
    assert fila["limites"]["paginasDia"] == 300 and fila["orcamento"]["paginasRestantes"] == 300
    assert db.get(Tarefa, uuid.UUID(tid)).estado.value == "reservada"
    coletor.abrir()
    campos = coletor.campos_produto(0, 0)
    r = coletor.itens([coletor.item(tid, campos, HOJE)])
    res = r["resultados"][0]
    assert res["status"] == "gravado" and res["fichaNova"] is True
    assert res["dataLocal"] == HOJE.isoformat() and res["turno"] == "manha"
    assert r["orcamento"]["paginasHoje"] == 1 and r["parar"] is False
    # Reenvio do mesmo item (timeout do lado do coletor): repetido, nada gravado duas vezes.
    r = coletor.itens([coletor.item(tid, campos, HOJE)])
    assert r["resultados"][0]["status"] == "repetido"
    assert _n(db, FotoProduto) == 2  # pagina_publica + affiliate
    assert _n(db, Ficha) == 1 and _n(db, Produto) == 1
    assert _n(db, ColetaItem) == 2
    tarefa = db.get(Tarefa, uuid.UUID(tid))
    assert tarefa.estado.value == "recebida" and tarefa.resultado_status.value == "gravado"
    produto = db.scalar(select(Produto))
    assert produto.titulo_atual == "Produto 0" and produto.ficha_atual_id is not None
    assert produto.ultima_foto_em == HOJE and produto.ultima_foto_affiliate_em == HOJE
    assert produto.loja_id is not None and produto.categoria_id is not None
    c = coletor.fechar()
    assert c["estado"] == "encerrada" and c["itensOk"] == 1 and c["itensRepetidos"] == 1
    assert c["paginas"] == 2


def test_turno_noite_e_dia_do_servidor(client, db, coletor):  # noqa: F811
    """Dia e turno vêm do `coletadoEm` no fuso do mercado, não do relógio do coletor."""
    tid = _tarefa_produto(coletor, db)
    coletor.fila()
    coletor.abrir()
    item = coletor.item(tid, coletor.campos_produto(0, 0), HOJE, hora=16)
    res = coletor.itens([item])["resultados"][0]
    assert res["turno"] == "noite"
    # 01:30 UTC é 22:30 do dia anterior em São Paulo.
    tid2 = _tarefa_produto(coletor, db, 1, dia=HOJE - timedelta(days=1))
    coletor.fila()  # a tarefa de ontem não entra na fila de hoje (fica pendente)
    db.execute(text("UPDATE mercado_fila SET estado = 'reservada', cliente_id = (SELECT id FROM "
                    "coleta_clientes LIMIT 1), reservada_ate = now() + interval '30 minutes' "
                    "WHERE id = :id"), {"id": tid2})
    db.commit()
    utc = datetime.combine(HOJE, time(1, 30), UTC).isoformat()
    item = coletor.item(tid2, coletor.campos_produto(1, 0), HOJE)
    item["coletadoEm"] = utc
    res = coletor.itens([item])["resultados"][0]
    assert res["status"] == "gravado"
    assert res["dataLocal"] == (HOJE - timedelta(days=1)).isoformat() and res["turno"] == "noite"


def test_item_invalido_nao_derruba_o_lote(client, db, coletor):  # noqa: F811
    t_ok = _tarefa_produto(coletor, db, 0)
    t_ruim = _tarefa_produto(coletor, db, 1)
    coletor.fila()
    coletor.abrir()
    ruim = coletor.item(t_ruim, {"redeProdutoId": coletor.produto_id(1),
                                 "urlCanonica": coletor.url_produto(1),
                                 "ficha": {"descricao": "sem título"}}, HOJE)
    r = coletor.itens([coletor.item(t_ok, coletor.campos_produto(0, 0), HOJE), ruim])
    por = {x["tarefaId"]: x for x in r["resultados"]}
    assert por[t_ok]["status"] == "gravado"
    assert por[t_ruim]["status"] == "invalido"
    assert por[t_ruim]["erroCodigo"] == "campos_invalidos"
    assert por[t_ruim]["erroCampo"] == "ficha.titulo"
    assert por[t_ruim]["tentativas"] == 1 and por[t_ruim]["voltaParaFila"] is True
    assert db.get(Tarefa, uuid.UUID(t_ruim)).estado.value == "pendente"
    # Tarefa desconhecida, de outro cliente e esquema errado.
    r = coletor.itens([coletor.item(str(uuid.uuid4()), coletor.campos_produto(2, 0), HOJE)])
    assert r["resultados"][0]["erroCodigo"] == "tarefa_desconhecida"
    t3 = _tarefa_produto(coletor, db, 3)
    coletor.fila()
    item = coletor.item(t3, coletor.campos_produto(3, 0), HOJE)
    item["esquemaVersao"] = "tiktok_shop/9"
    assert coletor.itens([item])["resultados"][0]["erroCodigo"] == "esquema_desconhecido"
    t4 = _tarefa_produto(coletor, db, 4)
    coletor.fila()
    campos = coletor.campos_produto(4, 0)
    campos["urlCanonica"] = "https://exemplo.test/shop/product/999"
    assert coletor.itens([coletor.item(t4, campos, HOJE)])["resultados"][0]["erroCodigo"] \
        == "url_divergente"


def test_ficha_igual_nao_cria_versao_e_mudada_cria(client, db, coletor):  # noqa: F811
    for n in range(3):
        tid = _tarefa_produto(coletor, db, 0, dia=HOJE)
        db.execute(text("UPDATE mercado_fila SET data_local = :d WHERE id = :id"),
                   {"d": HOJE - timedelta(days=2 - n), "id": tid})
        db.commit()
        db.execute(text("UPDATE mercado_fila SET estado = 'reservada', cliente_id = (SELECT id "
                        "FROM coleta_clientes LIMIT 1), reservada_ate = now() + interval "
                        "'30 minutes' WHERE id = :id"), {"id": tid})
        db.commit()
        coletor.abrir()
        titulo = "Produto 0" if n < 2 else "Produto 0 renomeado"
        res = coletor.itens([coletor.item(tid, coletor.campos_produto(0, n, titulo=titulo),
                                          HOJE - timedelta(days=2 - n))])["resultados"][0]
        assert res["status"] == "gravado"
        assert res["fichaNova"] is (n != 1)
        coletor.fechar()
    assert _n(db, Ficha) == 2
    produto = db.scalar(select(Produto))
    assert produto.titulo_atual == "Produto 0 renomeado"
    fichas = db.scalars(select(Ficha).order_by(Ficha.created_at)).all()
    assert fichas[0].titulo == "Produto 0" and produto.ficha_atual_id == fichas[1].id


def test_imagens_dedup_validacao_sha_e_vinculo_pendente(client, db, coletor, s3):  # noqa: F811
    a, b = png(1), png(2)
    t0 = _tarefa_produto(coletor, db, 0)
    t1 = _tarefa_produto(coletor, db, 1)
    coletor.fila()
    coletor.abrir()
    # O item cita 2 shas antes de as imagens subirem: ficam pendentes.
    campos0 = coletor.campos_produto(0, 0, imagens=[a, b])
    res = coletor.itens([coletor.item(t0, campos0, HOJE, imagens=[a, b])])["resultados"][0]
    assert sorted(res["imagensPendentes"]) == sorted([sha(a), sha(b)])
    assert db.scalar(select(Produto).where(Produto.rede_produto_id == coletor.produto_id(0))
                     ).imagens_pendentes is True
    r = coletor.imagens([a, b], t0)
    assert sorted(r["aceitas"]) == sorted([sha(a), sha(b)]) and r["recusadas"] == []
    assert r["orcamento"]["imagensHoje"] == 2
    db.expire_all()
    assert _n(db, ProdutoImagem) == 2  # vínculos materializados
    assert db.scalar(select(Produto).where(Produto.rede_produto_id == coletor.produto_id(0))
                     ).imagens_pendentes is False
    # A mesma imagem em outro produto: 1 objeto, 2 vínculos.
    campos1 = coletor.campos_produto(1, 0, imagens=[a])
    coletor.itens([coletor.item(t1, campos1, HOJE, imagens=[a])])
    r = coletor.imagens([a], t1)
    assert r["repetidas"] == [sha(a)] and r["aceitas"] == []
    assert _n(db, Imagem) == 2 and _n(db, ProdutoImagem) == 3
    chaves = db.scalars(select(Imagem.object_key)).all()
    assert all(k.startswith(f"mercado/{sha(x)[:2]}/{sha(x)}.png") for k, x in
               zip(sorted(chaves), sorted([a, b], key=sha), strict=True))
    # Não é imagem e sha divergente.
    manifesto_errado = [("arquivos", ("x.png", b"nao e imagem", "image/png"))]
    import json
    r = client.post(f"/api/coleta/coletas/{coletor.coleta['id']}/imagens", headers=coletor.h,
                    files=manifesto_errado,
                    data={"manifesto": json.dumps([{"sha256": sha(b"nao e imagem"),
                                                    "tarefaId": t0, "origem": "produto"}])})
    assert r.json()["recusadas"][0]["motivo"] == "imagem_invalida"
    c = png(3)
    r = client.post(f"/api/coleta/coletas/{coletor.coleta['id']}/imagens", headers=coletor.h,
                    files=[("arquivos", ("c.png", c, "image/png"))],
                    data={"manifesto": json.dumps([{"sha256": "0" * 64, "tarefaId": t0,
                                                    "origem": "produto"}])})
    assert r.json()["recusadas"][0]["motivo"] == "sha_divergente"
    assert _n(db, Imagem) == 2


def test_bruto_com_dado_pessoal_e_recusado(client, db, coletor):  # noqa: F811
    tid = _tarefa_produto(coletor, db)
    coletor.fila()
    coletor.abrir()
    item = coletor.item(tid, coletor.campos_produto(0, 0), HOJE)
    item["bruto"] = bruto({"reviews": [{"user_name": "Fulana", "texto": "ok"}]})
    res = coletor.itens([item])["resultados"][0]
    assert res["status"] == "invalido" and res["erroCodigo"] == "bruto_pessoal"
    assert "user_name" in res["erroCampo"]
    assert _n(db, FotoProduto) == 0
    # Chave já podada pelo coletor passa; nickname nos campos também é recusado.
    coletor.fila()
    item = coletor.item(tid, coletor.campos_produto(0, 0), HOJE)
    item["bruto"] = bruto({"reviews": [{"user_name": "[podado]", "texto": "ok"}]})
    assert coletor.itens([item])["resultados"][0]["status"] == "gravado"
    tid2 = _tarefa_produto(coletor, db, 1)
    coletor.fila()
    campos = coletor.campos_produto(1, 0)
    campos["ficha"]["nickname"] = "alguém"
    res = coletor.itens([coletor.item(tid2, campos, HOJE)])["resultados"][0]
    assert res["erroCodigo"] == "bruto_pessoal"


def test_hd_ausente_grava_foto_e_marca_bruto_pendente(client, db, coletor, monkeypatch):  # noqa: F811
    tid = _tarefa_produto(coletor, db)
    coletor.fila()
    coletor.abrir()
    real = datadir.status

    def _sem_hd(min_free_gb=None):
        s = real(min_free_gb)
        return datadir.DataDirStatus(False, "sem_sentinela", s.free_bytes, s.total_bytes,
                                     s.min_free_bytes)

    monkeypatch.setattr(datadir, "status", _sem_hd)
    res = coletor.itens([coletor.item(tid, coletor.campos_produto(0, 0), HOJE)])["resultados"][0]
    assert res["status"] == "gravado" and res["brutoPendente"] is True
    foto = db.scalar(select(FotoProduto))
    assert foto is not None and foto.bruto_ref is None
    r = client.get(f"/api/coleta/coletas/{coletor.coleta['id']}/bruto/{tid}", headers=coletor.h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "bruto_nao_encontrado"


def test_link_do_bruto_para_reprocessar(client, db, coletor, s3):  # noqa: F811
    tid = _tarefa_produto(coletor, db)
    coletor.fila()
    coletor.abrir()
    res = coletor.itens([coletor.item(tid, coletor.campos_produto(0, 0), HOJE)])["resultados"][0]
    assert res["brutoPendente"] is False
    r = client.get(f"/api/coleta/coletas/{coletor.coleta['id']}/bruto/{tid}", headers=coletor.h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["link"]["url"].startswith("/api/midia/") and body["link"]["expiresAt"]
    assert body["esquemaVersao"] == "tiktok_shop/1" and body["bytes"] > 0
    r = client.get(body["link"]["url"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/gzip")
    import gzip
    import json
    assert json.loads(gzip.decompress(r.content))["campos"]["redeProdutoId"] == coletor.produto_id(0)


def test_eventos_mudam_a_rodada_e_notificam_uma_vez_por_dia(client, db, coletor, dono):  # noqa: F811
    _, h = dono
    coletor.abrir()
    r = coletor.evento("captcha", detalhe={"contagem": 1, "tipoTarefa": "produto"})
    assert r["notificado"] is True and r["coleta"]["estado"] == "pausada_captcha"
    r = coletor.evento("captcha")
    assert r["notificado"] is False  # dedupe por tipo e dia
    assert _n(db, Notificacao, Notificacao.tipo == "coleta_captcha") == 1
    assert _n(db, Evento) == 2
    # Fila vazia enquanto aguarda o "Continuar".
    assert coletor.fila()["motivoVazia"] == "aguardando_continuar"
    # Detalhe com dado pessoal é recusado.
    rr = client.post("/api/coleta/eventos", headers=coletor.h,
                     json={"tipo": "captcha", "detalhe": {"nickname": "x"}})
    assert rr.status_code == 400 and rr.json()["error"]["code"] == "bruto_pessoal"
    # Bloqueio: rodada abortada, recuo de 24 h na config, notificação própria.
    r = coletor.evento("bloqueio_suspeito", detalhe={"codigoHttp": 429, "contagem": 3})
    assert r["coleta"]["estado"] == "abortada" and r["pausadaAte"] is not None
    assert coletor.fila()["motivoVazia"] == "pausada"
    cfg = client.get("/api/coleta/config", headers=h).json()
    assert cfg["pausadaAte"] is not None
    coletor.coleta = None
    # Um "parado" não notifica.
    coletor.abrir()
    r = coletor.evento("parado")
    assert r["notificado"] is False and r["coleta"]["estado"] == "interrompida"


def test_fechar_devolve_reservas_e_batimento(client, db, coletor):  # noqa: F811
    t0 = _tarefa_produto(coletor, db, 0)
    _tarefa_produto(coletor, db, 1)
    coletor.fila()
    coletor.abrir()
    b = coletor.batimento(tarefaAtualId=t0)
    assert b["parar"] is False and b["limites"]["paginasDia"] == 300
    coletor.itens([coletor.item(t0, coletor.campos_produto(0, 0), HOJE)])
    c = coletor.fechar("fila_vazia")
    assert c["estado"] == "encerrada" and c["resumo"]["motivo"] == "fila_vazia"
    estados = sorted(e.value for e in db.scalars(select(Tarefa.estado)))
    assert estados == ["pendente", "recebida"]
    # Fechar de novo é idempotente; batimento numa fechada → 409.
    r = client.post(f"/api/coleta/coletas/{c['id']}/fim", headers=coletor.h,
                    json={"motivo": "fila_vazia"})
    assert r.status_code == 200
    r = client.post(f"/api/coleta/coletas/{c['id']}/batimento", headers=coletor.h,
                    json={"estado": "ativa"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "coleta_fechada"


def test_ranking_avaliacoes_videos_loja_categorias_vitrine(client, db, coletor):  # noqa: F811
    coletor.abrir()
    tr = coletor.tarefa(db, "ranking", "ranking:cat45:mais_vendidos:7d",
                        "https://exemplo.test/shop/ranking/cat45", HOJE, nivel=3,
                        fonte="affiliate")
    ta = coletor.tarefa(db, "avaliacoes", f"avaliacoes:{coletor.produto_id(0)}:1",
                        coletor.url_produto(0), HOJE, nivel=8, fonte="pagina_publica")
    tv = coletor.tarefa(db, "produto_videos", f"produto_videos:{coletor.produto_id(0)}",
                        coletor.url_produto(0), HOJE, nivel=7, fonte="affiliate")
    tl = coletor.tarefa(db, "loja", "loja:loja123", "https://exemplo.test/shop/shop/loja123",
                        HOJE, nivel=6, fonte="pagina_publica")
    tc = coletor.tarefa(db, "categorias", "categorias", "https://exemplo.test/shop/categorias",
                        HOJE, nivel=6, fonte="affiliate")
    tvit = coletor.tarefa(db, "vitrine", "vitrine", "https://exemplo.test/shop/vitrine", HOJE,
                          nivel=1, fonte="affiliate")
    coletor.fila()
    foto = png(9)
    coletor.imagens([foto], ta, origem="avaliacao")
    r = coletor.itens([
        coletor.item(tr, coletor.campos_ranking(3, 0), HOJE),
        coletor.item(ta, coletor.campos_avaliacoes(0, 5, imagens=[foto]), HOJE),
        coletor.item(tv, coletor.campos_videos(0, 3), HOJE),
        coletor.item(tl, coletor.campos_loja(2), HOJE),
        coletor.item(tc, coletor.campos_categorias(), HOJE),
        coletor.item(tvit, coletor.campos_vitrine([0, 1]), HOJE),
    ])
    assert all(x["status"] == "gravado" for x in r["resultados"]), r["resultados"]
    assert _n(db, Avaliacao) == 5 and _n(db, VideoProduto) == 3
    av = db.scalars(select(Avaliacao)).all()
    assert all(len(a.autor_hash) == 64 for a in av)
    assert not any("autor" in str(a.campos) for a in av)
    assert av[0].imagens_sha == [sha(foto)] or any(a.imagens_sha == [sha(foto)] for a in av)
    produto0 = db.scalar(select(Produto).where(Produto.rede_produto_id == coletor.produto_id(0)))
    assert produto0.ultimo_ranking_em == HOJE
    assert produto0.ultimas_avaliacoes_em == HOJE and produto0.ultimos_videos_em == HOJE
    assert _n(db, Produto) == 3 + 2  # 3 do ranking + 2 novos da loja
    assert _n(db, Interesse) == 2  # vitrine → interesses `vitrine` com perfil nulo
    assert all(i.perfil_id is None and i.origem.value == "vitrine"
               for i in db.scalars(select(Interesse)))
    # Reenvio: tudo repetido, nada duplicado; vitrine de novo não duplica interesses.
    r = coletor.itens([
        coletor.item(tr, coletor.campos_ranking(3, 0), HOJE),
        coletor.item(ta, coletor.campos_avaliacoes(0, 5), HOJE),
        coletor.item(tvit, coletor.campos_vitrine([0, 1]), HOJE),
    ])
    assert {x["status"] for x in r["resultados"]} == {"repetido"}
    assert _n(db, Avaliacao) == 5 and _n(db, Interesse) == 2


def test_lote_vazio_ou_grande_e_rodada_de_outro_cliente(client, db, coletor, ligado):  # noqa: F811
    c = coletor.abrir()
    r = client.post(f"/api/coleta/coletas/{c['id']}/itens", headers=coletor.h, json={"itens": []})
    assert r.status_code == 400
    _, outro_token = criar_cliente_coleta(client, ligado, "outro")
    outro = ColetorFake(client, outro_token)
    r = client.post(f"/api/coleta/coletas/{c['id']}/batimento", headers=outro.h,
                    json={"estado": "ativa"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "coleta_nao_encontrada"


@pytest.mark.parametrize("hora, turno", [(8, "manha"), (15, "manha"), (16, "noite")])
def test_segunda_foto_do_dia_por_turno(client, db, coletor, hora, turno):  # noqa: F811
    tid = _tarefa_produto(coletor, db, 0, turno=turno)
    coletor.fila()
    coletor.abrir()
    item = coletor.item(tid, coletor.campos_produto(0, 0), HOJE, hora=hora)
    res = coletor.itens([item])["resultados"][0]
    assert res["status"] == "gravado" and res["turno"] == turno
    assert coletado_em(HOJE, hora).endswith("-03:00")
