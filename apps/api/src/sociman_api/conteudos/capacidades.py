"""Modos de agendamento por rede e por conta (research R4 da 014; R12 da 015; FR-006, FR-013).

Registro em código, sem tabela: as capacidades são fatos das APIs das redes
(`docs/pesquisa/publicacao-redes.md`). `modos_da_conta` combina três camadas, e o primeiro
"não" dá o motivo:

1. a rede oferece o modo? (fato permanente);
2. existe executor para a rede e o modo? (`publicacao.registro.executor_para`; na 015, só a
   TikTok, com `criar_rascunho` e `publicar`);
3. a conta pode? Conta arquivada, `pausada` ou `encerrada` não tem nenhum modo, nem o lembrete;
   os modos automáticos exigem a conexão `conectada` com o escopo do modo.

O interruptor desligado **não** tira a disponibilidade (dá para agendar; fica pausado). O mesmo
resultado valida a escrita (409 `modo_indisponivel`) e alimenta a tela
(`GET /api/contas/{id}/modos`). `aviso` é um alerta que não bloqueia (ex.: `publicar` com o app
em sandbox).
"""

from dataclasses import dataclass
from typing import Protocol

from sociman_api.config import get_settings
from sociman_api.conteudos.models import Modo
from sociman_api.perfis.models import Conta, ContaStatus, Platform

AGUARDANDO = "Aguardando a spec de integração desta rede"
SEM_INTEGRACAO = "Sem integração prevista para esta rede"
CONECTE = "Conecte a conta"
RECONECTE = "Reconecte a conta"
# `publicar` (Direct Post, US3) só depois do teste real do rascunho: até lá, indisponível na API
# e no SPA. Para religar quando a US3 entrar, basta `True` (e os testes de US3 passam a valer).
PUBLICAR_LIBERADO = True
PUBLICAR_DEPOIS = "Chega depois do teste real do rascunho (spec 015, US3)"
AVISO_SANDBOX = ("Sem auditoria da TikTok, o post sai só para você e a conta precisa estar "
                 "privada")

# Ordem da spec (US3): é a ordem da resposta de `contas_modos`.
ORDEM = (Modo.lembrete, Modo.criar_rascunho, Modo.publicar, Modo.rascunho_e_publicar)


@dataclass(frozen=True)
class Capacidade:
    existe: bool  # a rede oferece o modo pela API
    motivo: str | None = None  # por que não existe (camada 1)


@dataclass(frozen=True)
class ModoInfo:
    modo: Modo
    disponivel: bool
    motivo: str | None  # em pt-BR; sempre preenchido quando indisponível
    aviso: str | None = None  # alerta que não bloqueia (R12)


class ConexaoLike(Protocol):
    """O que a camada 3 lê da conexão viva da conta (`publicacao.models.Conexao`)."""

    estado: str
    escopos: list[str]


def _sem_integracao() -> dict[Modo, Capacidade]:
    return {
        Modo.criar_rascunho: Capacidade(False, SEM_INTEGRACAO),
        Modo.publicar: Capacidade(False, SEM_INTEGRACAO),
        Modo.rascunho_e_publicar: Capacidade(False, SEM_INTEGRACAO),
    }


CAPACIDADES: dict[Platform, dict[Modo, Capacidade]] = {
    Platform.tiktok: {
        Modo.criar_rascunho: Capacidade(True),
        # Sem auditoria da TikTok, a rede só publica como privado (pesquisa).
        Modo.publicar: Capacidade(True),
        Modo.rascunho_e_publicar: Capacidade(
            False, "O TikTok não permite publicar um rascunho pela API"),
    },
    Platform.youtube: {
        Modo.criar_rascunho: Capacidade(True),  # envio privado
        Modo.publicar: Capacidade(True),  # `publishAt`; privado até a auditoria do Google
        Modo.rascunho_e_publicar: Capacidade(True),  # privado + horário
    },
    Platform.instagram: {
        Modo.criar_rascunho: Capacidade(False, "O Instagram não tem rascunho pela API"),
        Modo.publicar: Capacidade(True),
        Modo.rascunho_e_publicar: Capacidade(
            False, "O Instagram não tem rascunho pela API"),
    },
    Platform.kwai: _sem_integracao(),
    Platform.facebook: _sem_integracao(),
    Platform.x: _sem_integracao(),
    Platform.outra: _sem_integracao(),
}

def motivo_atencao(conta: Conta) -> str | None:
    """Conta que não executa nada (nem o lembrete): o motivo, ou None se está em condição."""
    if conta.archived:
        return "Conta arquivada"
    if conta.status == ContaStatus.pausada:
        return "Conta pausada"
    if conta.status == ContaStatus.encerrada:
        return "Conta encerrada"
    return None


def _executor(platform: Platform):
    """Import tardio: `publicacao` depende da central (014), não o contrário."""
    from sociman_api.publicacao import registro

    return registro.executor_para(platform)


def _camada3(conta: Conta, modo: Modo, conexao: ConexaoLike | None) -> str | None:
    """Motivo pelo qual a conta não executa o modo automático, ou None se pode."""
    if conexao is None or conexao.estado == "desconectada":
        return CONECTE
    if conexao.estado != "conectada":
        return RECONECTE
    executor = _executor(conta.platform)
    escopo = executor.escopos_por_modo.get(modo) if executor is not None else None
    if escopo and escopo not in (conexao.escopos or []):
        return f"{RECONECTE} e autorize a permissão {escopo}"
    return None


def _aviso(conta: Conta, modo: Modo, situacao: str) -> str | None:
    if conta.platform == Platform.tiktok and modo == Modo.publicar and situacao == "sandbox":
        return AVISO_SANDBOX
    return None


def modos_da_conta(conta: Conta, conexao: ConexaoLike | None = None,
                   situacao_app: str | None = None) -> list[ModoInfo]:
    """Os quatro modos, na ordem da spec, com o motivo de cada indisponível.

    `conexao` é a conexão viva da conta (`publicacao.conexoes.conexao_viva`), ou None.
    `situacao_app` (`sandbox` | `auditado`) vem de `TIKTOK_APP_SITUACAO` quando omitida.
    """
    situacao = situacao_app or get_settings().tiktok_app_situacao
    atencao = motivo_atencao(conta)
    out: list[ModoInfo] = []
    for modo in ORDEM:
        if atencao is not None:
            out.append(ModoInfo(modo, False, atencao))
            continue
        if modo == Modo.lembrete:
            out.append(ModoInfo(modo, True, None))
            continue
        cap = CAPACIDADES[conta.platform][modo]
        if not cap.existe:
            out.append(ModoInfo(modo, False, cap.motivo))
            continue
        executor = _executor(conta.platform)
        if executor is None or modo not in executor.modos:
            out.append(ModoInfo(modo, False, AGUARDANDO))
            continue
        if modo == Modo.publicar and not PUBLICAR_LIBERADO:
            out.append(ModoInfo(modo, False, PUBLICAR_DEPOIS))
            continue
        motivo = _camada3(conta, modo, conexao)
        if motivo is not None:
            out.append(ModoInfo(modo, False, motivo))
        else:
            out.append(ModoInfo(modo, True, None, _aviso(conta, modo, situacao)))
    return out


def modo_info(conta: Conta, modo: Modo, conexao: ConexaoLike | None = None) -> ModoInfo:
    return next(m for m in modos_da_conta(conta, conexao) if m.modo == modo)
