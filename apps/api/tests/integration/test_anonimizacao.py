"""Desconectar anonimiza as métricas (spec 016, R13; FR-009; Q1 = A; guarda 9).

Só UPDATE: nenhuma linha some das tabelas `metricas_*`, e nenhuma coluna identificadora da série
fica preenchida. A série anônima não é mais coletada, e reconectar cria outra.
"""

import uuid
from datetime import timedelta

from atores import ator_fake
from sqlalchemy import select, text

from integration.conexao_helpers import app_tiktok, conectar  # noqa: F401
from integration.metricas_helpers import OUTRA, _agora, err, m  # noqa: F401
from integration.postagem_helpers import membro  # noqa: F401
from sociman_api.auth.deps import Actor, current_user
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import BuscaPost, Serie, VideoRede
from sociman_api.publicacao.models import Conexao

TABELAS = ("metricas_series", "metricas_videos", "metricas_video_fotos", "metricas_conta_fotos",
           "metricas_buscas_post")
TEXTOS_PROIBIDOS = ("atavernanerd", "Legenda de teste", "Você usa isso?", "tiktok.com",
                    "Taverna")


def _contagens() -> dict[str, int]:
    with get_engine().connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABELAS}


def _dados(m) -> dict:  # noqa: F811
    """Série com vídeos (um ligado a um lembrete, outros de fora), fotos e uma busca aberta."""
    lembrete = m.lembrete()
    ligado = m.post(minutos=30)
    fora = m.post(minutos=90, duracao=45, legenda="Outro vídeo #fyp #nerd")
    m.coletar(_agora() + timedelta(hours=2))
    r = m.ligar(lembrete, videoId=str(m.video_de(ligado).id))
    assert r.status_code == 200, r.text
    rascunho = m.rascunho(legenda=OUTRA)
    m.coletar(_agora() + timedelta(hours=2, minutes=5))  # a busca do rascunho fica aberta
    assert m.busca(rascunho["id"]).encerrada_em is None
    return {"lembrete": lembrete, "ligado": ligado, "fora": fora, "rascunho": rascunho}


def _serie(m) -> Serie:  # noqa: F811
    m.db.expire_all()
    return m.db.scalar(select(Serie).where(Serie.conta_id == uuid.UUID(m.conta["id"])))


def _conexao(m) -> dict:  # noqa: F811
    r = m.client.get(f"/api/contas/{m.conta['id']}/conexao", headers=m.h)
    assert r.status_code == 200, r.text
    return r.json()["conexao"]


def _desconectar(m, h=None, **body):  # noqa: F811
    version = _conexao(m)["version"]
    return m.client.post(f"/api/contas/{m.conta['id']}/conexao/desconectar",
                         headers=h or m.h, json={"version": version, **body})


def _conferir_anonima(m, serie_id: uuid.UUID, dados: dict) -> None:  # noqa: F811
    m.db.expire_all()
    serie = m.db.get(Serie, serie_id)
    assert serie.conta_id is None and serie.anonimizada_em is not None
    assert serie.rotulo == f"Conta anônima {serie.anonima_n}"
    assert serie.anonimizada_por == m.dono.id
    assert serie.varredura_cursor is None and serie.ultimo_erro_codigo is None
    videos = list(m.db.scalars(select(VideoRede).where(VideoRede.serie_id == serie_id)))
    assert videos
    for v in videos:
        assert (v.rede_video_id, v.share_url, v.legenda, v.titulo) == (None, None, None, None)
        assert (v.destino_id, v.vinculo_metodo, v.vinculado_por, v.vinculado_em) == \
            (None, None, None, None)
        assert v.proxima_coleta_em is None and v.anonimizado_em is not None
        assert (v.publicado_em.minute, v.publicado_em.second, v.publicado_em.microsecond) == \
            (0, 0, 0)
        assert set(v.features) == set(anonimizar.FEATURES)
        for valor in v.features.values():  # nenhum texto identificador
            assert valor is None or isinstance(valor, (int, float)) or valor in (
                "corte", "video_proprio", "fora", "lembrete", "criar_rascunho", "publicar",
                "envio", "casamento", "link", "escolha", "proprio", "parceiro",
                "programa_de_cortes", "sem_acordo")
        texto = str(v.features)
        for proibido in TEXTOS_PROIBIDOS + (dados["ligado"], dados["fora"]):
            assert proibido not in texto
    ligado = next(v for v in videos if v.features["origem"] == "corte")
    assert ligado.features["modo_envio"] == "lembrete"
    assert ligado.features["vinculo_metodo"] == "escolha"
    assert ligado.features["gancho_caracteres"] == len("Você usa isso?")
    assert ligado.features["duracao_s"] == 30
    de_fora = next(v for v in videos if v.features["duracao_s"] == 45)
    assert de_fora.features["origem"] == "fora" and de_fora.features["hashtags_n"] == 2
    buscas = list(m.db.scalars(select(BuscaPost)))
    assert buscas and all(b.post_id is None for b in buscas)
    assert all(b.encerrada_em is not None for b in buscas)
    assert m.busca(dados["rascunho"]["id"]).fim == "anonimizada"


def test_anonimizar_serie_so_com_update(m):  # noqa: F811
    """A função (T052), sem a rota: nenhuma linha some e nada identificável sobra."""
    dados = _dados(m)
    serie = _serie(m)
    antes = _contagens()
    esperado = anonimizar.contagem(m.db, serie)
    assert esperado[0] == 2 and esperado[1] > 2
    n = anonimizar.serie(m.db, serie, Actor(kind="user", user_id=m.dono.id, user=m.dono))
    m.db.commit()
    assert n == esperado
    assert _contagens() == antes
    _conferir_anonima(m, serie.id, dados)
    # A mesma série não é anonimizada de novo (idempotente) e o N não muda.
    n_rotulo = m.db.get(Serie, serie.id).anonima_n
    anonimizar.serie(m.db, m.db.get(Serie, serie.id), Actor(kind="user", user_id=m.dono.id))
    m.db.commit()
    assert m.db.get(Serie, serie.id).anonima_n == n_rotulo


def test_desconectar_exige_confirmacao_e_anonimiza_na_mesma_transacao(m):  # noqa: F811
    dados = _dados(m)
    serie = _serie(m)
    videos, fotos = anonimizar.contagem(m.db, serie)
    antes = _contagens()

    r = _desconectar(m)
    assert r.status_code == 409 and err(r) == "confirmar_anonimizacao"
    assert r.json()["error"]["details"] == {"videos": videos, "fotos": fotos,
                                            "conta": "@atavernanerd"}
    assert _serie(m) is not None  # nada mudou
    assert _conexao(m)["estado"] == "conectada"

    r = _desconectar(m, confirmoAnonimizar=True)
    assert r.status_code == 200, r.text
    assert r.json()["metricasAnonimizadas"] == {"videos": videos, "fotos": fotos}
    assert _contagens() == antes
    _conferir_anonima(m, serie.id, dados)
    m.db.expire_all()
    conexao = m.db.scalars(select(Conexao).where(
        Conexao.conta_id == uuid.UUID(m.conta["id"]))).one()
    versao = m.db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "conexao", EntityVersion.entity_id == conexao.id,
        EntityVersion.details["acao"].astext == "metricas_anonimizadas")).one()
    assert versao.details == {"acao": "metricas_anonimizadas", "videos": videos,
                              "fotos": fotos, "importacoes": 0}  # spec 020 (R9)
    assert str(serie.id) not in str(versao.details)

    # A série anônima não é mais coletada; reconectar cria outra.
    pedidos = len(m.fake.requests)
    m.coletar(_agora() + timedelta(hours=5))
    assert len(m.fake.requests) == pedidos
    from fakes.tiktok_fake import ESCOPOS_016

    conectar(m.client, m.h, m.conta, m.fake, escopos=ESCOPOS_016)
    m.coletar(_agora() + timedelta(hours=6))
    nova = _serie(m)
    assert nova is not None and nova.id != serie.id
    assert m.db.get(Serie, serie.id).conta_id is None


def test_serie_sem_foto_desconecta_sem_confirmar(m):  # noqa: F811
    with get_engine().begin() as conn:  # a série existe, mas sem nenhuma foto
        conn.execute(text("TRUNCATE metricas_video_fotos, metricas_conta_fotos"))
    r = _desconectar(m)
    assert r.status_code == 200, r.text


def test_membro_e_mcp_nao_desconectam(m, membro):  # noqa: F811
    _dados(m)
    r = _desconectar(m, h=membro[1], confirmoAnonimizar=True)
    assert r.status_code == 403 and err(r) == "somente_dono"
    app.dependency_overrides[current_user] = lambda: ator_fake("mcp_client", m.dono)
    r = _desconectar(m, confirmoAnonimizar=True)
    del app.dependency_overrides[current_user]
    assert r.status_code == 403 and err(r) == "somente_humano"
    assert _serie(m).anonimizada_em is None
