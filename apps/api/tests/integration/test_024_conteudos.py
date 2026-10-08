"""Paginação numerada da central (spec 024, US6, FR-020/021, T043): `offset` em
`GET /api/conteudos` cobre o mesmo conjunto que o cursor, sem repetir nem pular, nas duas ordens;
`offset` + `cursor` → 400 `paginacao_invalida`; `offset` além do total → página vazia."""

import pytest
from sqlalchemy import text

from integration.postagem_helpers import criar_conta, criar_perfil, dono  # noqa: F401
from sociman_api.db import get_engine

CONTEUDOS = 60


@pytest.fixture
def central(client, dono):  # noqa: F811
    """60 conteúdos; metade com agendamento (em pares no mesmo horário, para o desempate por id)
    e vários com o mesmo `created_at`."""
    _, h = dono
    perfil = criar_perfil(client, h)["id"]
    conta = criar_conta(client, h, perfil, "tiktok")["id"]
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO cortes (id, perfil_id, hook_text, status, kit_version, kit_tokens,
                original_filename, original_key, original_content_type, original_bytes,
                duration_ms, width, height, fps, video_codec, original_sha256, result_key,
                openshorts_title, created_at)
            SELECT g.id, CAST(:p AS uuid), 'Gancho ' || g.n, CAST('pronto' AS corte_status), 1,
                CAST('{}' AS jsonb), 'c.mp4', 'k/' || g.id, 'video/mp4', 1, 30000, 1080, 1920,
                30, 'h264', 'x', 'r/' || g.id, 'Clipe ' || g.n,
                now() - make_interval(mins => g.n / 3)
            FROM (SELECT gen_random_uuid() AS id, n FROM generate_series(1, :total) n) g
        """), {"p": perfil, "total": CONTEUDOS})
        conn.execute(text("""
            INSERT INTO conteudos (id, perfil_id, origem, corte_id, titulo, created_at)
            SELECT id, perfil_id, 'corte', id, left(openshorts_title, 100), created_at
            FROM cortes
        """))
        conn.execute(text("""
            INSERT INTO postagens (id, conteudo_id, conta_id, titulo, estado, planned_at,
                                   aprovado_em)
            SELECT gen_random_uuid(), r.id, CAST(:k AS uuid), 'Título ' || r.n,
                CAST('agendado' AS destino_estado),
                now() + make_interval(hours => CAST(r.n / 2 AS int) + 1), now()
            FROM (SELECT id, row_number() OVER (ORDER BY id) AS n FROM conteudos) r
            WHERE r.n % 2 = 0
        """), {"k": conta})
        assert conn.execute(text("SELECT count(*) FROM conteudos")).scalar() == CONTEUDOS
    return h, perfil


def _pagina(client, h, perfil, ordem, **params) -> dict:
    r = client.get("/api/conteudos", headers=h,
                   params={"perfilId": perfil, "ordem": ordem, "limit": 25, **params})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("ordem", ["recentes", "agenda"])
def test_offset_cobre_tudo_sem_repetir(client, central, ordem):
    h, perfil = central
    vistos = []
    for offset in (0, 25, 50):
        body = _pagina(client, h, perfil, ordem, offset=offset)
        assert body["total"] == CONTEUDOS
        vistos += [i["id"] for i in body["items"]]
    assert len(vistos) == len(set(vistos)) == CONTEUDOS

    # Mesma sequência que o cursor.
    pelo_cursor, cursor = [], None
    while True:
        body = _pagina(client, h, perfil, ordem, **({"cursor": cursor} if cursor else {}))
        pelo_cursor += [i["id"] for i in body["items"]]
        cursor = body["nextCursor"]
        if not cursor:
            break
    assert vistos == pelo_cursor


def test_offset_com_cursor_e_400(client, central):
    h, perfil = central
    cursor = _pagina(client, h, perfil, "recentes")["nextCursor"]
    assert cursor
    r = client.get("/api/conteudos", headers=h,
                   params={"perfilId": perfil, "cursor": cursor, "offset": 25})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "paginacao_invalida"


def test_offset_alem_do_total(client, central):
    h, perfil = central
    body = _pagina(client, h, perfil, "recentes", offset=75)
    assert body["items"] == [] and body["total"] == CONTEUDOS and body["nextCursor"] is None


def test_offset_negativo_e_400(client, central):
    h, perfil = central
    r = client.get("/api/conteudos", headers=h, params={"perfilId": perfil, "offset": -1})
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"
