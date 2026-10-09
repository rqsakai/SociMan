"""Migration 0022 (spec 012, T004): sobe sobre a 0021 com cenas existentes (que ficam com as
colunas novas NULL); cada CHECK recusa por INSERT direto; desce vazia e sobe; com produto, o
downgrade recusa."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0021_geracao_interrupcoes"


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _perfil(conn) -> uuid.UUID:
    return conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:i, :s, 'P') "
                             "RETURNING id"),
                        {"i": uuid.uuid4(), "s": f"p{uuid.uuid4().hex[:8]}"}).scalar()


def _imagem(conn, perfil: uuid.UUID, kind: str = "produto") -> uuid.UUID:
    iid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO images (id, perfil_id, kind, object_key, content_type, bytes, width, height, "
        "sha256) VALUES (:i, :p, CAST(:kind AS image_kind), :k, 'image/png', 1, 600, 600, 'x')"),
        {"i": iid, "p": perfil, "k": f"perfis/{perfil}/{iid}.png", "kind": kind})
    return iid


def _cena(conn, perfil: uuid.UUID, **extra) -> uuid.UUID:
    cid = uuid.uuid4()
    cols = {"id": cid, "perfil_id": perfil, "nome": "Cena", "acao": "acts", "duracao_s": 8,
            **extra}
    conn.execute(text(f"INSERT INTO cenas ({', '.join(cols)}) "
                      f"VALUES ({', '.join(':' + c for c in cols)})"), cols)
    return cid


def _produto(conn, perfil: uuid.UUID, **extra) -> uuid.UUID:
    pid = uuid.uuid4()
    cols = {"id": pid, "perfil_id": perfil, "name": "Shorts", **extra}
    valores = ", ".join(f"CAST(:{c} AS produto_status)" if c == "status" else f":{c}"
                        for c in cols)
    conn.execute(text(f"INSERT INTO produtos ({', '.join(cols)}) VALUES ({valores})"), cols)
    return pid


def _variante(conn, produto: uuid.UUID, original: uuid.UUID, **extra) -> uuid.UUID:
    vid = uuid.uuid4()
    cols = {"id": vid, "produto_id": produto, "position": 0, "original_image_id": original,
            **extra}
    conn.execute(text(f"INSERT INTO produto_variantes ({', '.join(cols)}) "
                      f"VALUES ({', '.join(':' + c for c in cols)})"), cols)
    return vid


def _geracao(conn, perfil: uuid.UUID, alvo: uuid.UUID) -> uuid.UUID:
    gid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO geracoes (id, perfil_id, alvo_tipo, alvo_id, passo, motor, status, params, "
        "n_opcoes) VALUES (:i, :p, 'produto', :a, 'produto.flat', 'comfyui', 'na_fila', "
        "'{}'::jsonb, 2)"), {"i": gid, "p": perfil, "a": alvo})
    return gid


def _recusa(sql_fn) -> None:
    with pytest.raises(IntegrityError), get_engine().begin() as conn:
        sql_fn(conn)


def test_sobe_com_cenas_existentes_e_desce_vazia():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "produtos")
            _cena(conn, _perfil(conn), produto_nome="Garrafa")
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            assert _existe(conn, "produtos") and _existe(conn, "produto_variantes")
            linha = conn.execute(text(
                "SELECT produto_id, produto_variante_id, produto_nome FROM cenas")).one()
            assert linha == (None, None, "Garrafa")
            valores = conn.execute(text(
                "SELECT unnest(enum_range(NULL::image_kind))::text")).scalars().all()
            assert "produto" in valores
            alvos = conn.execute(text(
                "SELECT unnest(enum_range(NULL::anotacao_alvo))::text")).scalars().all()
            assert "produto" in alvos
        # Desce vazia (só a cena da 010) e sobe de novo.
        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not _existe(conn, "produtos")
            assert conn.execute(text("SELECT count(*) FROM cenas")).scalar() == 1
    finally:
        command.upgrade(_cfg(), "head")


def test_checks_recusam():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        prod = _produto(conn, p)
        img, img2, img3 = _imagem(conn, p), _imagem(conn, p), _imagem(conn, p)
        var = _variante(conn, prod, img)
        g = _geracao(conn, p, prod)
        asset = conn.execute(text(
            "INSERT INTO assets (id, perfil_id, tipo, name) VALUES (:i, :p, 'imagem', 'Foto') "
            "RETURNING id"), {"i": uuid.uuid4(), "p": p}).scalar()
    # ck_variantes_flat: o flat e a geração andam juntos.
    _recusa(lambda c: _variante(c, prod, img2, flat_image_id=img3))
    _recusa(lambda c: _variante(c, prod, img2, flat_geracao_id=g))
    # A foto original é de uma variante só.
    _recusa(lambda c: _variante(c, prod, img))
    # ck_produtos_aprovado: aprovado exige a ficha.
    _recusa(lambda c: _produto(c, p, status="aprovado"))
    # ck_produtos_ficha: ficha preenchida exige `precisa_flat`.
    _recusa(lambda c: c.execute(text(
        "UPDATE produtos SET ficha_por = 'ia' WHERE id = :i"), {"i": prod}))
    # ck_cenas_produto_variante e ck_cenas_produto_modo.
    _recusa(lambda c: _cena(c, p, produto_variante_id=var))
    _recusa(lambda c: _cena(c, p, produto_id=prod, produto_nome="Garrafa"))
    _recusa(lambda c: _cena(c, p, produto_id=prod, produto_nome="Garrafa",
                            produto_imagem_id=asset))
    with get_engine().begin() as conn:  # os válidos passam
        _variante(conn, prod, img2, position=1, flat_image_id=img3, flat_geracao_id=g)
        _cena(conn, p, produto_id=prod, produto_variante_id=var)
        _cena(conn, p, produto_id=prod)


def test_downgrade_recusa_com_dados():
    with get_engine().begin() as conn:
        _produto(conn, _perfil(conn))
    with pytest.raises(RuntimeError, match="recusado"):
        command.downgrade(_cfg(), ANTERIOR)
    with get_engine().begin() as conn:
        assert _existe(conn, "produtos")
