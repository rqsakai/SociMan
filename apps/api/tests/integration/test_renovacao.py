"""Renovação do token com rotação do refresh, sob `FOR UPDATE` (spec 015, T027, research R5).

Sempre com a TikTok falsa; o fake invalida o refresh usado (rotação)."""

import base64
import threading
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from integration.conexao_helpers import app_tiktok, conectar  # noqa: F401
from integration.postagem_helpers import criar_conta, criar_perfil, dono  # noqa: F401
from sociman_api.config import get_settings
from sociman_api.db import get_sessionmaker
from sociman_api.history import EntityVersion
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo
from sociman_api.publicacao import cifra, conexoes
from sociman_api.publicacao.executor import ConexaoIndisponivel, ConexaoPerdida
from sociman_api.publicacao.models import Conexao, ConexaoCredencial, ConexaoEstado


@pytest.fixture
def cx(client, db, dono, app_tiktok):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], handle="atavernanerd")
    conectar(client, h, conta, app_tiktok)
    conexao = db.scalar(select(Conexao))
    return conexao


def _cred(db, conexao) -> ConexaoCredencial | None:
    db.expire_all()
    return db.get(ConexaoCredencial, conexao.id)


def _vencer(db, conexao, quanto=timedelta(minutes=1)) -> None:
    cred = _cred(db, conexao)
    cred.access_expira_em = datetime.now(UTC) + quanto
    db.commit()


def _refreshes(fake) -> int:
    return sum(1 for p in fake.pedidos("token") if p["grant_type"] == "refresh_token")


def test_access_valido_nao_renova(db, cx, app_tiktok):  # noqa: F811
    token = conexoes.token_valido(cx.id, app_tiktok.client())
    assert app_tiktok.access[token] == cx.open_id
    assert _refreshes(app_tiktok) == 0
    assert _cred(db, cx).renovacoes == 0


def test_margem_de_5_minutos_renova(db, cx, app_tiktok):  # noqa: F811
    _vencer(db, cx, timedelta(minutes=4))
    antigo_refresh = set(app_tiktok.refresh)
    token = conexoes.token_valido(cx.id, app_tiktok.client())
    assert _refreshes(app_tiktok) == 1
    assert app_tiktok.access[token] == cx.open_id
    assert antigo_refresh & app_tiktok.usados  # o refresh antigo foi gasto (rotação)
    cred = _cred(db, cx)
    assert cred.renovacoes == 1 and cred.renovado_em is not None
    assert cred.access_expira_em > datetime.now(UTC) + timedelta(hours=1)
    # a próxima chamada usa o token novo, sem renovar
    assert conexoes.token_valido(cx.id, app_tiktok.client()) == token
    assert _refreshes(app_tiktok) == 1


def test_renovacao_regrava_com_a_chave_atual(db, cx, app_tiktok, monkeypatch):  # noqa: F811
    s = get_settings()
    antiga = s.sociman_tokens_key
    nova = SecretStr(base64.urlsafe_b64encode(b"n" * 32).decode())
    monkeypatch.setattr(s, "sociman_tokens_key", nova)
    monkeypatch.setattr(s, "sociman_tokens_key_anterior", antiga)
    assert cifra.precisa_recifrar(_cred(db, cx).key_id)
    _vencer(db, cx)
    conexoes.token_valido(cx.id, app_tiktok.client())
    assert _cred(db, cx).key_id == cifra.key_id_atual()


def test_duas_renovacoes_concorrentes_gastam_um_refresh(db, cx, app_tiktok):  # noqa: F811
    _vencer(db, cx)
    barreira = threading.Barrier(2)
    tokens, erros = [], []

    def _renovar():
        try:
            barreira.wait()
            tokens.append(conexoes.token_valido(cx.id, app_tiktok.client()))
        except Exception as e:  # noqa: BLE001 — o teste confere abaixo
            erros.append(e)

    threads = [threading.Thread(target=_renovar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert erros == []
    assert _refreshes(app_tiktok) == 1  # o segundo esperou a trava e releu o token novo
    assert len(set(tokens)) == 1
    db.expire_all()
    assert db.get(Conexao, cx.id).estado == ConexaoEstado.conectada


def test_invalid_grant_precisa_reconectar(db, cx, app_tiktok, dono):  # noqa: F811
    _vencer(db, cx)
    app_tiktok.refresh.clear()  # o refresh foi revogado do lado da TikTok
    with pytest.raises(ConexaoPerdida):
        conexoes.token_valido(cx.id, app_tiktok.client())
    db.expire_all()
    conexao = db.get(Conexao, cx.id)
    assert conexao.estado == ConexaoEstado.precisa_reconectar and conexao.motivo
    assert _cred(db, cx) is None
    [versao] = db.scalars(select(EntityVersion).where(
        EntityVersion.entity_id == cx.id, EntityVersion.version == conexao.version))
    assert versao.actor_kind == "system:publicacao"
    assert versao.details == {"acao": "precisa_reconectar"}
    avisos = list(db.scalars(select(Notificacao).where(
        Notificacao.tipo == NotificacaoTipo.conexao_precisa_reconectar)))
    assert [a.user_id for a in avisos] == [dono[0].id]
    # de novo: sem credencial, perde na hora, sem pedir à TikTok e sem outro aviso
    with pytest.raises(ConexaoPerdida):
        conexoes.token_valido(cx.id, app_tiktok.client())
    assert _refreshes(app_tiktok) == 1
    assert db.scalar(select(func.count()).select_from(Notificacao)) == 1


def test_5xx_nao_muda_nada(db, cx, app_tiktok):  # noqa: F811
    _vencer(db, cx)
    antes = _cred(db, cx).access_cifrado
    app_tiktok.falhar_proximo("token", "5xx")
    with pytest.raises(ConexaoIndisponivel):
        conexoes.token_valido(cx.id, app_tiktok.client())
    app_tiktok.falhar_proximo("token", "conexao")
    with pytest.raises(ConexaoIndisponivel):
        conexoes.token_valido(cx.id, app_tiktok.client())
    db.expire_all()
    assert db.get(Conexao, cx.id).estado == ConexaoEstado.conectada
    assert _cred(db, cx).access_cifrado == antes
    # e na volta seguinte renova normalmente
    conexoes.token_valido(cx.id, app_tiktok.client())
    assert _cred(db, cx).renovacoes == 1


def test_aviso_de_30_dias_uma_vez_por_ciclo(db, cx):
    agora = datetime.now(UTC)
    conexao = db.get(Conexao, cx.id)
    conexao.refresh_expira_em = agora + timedelta(days=40)
    db.commit()

    def _rodar(quando):
        with get_sessionmaker()() as s:
            n = conexoes.avisar_vencimentos(s, quando)
            s.commit()
            return n

    assert _rodar(agora) == 0
    assert _rodar(agora + timedelta(days=11)) == 1
    assert _rodar(agora + timedelta(days=12)) == 0  # mesmo ciclo
    # renovou e o vencimento andou 365 dias: novo ciclo, novo aviso quando chegar a hora
    db.expire_all()
    conexao = db.get(Conexao, cx.id)
    conexao.refresh_expira_em = agora + timedelta(days=405)
    db.commit()
    assert _rodar(agora + timedelta(days=12)) == 0
    assert _rodar(agora + timedelta(days=380)) == 1
    avisos = db.scalar(select(func.count()).select_from(Notificacao).where(
        Notificacao.tipo == NotificacaoTipo.conexao_precisa_reconectar))
    assert avisos == 2  # um por ciclo
