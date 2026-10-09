"""Guardas de integração da spec 016 (plan, "Guardas" 6 e 7; princípio I): a coleta e o vínculo
só leem. Com os dois níveis do interruptor de publicação desligados (`PUBLICACAO_HABILITADA`
e o botão "Envios automáticos"), a TikTok falsa só vê `token`, `user_info`, `video_list`,
`video_query` e `status`; nenhum destino vai a `enviando` e nenhuma tentativa é criada."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fakes.tiktok_fake import ESCOPOS_016
from sqlalchemy import func, select

from integration.conexao_helpers import app_tiktok, conectar, destino_auto  # noqa: F401
from integration.metricas_helpers import HANDLE as H_M
from integration.metricas_helpers import OUTRA, POST_ID, m  # noqa: F401
from integration.postagem_helpers import LEGENDA, criar_conta, criar_perfil, dono  # noqa: F401
from integration.publicacao_helpers import ligar_botao
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.metricas import coleta
from sociman_api.metricas.models import FotoConta, FotoVideo, VideoRede
from sociman_api.postagem import service
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao.models import PublicacaoConfig, Tentativa

H = "atavernanerd"
ID_GRANDE = 7_400_000_000_000_000_001  # acima de 2^53
SO_LEITURA = {"token", "user_info", "video_list", "video_query", "status"}


@pytest.fixture
def cenario(client, db, dono, app_tiktok):  # noqa: F811
    """Conta conectada com os escopos de métricas, vídeos na TikTok falsa e um destino
    automático vencido (que a trilha de publicação pegaria se estivesse ligada)."""
    usuario, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], handle=H)
    conectar(client, h, conta, app_tiktok, escopos=ESCOPOS_016)
    agora = datetime.now(UTC).replace(second=0, microsecond=0)
    for n in range(3):
        app_tiktok.video(H, ID_GRANDE + n, agora - timedelta(hours=2 + n), duracao=30 + n,
                         legenda=f"corte {n}")
    app_tiktok.seguidores(H, 100)
    destino = destino_auto(db, perfil["id"], conta["id"], usuario,
                           planned_at=agora - timedelta(minutes=5))
    app_tiktok.requests.clear()  # o login não conta
    return {"fake": app_tiktok, "agora": agora, "destino": destino.id}


def _interruptor_desligado(db) -> None:
    assert get_settings().publicacao_habilitada is False  # a stack de teste sobe desligada
    config = db.get(PublicacaoConfig, 1)
    assert config is not None and config.envios_habilitados is False


def test_coleta_so_le_com_interruptor_desligado(db, cenario):
    """Guarda 6, parte da coleta: várias voltas (descoberta, fila e conta) só leem."""
    _interruptor_desligado(db)
    fake, agora = cenario["fake"], cenario["agora"]
    for passo in range(4):
        coleta.rodar(db, client=fake.client(), agora=agora + timedelta(hours=passo))
        db.commit()
        fake.contadores(ID_GRANDE, views=10 * (passo + 1))

    endpoints = {e for _, e, _ in fake.requests}
    assert endpoints <= SO_LEITURA, endpoints - SO_LEITURA
    assert {"video_list", "video_query", "user_info"} <= endpoints  # a coleta rodou
    assert fake.inits == 0 and fake.pedidos("put") == []
    # O que a coleta gravou é só observação (o guarda não é vazio).
    assert db.scalar(select(func.count()).select_from(VideoRede)) == 3
    assert db.scalar(select(func.count()).select_from(FotoVideo)) >= 3
    assert db.scalar(select(func.count()).select_from(FotoConta)) >= 1
    # Nada da publicação mudou.
    db.expire_all()
    assert db.get(Postagem, cenario["destino"]).estado == DestinoEstado.agendado
    assert db.scalar(select(func.count()).select_from(Postagem).where(
        Postagem.estado == DestinoEstado.enviando)) == 0
    assert db.scalar(select(func.count()).select_from(Tentativa)) == 0


# ---- guarda 4 (T040): a única transição do destino pelo vínculo ----

@pytest.mark.parametrize(("modo", "estado", "extra", "resultado"), [
    ("criar_rascunho", "rascunho_criado", {}, DestinoEstado.publicado),
    ("criar_rascunho", "falhou", {"falha_incerta": True}, DestinoEstado.publicado),
    ("criar_rascunho", "falhou", {"falha_incerta": False}, "destino_sem_post"),
    ("criar_rascunho", "agendado", {}, "destino_sem_post"),
    ("criar_rascunho", "pendente", {}, "destino_sem_post"),
    ("criar_rascunho", "enviando", {}, "destino_sem_post"),
])
def test_publicacao_pelo_vinculo_so_nos_estados_do_r12(m, modo, estado, extra,  # noqa: F811
                                                        resultado):
    """R12: ligar só move `rascunho_criado → publicado` e `falhou` (incerto) `→ publicado`;
    qualquer outro estado de execução é recusado sem mudar nada. (Conta diferente, desfazer e
    os estados que não voltam estão em `test_vinculo.py`.)"""
    destino = destino_auto(m.db, m.perfil["id"], m.conta["id"], m.dono, estado=estado,
                           modo=modo, **extra)
    ator = Actor(kind="system:metricas")
    if isinstance(resultado, DestinoEstado):
        service.publicacao_pelo_vinculo(m.db, ator, destino, True, conta_do_video=destino.conta_id,
                                        metodo="casamento")
        m.db.commit()
        assert m.destino(destino.id).estado == resultado
        return
    versao = destino.version
    with pytest.raises(ApiError) as exc:
        service.publicacao_pelo_vinculo(m.db, ator, destino, True,
                                        conta_do_video=destino.conta_id, metodo="casamento")
    m.db.rollback()
    assert exc.value.code == resultado
    atual = m.destino(destino.id)
    assert (atual.estado.value, atual.version) == (estado, versao)


# ---- guarda 6, parte do vínculo (T041) ----

def test_vinculo_so_le_com_interruptor_desligado(m, publicacao_habilitada):  # noqa: F811
    """Os níveis 1 e 2 e o lembrete depois do clique, com os dois níveis do interruptor
    desligados: só pedidos de leitura, nenhum destino em `enviando`, nenhuma tentativa nova."""
    d1 = m.rascunho(legenda=OUTRA)  # entregue com a publicação ligada (fixture `m`)
    d2 = m.rascunho(legenda=LEGENDA)
    publicacao_habilitada(False)
    ligar_botao(False)
    _interruptor_desligado(m.db)
    tentativas = m.db.scalar(select(func.count()).select_from(Tentativa))
    m.fake.requests.clear()
    agora = datetime.now(UTC)

    # Nível 1: o dono finaliza d1 no app com outra legenda; liga pelo envio.
    m.fake.video(H_M, POST_ID, agora, legenda="Terceira legenda sem relação alguma")
    m.fake.publicar_rascunho(m.publish_id(d1), POST_ID)
    m.coletar(agora + timedelta(minutes=11))
    assert m.destino(d1["id"]).estado == DestinoEstado.publicado
    # Nível 2: um post com a legenda de d2 e a mesma duração; liga pela lista.
    m.post(legenda=LEGENDA)
    m.coletar(agora + timedelta(hours=2))
    assert m.destino(d2["id"]).estado == DestinoEstado.publicado
    # Lembrete depois do clique: liga sozinho e continua `postado`.
    lembrete = m.postado(m.lembrete())
    pid = m.post(minutos=20, legenda=LEGENDA)
    m.coletar(agora + timedelta(hours=4))
    assert m.video_de(pid).destino_id == uuid.UUID(lembrete["id"])
    assert m.destino(lembrete["id"]).estado == DestinoEstado.postado

    endpoints = {e for _, e, _ in m.fake.requests}
    assert endpoints <= SO_LEITURA, endpoints - SO_LEITURA
    assert {"status", "video_list", "video_query"} <= endpoints  # o ciclo rodou
    assert m.fake.inits == 0 and m.fake.pedidos("put") == []
    assert m.db.scalar(select(func.count()).select_from(Tentativa)) == tentativas
    assert m.db.scalar(select(func.count()).select_from(Postagem).where(
        Postagem.estado == DestinoEstado.enviando)) == 0
