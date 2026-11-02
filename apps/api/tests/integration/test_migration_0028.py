"""Migration 0028 (spec 031, T004): sobe sobre dados da 011 (os roteiros, posições, cenas e
tomadas ficam iguais, com as colunas novas nulas); o CHECK do guiado (as 4 juntas ou nenhuma) e
o da grade; o UNIQUE parcial dos quadros; a conversa só de inserção; os passos novos sem mídia;
desce vazia e sobe; com dado do guiado, o downgrade recusa."""

import json
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0027_roteiros_video_local"
TABELAS = ("roteiro_conversa", "roteiro_trechos", "cena_quadros")
SEM_ID = ("roteiro_cenas", "roteiro_trechos")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _colunas(conn, tabela: str) -> set[str]:
    return set(conn.execute(text("SELECT column_name FROM information_schema.columns "
                                 "WHERE table_name = :t"), {"t": tabela}).scalars())


def _insert(conn, tabela: str, casts: dict[str, str] | None = None, **cols) -> uuid.UUID | None:
    casts = casts or {}
    if tabela not in SEM_ID:
        cols = {"id": uuid.uuid4(), **cols}
    valores = ", ".join(f"CAST(:{c} AS {casts[c]})" if c in casts else f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({valores})"), cols)
    return cols.get("id")


def _perfil(conn) -> uuid.UUID:
    return _insert(conn, "perfis", slug=f"p{uuid.uuid4().hex[:8]}", name="P")


def _user(conn) -> uuid.UUID:
    return _insert(conn, "users", email=f"u{uuid.uuid4().hex[:8]}@x.com", name="U",
                   password_hash="x", role="dono", password_changed_at="2026-10-13")


def _imagem(conn, perfil, kind: str = "keyframe") -> uuid.UUID:
    iid = uuid.uuid4()
    return _insert(conn, "images", {"kind": "image_kind"}, id=iid, perfil_id=perfil, kind=kind,
                   object_key=f"perfis/{perfil}/{iid}.png", content_type="image/png", bytes=1,
                   width=736, height=1280, sha256="x")


def _asset(conn, perfil, tipo: str = "cenario") -> uuid.UUID:
    return _insert(conn, "assets", {"tipo": "asset_tipo"}, perfil_id=perfil, tipo=tipo,
                   name=f"a{uuid.uuid4().hex[:6]}")


def _cena(conn, perfil, **extra) -> uuid.UUID:
    return _insert(conn, "cenas", perfil_id=perfil, nome="Cena", acao="ela mostra o vestido",
                   **extra)


def _tomada(conn, cena, kf, **extra) -> uuid.UUID:
    tid = uuid.uuid4()
    g = _geracao(conn, None, passo="cena.clipe", alvo="cena")
    cols = {"id": tid, "cena_id": cena, "video_key": f"cenas/{cena}/tomadas/{tid}.mp4",
            "content_type": "video/mp4", "bytes": 10, "sha256": "x", "original_filename": "t.mp4",
            "duracao_ms": 5000, "largura": 736, "altura": 1280,
            "miniatura_key": f"perfis/x/cenas/{cena}/tomadas/{tid}.jpg", "prompt_usado": "p",
            "negative_usado": "n", "origem": "geracao_local", "geracao_id": g,
            "keyframe_image_id": kf, "motor": "minimax", **extra}
    return _insert(conn, "cena_tomadas", {"origem": "tomada_origem", "motor": "cena_motor"},
                   **cols)


def _geracao(conn, perfil, passo: str = "cenario.cena", motor: str = "comfyui",
             alvo: str = "asset") -> uuid.UUID:
    return _insert(conn, "geracoes", {"motor": "geracao_motor", "status": "geracao_status",
                                      "alvo_tipo": "geracao_alvo", "params": "jsonb"},
                   perfil_id=perfil, alvo_tipo=alvo, alvo_id=uuid.uuid4(), passo=passo,
                   motor=motor, status="na_fila", n_opcoes=1, params="{}")


def _roteiro(conn, perfil, **extra) -> uuid.UUID:
    casts = {"tipo_video": "roteiro_tipo_video", "conversa_estado": "conversa_estado"}
    cols = {"perfil_id": perfil, "nome": "Vestido", **extra}
    return _insert(conn, "roteiros", {k: v for k, v in casts.items() if k in cols}, **cols)


def _guiado(conn, perfil, cenario, **extra) -> uuid.UUID:
    return _roteiro(conn, perfil, tipo_video="avatar_pov", cenario_id=cenario,
                    duracao_alvo_s=20, trecho_base_s=5, **extra)


def _quadro(conn, cena, ordem: int, papel: str, **extra) -> uuid.UUID:
    extra = {"instrucao": "She holds the dress", **extra}
    return _insert(conn, "cena_quadros", {"papel": "quadro_papel"}, cena_id=cena, ordem=ordem,
                   papel=papel, **extra)


def _mensagem(conn, roteiro, seq: int, **extra) -> uuid.UUID:
    cols = {"roteiro_id": roteiro, "seq": seq, "tipo": "pergunta", "pergunta_id": "foco",
            "conteudo": json.dumps({"texto": "Qual o foco?"}), "autor_tipo": "system:roteiro",
            **extra}
    return _insert(conn, "roteiro_conversa", {"tipo": "conversa_tipo", "conteudo": "jsonb",
                                              "alvo": "jsonb"}, **cols)


def _recusa(sql_fn) -> None:
    with pytest.raises(IntegrityError), get_engine().begin() as conn:
        sql_fn(conn)


def test_sobe_sobre_a_011_e_desce_vazia():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            for t in TABELAS:
                assert not _existe(conn, t)
            p = _perfil(conn)
            kf = _imagem(conn, p)
            cena = _cena(conn, p, keyframe_inicial_id=kf)
            tomada = _tomada(conn, cena, kf)
            r = _roteiro(conn, p, frases=["Oi"])
            conn.execute(text("INSERT INTO roteiro_cenas (roteiro_id, ordem, cena_id, frases, "
                              "tomada_id) VALUES (:r, 0, :c, '{0}', :t)"),
                         {"r": r, "c": cena, "t": tomada})
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            for t in TABELAS:
                assert _existe(conn, t)
            # A 011 fica igual: as colunas novas nulas.
            assert conn.execute(text(
                "SELECT tipo_video, cenario_id, duracao_alvo_s, trecho_base_s, conversa_estado, "
                "nome, frases FROM roteiros")).one() == (None, None, None, None, None, "Vestido",
                                                        ["Oi"])
            assert conn.execute(text(
                "SELECT trechos, reuso, motivo, aprovado_keyframes_em, aprovado_clipe_em, "
                "orcamento_chars, tomada_id FROM roteiro_cenas")).one() == (
                None, None, None, None, None, None, tomada)
            assert conn.execute(text("SELECT trechos, origem_cena_id, keyframe_inicial_id "
                                     "FROM cenas")).one() == (None, None, kf)
            assert conn.execute(text("SELECT trecho, keyframe_fim_image_id FROM "
                                     "cena_tomadas")).one() == (None, None)
        # Down vazio (sem nada do guiado) e up de novo; a 011 fica.
        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            for t in TABELAS:
                assert not _existe(conn, t)
            assert "tipo_video" not in _colunas(conn, "roteiros")
            assert "trechos" not in _colunas(conn, "cenas")
            assert "trecho" not in _colunas(conn, "cena_tomadas")
            assert conn.execute(text("SELECT count(*) FROM roteiro_cenas")).scalar() == 1
            # O CHECK das frases da 0027 voltou (a posição sem fala é só do guiado).
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(text("UPDATE roteiro_cenas SET frases = '{}'"))
    finally:
        command.upgrade(_cfg(), "head")


def test_check_do_guiado_e_da_grade():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        cenario = _asset(conn, p)
    # As 4 juntas ou nenhuma.
    _recusa(lambda c: _roteiro(c, p, tipo_video="avatar_pov"))
    _recusa(lambda c: _roteiro(c, p, tipo_video="avatar_pov", cenario_id=cenario,
                               duracao_alvo_s=20))
    _recusa(lambda c: _roteiro(c, p, duracao_alvo_s=20, trecho_base_s=5))
    # A grade: múltiplo da base, de 1× a 12×, base de 3 a 10.
    _recusa(lambda c: _roteiro(c, p, tipo_video="avatar_pov", cenario_id=cenario,
                               duracao_alvo_s=22, trecho_base_s=5))
    _recusa(lambda c: _roteiro(c, p, tipo_video="avatar_pov", cenario_id=cenario,
                               duracao_alvo_s=65, trecho_base_s=5))
    _recusa(lambda c: _roteiro(c, p, tipo_video="avatar_pov", cenario_id=cenario,
                               duracao_alvo_s=2, trecho_base_s=2))
    # A conversa só no guiado.
    _recusa(lambda c: _roteiro(c, p, conversa_estado="perguntando"))
    with get_engine().begin() as conn:
        r = _guiado(conn, p, cenario, conversa_estado="respondida")
        cena = _cena(conn, p, trechos=2)
        _roteiro(conn, p)  # a 011
    # A posição do guiado: trechos 1..3, motivo ≤ 300, aprovação com o autor; pode ficar sem
    # fala. A da 011 continua exigindo frase.
    def _posicao(c, ordem: int, frases: str = "{0}", **extra):
        cols = {"r": r, "o": ordem, "c": cena, "f": frases, **extra}
        nomes = ", ".join(["roteiro_id", "ordem", "cena_id", "frases", *extra])
        valores = ", ".join([":r", ":o", ":c", "CAST(:f AS smallint[])",
                             *(f":{k}" for k in extra)])
        c.execute(text(f"INSERT INTO roteiro_cenas ({nomes}) VALUES ({valores})"), cols)

    _recusa(lambda c: _posicao(c, 0, trechos=4))
    _recusa(lambda c: _posicao(c, 0, trechos=1, motivo="x" * 301))
    _recusa(lambda c: _posicao(c, 0, trechos=1, aprovado_keyframes_em="2026-10-13"))
    _recusa(lambda c: _posicao(c, 0, frases="{}"))  # sem trechos (011): precisa de frase
    with get_engine().begin() as conn:
        _posicao(conn, 0, frases="{}", trechos=1, motivo="Mostra o caimento")
        _posicao(conn, 1, trechos=3)
        u = _user(conn)
        conn.execute(text("UPDATE roteiro_cenas SET aprovado_keyframes_em = now(), "
                          "aprovado_keyframes_por = :u WHERE ordem = 1"), {"u": u})
    # Trechos: 0..2, só de uma posição que existe.
    _recusa(lambda c: _insert(c, "roteiro_trechos", roteiro_id=r, ordem=0, trecho=3))
    _recusa(lambda c: _insert(c, "roteiro_trechos", roteiro_id=r, ordem=7, trecho=0))
    with get_engine().begin() as conn:
        for t in range(3):
            _insert(conn, "roteiro_trechos", roteiro_id=r, ordem=1, trecho=t)


def test_quadros_unicos_entre_os_ativos_e_tomada_de_trecho():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        cena = _cena(conn, p, trechos=1)
        img = _imagem(conn, p)
        q0 = _quadro(conn, cena, 0, "inicio")
        _quadro(conn, cena, 1, "fim")
    _recusa(lambda c: _quadro(c, cena, 1, "fim"))  # a mesma ordem ativa
    _recusa(lambda c: _quadro(c, cena, 4, "fim"))  # ordem fora
    _recusa(lambda c: _quadro(c, cena, 2, "inicio"))  # papel × ordem
    _recusa(lambda c: _quadro(c, cena, 0, "fim"))
    _recusa(lambda c: _quadro(c, cena, 2, "meio1", provisorio=True))  # provisório sem imagem
    _recusa(lambda c: _quadro(c, cena, 2, "meio1", instrucao="x" * 2001))
    _recusa(lambda c: _cena(c, p, trechos=0))
    with get_engine().begin() as conn:
        # Arquivado libera a ordem (refazer = arquivar e recriar).
        conn.execute(text("UPDATE cena_quadros SET archived_at = now() WHERE id = :q"),
                     {"q": q0})
        _quadro(conn, cena, 0, "inicio", image_id=img, provisorio=True)
        derivada = _cena(conn, p, trechos=1, origem_cena_id=cena)
    _recusa(lambda c: c.execute(text("UPDATE cenas SET origem_cena_id = id WHERE id = :c"),
                                {"c": derivada}))
    # A tomada de um trecho é local, com o quadro final, no trecho 0..2.
    _recusa(lambda c: _tomada(c, cena, img, trecho=0))
    _recusa(lambda c: _tomada(c, cena, img, trecho=3, keyframe_fim_image_id=img))
    with get_engine().begin() as conn:
        _tomada(conn, cena, img, trecho=0, keyframe_fim_image_id=img)


def test_conversa_so_insercao_e_seq_unica():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        r = _guiado(conn, p, _asset(conn, p), conversa_estado="perguntando")
        m = _mensagem(conn, r, 1)
        u = _user(conn)
        _mensagem(conn, r, 2, tipo="resposta", conteudo=json.dumps({"opcoes": ["caimento"]}),
                  autor_tipo="user", autor_id=u)
    _recusa(lambda c: _mensagem(c, r, 2))  # seq repetida
    _recusa(lambda c: _mensagem(c, r, 3, autor_tipo="user"))  # humano sem id
    _recusa(lambda c: _mensagem(c, r, 3, autor_tipo="mcp_client"))
    _recusa(lambda c: _mensagem(c, r, 3, conteudo=json.dumps(["x"])))
    _recusa(lambda c: _mensagem(c, r, 3, alvo=json.dumps([1])))
    for sql in ("UPDATE roteiro_conversa SET seq = 9 WHERE id = :m",
                "DELETE FROM roteiro_conversa WHERE id = :m"):
        with pytest.raises(DBAPIError), get_engine().begin() as conn:
            conn.execute(text(sql), {"m": m})


def test_passos_novos_sem_midia():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        perguntas = _geracao(conn, p, passo="roteiro.perguntas", motor="claude", alvo="roteiro")
        ajuste = _geracao(conn, p, passo="roteiro.ajuste", motor="claude", alvo="roteiro")
        img = _imagem(conn, p)
    _recusa(lambda c: _geracao(c, p, passo="roteiro.outro", motor="claude", alvo="roteiro"))
    _recusa(lambda c: _insert(c, "geracao_candidatos", geracao_id=perguntas, numero=1,
                              image_id=img))
    with get_engine().begin() as conn:
        _insert(conn, "geracao_candidatos", geracao_id=perguntas, numero=1)
        _insert(conn, "geracao_candidatos", geracao_id=ajuste, numero=1)


def test_downgrade_recusa_com_dados_do_guiado():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        _quadro(conn, _cena(conn, p, trechos=1), 0, "inicio")
    with pytest.raises(RuntimeError, match="0028 recusado"):
        command.downgrade(_cfg(), ANTERIOR)
    with get_engine().begin() as conn:
        assert _existe(conn, "cena_quadros")
