"""Trilha `publicacao` do agendador (spec 015, research R6 a R11): executa na rede os destinos
agendados em modo automático, a partir da decisão de um dono humano (princípio I).

Cada volta (`rodar`):
1. **retoma** as tentativas abertas pela fase gravada (R8): `iniciando` sem init → init;
   `iniciando` com init e sem `publish_id` → `incerta` (nunca repete o init); `enviando_partes`
   → reenvia a partir de `partes_enviadas` (ou `recusada` com o link vencido); `processando` →
   `status/fetch`;
2. **reivindica** até 5 destinos vencidos (`_reivindicar`, `SKIP LOCKED`), com a conta
   conectada, a janela de 1 h (ou a confirmação do dono) e a decisão humana conferida de novo;
3. uma vez por hora, o aviso de refresh perto de vencer (`conexoes.avisar_vencimentos`).

Regras que valem sempre:
- **cada passo que muda estado faz commit antes de chamar a rede** (a trilha faz os próprios
  commits; o agendador só fecha a volta): `init_enviado_em` antes do init; `publish_id` e o
  `upload_url` (cifrado) antes do primeiro PUT; `partes_enviadas` depois de cada parte;
- **interruptor em dois níveis** (R11): com `PUBLICACAO_HABILITADA` desligada nada roda; com o
  botão desligado, nenhum init e nenhum PUT (a tentativa fica parada, o destino aparece
  `pausado`), e só o `status/fetch` de `processando` continua (é leitura);
- as atribuições de estado do destino ficam em três funções (o guarda de AST confere):
  `enviando` só em `_reivindicar`; `rascunho_criado`, `publicado` e `falhou` só em `_concluir`;
  `_devolver` volta a `agendado` quando nada foi criado na rede;
- nada daqui conhece a TikTok: tudo passa pelo `ExecutorRede` de `publicacao.registro` (R20).
  Tokens e `upload_url` nunca vão para log, `details` nem histórico.
"""

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from minio.error import S3Error
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from sociman_api import history, storage
from sociman_api.auth.deps import Actor, registrar_recusa
from sociman_api.config import get_settings
from sociman_api.conteudos import consulta
from sociman_api.conteudos.models import Conteudo, Modo
from sociman_api.history import EntityVersion
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo
from sociman_api.perfis.models import Conta, Platform
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao import cifra, conexoes, limites, registro
from sociman_api.publicacao.executor import (
    LINK_EXPIRADO,
    LINK_EXPIRADO_INTERRUPTOR,
    SEM_CONFIRMACAO,
    SEM_DECISAO_HUMANA,
    SEM_RESPOSTA,
    VIDEO_MUDOU,
    Acao,
    ConexaoIndisponivel,
    ConexaoPerdida,
    Contexto,
    EmAndamento,
    Entregue,
    ExecutorRede,
    Iniciado,
    Motivo,
    Publicado,
    Recusado,
    RecusaRede,
    RedeErro,
    SemResposta,
    SemVaga,
)
from sociman_api.publicacao.models import (
    Conexao,
    ConexaoEstado,
    PublicacaoConfig,
    Tentativa,
    TentativaFase,
)

log = logging.getLogger("sociman.agendador.publicacao")

ATOR = Actor(kind="system:publicacao")
ENTITY = "postagem"
LOTE = 5  # destinos reivindicados por volta
JANELA = consulta.JANELA_ENVIO  # depois disso, só com "Confirmar envio" (R11)
CHUNK = storage.PART_SIZE  # 16 MB (R9)
INTEIRO_ATE = 64 * 1024 * 1024  # até 64 MB vai inteiro (a TikTok exige chunk_size == video_size com 1 parte)
LINK_VALE = timedelta(minutes=55)
STATUS_PRIMEIRO = timedelta(seconds=10)
STATUS_MAX = timedelta(seconds=60)
STATUS_PRAZO = timedelta(hours=2)  # sem estado final depois do upload → `incerta`
ADIAR = timedelta(seconds=60)  # taxa local, `rate_limit_exceeded` ou rede fora
AVISOS_A_CADA = timedelta(hours=1)

ABERTAS = (TentativaFase.iniciando, TentativaFase.enviando_partes, TentativaFase.processando)
AUTOMATICOS = (Modo.criar_rascunho, Modo.publicar)
# Versões que valem como decisão de envio (a última precisa ser de um humano, R15).
ACOES_DECISAO = ("agendado", "reagendado", "tentar_de_novo", "envio_confirmado",
                 "snapshot_atualizado")

SEM_VIDEO = Motivo("O vídeo final não está disponível; confira o conteúdo e tente de novo",
                   Acao.tentar_de_novo)
SEM_CONEXAO = Motivo("A conta precisa ser conectada (ou reconectada) para enviar",
                     Acao.reconectar)
SEM_SNAPSHOT = Motivo("Falta o que o dono confirmou na tela de publicar; agende de novo",
                      Acao.reagendar)
SEM_VAGA_LOCAL = Motivo("Já há 5 rascunhos esperando na rede nas últimas 24 h", Acao.esperar)

_ultimos_avisos: dict[str, datetime] = {}


# ---- interruptor ----

def servidor_habilitado() -> bool:
    return bool(get_settings().publicacao_habilitada)


def botao_ligado(db: Session) -> bool:
    cfg = db.get(PublicacaoConfig, 1, populate_existing=True)
    return bool(cfg is not None and cfg.envios_habilitados)


def pode_enviar(db: Session) -> bool:
    """Os dois níveis ligados, lidos na hora (o dono pode desligar no meio do envio)."""
    return servidor_habilitado() and botao_ligado(db)


# ---- auxiliares ----

def _agora() -> datetime:
    return datetime.now(UTC)


def _details(t: Tentativa, **extra: Any) -> None:
    t.details = {**(t.details or {}), **extra}


def _record(db: Session, destino: Postagem, acao: str, t: Tentativa, before: dict,
            **extra: Any) -> None:
    details: dict[str, Any] = {"acao": acao, "tentativaId": str(t.id), **extra}
    if t.publish_id:
        details["publishId"] = t.publish_id
    history.record(db, ATOR, ENTITY, destino, "updated", before, history.snapshot(destino),
                   details)


def _nome_e_conta(db: Session, destino: Postagem) -> tuple[str, Conta]:
    conteudo = db.get(Conteudo, destino.conteudo_id)
    conta = db.get(Conta, destino.conta_id)
    assert conteudo is not None and conta is not None
    return destino.titulo or conteudo.titulo or "seu conteúdo", conta


def _avisar(db: Session, destino: Postagem, tipo: NotificacaoTipo, titulo: str, corpo: str,
            dedupe: str) -> None:
    notificacoes.criar(db, tipo, titulo=titulo, corpo=corpo,
                       link=f"/app/conteudos/{destino.conteudo_id}?conta={destino.conta_id}",
                       entidade=(ENTITY, destino.id), dedupe_key=dedupe,
                       destinatarios=notificacoes.donos_ativos(db))


def _numero(db: Session, destino_id: uuid.UUID) -> int:
    ultimo = db.scalar(select(func.max(Tentativa.numero))
                       .where(Tentativa.destino_id == destino_id))
    return (ultimo or 0) + 1


def partes(tamanho: int) -> tuple[int, int]:
    """(chunk_size, total_partes): até 64 MB, uma parte só com chunk_size == video_size
    (regra da TikTok: total_chunk_count = floor(video_size / chunk_size); com 1 parte o
    chunk_size declarado tem de ser o vídeo inteiro, senão `invalid_params` — visto no
    sandbox em 2026-09-29). Acima de 64 MB, partes de 16 MB e a última absorve o resto."""
    if tamanho <= INTEIRO_ATE:
        return tamanho, 1
    return CHUNK, max(1, tamanho // CHUNK)


def faixa(t: Tentativa, indice: int) -> tuple[int, int]:
    """(início, tamanho) da parte `indice` (0-based)."""
    inicio = indice * t.chunk_size
    if indice == t.total_partes - 1:
        return inicio, t.video_bytes - inicio
    return inicio, t.chunk_size


def _stat(key: str) -> tuple[str, int] | None:
    """(etag, tamanho) do vídeo no MinIO, ou None se não deu para ler."""
    try:
        obj = storage.stat(key, bucket="videos")
    except (S3Error, OSError, ValueError):  # objeto sumiu ou MinIO fora: quem chama decide
        log.warning("publicacao: não foi possível ler o vídeo %s", key)
        return None
    return obj.etag or "", int(obj.size or 0)


def _ler(key: str, inicio: int, tamanho: int) -> bytes:
    return b"".join(storage.get_range(key, inicio, tamanho, bucket="videos"))


def _sha256(t: Tentativa) -> str:
    hasher = hashlib.sha256()
    for indice in range(t.total_partes):
        inicio, tamanho = faixa(t, indice)
        for pedaco in storage.get_range(t.video_ref, inicio, tamanho, bucket="videos"):
            hasher.update(pedaco)
    return hasher.hexdigest()


def _motivo(r: Recusado) -> Motivo:
    return Motivo(r.motivo, Acao(r.acao))


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


# ---- decisão humana (R15) ----

def _ultima_decisao(db: Session, destino_id: uuid.UUID) -> EntityVersion | None:
    """A versão mais recente que agendou, reagendou, confirmou, tentou de novo ou regravou o
    snapshot (também em lote e na sequência: `acao = lote` com `loteAcao`)."""
    acao = EntityVersion.details["acao"].astext
    lote = EntityVersion.details["loteAcao"].astext
    return db.scalar(
        select(EntityVersion)
        .where(EntityVersion.entity_type == ENTITY, EntityVersion.entity_id == destino_id,
               or_(acao.in_(ACOES_DECISAO), and_(acao == "lote", lote.in_(ACOES_DECISAO))))
        .order_by(EntityVersion.version.desc())
        .limit(1)
    )


def decisao_humana(destino: Postagem, versao: EntityVersion | None) -> bool:
    if destino.aprovado_por is None or destino.agendado_por is None:
        return False
    return versao is not None and versao.actor_kind == "user" \
        and versao.actor_user_id is not None


def _disparo(destino: Postagem, versao: EntityVersion | None) -> tuple[str, uuid.UUID | None]:
    acao = (versao.details or {}).get("acao") if versao is not None else None
    if acao == "tentar_de_novo":
        return "tentar_de_novo", versao.actor_user_id if versao else None
    if destino.envio_confirmado_em is not None and destino.planned_at is not None \
            and destino.envio_confirmado_em >= destino.planned_at:
        return "confirmado", destino.envio_confirmado_por
    return "agendador", None


# ---- as três únicas transições do destino ----

def _reivindicar(db: Session, agora: datetime) -> list[Tentativa]:
    """`agendado → enviando` (a ÚNICA atribuição de `enviando`, guarda de AST) e a tentativa
    `iniciando`, na mesma transação, com commit. Um destino sem decisão humana (ou sem vídeo)
    termina `recusada` na hora, e a falta de decisão humana grava o evento de segurança."""
    horario = consulta.horario_envio()
    rows = db.execute(
        consulta.destinos_do_conteudo()
        .add_columns(Conexao, consulta.video_ref())
        .join(Conexao, and_(Conexao.conta_id == Postagem.conta_id,
                            Conexao.estado == ConexaoEstado.conectada))
        .where(Postagem.estado == DestinoEstado.agendado, Postagem.modo.in_(AUTOMATICOS),
               Postagem.archived_at.is_(None), ~consulta.arquivado(), consulta.pronto(),
               ~consulta.conta_em_atencao(), horario <= agora,
               or_(horario > agora - JANELA,
                   Postagem.envio_confirmado_em >= Postagem.planned_at),
               ~consulta.tem_tentativa_aberta(), ~consulta.aguardando_vaga(agora))
        .order_by(Postagem.planned_at, Postagem.id)
        .limit(LOTE)
        .with_for_update(of=Postagem, skip_locked=True)
    ).all()
    novas: list[Tentativa] = []
    recusas: list[tuple[Postagem, str]] = []
    for destino, conexao, video_ref in rows:
        versao = _ultima_decisao(db, destino.id)
        disparo, disparado_por = _disparo(destino, versao)
        video = _stat(video_ref) if video_ref else None
        tamanho = video[1] if video else 0
        chunk, total = partes(tamanho) if tamanho > 0 else (1, 1)
        t = Tentativa(
            id=uuid.uuid4(), destino_id=destino.id, numero=_numero(db, destino.id),
            conexao_id=conexao.id, rede=conexao.rede, modo=destino.modo,
            fase=TentativaFase.iniciando, disparo=disparo, disparado_por=disparado_por,
            video_ref=video_ref or "", video_etag=video[0] if video else "",
            video_bytes=tamanho, chunk_size=chunk, total_partes=total, partes_enviadas=0,
            iniciada_em=agora, details={},
        )
        db.add(t)
        before = history.snapshot(destino)
        destino.estado = DestinoEstado.enviando
        _record(db, destino, "envio_iniciado", t, before)
        db.flush()
        if not decisao_humana(destino, versao):
            recusas.append((destino, versao.actor_kind if versao else "desconhecido"))
            _concluir(db, destino, t, TentativaFase.recusada, SEM_DECISAO_HUMANA,
                      codigo="sem_decisao_humana")
        elif video is None or tamanho <= 0:
            _concluir(db, destino, t, TentativaFase.recusada, SEM_VIDEO,
                      codigo="video_indisponivel")
        else:
            novas.append(t)
    db.commit()
    for destino, kind in recusas:
        registrar_recusa(Actor(kind=kind), "trilha:publicacao", conta_id=destino.conta_id,
                         destino_id=destino.id)
        log.warning("publicacao: destino %s sem decisão humana; recusado", destino.id)
    return novas


def _concluir(db: Session, destino: Postagem, t: Tentativa, fase: TentativaFase,
              motivo: Motivo | None = None, *, codigo: str | None = None,
              post_id: str | None = None) -> None:
    """Fase final da tentativa e o estado do destino: `entregue → rascunho_criado`,
    `publicada → publicado`, `recusada`/`incerta → falhou` (a ÚNICA atribuição desses três
    estados, guarda de AST), com a versão e o aviso aos donos. Sem commit."""
    t.fase = fase
    t.concluida_em = _agora()
    t.proxima_em = None
    t.upload_url_cifrado = None
    if codigo is not None:
        t.codigo_rede = codigo
    if motivo is not None:
        t.motivo = motivo.motivo
        _details(t, acao=motivo.acao.value)
    if post_id:
        t.rede_post_id = post_id
    before = history.snapshot(destino)
    nome, conta = _nome_e_conta(db, destino)
    if fase == TentativaFase.entregue:
        destino.estado = DestinoEstado.rascunho_criado
        destino.falha_motivo = None
        destino.falha_incerta = False
        _record(db, destino, "rascunho_criado", t, before)
        _avisar(db, destino, NotificacaoTipo.rascunho_criado,
                f"Rascunho na TikTok: {nome} (@{conta.handle})",
                "Abra o app da TikTok para finalizar", f"rascunho_criado:{t.id}")
    elif fase == TentativaFase.publicada:
        destino.estado = DestinoEstado.publicado
        destino.falha_motivo = None
        destino.falha_incerta = False
        destino.rede_post_id = post_id
        _record(db, destino, "publicado", t, before)
        _avisar(db, destino, NotificacaoTipo.envio_publicado, f"Publicado na TikTok: {nome}",
                f"@{conta.handle}", f"envio_publicado:{t.id}")
    else:
        assert fase in (TentativaFase.recusada, TentativaFase.incerta), fase
        destino.estado = DestinoEstado.falhou
        destino.falha_motivo = t.motivo
        destino.falha_incerta = fase == TentativaFase.incerta
        _record(db, destino, "envio_falhou", t, before, motivo=t.motivo)
        _avisar(db, destino, NotificacaoTipo.envio_rede_falhou, f"Falhou na TikTok: {nome}",
                f"@{conta.handle}: {t.motivo or ''}", f"envio_rede_falhou:{t.id}")
    log.info("publicacao: destino %s, tentativa %d → %s", destino.id, t.numero, fase.value)


def _devolver(db: Session, destino: Postagem, t: Tentativa, fase: TentativaFase,
              motivo: Motivo, *, codigo: str | None = None,
              proxima_em: datetime | None = None) -> None:
    """`enviando → agendado` quando a tentativa terminou **sem criar nada** na rede (sem vaga,
    conta desconectada antes do init). O estado efetivo mostra `aguardando_vaga` ou `atencao`.
    Sem commit."""
    t.fase = fase
    t.concluida_em = _agora()
    t.proxima_em = proxima_em
    t.motivo = motivo.motivo
    t.upload_url_cifrado = None
    _details(t, acao=motivo.acao.value)
    if codigo is not None:
        t.codigo_rede = codigo
    before = history.snapshot(destino)
    destino.estado = DestinoEstado.agendado
    _record(db, destino, "envio_devolvido", t, before, motivo=motivo.motivo)
    if fase == TentativaFase.sem_vaga and proxima_em is not None:
        nome, conta = _nome_e_conta(db, destino)
        hora = proxima_em.astimezone(_tz()).strftime("%d/%m %H:%M")
        _avisar(db, destino, NotificacaoTipo.envio_aguardando_vaga,
                f"Aguardando vaga na TikTok: {nome}",
                f"@{conta.handle}: {motivo.motivo}; nova tentativa às {hora}",
                f"envio_aguardando_vaga:{destino.id}:{proxima_em.isoformat()}")
    log.info("publicacao: destino %s devolvido (%s)", destino.id, fase.value)


# ---- passos da tentativa ----

class _Clientes:
    """Um cliente HTTP por rede por volta (ou o injetado pelos testes)."""

    def __init__(self, injetado: Any = None):
        self.injetado = injetado
        self._abertos: dict[Platform, Any] = {}

    def para(self, executor: ExecutorRede) -> Any:
        if self.injetado is not None:
            return self.injetado
        if executor.rede not in self._abertos:
            self._abertos[executor.rede] = executor.novo_cliente()
        return self._abertos[executor.rede]

    def fechar(self) -> None:
        for c in self._abertos.values():
            c.close()


def _executor(t: Tentativa) -> ExecutorRede:
    executor = registro.executor_para(t.rede)
    assert executor is not None, f"rede sem executor: {t.rede}"
    return executor


def _ctx(t: Tentativa, cliente: Any) -> Contexto:
    return Contexto(client=cliente,
                    token=lambda: conexoes.token_valido(t.conexao_id, client=cliente))


def _destino(db: Session, t: Tentativa) -> Postagem:
    destino = db.get(Postagem, t.destino_id, with_for_update=True, populate_existing=True)
    assert destino is not None
    return destino


def _iniciar(db: Session, t: Tentativa, clientes: _Clientes) -> None:
    """Fase `iniciando`. Sem `init_enviado_em`, o init nunca saiu: é seguro chamá-lo. Com ele e
    sem `publish_id`, não dá para saber se a rede criou algo: `incerta` (R8)."""
    agora = _agora()
    if t.init_enviado_em is not None:
        _concluir(db, _destino(db, t), t, TentativaFase.incerta, SEM_RESPOSTA,
                  codigo="sem_resposta_no_init")
        db.commit()
        return
    if not pode_enviar(db) or (t.proxima_em is not None and t.proxima_em > agora):
        return
    conexao = db.get(Conexao, t.conexao_id, populate_existing=True)
    if conexao is None or conexao.estado != ConexaoEstado.conectada:
        _devolver(db, _destino(db, t), t, TentativaFase.recusada, SEM_CONEXAO,
                  codigo="conta_nao_conectada")
        db.commit()
        return
    if t.modo == Modo.criar_rascunho:
        ocupadas, proxima = limites.vagas_rascunho(db, t.conexao_id, agora)
        if ocupadas >= limites.RASCUNHOS_24H:
            _devolver(db, _destino(db, t), t, TentativaFase.sem_vaga, SEM_VAGA_LOCAL,
                      codigo="limite_local", proxima_em=proxima)
            db.commit()
            return
    executor = _executor(t)
    ctx = _ctx(t, clientes.para(executor))
    try:
        ctx.token()  # antes do init: sem conexão, nada foi criado
    except ConexaoPerdida:
        _devolver(db, _destino(db, t), t, TentativaFase.recusada, SEM_CONEXAO,
                  codigo="conexao_perdida")
        db.commit()
        return
    except ConexaoIndisponivel:
        t.proxima_em = agora + ADIAR
        db.commit()
        return
    snapshot = _destino(db, t).envio_snapshot
    if t.modo == Modo.publicar and not _revalidar(db, t, executor, ctx, snapshot):
        return
    if not limites.consumir(t.conexao_id, "init"):
        t.proxima_em = agora + ADIAR
        db.commit()
        return

    t.init_enviado_em = _agora()
    t.proxima_em = None
    db.commit()  # R8: gravado ANTES do init
    try:
        resultado = executor.iniciar(ctx, t, snapshot)
    except ConexaoIndisponivel as e:
        if e.status is None:
            # O pedido não chegou à rede (conexão recusada): nada criado, o init pode sair de
            # novo na próxima volta.
            t.init_enviado_em = None
            t.proxima_em = _agora() + ADIAR
            db.commit()
            return
        # 5xx: a rede recebeu o pedido e falhou no meio; não dá para saber se criou.
        _concluir(db, _destino(db, t), t, TentativaFase.incerta, SEM_RESPOSTA,
                  codigo=f"http_{e.status}")
        db.commit()
        return
    except (SemResposta, ConexaoPerdida):
        # Saiu e não voltou (ou o token caiu no meio): pode ter criado. Nunca repetir.
        _concluir(db, _destino(db, t), t, TentativaFase.incerta, SEM_RESPOSTA,
                  codigo="sem_resposta_no_init")
        db.commit()
        return
    if isinstance(resultado, Iniciado):
        dados, _ = cifra.cifrar(resultado.upload_url, cifra.aad(t.id, "upload"))
        t.publish_id = resultado.publish_id
        t.upload_url_cifrado = dados
        t.upload_url_expira_em = t.init_enviado_em + LINK_VALE
        t.fase = TentativaFase.enviando_partes
        db.commit()  # R8: antes do primeiro PUT
        _enviar_partes(db, t, clientes)
    elif isinstance(resultado, SemVaga):
        motivo = Motivo(resultado.motivo, Acao.esperar) if resultado.motivo else SEM_VAGA_LOCAL
        _devolver(db, _destino(db, t), t, TentativaFase.sem_vaga, motivo,
                  codigo=resultado.codigo,
                  proxima_em=resultado.proxima_em or _agora() + timedelta(hours=1))
        db.commit()
    elif resultado.adiar_s:
        # Taxa da rede: ela respondeu que não criou nada; adia sem gastar a tentativa.
        t.init_enviado_em = None
        t.proxima_em = _agora() + timedelta(seconds=resultado.adiar_s)
        _details(t, adiadoPor=resultado.codigo)
        db.commit()
    else:
        _concluir(db, _destino(db, t), t, TentativaFase.recusada, _motivo(resultado),
                  codigo=resultado.codigo)
        db.commit()


def _duracao_s(db: Session, destino_id: uuid.UUID) -> float | None:
    ms = db.scalar(consulta.destinos_do_conteudo().with_only_columns(consulta.duration_ms())
                   .where(Postagem.id == destino_id))
    return ms / 1000 if ms else None


def _revalidar(db: Session, t: Tentativa, executor: ExecutorRede, ctx: Contexto,
               snapshot: dict[str, Any] | None) -> bool:
    """Publicar (R13): no horário, consulta o `creator_info` de novo e confere o snapshot que o
    dono confirmou (privacidade nas opções da conta, toggles que a conta desligou, duração
    máxima, "pode postar"). Um problema recusa **sem trocar a escolha do humano**; nada é
    criado na rede. False = a tentativa não segue nesta volta."""
    if not snapshot or not snapshot.get("opcoes"):
        _concluir(db, _destino(db, t), t, TentativaFase.recusada, SEM_SNAPSHOT,
                  codigo="sem_snapshot")
        db.commit()
        return False
    if not limites.consumir(t.conexao_id, "creator_info"):
        t.proxima_em = _agora() + ADIAR
        db.commit()
        return False
    try:
        criador = executor.consultar_criador(ctx)
    except ConexaoPerdida:
        _devolver(db, _destino(db, t), t, TentativaFase.recusada, SEM_CONEXAO,
                  codigo="conexao_perdida")
        db.commit()
        return False
    except RecusaRede as e:
        _concluir(db, _destino(db, t), t, TentativaFase.recusada, executor.traduzir(e.codigo),
                  codigo=e.codigo)
        db.commit()
        return False
    except RedeErro:  # fora do ar ou sem resposta: é só leitura, tenta na próxima volta
        t.proxima_em = _agora() + ADIAR
        db.commit()
        return False
    problemas = list(executor.validar_opcoes(snapshot["opcoes"], criador,
                                             _duracao_s(db, t.destino_id)))
    if problemas:
        motivo = Motivo("; ".join(p.mensagem for p in problemas)
                        + ". Reagende e escolha de novo", Acao.reagendar)
        _details(t, problemas=[{"campo": p.campo, "motivo": p.mensagem} for p in problemas])
        _concluir(db, _destino(db, t), t, TentativaFase.recusada, motivo,
                  codigo="opcoes_mudaram")
        db.commit()
        return False
    return True


def _enviar_partes(db: Session, t: Tentativa, clientes: _Clientes) -> None:
    """Fase `enviando_partes`: do MinIO (HD) para o `upload_url`, parte a parte, com commit
    depois de cada uma. Para, sem mudar nada, se o interruptor desligar no meio."""
    if t.upload_url_expira_em is None or t.upload_url_expira_em <= _agora() \
            or t.upload_url_cifrado is None:
        pausado = (t.details or {}).get("pausadoEm") is not None
        _concluir(db, _destino(db, t), t, TentativaFase.recusada,
                  LINK_EXPIRADO_INTERRUPTOR if pausado else LINK_EXPIRADO,
                  codigo="upload_url_expirou")
        db.commit()
        return
    executor = _executor(t)
    ctx = _ctx(t, clientes.para(executor))
    upload_url = cifra.decifrar(t.upload_url_cifrado, cifra.aad(t.id, "upload"))
    hasher = hashlib.sha256() if t.partes_enviadas == 0 else None
    while t.partes_enviadas < t.total_partes:
        if not pode_enviar(db):
            _details(t, pausadoEm=_agora().isoformat())
            db.commit()
            log.info("publicacao: interruptor desligado; tentativa %s parada na parte %d/%d",
                     t.id, t.partes_enviadas, t.total_partes)
            return
        video = _stat(t.video_ref)
        if video is None or video[0] != t.video_etag:
            _concluir(db, _destino(db, t), t, TentativaFase.recusada, VIDEO_MUDOU,
                      codigo="video_mudou")
            db.commit()
            return
        indice = t.partes_enviadas
        inicio, tamanho = faixa(t, indice)
        dados = _ler(t.video_ref, inicio, tamanho)
        try:
            recusa = executor.enviar_parte(ctx, t, upload_url, indice, inicio, dados)
        except RedeErro:
            # O PUT de uma parte é repetível: a próxima volta reenvia esta parte inteira.
            log.warning("publicacao: parte %d da tentativa %s sem resposta; próxima volta",
                        indice + 1, t.id)
            return
        if recusa is not None:
            _concluir(db, _destino(db, t), t, TentativaFase.recusada, _motivo(recusa),
                      codigo=recusa.codigo)
            db.commit()
            return
        if hasher is not None:
            hasher.update(dados)
        t.partes_enviadas = indice + 1
        db.commit()
    t.video_sha256 = hasher.hexdigest() if hasher is not None else _sha256(t)
    t.fase = TentativaFase.processando
    t.upload_url_cifrado = None
    t.proxima_em = _agora() + STATUS_PRIMEIRO
    _details(t, uploadConcluidoEm=_agora().isoformat(), consultas=0)
    db.commit()


def _consultar(db: Session, t: Tentativa, clientes: _Clientes) -> None:
    """Fase `processando`: `status/fetch` até um estado final (é leitura: roda mesmo com o
    botão desligado). Sem final em 2 h depois do upload → `incerta`."""
    agora = _agora()
    if t.proxima_em is not None and t.proxima_em > agora:
        return
    fim = (t.details or {}).get("uploadConcluidoEm")
    fim_dt = datetime.fromisoformat(fim) if fim else (t.init_enviado_em or agora)
    if agora - fim_dt > STATUS_PRAZO:
        _concluir(db, _destino(db, t), t, TentativaFase.incerta, SEM_CONFIRMACAO,
                  codigo="status_sem_final")
        db.commit()
        return
    if not limites.consumir(t.conexao_id, "status"):
        t.proxima_em = agora + ADIAR
        db.commit()
        return
    executor = _executor(t)
    ctx = _ctx(t, clientes.para(executor))
    consultas = int((t.details or {}).get("consultas", 0)) + 1
    _details(t, consultas=consultas)
    try:
        resultado = executor.consultar(ctx, t)
    except RedeErro as e:
        t.proxima_em = _agora() + STATUS_MAX
        _details(t, ultimoErro=type(e).__name__)
        db.commit()
        return
    if isinstance(resultado, EmAndamento):
        t.status_rede = resultado.status
        t.proxima_em = _agora() + min(STATUS_PRIMEIRO * 2 ** min(consultas - 1, 3), STATUS_MAX)
        db.commit()
        return
    destino = _destino(db, t)
    if isinstance(resultado, Entregue):
        t.status_rede = resultado.status
        _concluir(db, destino, t, TentativaFase.entregue)
    elif isinstance(resultado, Publicado):
        t.status_rede = resultado.status
        _concluir(db, destino, t, TentativaFase.publicada, post_id=resultado.post_id)
    else:
        t.status_rede = "FAILED"
        _concluir(db, destino, t, TentativaFase.recusada, _motivo(resultado),
                  codigo=resultado.codigo)
    db.commit()


def _avancar(db: Session, t: Tentativa, clientes: _Clientes) -> None:
    if t.fase == TentativaFase.iniciando:
        _iniciar(db, t, clientes)
    elif t.fase == TentativaFase.enviando_partes:
        if pode_enviar(db):
            _enviar_partes(db, t, clientes)
    elif t.fase == TentativaFase.processando:
        _consultar(db, t, clientes)


def _abertas(db: Session) -> list[uuid.UUID]:
    return list(db.scalars(
        select(Tentativa.id).where(Tentativa.fase.in_(ABERTAS))
        .order_by(Tentativa.iniciada_em, Tentativa.id)
    ))


# ---- volta ----

def rodar(db: Session, client: Any = None) -> int:
    """Uma volta da trilha; devolve quantas tentativas avançou ou criou. `client` injeta o
    cliente HTTP da rede (testes com a TikTok falsa); None = o cliente padrão do executor."""
    if not servidor_habilitado():
        return 0  # o agendador já deixa a trilha ociosa; defesa redundante (princípio I)
    clientes = _Clientes(client)
    feitos = 0
    try:
        for tid in _abertas(db):
            t = db.get(Tentativa, tid, populate_existing=True)
            if t is not None and t.fase in ABERTAS:
                _avancar(db, t, clientes)
                feitos += 1
        if botao_ligado(db):
            for t in _reivindicar(db, _agora()):
                _avancar(db, t, clientes)
                feitos += 1
        _avisos_por_hora(db)
    finally:
        clientes.fechar()
    return feitos


def _avisos_por_hora(db: Session) -> None:
    agora = _agora()
    ultimo = _ultimos_avisos.get("vencimentos")
    if ultimo is not None and agora - ultimo < AVISOS_A_CADA:
        return
    _ultimos_avisos["vencimentos"] = agora
    conexoes.avisar_vencimentos(db)
    db.commit()
