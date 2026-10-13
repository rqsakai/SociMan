"""Migration 0027 (spec 011, T005): sobe sobre dados da 010, 012, 021 e 025 (as colunas novas ficam
nulas ou com o padrão); cada CHECK e trigger novo recusa por INSERT direto (e UPDATE/DELETE nas
entregas); o `ffmpeg` roda ao lado de um job de GPU; desce vazia e sobe; com dado novo, o
downgrade recusa."""

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
ANTERIOR = "0026_uniao_mercado"
TABELAS = ("roteiros", "roteiro_produtos", "roteiro_cenas", "roteiro_narracoes",
           "roteiro_entregas", "roteiro_padroes", "pronuncias")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


SEM_ID = ("roteiro_produtos", "roteiro_cenas")


def _insert(conn, tabela: str, casts: dict[str, str] | None = None, **cols) -> uuid.UUID | None:
    casts = casts or {}
    if tabela not in SEM_ID:
        cols = {"id": uuid.uuid4(), **cols}
    valores = ", ".join(f"CAST(:{c} AS {casts[c]})" if c in casts else f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({valores})"), cols)
    return cols.get("id")


def _perfil(conn) -> uuid.UUID:
    return _insert(conn, "perfis", slug=f"p{uuid.uuid4().hex[:8]}", name="P")


def _imagem(conn, perfil, kind: str = "fundo") -> uuid.UUID:
    iid = uuid.uuid4()
    return _insert(conn, "images", {"kind": "image_kind"}, id=iid, perfil_id=perfil, kind=kind,
                   object_key=f"perfis/{perfil}/{iid}.png", content_type="image/png", bytes=1,
                   width=736, height=1280, sha256="x")


def _audio(conn, perfil) -> uuid.UUID:
    aid = uuid.uuid4()
    return _insert(conn, "audios", id=aid, perfil_id=perfil,
                   object_key=f"perfis/{perfil}/audios/{aid}.wav", formato="wav",
                   sample_rate=24000, duracao_ms=1000, sha256="a" * 64, bytes=10)


def _cena(conn, perfil, **extra) -> uuid.UUID:
    return _insert(conn, "cenas", {"motor": "cena_motor"} if "motor" in extra else None,
                   perfil_id=perfil, nome="Cena", acao="ela mostra o vestido", **extra)


def _tomada(conn, cena, **extra) -> uuid.UUID:
    tid = uuid.uuid4()
    cols = {"id": tid, "cena_id": cena, "video_key": f"cenas/{cena}/tomadas/{tid}.mp4",
            "content_type": "video/mp4", "bytes": 10, "sha256": "x", "original_filename": "t.mp4",
            "duracao_ms": 3000, "largura": 736, "altura": 1280,
            "miniatura_key": f"perfis/x/cenas/{cena}/tomadas/{tid}.jpg", "prompt_usado": "p",
            "negative_usado": "n", **extra}
    casts = {"origem": "tomada_origem", "motor": "cena_motor"}
    return _insert(conn, "cena_tomadas", {k: v for k, v in casts.items() if k in cols}, **cols)


def _geracao(conn, perfil, passo: str = "cenario.cena", motor: str = "comfyui",
             alvo: str = "asset", status: str = "na_fila", **extra) -> uuid.UUID:
    return _insert(conn, "geracoes", {"motor": "geracao_motor", "status": "geracao_status",
                                      "alvo_tipo": "geracao_alvo", "params": "jsonb"},
                   perfil_id=perfil, alvo_tipo=alvo, alvo_id=uuid.uuid4(), passo=passo,
                   motor=motor, status=status, n_opcoes=1, params="{}", **extra)


def _candidato(conn, gid, numero: int = 1, **midia) -> uuid.UUID:
    return _insert(conn, "geracao_candidatos", geracao_id=gid, numero=numero, **midia)


def _video(gid=None) -> dict:
    n = uuid.uuid4().hex[:8]
    return {"video_key": f"geracoes/{gid or n}/{n}.mp4",
            "video_miniatura_key": f"agencia/geracoes/{n}.jpg"}


def _voz(conn, perfil) -> uuid.UUID:
    return _insert(conn, "vozes", {"origem": "voz_origem"}, perfil_id=perfil,
                   name=f"v{uuid.uuid4().hex[:6]}", origem="gravacao", tom="vendas")


def _conteudo(conn, perfil, **extra) -> uuid.UUID:
    cid = uuid.uuid4()
    return _insert(conn, "conteudos", {"origem": "conteudo_origem"}, id=cid, perfil_id=perfil,
                   origem="video_proprio", video_key=f"conteudos/{cid}/video.mp4",
                   poster_key=f"perfis/{perfil}/conteudos/{cid}.jpg", duration_ms=17000,
                   **extra)


def _roteiro(conn, perfil, **extra) -> uuid.UUID:
    casts = {"status": "roteiro_status", "etapa_falhou": "roteiro_etapa"}
    cols = {"perfil_id": perfil, "nome": "Vestido", **extra}
    return _insert(conn, "roteiros", {k: v for k, v in casts.items() if k in cols}, **cols)


def _recusa(sql_fn) -> None:
    with pytest.raises(IntegrityError), get_engine().begin() as conn:
        sql_fn(conn)


def test_sobe_sobre_dados_das_anteriores_e_desce_vazia():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            for t in TABELAS:
                assert not _existe(conn, t)
            p = _perfil(conn)
            cena = _cena(conn, p)
            _tomada(conn, cena)
            g = _geracao(conn, p)
            _candidato(conn, g, image_id=_imagem(conn, p))
            _conteudo(conn, p)
            _voz(conn, p)
            _insert(conn, "produtos", perfil_id=p, name="Vestido")
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            for t in TABELAS:
                assert _existe(conn, t)
            assert conn.execute(text(
                "SELECT motor::text, largura, altura, keyframe_inicial_id, keyframe_final_id, "
                "keyframe_instrucao, keyframe_refs, keyframe_geracao_id, duracao_max_s "
                "FROM cenas")).one() == ("minimax", 736, 1280, None, None, None, [], None, None)
            assert conn.execute(text(
                "SELECT origem::text, geracao_id, keyframe_image_id, motor, fps, desuso_em, "
                "limpa_em FROM cena_tomadas")).one() == ("flow_manual", None, None, None, None,
                                                         None, None)
            assert conn.execute(text("SELECT desuso_em FROM geracoes")).scalar() is None
            assert conn.execute(text(
                "SELECT video_key, video_miniatura_key, video_bytes FROM geracao_candidatos"
            )).one() == (None, None, None)
            assert conn.execute(text("SELECT gerado_ia FROM conteudos")).scalar() is False
            # Os padrões do roteiro novo.
            r = _roteiro(conn, p)
            linha = conn.execute(text(
                "SELECT status::text, modo::text, formato::text, velocidade, frases, portoes, "
                "avisos FROM roteiros WHERE id = :r"), {"r": r}).one()
            assert linha[:3] == ("rascunho", "revisar", "voice_over")
            assert float(linha[3]) == 1.08 and linha[4] == []
            assert linha[5] == {"texto": True, "narracao": True, "keyframes": True,
                                "clipes": True, "final": True}
            assert linha[6] == []
            conn.execute(text("DELETE FROM roteiros WHERE id = :r"), {"r": r})
        # Down vazio (sem nada da 011) e up de novo; os dados das anteriores ficam.
        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            for t in TABELAS:
                assert not _existe(conn, t)
            assert conn.execute(text("SELECT count(*) FROM cena_tomadas")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM geracao_candidatos")).scalar() == 1
            colunas = set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'cenas'"
            )).scalars())
            assert "motor" not in colunas and "keyframe_inicial_id" not in colunas
    finally:
        command.upgrade(_cfg(), "head")


def test_checks_do_roteiro_e_da_tomada_recusam():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        cena = _cena(conn, p)
        kf = _imagem(conn, p, "keyframe")
        clipe = _geracao(conn, p, passo="cena.clipe", alvo="cena")
    # Roteiro: falhou sem etapa, etapa sem falhou, pronto sem conteúdo, velocidade, erro fora.
    _recusa(lambda c: _roteiro(c, p, status="falhou"))
    _recusa(lambda c: _roteiro(c, p, etapa_falhou="plano"))
    _recusa(lambda c: _roteiro(c, p, status="pronto"))
    _recusa(lambda c: _roteiro(c, p, velocidade=1.5))
    _recusa(lambda c: _roteiro(c, p, erro_code="internal"))
    _recusa(lambda c: _roteiro(c, p, nome=" com espaço "))
    # Tomada local sem geração/keyframe/motor; do Flow com geração; sem mídia sem limpeza; do
    # Flow limpa.
    _recusa(lambda c: _tomada(c, cena, origem="geracao_local"))
    _recusa(lambda c: _tomada(c, cena, origem="geracao_local", geracao_id=clipe,
                              keyframe_image_id=kf))
    _recusa(lambda c: _tomada(c, cena, geracao_id=clipe, keyframe_image_id=kf, motor="wan"))
    _recusa(lambda c: _tomada(c, cena, origem="geracao_local", geracao_id=clipe,
                              keyframe_image_id=kf, motor="wan", video_key=None))
    _recusa(lambda c: _tomada(c, cena, video_key=None, miniatura_key=None, bytes=None,
                              limpa_em="2026-01-01"))
    _recusa(lambda c: _tomada(c, cena, origem="geracao_local", geracao_id=clipe,
                              keyframe_image_id=kf, motor="wan", fps=30))
    # Cena: resolução fora do múltiplo de 16, keyframe final sem inicial, 7 referências.
    _recusa(lambda c: _cena(c, p, largura=730))
    _recusa(lambda c: _cena(c, p, keyframe_final_id=kf))
    _recusa(lambda c: _cena(c, p, keyframe_refs=[uuid.uuid4() for _ in range(7)]))
    _recusa(lambda c: _cena(c, p, duracao_max_s=0.5))
    with get_engine().begin() as conn:  # os válidos passam
        _roteiro(conn, p, status="falhou", etapa_falhou="narracao", erro_code="internal",
                 erro_message="x")
        _tomada(conn, cena, origem="geracao_local", geracao_id=clipe, keyframe_image_id=kf,
                motor="minimax", fps=24)
        _tomada(conn, cena, origem="geracao_local", geracao_id=clipe, keyframe_image_id=kf,
                motor="wan", fps=16, video_key=None, miniatura_key=None, bytes=None,
                limpa_em="2026-01-01")
        _cena(conn, p, motor="ltx", largura=720, altura=1248, keyframe_inicial_id=kf,
              keyframe_final_id=kf, keyframe_refs=[uuid.uuid4()], duracao_max_s=4.5)


def test_midia_dos_candidatos_recusa():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        img, aud = _imagem(conn, p), _imagem(conn, p)
        audio = _audio(conn, p)
        clipe = _geracao(conn, p, passo="cena.clipe", alvo="cena")
        narracao = _geracao(conn, p, passo="roteiro.narracao", motor="tts", alvo="roteiro")
        keyframe = _geracao(conn, p, passo="cena.keyframe", alvo="cena")
        plano = _geracao(conn, p, passo="roteiro.plano", motor="claude", alvo="roteiro")
        montagem = _geracao(conn, p, passo="roteiro.montagem", motor="ffmpeg", alvo="roteiro")
        cena = _geracao(conn, p)
    _recusa(lambda c: _candidato(c, clipe, image_id=img))  # o clipe é vídeo
    _recusa(lambda c: _candidato(c, clipe, image_id=img, **_video()))  # CHECK de mídia
    _recusa(lambda c: _candidato(c, clipe, video_key="x.mp4"))  # vídeo sem miniatura
    _recusa(lambda c: _candidato(c, narracao, image_id=img))  # a narração é áudio
    _recusa(lambda c: _candidato(c, narracao, **_video()))
    _recusa(lambda c: _candidato(c, keyframe, audio_id=audio))  # o keyframe é imagem
    _recusa(lambda c: _candidato(c, plano, **_video()))  # o plano não tem mídia
    _recusa(lambda c: _candidato(c, cena, **_video()))  # passo de imagem da 021
    _recusa(lambda c: _candidato(c, montagem))
    with get_engine().begin() as conn:
        v = _video(clipe)
        _candidato(conn, clipe, **v, video_duracao_ms=3000, video_largura=736,
                   video_altura=1280, video_fps=24, video_bytes=99)
        _candidato(conn, narracao, audio_id=audio)
        _candidato(conn, keyframe, image_id=aud)
        _candidato(conn, plano)
        _candidato(conn, montagem, **_video(montagem))
        _candidato(conn, cena, image_id=img)
    _recusa(lambda c: _candidato(c, montagem, 2, video_key=v["video_key"],
                                 video_miniatura_key="y.jpg"))  # vídeo repetido


def test_entregas_so_insercao():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        r = _roteiro(conn, p)
        narr_g = _geracao(conn, p, passo="roteiro.narracao", motor="tts", alvo="roteiro")
        montagem = _geracao(conn, p, passo="roteiro.montagem", motor="ffmpeg", alvo="roteiro")
        acabamento = _geracao(conn, p, passo="roteiro.acabamento", alvo="roteiro")
        narr = _insert(conn, "roteiro_narracoes", {"tempos": "jsonb"}, roteiro_id=r,
                       geracao_id=narr_g, audio_id=_audio(conn, p), voz_id=_voz(conn, p),
                       texto_hash="a" * 64, frases=["Oi"], tempos="[]", total_s=1.5,
                       similaridade=0.97, seed=7, velocidade=1.08)
        ent = _insert(conn, "roteiro_entregas", {"posicoes": "jsonb"}, roteiro_id=r,
                      conteudo_id=_conteudo(conn, p, gerado_ia=True), narracao_id=narr,
                      montagem_geracao_id=montagem, acabamento_geracao_id=acabamento,
                      posicoes=json.dumps([]), motores=["minimax"])
    for sql in ("UPDATE roteiro_entregas SET motores = '{}' WHERE id = :e",
                "DELETE FROM roteiro_entregas WHERE id = :e"):
        with pytest.raises(DBAPIError), get_engine().begin() as conn:
            conn.execute(text(sql), {"e": ent})
    # A narração sem áudio só depois da limpeza.
    _recusa(lambda c: c.execute(text(
        "UPDATE roteiro_narracoes SET audio_id = NULL WHERE id = :n"), {"n": narr}))
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE roteiro_narracoes SET audio_id = NULL, limpa_em = now() "
                          "WHERE id = :n"), {"n": narr})


def test_pronuncias_unicas_e_posicoes():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        _insert(conn, "pronuncias", perfil_id=p, escrita="levinho", falada="lévinho")
        r = _roteiro(conn, p)
        cena = _cena(conn, p)
        produto = _insert(conn, "produtos", perfil_id=p, name="Vestido")
        _insert(conn, "roteiro_produtos", roteiro_id=r, ordem=0, produto_id=produto)
    _recusa(lambda c: _insert(c, "pronuncias", perfil_id=p, escrita="Levinho", falada="x"))
    _recusa(lambda c: _insert(c, "pronuncias", perfil_id=p, escrita="duas\nlinhas", falada="x"))
    _recusa(lambda c: _insert(c, "roteiro_produtos", roteiro_id=r, ordem=1, produto_id=produto))
    _recusa(lambda c: _insert(c, "roteiro_cenas", roteiro_id=r, ordem=0, cena_id=cena,
                              frases=[]))
    _recusa(lambda c: _insert(c, "roteiro_cenas", roteiro_id=r, ordem=0, cena_id=cena,
                              frases=[0], inicio_s=0))  # início sem duração
    _recusa(lambda c: _insert(c, "roteiro_cenas", roteiro_id=r, ordem=0, cena_id=cena,
                              frases=[0], aviso="outro"))
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE pronuncias SET archived_at = now()"))
        _insert(conn, "pronuncias", perfil_id=p, escrita="Levinho", falada="lévinho")
        for ordem in (0, 1):  # a mesma cena pode repetir
            conn.execute(text(
                "INSERT INTO roteiro_cenas (roteiro_id, ordem, cena_id, frases, inicio_s, "
                "duracao_s, aviso) VALUES (:r, :o, :c, :f, 0, 3.327, 'tomada_curta')"),
                {"r": r, "o": ordem, "c": cena, "f": [ordem]})


def test_ffmpeg_fora_da_trava_de_gpu():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        _geracao(conn, p, passo="cena.clipe", alvo="cena", status="rodando")
        _geracao(conn, p, passo="roteiro.montagem", motor="ffmpeg", alvo="roteiro",
                 status="rodando")
    _recusa(lambda c: _geracao(c, p, passo="roteiro.acabamento", alvo="roteiro",
                               status="rodando"))


def test_downgrade_recusa_com_dados():
    with get_engine().begin() as conn:
        _insert(conn, "pronuncias", perfil_id=_perfil(conn), escrita="leve", falada="lévi")
    with pytest.raises(RuntimeError, match="recusado"):
        command.downgrade(_cfg(), ANTERIOR)
    with get_engine().begin() as conn:
        assert _existe(conn, "pronuncias")
