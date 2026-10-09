"""Escala da central (spec 014, SC-006, T017): 500 conteúdos e 1.000 destinos; 30 chamadas de
`GET /api/conteudos` com filtros combinados ficam com p95 < 200 ms no servidor, e o número de
consultas por página não cresce com o tamanho da página (sem N+1)."""

import statistics
import time

import pytest
from sqlalchemy import event, text

from integration.postagem_helpers import criar_conta, criar_perfil, dono  # noqa: F401
from sociman_api.db import get_engine

CONTEUDOS = 500
P95_MS = 200


def _semear(conn, perfis: list[str], contas: list[str]) -> None:
    """Cortes e conteúdos em massa (metade em cada perfil) e dois destinos por conteúdo."""
    conn.execute(text("""
        INSERT INTO cortes (id, perfil_id, hook_text, status, kit_version, kit_tokens,
            original_filename, original_key, original_content_type, original_bytes,
            duration_ms, width, height, fps, video_codec, original_sha256, result_key,
            openshorts_title, created_at)
        SELECT g.id, CASE WHEN g.n % 2 = 0 THEN CAST(:p0 AS uuid) ELSE CAST(:p1 AS uuid) END,
            'Gancho ' || g.n,
            CAST(CASE WHEN g.n % 10 = 0 THEN 'revisao' ELSE 'pronto' END AS corte_status),
            CASE WHEN g.n % 10 = 0 THEN NULL ELSE 1 END,
            CASE WHEN g.n % 10 = 0 THEN NULL ELSE CAST('{}' AS jsonb) END,
            'c.mp4', 'k/' || g.id, 'video/mp4', 1, 30000, 1080, 1920, 30, 'h264', 'x',
            CASE WHEN g.n % 10 = 0 THEN NULL ELSE 'r/' || g.id END,
            'Clipe ' || g.n, now() - make_interval(mins => g.n)
        FROM (SELECT gen_random_uuid() AS id, n FROM generate_series(1, :total) n) g
    """), {"p0": perfis[0], "p1": perfis[1], "total": CONTEUDOS})
    conn.execute(text("""
        INSERT INTO conteudos (id, perfil_id, origem, corte_id, titulo, created_at)
        SELECT id, perfil_id, 'corte', id, left(openshorts_title, 100), created_at FROM cortes
    """))
    # Dois destinos por conteúdo, nas contas do perfil, com estados variados.
    conn.execute(text("""
        INSERT INTO postagens (id, conteudo_id, conta_id, titulo, estado, planned_at,
                               aprovado_em, pedido_em)
        SELECT gen_random_uuid(), c.id, k.conta,
            CASE WHEN r.n % 3 = 0 THEN '' ELSE 'Título ' || r.n END,
            CAST(e.estado AS destino_estado),
            CASE WHEN e.estado IN ('agendado', 'postado')
                 THEN now() + make_interval(hours => CAST((r.n % 400) - 100 AS int)) END,
            CASE WHEN e.estado IN ('aprovado', 'agendado', 'postado') THEN now() END,
            CASE WHEN e.estado = 'aprovacao_pedida' THEN now() END
        FROM (SELECT id, perfil_id, row_number() OVER (ORDER BY id) AS n FROM conteudos) r
        JOIN conteudos c ON c.id = r.id
        CROSS JOIN LATERAL (VALUES (0), (1)) AS i(j)
        JOIN LATERAL (
            SELECT CASE WHEN c.perfil_id = CAST(:p0 AS uuid)
                        THEN (ARRAY[CAST(:k0 AS uuid), CAST(:k1 AS uuid)])[i.j + 1]
                        ELSE (ARRAY[CAST(:k2 AS uuid), CAST(:k3 AS uuid)])[i.j + 1] END AS conta
        ) k ON true
        JOIN LATERAL (
            SELECT (ARRAY['pendente', 'aprovacao_pedida', 'aprovado', 'agendado',
                          'postado'])[((r.n + i.j) % 5) + 1] AS estado
        ) e ON true
    """), {"p0": perfis[0], "k0": contas[0], "k1": contas[1], "k2": contas[2],
           "k3": contas[3]})


@pytest.fixture
def escala(client, dono):  # noqa: F811
    _, h = dono
    perfis = [criar_perfil(client, h, "A Taverna Nerd")["id"],
              criar_perfil(client, h, "Queridinhos")["id"]]
    contas = [criar_conta(client, h, perfis[0], "tiktok")["id"],
              criar_conta(client, h, perfis[0], "youtube")["id"],
              criar_conta(client, h, perfis[1], "tiktok")["id"],
              criar_conta(client, h, perfis[1], "instagram")["id"]]
    with get_engine().begin() as conn:
        _semear(conn, perfis, contas)
        assert conn.execute(text("SELECT count(*) FROM conteudos")).scalar() == CONTEUDOS
        assert conn.execute(text("SELECT count(*) FROM postagens")).scalar() == 2 * CONTEUDOS
        conn.execute(text("ANALYZE conteudos; ANALYZE postagens; ANALYZE cortes"))
    return h, perfis, contas


class _Contador:
    def __init__(self):
        self.n = 0

    def __call__(self, *args, **kwargs):
        self.n += 1


def _consultas(client, h, params) -> int:
    contador = _Contador()
    engine = get_engine()
    event.listen(engine, "before_cursor_execute", contador)
    try:
        r = client.get("/api/conteudos", headers=h, params=params)
        assert r.status_code == 200, r.text
    finally:
        event.remove(engine, "before_cursor_execute", contador)
    return contador.n


def test_lista_filtrada_p95_e_sem_n_mais_1(client, escala):
    h, perfis, contas = escala
    combinacoes = [
        {},
        {"perfilId": perfis[0]},
        {"perfilId": perfis[0], "atalho": "prontos_sem_agendamento"},
        {"perfilId": perfis, "estado": ["agendado", "a_postar", "atrasado"]},
        {"contaId": contas[0], "atalho": "esta_semana"},
        {"plataforma": "tiktok", "estado": ["aprovado"], "q": "clipe 1"},
        {"perfilId": perfis[1], "ordem": "agenda"},
        {"estado": ["sem_conta", "aprovacao_pedida"], "criadoDe": "2026-01-01"},
        {"atalho": "aprovados_sem_data", "contaId": contas[2]},
        {"q": "Título 4", "ordem": "agenda", "limit": 100},
    ]
    client.get("/api/conteudos", headers=h)  # aquece
    tempos = []
    for n in range(30):
        params = combinacoes[n % len(combinacoes)]
        inicio = time.perf_counter()
        r = client.get("/api/conteudos", headers=h, params=params)
        tempos.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200, (params, r.text)
    p95 = statistics.quantiles(tempos, n=20)[-1]
    print(f"\nGET /api/conteudos: p95 = {p95:.1f} ms, mediana = {statistics.median(tempos):.1f} ms")
    assert p95 < P95_MS, f"p95 {p95:.1f} ms"

    # Sem N+1: 10 ou 100 linhas custam o mesmo número de consultas.
    pequena = _consultas(client, h, {"limit": 10})
    grande = _consultas(client, h, {"limit": 100})
    assert pequena == grande, (pequena, grande)
    assert grande <= 10
