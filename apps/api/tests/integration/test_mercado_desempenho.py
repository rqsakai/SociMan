"""Desempenho do mercado (spec 026, FR-050, SC-007): o lago com um ano de coleta em 10× o volume
esperado — 20 mil produtos, ~600 mil fotos (55 dias × 2 fotos para 20% dos produtos e 1 foto
semanal para o resto, sobre um ano), 10 categorias × 60 fotos de ranking × 30 itens, 2 mil
interesses — semeados por SQL em lote, e cada rota de leitura responde em menos de 2 s no período
padrão (30 dias). Medir isolado (sem e2e em paralelo)."""

import time
from datetime import UTC, datetime, timedelta

from fakes.coletor_fake import SP
from sqlalchemy import select, text

from integration.coleta_helpers import coletor, dono, ligado  # noqa: F401
from integration.postagem_helpers import criar_perfil
from sociman_api.mercado.models import Categoria, Coleta, Loja

LIMITE_S = 2.0
PRODUTOS = 20_000


def _semear(db, coleta_id, loja_id, cat_id, hoje) -> None:
    p = {"coleta": str(coleta_id), "loja": str(loja_id), "cat": str(cat_id), "hoje": hoje}
    sqls = [
        # 20 mil produtos (20% quentes com 2 fotos/dia nos últimos 55 dias; o resto semanal).
        ("INSERT INTO mercado_produtos (id, rede, mercado, rede_produto_id, url_canonica, titulo_atual,"
         " loja_id, categoria_id, primeira_vez_em, ultimo_visto_em, calor, fotos_por_dia,"
         " proxima_coleta_em, imagens_pendentes, fonte_descoberta, ultimo_ranking_em, coleta_id)"
         " SELECT gen_random_uuid(), 'tiktok', 'BR', 'perf' || lpad(g::text, 15, '0'),"
         " 'https://exemplo.test/shop/product/perf' || g, 'Perf ' || g, CAST(:loja AS uuid),"
         " CAST(:cat AS uuid), now() - (g % 365) * interval '1 day', now(),"
         " CASE WHEN g % 5 = 0 THEN 'quente' ELSE 'morna' END::mercado_calor,"
         " CASE WHEN g % 5 = 0 THEN 2 ELSE 1 END, now(), false, 'ranking',"
         " CAST(:hoje AS date) - (g % 20), CAST(:coleta AS uuid)"
         " FROM generate_series(1, 20000) g"),
        # Quentes: 55 dias × 2 turnos (página pública), vendidos crescendo.
        ("INSERT INTO mercado_produto_fotos (produto_id, data_local, turno, fonte, vendidos,"
         " vendidos_exato, preco_min_centavos, preco_max_centavos, moeda,"
         " disponivel, campos, esquema_versao, coleta_id, coletado_em)"
         " SELECT p.id, CAST(:hoje AS date) - d, t.turno::mercado_turno, 'pagina_publica',"
         " 1000 + p.i * 3 + (55 - d) * (1 + p.i % 30), true, 2990 + p.i % 5000, 3990 + p.i % 5000,"
         " 'BRL', true, '{}', 'tiktok_shop/1',"
         " CAST(:coleta AS uuid), now() - d * interval '1 day'"
         " FROM (SELECT id, row_number() OVER (ORDER BY rede_produto_id) AS i FROM mercado_produtos"
         " WHERE rede_produto_id LIKE 'perf%' AND calor = 'quente') p"
         " CROSS JOIN generate_series(0, 54) d CROSS JOIN (VALUES ('manha'), ('noite')) t(turno)"),
        # Quentes: foto do Affiliate Center 1/dia.
        ("INSERT INTO mercado_produto_fotos (produto_id, data_local, turno, fonte, vendidos,"
         " preco_min_centavos, moeda, comissao_bp, n_criadores, vendas_7d, disponivel, campos,"
         " esquema_versao, coleta_id, coletado_em)"
         " SELECT p.id, CAST(:hoje AS date) - d, 'manha', 'affiliate', NULL, 2990 + p.i % 5000,"
         " 'BRL', 500 + (p.i % 20) * 100, 10 + p.i % 200, 7 * (1 + p.i % 30), true, '{}',"
         " 'tiktok_shop/1', CAST(:coleta AS uuid), now() - d * interval '1 day'"
         " FROM (SELECT id, row_number() OVER (ORDER BY rede_produto_id) AS i FROM mercado_produtos"
         " WHERE rede_produto_id LIKE 'perf%' AND calor = 'quente') p"
         " CROSS JOIN generate_series(0, 54) d"),
        # Mornas: uma foto por semana ao longo de um ano.
        ("INSERT INTO mercado_produto_fotos (produto_id, data_local, turno, fonte, vendidos,"
         " vendidos_exato, preco_min_centavos, moeda, disponivel, campos, esquema_versao,"
         " coleta_id, coletado_em)"
         " SELECT p.id, CAST(:hoje AS date) - 7 * w, 'manha', 'pagina_publica',"
         " 500 + p.i + (52 - w) * 2, true, 1990 + p.i % 3000, 'BRL', true, '{}',"
         " 'tiktok_shop/1', CAST(:coleta AS uuid), now() - 7 * w * interval '1 day'"
         " FROM (SELECT id, row_number() OVER (ORDER BY rede_produto_id) AS i FROM mercado_produtos"
         " WHERE rede_produto_id LIKE 'perf%' AND calor = 'morna') p"
         " CROSS JOIN generate_series(0, 52) w"),
        # Rankings: 60 fotos (dias) × 30 itens na categoria.
        ("INSERT INTO mercado_ranking_fotos (id, rede, mercado, fonte, categoria_id, tipo, janela,"
         " data_local, n_itens, esquema_versao, coleta_id, coletado_em)"
         " SELECT gen_random_uuid(), 'tiktok', 'BR', 'affiliate', CAST(:cat AS uuid),"
         " 'mais_vendidos', '7d', CAST(:hoje AS date) - d, 30, 'tiktok_shop/1',"
         " CAST(:coleta AS uuid), now() - d * interval '1 day' FROM generate_series(1, 60) d"),
        ("INSERT INTO mercado_ranking_foto_itens (ranking_foto_id, posicao, produto_id, valor_exibido,"
         " campos)"
         " SELECT f.id, k, p.id, (1000 - k * 10)::text || ' vendidos', '{}'"
         " FROM mercado_ranking_fotos f CROSS JOIN generate_series(1, 30) k"
         " JOIN (SELECT id, row_number() OVER (ORDER BY rede_produto_id) AS i FROM mercado_produtos"
         " WHERE rede_produto_id LIKE 'perf%' AND calor = 'quente') p"
         " ON p.i = ((extract(day from f.data_local)::int + k) % 300) + 1"
         " WHERE f.categoria_id = CAST(:cat AS uuid) AND f.data_local < CAST(:hoje AS date)"),
        # 2 mil interesses de vitrine (perfil nulo).
        ("INSERT INTO mercado_interesses (id, perfil_id, mercado_produto_id, origem, situacao,"
         " motivo, nota, version, created_at, updated_at)"
         " SELECT gen_random_uuid(), NULL, p.id, 'vitrine', 'ativo', '{}', '', 1, now(), now()"
         " FROM (SELECT id, row_number() OVER (ORDER BY rede_produto_id) AS i FROM mercado_produtos"
         " WHERE rede_produto_id LIKE 'perf%') p WHERE p.i % 10 = 0"),
    ]
    for sql in sqls:
        db.execute(text(sql), p)
    db.execute(text("ANALYZE mercado_produtos; ANALYZE mercado_produto_fotos; "
                    "ANALYZE mercado_ranking_fotos; ANALYZE mercado_ranking_foto_itens; "
                    "ANALYZE mercado_interesses"))
    db.commit()


def test_rotas_de_leitura_abaixo_de_2s(client, db, ligado, coletor):  # noqa: F811
    criar_perfil(client, ligado)
    coletor.semear(db, produtos=1, dias=1)  # a coleta, a loja X e a categoria cat45
    coleta_id = db.scalar(select(Coleta.id))
    loja_id = db.scalar(select(Loja.id))
    cat_id = db.scalar(select(Categoria.id).where(Categoria.rede_categoria_id == "cat45"))
    hoje = datetime.now(UTC).astimezone(SP).date()
    t0 = time.perf_counter()
    _semear(db, coleta_id, loja_id, cat_id, hoje.isoformat())
    semeadura = time.perf_counter() - t0
    assert db.scalar(text("SELECT count(*) FROM mercado_produto_fotos")) > 500_000
    periodo = {"de": (hoje - timedelta(days=29)).isoformat(), "ate": hoje.isoformat()}
    rotas = {
        "mercado_produtos_listar": ("/api/mercado/produtos", {**periodo, "limite": 50}),
        "mercado_produtos_listar_ordenado": ("/api/mercado/produtos",
                                             {**periodo, "limite": 50, "ordenar": "crescimento"}),
        "mercado_resumo": ("/api/mercado/resumo", periodo),
        "mercado_rankings_listar": ("/api/mercado/rankings",
                                    {**periodo, "categoriaId": str(cat_id)}),
        "mercado_lojas_listar": ("/api/mercado/lojas", periodo),
    }
    pid = client.get("/api/mercado/produtos", headers=ligado,
                     params={**periodo, "limite": 1}).json()["itens"][0]["id"]
    rotas["mercado_produtos_serie"] = (f"/api/mercado/produtos/{pid}/serie", periodo)
    tempos = {}
    for nome, (url, params) in rotas.items():
        t = time.perf_counter()
        r = client.get(url, headers=ligado, params=params)
        tempos[nome] = time.perf_counter() - t
        assert r.status_code == 200, (nome, r.text[:300])
    lentas = {n: round(s, 2) for n, s in tempos.items() if s > LIMITE_S}
    assert not lentas, f"rotas acima de {LIMITE_S}s: {lentas} (semeadura {semeadura:.0f}s)"
