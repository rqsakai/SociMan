"""Migration 0020 (spec 021, T005): sobe sobre a 0019 com `ia_chamadas` existentes (que ficam
com `geracao_id` NULL); cada CHECK e o trigger recusam por INSERT direto; dois `rodando` de GPU
violam o índice único; desce vazia e sobe; com dados, o downgrade recusa."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0019_aprendizado_fonte_temas"  # a 0021 (aditiva) desce junto


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


def _imagem(conn, perfil: uuid.UUID) -> uuid.UUID:
    iid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO images (id, perfil_id, kind, object_key, content_type, bytes, width, height, "
        "sha256) VALUES (:i, :p, 'fundo', :k, 'image/png', 1, 768, 1344, 'x')"),
        {"i": iid, "p": perfil, "k": f"perfis/{perfil}/{iid}.png"})
    return iid


def _audio(conn, perfil: uuid.UUID) -> uuid.UUID:
    aid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO audios (id, perfil_id, object_key, formato, sample_rate, duracao_ms, sha256, "
        "bytes) VALUES (:i, :p, :k, 'wav', 24000, 1000, :h, 10)"),
        {"i": aid, "p": perfil, "k": f"perfis/{perfil}/audios/{aid}.wav", "h": "a" * 64})
    return aid


def _geracao(conn, perfil: uuid.UUID, passo: str = "cenario.cena", motor: str = "comfyui",
             status: str = "na_fila", **extra) -> uuid.UUID:
    gid = uuid.uuid4()
    cols = {"id": gid, "perfil_id": perfil, "alvo_id": uuid.uuid4(), "passo": passo,
            "motor": motor, "status": status, "n_opcoes": 2, **extra}
    nomes = ", ".join(cols)
    valores = ", ".join(
        f"CAST(:{c} AS geracao_motor)" if c == "motor" else
        f"CAST(:{c} AS geracao_status)" if c == "status" else f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO geracoes (alvo_tipo, params, {nomes}) "
                      f"VALUES ('asset', '{{}}'::jsonb, {valores})"), cols)
    return gid


def _candidato(conn, gid: uuid.UUID, numero: int = 1, **midia) -> None:
    cols = {"id": uuid.uuid4(), "geracao_id": gid, "numero": numero, **midia}
    conn.execute(text(f"INSERT INTO geracao_candidatos ({', '.join(cols)}) "
                      f"VALUES ({', '.join(':' + c for c in cols)})"), cols)


def _recusa(sql_fn) -> None:
    with pytest.raises(IntegrityError), get_engine().begin() as conn:
        sql_fn(conn)


def test_sobe_com_chamadas_existentes_e_desce_vazia():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "geracoes")
            p = _perfil(conn)
            conn.execute(text(
                "INSERT INTO ia_chamadas (id, tipo_campo, perfil_id, entity_type, model, "
                "prompt_version, duration_ms) VALUES (:i, 'asset.descricao', :p, 'asset', 'm', "
                "'ia/1', 1)"), {"i": uuid.uuid4(), "p": p})
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            for t in ("geracoes", "geracao_candidatos", "audios"):
                assert _existe(conn, t)
            assert conn.execute(text(
                "SELECT count(*) FROM ia_chamadas WHERE geracao_id IS NULL")).scalar() == 1
        # Down vazio (só a chamada da 008, sem geração) e up de novo.
        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not _existe(conn, "geracoes")
            assert conn.execute(text("SELECT count(*) FROM ia_chamadas")).scalar() == 1
    finally:
        command.upgrade(_cfg(), "head")


def test_checks_e_trigger_recusam():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        img, img2, aud = _imagem(conn, p), _imagem(conn, p), _audio(conn, p)
        cena = _geracao(conn, p)
        par = _geracao(conn, p, passo="avatar.rostos_34")
        ficha = _geracao(conn, p, passo="produto.ficha", motor="claude")
    # Passo fora da lista, n fora de 1..4, escolhido sem candidato, erro com status errado.
    _recusa(lambda c: _geracao(c, p, passo="avatar.outro"))
    _recusa(lambda c: _geracao(c, p, n_opcoes=5))
    _recusa(lambda c: _geracao(c, p, status="escolhido", finished_at="2026-01-01"))
    _recusa(lambda c: _geracao(c, p, status="revisao", error_code="internal"))
    _recusa(lambda c: _geracao(c, p, status="falhou", error_code="outro", finished_at="2026-01-01"))
    _recusa(lambda c: _geracao(c, p, status="cancelada"))  # final sem finished_at
    _recusa(lambda c: _geracao(c, p, status="entregue", finished_at="2026-01-01"))  # só voz.teste
    _recusa(lambda c: _geracao(c, p, progress=101))
    # Trigger e CHECKs do candidato.
    _recusa(lambda c: _candidato(c, cena, image_id=img, image_par_id=img2))  # par fora do 34
    _recusa(lambda c: _candidato(c, cena))  # sem mídia num passo de imagem
    _recusa(lambda c: _candidato(c, cena, image_id=img, audio_id=aud))
    _recusa(lambda c: _candidato(c, par, image_id=img))  # o 34 exige o par
    _recusa(lambda c: _candidato(c, ficha, image_id=img))  # mídia num passo de texto
    _recusa(lambda c: _candidato(c, cena, image_par_id=img2))
    with get_engine().begin() as conn:  # os válidos passam
        _candidato(conn, cena, image_id=img)
        _candidato(conn, par, image_id=img, image_par_id=img2)
        _candidato(conn, ficha)
        teste = _geracao(conn, p, passo="voz.teste", motor="tts", status="entregue",
                         finished_at="2026-01-01")
        _candidato(conn, teste, audio_id=aud)
    _recusa(lambda c: _candidato(c, cena, image_id=img2))  # número repetido


def test_um_job_de_gpu_rodando():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        _geracao(conn, p, status="rodando")
        _geracao(conn, p, motor="claude", passo="produto.ficha", status="rodando")
    _recusa(lambda c: _geracao(c, p, motor="tts", passo="voz.design", status="rodando"))


def test_downgrade_recusa_com_dados():
    with get_engine().begin() as conn:
        _geracao(conn, _perfil(conn))
    with pytest.raises(RuntimeError, match="recusado"):
        command.downgrade(_cfg(), ANTERIOR)
    with get_engine().begin() as conn:
        assert _existe(conn, "geracoes")
