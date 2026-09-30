"""Casamento de vídeo e destino (spec 016, R10; Q3 = A): legenda, duração, âncoras e unicidade
nos dois sentidos. Funções puras; nada toca o banco."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from sociman_api.conteudos.models import Modo
from sociman_api.metricas import casamento
from sociman_api.metricas.casamento import Ancora, Par, classificar_legenda, normalizar
from sociman_api.postagem.models import DestinoEstado
from sociman_api.publicacao.legenda import legenda_tiktok

T0 = datetime(2026, 9, 30, 15, 0, tzinfo=UTC)


# ---- normalização e legenda ----

def test_normalizar_tira_acento_tags_emoji_pontuacao_e_espacos():
    assert normalizar("Olá, MUNDO!!  Ação 🔥 #fyp #Nerd   ok…") == ["ola", "mundo", "acao", "ok"]
    assert normalizar(None) == []
    assert normalizar("   ") == []


def test_legenda_do_destino_e_a_do_copiar_textos():
    destino = SimpleNamespace(descricao="O melhor jogo de 2026", hashtags=["#games", "#rpg"])
    assert legenda_tiktok(destino) == "O melhor jogo de 2026\n\n#games #rpg"
    # As hashtags do destino somem na normalização, como as do vídeo.
    assert classificar_legenda("o melhor jogo de 2026 #games", legenda_tiktok(destino)) \
        == "compativel"


@pytest.mark.parametrize(("video", "destino", "esperado"), [
    ("O melhor jogo de 2026", "O melhor jogo de 2026", "compativel"),
    ("o MELHOR jogo de 2026!!! 🔥", "O melhor jogo de 2026", "compativel"),
    # contém a outra
    ("O melhor jogo de 2026 segundo a Taverna e amigos", "melhor jogo de 2026", "compativel"),
    # Jaccard: {a,b,c,d} × {a,b,c,e} = 3/5 = 0,6
    ("aa bb cc dd", "aa bb cc ee", "compativel"),
    # Jaccard: {a,b,c,d} × {a,b,e,f} = 2/6 < 0,5
    ("aa bb cc dd", "aa bb ee ff", "incompativel"),
    # menos de 3 tokens no vídeo: neutra (o dono não colou a legenda)
    ("#fyp 🔥", "O melhor jogo de 2026", "neutra"),
    ("dois tokens", "qualquer coisa", "neutra"),
    ("", "O melhor jogo", "neutra"),
    ("tres tokens aqui", "", "incompativel"),
])
def test_classificar_legenda(video, destino, esperado):
    assert classificar_legenda(video, destino) == esperado


def test_jaccard_na_borda_de_meio_e_compativel():
    # {a,b,c} × {a,b,c,d,e,f}: contém? não ("aa bb cc" está contido no outro, então sim)
    assert classificar_legenda("aa bb cc", "aa bb cc dd ee ff") == "compativel"
    # {a,b,c,x} × {a,b,c,y,z,w}: 3/7 < 0,5; sem conter
    assert classificar_legenda("aa bb cc xx", "aa bb cc yy zz ww") == "incompativel"
    # {a,b,x} × {a,b,y}: 2/4 = 0,5
    assert classificar_legenda("aa bb xx", "aa bb yy") == "compativel"


# ---- duração ----

@pytest.mark.parametrize(("video", "conteudo", "ok"), [
    (30, 30.0, True), (31, 30.0, True), (29, 30.0, True), (32, 30.0, False),
    (30, 30.9, True), (30, 31.2, False), (30, None, False),
])
def test_duracao_mais_ou_menos_1s(video, conteudo, ok):
    assert casamento.duracao_compativel(video, conteudo) is ok


# ---- âncoras ----

def _destino(modo: Modo, estado: DestinoEstado, posted_at=None, archived_at=None):
    return SimpleNamespace(modo=modo, estado=estado, posted_at=posted_at, archived_at=archived_at)


def test_ancora_da_entrega_menos_5min_mais_14d_bordas_incluidas():
    a = Ancora("entrega", T0)
    assert a.contem(T0 - timedelta(minutes=5))
    assert a.contem(T0 + timedelta(days=14))
    assert not a.contem(T0 - timedelta(minutes=5, seconds=1))
    assert not a.contem(T0 + timedelta(days=14, seconds=1))
    assert a.minutos(T0 + timedelta(minutes=90)) == 90


def test_ancora_do_lembrete_postado_menos_24h_mais_1h_bordas_incluidas():
    a = Ancora("postado", T0)
    assert a.contem(T0 - timedelta(hours=24))
    assert a.contem(T0 + timedelta(hours=1))
    assert not a.contem(T0 - timedelta(hours=24, seconds=1))
    assert not a.contem(T0 + timedelta(hours=1, seconds=1))
    assert a.minutos(T0 - timedelta(minutes=30)) == -30


def test_qual_ancora_cada_destino_tem():
    rascunho = _destino(Modo.criar_rascunho, DestinoEstado.rascunho_criado)
    assert casamento.ancora(rascunho, T0) == Ancora("entrega", T0)
    assert casamento.ancora(rascunho, None) is None  # sem busca, sem âncora
    marcado = _destino(Modo.criar_rascunho, DestinoEstado.postado, posted_at=T0)
    assert casamento.ancora(marcado, T0 - timedelta(hours=2)).tipo == "entrega"
    lembrete = _destino(Modo.lembrete, DestinoEstado.postado, posted_at=T0)
    assert casamento.ancora(lembrete, None) == Ancora("postado", T0)
    # Q3 = A: lembrete antes do clique nunca liga sozinho.
    for estado in (DestinoEstado.aprovado, DestinoEstado.agendado):
        assert casamento.ancora(_destino(Modo.lembrete, estado), None) is None
    assert casamento.ancora(_destino(Modo.publicar, DestinoEstado.publicado), T0) is None
    assert casamento.ancora(_destino(Modo.criar_rascunho, DestinoEstado.falhou), T0) is None
    arquivado = _destino(Modo.lembrete, DestinoEstado.postado, posted_at=T0, archived_at=T0)
    assert casamento.ancora(arquivado, None) is None


# ---- unicidade nos dois sentidos ----

def _ids(n):
    return [uuid.uuid4() for _ in range(n)]


def test_candidato_unico_liga():
    (v,), (d,) = _ids(1), _ids(1)
    ligam, ambiguos = casamento.pares_unicos([Par(v, d, "compativel")])
    assert ligam == [Par(v, d, "compativel")]
    assert ambiguos == set()


def test_neutra_so_com_candidato_unico():
    v1, v2 = _ids(2)
    (d,) = _ids(1)
    assert casamento.pares_unicos([Par(v1, d, "neutra")])[0] == [Par(v1, d, "neutra")]
    ligam, ambiguos = casamento.pares_unicos([Par(v1, d, "neutra"), Par(v2, d, "neutra")])
    assert ligam == [] and ambiguos == {d}


def test_video_com_dois_destinos_nao_liga_nenhum():
    """Um rascunho entregue e um lembrete já postado disputando o mesmo vídeo."""
    (v,) = _ids(1)
    rascunho, lembrete = _ids(2)
    ligam, ambiguos = casamento.pares_unicos(
        [Par(v, rascunho, "compativel"), Par(v, lembrete, "neutra")])
    assert ligam == []
    assert ambiguos == {rascunho, lembrete}


def test_destino_com_dois_videos_nao_liga_e_o_outro_par_unico_liga():
    v1, v2, v3 = _ids(3)
    d1, d2 = _ids(2)
    ligam, ambiguos = casamento.pares_unicos(
        [Par(v1, d1, "compativel"), Par(v2, d1, "compativel"), Par(v3, d2, "compativel")])
    assert ligam == [Par(v3, d2, "compativel")]
    assert ambiguos == {d1}


def test_incompativel_nao_conta_na_unicidade():
    v1, v2 = _ids(2)
    (d,) = _ids(1)
    ligam, ambiguos = casamento.pares_unicos(
        [Par(v1, d, "compativel"), Par(v2, d, "incompativel")])
    assert ligam == [Par(v1, d, "compativel")]
    assert ambiguos == set()
