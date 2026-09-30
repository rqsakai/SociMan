"""Capacidades por rede e conta (spec 014 R4, spec 015 R12). Guarda 2 do princípio I: sem
conexão, nenhuma rede nem conta tem modo automático disponível; com conexão TikTok, só os modos
do executor com o escopo concedido. Todo modo indisponível diz o motivo."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from sociman_api.conteudos import capacidades
from sociman_api.conteudos.models import Modo
from sociman_api.perfis.models import Conta, ContaStatus, Platform


@dataclass
class _Conexao:
    estado: str = "conectada"
    escopos: list[str] = field(default_factory=lambda: [
        "user.info.basic", "user.info.profile", "video.upload", "video.publish"])


def _conta(platform: Platform, status: ContaStatus = ContaStatus.ativa,
           archived: bool = False) -> Conta:
    return Conta(platform=platform, platform_name="", handle="x", url="https://x",
                 status=status, archived_at=datetime.now(UTC) if archived else None)


@pytest.mark.parametrize("platform", list(Platform))
@pytest.mark.parametrize("status", list(ContaStatus))
@pytest.mark.parametrize("archived", [False, True])
@pytest.mark.parametrize("conexao", [None, _Conexao(estado="desconectada")])
def test_guarda_no_maximo_lembrete(platform, status, archived, conexao):
    """Sem conexão (ou com conexão desligada), nada automático, em nenhuma rede."""
    modos = capacidades.modos_da_conta(_conta(platform, status, archived), conexao)
    assert [m.modo for m in modos] == list(capacidades.ORDEM)
    disponiveis = {m.modo for m in modos if m.disponivel}
    assert disponiveis <= {Modo.lembrete}
    assert all(m.motivo for m in modos if not m.disponivel)
    assert all(m.motivo is None for m in modos if m.disponivel)


def test_ordem_da_spec():
    assert capacidades.ORDEM == (Modo.lembrete, Modo.criar_rascunho, Modo.publicar,
                                 Modo.rascunho_e_publicar)
    assert set(capacidades.ORDEM) == set(Modo)


@pytest.mark.parametrize("platform", [p for p in Platform if p != Platform.tiktok])
def test_so_tiktok_tem_executor(platform):
    """Com conexão "conectada" numa rede sem executor, nada automático (camada 2)."""
    modos = capacidades.modos_da_conta(_conta(platform), _Conexao())
    assert {m.modo for m in modos if m.disponivel} == {Modo.lembrete}


def test_tiktok_sem_conexao_so_lembrete_com_motivos(us3):
    modos = {m.modo: m for m in capacidades.modos_da_conta(_conta(Platform.tiktok))}
    assert modos[Modo.lembrete].disponivel
    assert modos[Modo.criar_rascunho].motivo == capacidades.CONECTE
    assert modos[Modo.publicar].motivo == capacidades.CONECTE
    assert modos[Modo.rascunho_e_publicar].motivo == (
        "O TikTok não permite publicar um rascunho pela API")


@pytest.fixture
def us3(monkeypatch):
    """Publicar liberado (US3), explícito para o teste não depender do valor da constante."""
    monkeypatch.setattr(capacidades, "PUBLICAR_LIBERADO", True)


def test_publicar_bloqueado_pela_chave(monkeypatch):
    """Com `PUBLICAR_LIBERADO = False` (antes da US3), publicar fica indisponível."""
    monkeypatch.setattr(capacidades, "PUBLICAR_LIBERADO", False)
    for conexao in (None, _Conexao()):
        modos = {m.modo: m for m in capacidades.modos_da_conta(
            _conta(Platform.tiktok), conexao, situacao_app="auditado")}
        assert not modos[Modo.publicar].disponivel
        assert modos[Modo.publicar].motivo == capacidades.PUBLICAR_DEPOIS
        assert modos[Modo.publicar].aviso is None


def test_tiktok_conectada_sandbox(us3):
    modos = {m.modo: m for m in capacidades.modos_da_conta(
        _conta(Platform.tiktok), _Conexao(), situacao_app="sandbox")}
    assert modos[Modo.criar_rascunho].disponivel
    assert modos[Modo.criar_rascunho].aviso is None
    assert modos[Modo.publicar].disponivel
    assert modos[Modo.publicar].aviso == capacidades.AVISO_SANDBOX
    assert not modos[Modo.rascunho_e_publicar].disponivel
    assert modos[Modo.rascunho_e_publicar].motivo == (
        "O TikTok não permite publicar um rascunho pela API")


def test_tiktok_conectada_auditado_sem_aviso(us3):
    modos = {m.modo: m for m in capacidades.modos_da_conta(
        _conta(Platform.tiktok), _Conexao(), situacao_app="auditado")}
    assert modos[Modo.publicar].disponivel
    assert modos[Modo.publicar].aviso is None


def test_tiktok_sem_video_publish(us3):
    conexao = _Conexao(escopos=["user.info.basic", "video.upload"])
    modos = {m.modo: m for m in capacidades.modos_da_conta(_conta(Platform.tiktok), conexao)}
    assert modos[Modo.criar_rascunho].disponivel
    assert not modos[Modo.publicar].disponivel
    assert modos[Modo.publicar].motivo.startswith(capacidades.RECONECTE)


def test_tiktok_precisa_reconectar(us3):
    modos = capacidades.modos_da_conta(_conta(Platform.tiktok),
                                       _Conexao(estado="precisa_reconectar"))
    assert {m.modo for m in modos if m.disponivel} == {Modo.lembrete}
    auto = [m for m in modos if m.modo in (Modo.criar_rascunho, Modo.publicar)]
    assert {m.motivo for m in auto} == {capacidades.RECONECTE}


def test_instagram_sem_rascunho():
    modos = {m.modo: m for m in capacidades.modos_da_conta(_conta(Platform.instagram))}
    assert "rascunho" in (modos[Modo.criar_rascunho].motivo or "")


@pytest.mark.parametrize(("status", "archived", "motivo"), [
    (ContaStatus.pausada, False, "Conta pausada"),
    (ContaStatus.encerrada, False, "Conta encerrada"),
    (ContaStatus.ativa, True, "Conta arquivada"),
])
def test_conta_em_atencao_nem_lembrete(status, archived, motivo):
    modos = capacidades.modos_da_conta(_conta(Platform.tiktok, status, archived), _Conexao())
    assert not any(m.disponivel for m in modos)
    assert {m.motivo for m in modos} == {motivo}


def test_planejada_tem_lembrete():
    info = capacidades.modo_info(_conta(Platform.youtube, ContaStatus.planejada), Modo.lembrete)
    assert info.disponivel
