"""Conexão de uma conta com a rede (research R1 a R5 e R14 da spec 015).

- `iniciar`: escolhe o endereço de retorno pelo `Host` (Web pelo IP da casa, Desktop com PKCE em
  `localhost`), guarda o `state` no Redis (10 min, uso único, preso ao dono) e devolve a URL
  de autorização;
- `concluir_retorno`: `GETDEL` do `state`, troca do código, escopos, identidade (o @ autorizado
  tem de ser o @ cadastrado, e o `open_id` o da conexão anterior), tokens cifrados em
  `conexao_credenciais`, avatar no MinIO e histórico. Qualquer recusa depois da troca **revoga**
  o token na rede e não grava nada;
- `desconectar`: revoga em melhor esforço, **apaga** a credencial e grava a versão;
- `token_valido`: a única leitura das credenciais, numa sessão própria, com `SELECT … FOR
  UPDATE` e renovação com rotação do refresh (R5);
- `avisar_vencimentos`: aviso de 30 dias antes de o refresh vencer, uma vez por ciclo.

Tokens, código, verifier e `state` nunca vão para log, histórico, evento ou resposta.
"""

import json
import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history, imaging, storage
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.conteudos import capacidades
from sociman_api.conteudos.models import Modo
from sociman_api.db import get_sessionmaker
from sociman_api.errors import ApiError
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo
from sociman_api.perfis.models import Conta, ContaStatus, Platform
from sociman_api.perfis.platforms import normalize_handle
from sociman_api.perfis.service_perfis import user_refs
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao import cifra, registro, schemas
from sociman_api.publicacao.executor import (
    ConexaoIndisponivel,
    ConexaoPerdida,
    RecusaRede,
    RedeErro,
    SemResposta,
)
from sociman_api.publicacao.models import Conexao, ConexaoCredencial, ConexaoEstado
from sociman_api.redis import get_redis

log = logging.getLogger("sociman.publicacao.conexoes")

ENTITY = "conexao"
SISTEMA = Actor(kind="system:publicacao")
STATE_TTL = timedelta(minutes=10)
STATE_KEY = "conexao:state:{}"
MARGEM_RENOVACAO = timedelta(minutes=5)
AVISO_VENCIMENTO = timedelta(days=30)
ESCOPO_OBRIGATORIO = "video.upload"
ESCOPO_PUBLICAR = "video.publish"
AVATAR_MAX = 1024 * 1024
LOCALHOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
REDE = Platform.tiktok  # a 015 só conecta TikTok

CONTA_NAO_ENCONTRADA = "Conta não encontrada"
NAO_CONFIGURADA = ("A publicação não está configurada no servidor (app da TikTok ou chave dos "
                   "tokens)")
STATE_INVALIDO = "O pedido de conexão expirou; clique em Conectar de novo"
MOTIVO_REFRESH = "A autorização da TikTok venceu ou foi revogada"


def _executor(platform: Platform):
    executor = registro.executor_para(platform)
    if executor is None:
        raise ApiError(400, "conta_invalida", "Esta rede não se conecta ao SociMan")
    return executor


# ---- consultas ----

def conexao_viva(db: Session, conta_id: uuid.UUID, lock: bool = False) -> Conexao | None:
    """A conexão não desconectada da conta (no máximo uma, `uq_conexoes_conta_viva`)."""
    stmt = select(Conexao).where(Conexao.conta_id == conta_id,
                                 Conexao.estado != ConexaoEstado.desconectada)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def conexoes_vivas(db: Session, conta_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Conexao]:
    """As conexões vivas de várias contas numa consulta só (sem N+1)."""
    ids = list(dict.fromkeys(conta_ids))
    if not ids:
        return {}
    rows = db.scalars(select(Conexao).where(Conexao.conta_id.in_(ids),
                                            Conexao.estado != ConexaoEstado.desconectada))
    return {c.conta_id: c for c in rows}


def estado_publico(conexao: Conexao | None) -> str:
    """`ContaRef.conexao` / `Conexao.estado`: `nao_conectada` sem conexão viva."""
    if conexao is None or conexao.estado == ConexaoEstado.desconectada:
        return "nao_conectada"
    return conexao.estado.value


def _ultima(db: Session, conta_id: uuid.UUID) -> Conexao | None:
    return db.scalar(select(Conexao).where(Conexao.conta_id == conta_id)
                     .order_by(Conexao.conectado_em.desc()).limit(1))


def conexao_out(db: Session, conta: Conta, conexao: Conexao | None) -> schemas.Conexao:
    viva = conexao if conexao is not None and conexao.estado != ConexaoEstado.desconectada \
        else None
    modos = [schemas.ModoInfo(modo=m.modo, disponivel=m.disponivel, motivo=m.motivo,
                              aviso=m.aviso)
             for m in capacidades.modos_da_conta(conta, viva)]
    if viva is None:
        return schemas.Conexao(
            conta_id=conta.id, rede=conta.platform, estado="nao_conectada", username=None,
            display_name=None, avatar_url=None, escopos=[], conectado_por=None,
            conectado_em=None, motivo=None, refresh_expira_em=None, modos=modos, version=None)
    users = user_refs(db, [viva.conectado_por])
    avatar = imaging.image_urls(viva.avatar_key)["medium"] if viva.avatar_key else None
    return schemas.Conexao(
        conta_id=conta.id, rede=viva.rede, estado=viva.estado.value, username=viva.username,
        display_name=viva.display_name, avatar_url=avatar, escopos=list(viva.escopos),
        conectado_por=users.get(viva.conectado_por), conectado_em=viva.conectado_em,
        motivo=viva.motivo, refresh_expira_em=viva.refresh_expira_em, modos=modos,
        version=viva.version)


def get_conta_or_404(db: Session, conta_id: uuid.UUID, lock: bool = False) -> Conta:
    conta = db.get(Conta, conta_id, with_for_update=lock)
    if conta is None:
        raise ApiError(404, "not_found", CONTA_NAO_ENCONTRADA)
    return conta


def _conta_valida(db: Session, conta_id: uuid.UUID, lock: bool = False) -> Conta:
    conta = get_conta_or_404(db, conta_id, lock)
    if conta.platform != REDE:
        raise ApiError(400, "conta_invalida", "Só contas TikTok se conectam por enquanto")
    if conta.archived:
        raise ApiError(400, "conta_invalida", "Conta arquivada")
    if conta.status == ContaStatus.encerrada:
        raise ApiError(400, "conta_invalida", "Conta encerrada")
    return conta


def versions(db: Session, conta_id: uuid.UUID) -> list[history.EntityVersion]:
    """Histórico de todas as conexões da conta (a mais recente primeiro)."""
    get_conta_or_404(db, conta_id)
    ids = list(db.scalars(select(Conexao.id).where(Conexao.conta_id == conta_id)))
    if not ids:
        return []
    return list(db.scalars(
        select(history.EntityVersion)
        .where(history.EntityVersion.entity_type == ENTITY,
               history.EntityVersion.entity_id.in_(ids))
        .order_by(history.EntityVersion.occurred_at.desc(), history.EntityVersion.id.desc())))


# ---- configuração ----

def app_configurado() -> bool:
    s = get_settings()
    return bool(s.tiktok_client_key.get_secret_value() and
                s.tiktok_client_secret.get_secret_value())


def enderecos_login() -> dict[str, str | None]:
    s = get_settings()
    return {"web": s.tiktok_redirect_web.strip() or None,
            "desktop": s.tiktok_redirect_desktop.strip() or None}


def _exigir_configurado() -> None:
    enderecos = enderecos_login()
    if not app_configurado() or not cifra.chave_configurada() or \
            not (enderecos["web"] or enderecos["desktop"]):
        raise ApiError(503, "publicacao_nao_configurada", NAO_CONFIGURADA)


def _origem(url: str) -> str:
    partes = urlsplit(url)
    return f"{partes.scheme}://{partes.netloc}"


def escolher_endereco(host: str | None) -> tuple[str, str]:
    """(`web` | `desktop`, redirect_uri) pelo host que o edge repassou (R1).

    `localhost` → Desktop (PKCE); qualquer outro host → Web. O host tem de ser o do endereço
    configurado: o navegador volta para lá, e a sessão do SPA precisa ser a mesma. Senão 409
    `endereco_de_login` com o endereço onde abrir o SociMan.
    """
    enderecos = enderecos_login()
    host = (host or "").strip().lower().strip("[]")
    for plataforma in ("web", "desktop"):
        url = enderecos[plataforma]
        if url and (urlsplit(url).hostname or "").lower() == host:
            return plataforma, url
    preferida = "desktop" if host in LOCALHOSTS else "web"
    outra = enderecos["web"] if preferida == "desktop" else enderecos["desktop"]
    alvo = enderecos[preferida] or outra
    abrir = _origem(alvo) if alvo else None
    raise ApiError(409, "endereco_de_login",
                   f"Para conectar, abra o SociMan em {abrir}" if abrir
                   else "Nenhum endereço de login configurado",
                   details={"abrirEm": abrir})


# ---- iniciar ----

def iniciar(db: Session, actor: Actor, conta_id: uuid.UUID, host: str | None
            ) -> schemas.IniciarOut:
    conta = _conta_valida(db, conta_id)
    viva = conexao_viva(db, conta.id)
    if viva is not None and viva.estado == ConexaoEstado.conectada:
        raise ApiError(409, "ja_conectada", "Esta conta já está conectada")
    _exigir_configurado()
    plataforma, redirect_uri = escolher_endereco(host)
    oauth = _executor(conta.platform).oauth
    state = oauth.novo_state()
    verifier = oauth.novo_code_verifier() if plataforma == "desktop" else None
    valor = {"userId": str(actor.user_id), "contaId": str(conta.id), "plataforma": plataforma,
             "redirectUri": redirect_uri, "codeVerifier": verifier}
    get_redis().set(STATE_KEY.format(state), json.dumps(valor),
                    ex=int(STATE_TTL.total_seconds()))
    url = oauth.url_autorizacao(state, redirect_uri, verifier)
    return schemas.IniciarOut(autorizar_url=url, expira_em=datetime.now(UTC) + STATE_TTL)


# ---- retorno ----

def _ler_state(actor: Actor, state: str) -> dict[str, Any]:
    bruto = get_redis().getdel(STATE_KEY.format(state))
    if not bruto:
        raise ApiError(400, "state_invalido", STATE_INVALIDO)
    try:
        valor = json.loads(bruto)
    except ValueError:
        raise ApiError(400, "state_invalido", STATE_INVALIDO) from None
    if valor.get("userId") != str(actor.user_id):
        raise ApiError(400, "state_invalido", STATE_INVALIDO)
    return valor


def _revogar(client: Any, access_token: str) -> None:
    """Melhor esforço: falha de rede não impede a recusa nem o desconectar."""
    try:
        _executor(REDE).oauth.revogar(client, access_token)
    except RedeErro as e:
        log.warning("revogação falhou (%s)", type(e).__name__)


def _validades(tokens: Any, agora: datetime) -> tuple[datetime, datetime]:
    return (agora + timedelta(seconds=tokens.expira_em_s),
            agora + timedelta(seconds=tokens.refresh_expira_em_s))


def _gravar_credencial(db: Session, conexao: Conexao, tokens: Any,
                       agora: datetime) -> None:
    access, key_id = cifra.cifrar(tokens.access_token, cifra.aad(conexao.id, "access"))
    refresh, _ = cifra.cifrar(tokens.refresh_token, cifra.aad(conexao.id, "refresh"))
    cred = db.get(ConexaoCredencial, conexao.id)
    if cred is None:
        cred = ConexaoCredencial(conexao_id=conexao.id, renovacoes=0)
        db.add(cred)
    access_expira, refresh_expira = _validades(tokens, agora)
    cred.key_id = key_id
    cred.access_cifrado = access
    cred.access_expira_em = access_expira
    cred.refresh_cifrado = refresh
    cred.refresh_expira_em = refresh_expira
    conexao.refresh_expira_em = refresh_expira


def gravar_avatar(conexao: Conexao, client: Any, url: str | None) -> None:
    """Baixa o avatar da CDN (cliente), valida pelo conteúdo e guarda no bucket `imagens`
    (R14). Mesma imagem → não regrava. Falha → fica o avatar anterior (melhor esforço)."""
    if not url:
        return
    try:
        dados, _tipo = client.get_avatar(url)
        info = imaging.validate_image(dados, "imagem", max_bytes=AVATAR_MAX)
        key = f"conexoes/{conexao.id}/avatar-{info.sha256[:8]}.{info.ext}"
        if key != conexao.avatar_key:
            storage.put(key, dados, info.content_type)
            conexao.avatar_key = key
    except Exception as e:  # noqa: BLE001 — rede, imagem ou MinIO/HD: o avatar é informativo
        log.warning("avatar da conexão %s não gravado (%s)", conexao.id, type(e).__name__)


def _identidade(client: Any, oauth: Any, access_token: str) -> tuple[str, str | None, str,
                                                                     str | None]:
    """(open_id, username, display_name, avatar_url). Sem `username` no `user/info`, cai para o
    `creator_info` (exige `video.publish`)."""
    ident = oauth.identidade(client, access_token)
    username, display, avatar = ident.username, ident.display_name, ident.avatar_url
    if username is None:
        try:
            criador = oauth.consultar_criador(client, access_token)
        except RecusaRede:
            criador = {}
        username = str(criador.get("creator_username") or "").strip().lstrip("@") or None
        display = display or str(criador.get("creator_nickname") or "")
        avatar = avatar or criador.get("creator_avatar_url") or None
    return ident.open_id, username, display, avatar


def concluir_retorno(db: Session, actor: Actor, body: schemas.RetornoIn, client: Any
                     ) -> tuple[Conexao, Conta]:
    valor = _ler_state(actor, body.state)
    conta = _conta_valida(db, uuid.UUID(valor["contaId"]), lock=True)
    if body.error or not body.code:
        raise ApiError(409, "autorizacao_negada",
                       "A autorização foi cancelada na TikTok; nada foi conectado")
    _exigir_configurado()
    oauth = _executor(conta.platform).oauth
    try:
        tokens = oauth.trocar_codigo(client, body.code, valor["redirectUri"],
                                     valor.get("codeVerifier"))
    except (RecusaRede, ConexaoPerdida):
        raise ApiError(409, "autorizacao_negada",
                       "A TikTok recusou a autorização; clique em Conectar de novo") from None
    except (ConexaoIndisponivel, SemResposta):
        raise ApiError(502, "rede_indisponivel",
                       "A TikTok não respondeu; tente de novo em instantes") from None

    # Daqui em diante, qualquer recusa revoga o token recém-emitido e não grava nada.
    try:
        conexao = _validar_e_gravar(db, actor, conta, tokens, client, oauth)
    except ApiError:
        _revogar(client, tokens.access_token)
        raise
    except (ConexaoIndisponivel, SemResposta):
        _revogar(client, tokens.access_token)
        raise ApiError(502, "rede_indisponivel",
                       "A TikTok não respondeu; tente de novo em instantes") from None
    except RedeErro:
        _revogar(client, tokens.access_token)
        raise ApiError(409, "identidade_indisponivel",
                       "A TikTok não informou qual conta autorizou; nada foi conectado") \
            from None
    return conexao, conta


def _validar_e_gravar(db: Session, actor: Actor, conta: Conta, tokens: Any, client: Any,
                      oauth: Any) -> Conexao:
    faltando = [e for e in (ESCOPO_OBRIGATORIO,) if e not in tokens.escopos]
    if faltando:
        raise ApiError(409, "escopo_faltando",
                       "Marque todas as permissões ao autorizar na TikTok",
                       details={"faltando": faltando})

    open_id, username, display, avatar = _identidade(client, oauth, tokens.access_token)
    open_id = open_id or tokens.open_id
    if not username or not open_id:
        raise ApiError(409, "identidade_indisponivel",
                       "A TikTok não informou qual conta autorizou; nada foi conectado")
    if normalize_handle(username) != normalize_handle(conta.handle):
        raise _conta_diferente(username, conta.handle)

    anterior = _ultima(db, conta.id)
    if anterior is not None and anterior.open_id != open_id:
        raise _conta_diferente(username, conta.handle)
    viva = conexao_viva(db, conta.id, lock=True)
    if viva is not None and viva.estado == ConexaoEstado.conectada:
        raise ApiError(409, "ja_conectada", "Esta conta já está conectada")
    outra = db.scalar(select(Conexao.id).where(
        Conexao.rede == conta.platform, Conexao.open_id == open_id,
        Conexao.estado != ConexaoEstado.desconectada, Conexao.conta_id != conta.id))
    if outra is not None:
        raise _em_uso()

    agora = datetime.now(UTC)
    if viva is not None:  # precisa_reconectar → reusa a linha (mesmo open_id, R3)
        conexao, before, acao, action = viva, history.snapshot(viva), "reconectada", "updated"
    else:
        conexao = Conexao(id=uuid.uuid4(), conta_id=conta.id, rede=conta.platform,
                          open_id=open_id, created_by=actor.user_id)
        before, acao, action = None, "conectada", "created"
        db.add(conexao)
    conexao.username = normalize_handle(username)
    conexao.display_name = display or ""
    conexao.escopos = list(tokens.escopos)
    conexao.estado = ConexaoEstado.conectada
    conexao.motivo = None
    conexao.conectado_por = actor.user_id
    conexao.conectado_em = agora
    conexao.avisado_vencimento_em = None
    conexao.updated_by = actor.user_id
    try:
        db.flush()
    except IntegrityError:  # corrida: outra conta ligou o mesmo open_id
        db.rollback()
        raise _em_uso() from None
    _gravar_credencial(db, conexao, tokens, agora)
    gravar_avatar(conexao, client, avatar)
    history.record(db, actor, ENTITY, conexao, action, before, history.snapshot(conexao),
                   {"acao": acao})
    db.flush()
    return conexao


def _conta_diferente(autorizado: str, esperado: str) -> ApiError:
    autorizado, esperado = normalize_handle(autorizado), normalize_handle(esperado)
    return ApiError(
        409, "conta_diferente",
        f"Você entrou como @{autorizado}, mas esta conta é @{esperado}. Saia da TikTok no "
        f"navegador e entre com @{esperado}",
        details={"autorizado": autorizado, "esperado": esperado})


def _em_uso() -> ApiError:
    return ApiError(409, "conexao_em_uso",
                    "Esta conta da TikTok já está conectada a outra conta do SociMan")


# ---- desconectar ----

def _destinos_automaticos(db: Session, conta_id: uuid.UUID, estado: DestinoEstado) -> int:
    return db.scalar(select(func.count()).select_from(Postagem).where(
        Postagem.conta_id == conta_id, Postagem.estado == estado,
        Postagem.modo != Modo.lembrete, Postagem.archived_at.is_(None))) or 0


def desconectar(db: Session, actor: Actor, conta_id: uuid.UUID, version: int, client: Any
                ) -> tuple[Conta, int]:
    """Devolve a conta e quantos destinos automáticos agendados ficaram em atenção."""
    conta = get_conta_or_404(db, conta_id, lock=True)
    conexao = conexao_viva(db, conta.id, lock=True)
    if conexao is None:
        raise ApiError(409, "conta_nao_conectada", "Esta conta não está conectada")
    history.check_version(conexao, version, "Esta conexão")
    if _destinos_automaticos(db, conta.id, DestinoEstado.enviando):
        raise ApiError(409, "envio_em_andamento",
                       "Há um envio em andamento para esta conta; espere terminar")
    cred = db.get(ConexaoCredencial, conexao.id, with_for_update=True)
    if cred is not None:
        try:
            access = cifra.decifrar(cred.access_cifrado, cifra.aad(conexao.id, "access"),
                                    cred.key_id)
        except cifra.CifraErro as e:
            log.warning("credencial da conexão %s ilegível (%s)", conexao.id, type(e).__name__)
        else:
            _revogar(client, access)
        db.delete(cred)  # a única exclusão física da 015: segredo, não domínio
    before = history.snapshot(conexao)
    agora = datetime.now(UTC)
    conexao.estado = ConexaoEstado.desconectada
    conexao.desconectado_por = actor.user_id
    conexao.desconectado_em = agora
    conexao.updated_by = actor.user_id
    history.record(db, actor, ENTITY, conexao, "updated", before, history.snapshot(conexao),
                   {"acao": "desconectada"})
    em_atencao = _destinos_automaticos(db, conta.id, DestinoEstado.agendado)
    db.flush()
    return conta, em_atencao


# ---- renovação (R5) ----

def _marcar_precisa_reconectar(db: Session, conexao: Conexao, motivo: str) -> None:
    """Na transação de quem chama: estado, versão (`system:publicacao`), credencial apagada e
    aviso aos donos (um por dia)."""
    cred = db.get(ConexaoCredencial, conexao.id)
    if cred is not None:
        db.delete(cred)
    if conexao.estado == ConexaoEstado.precisa_reconectar:
        return
    before = history.snapshot(conexao)
    conexao.estado = ConexaoEstado.precisa_reconectar
    conexao.motivo = motivo
    history.record(db, SISTEMA, ENTITY, conexao, "updated", before, history.snapshot(conexao),
                   {"acao": "precisa_reconectar"})
    _avisar(db, conexao, "precisa_reconectar", f"Reconecte @{conexao.username} na TikTok",
            motivo)


def _avisar(db: Session, conexao: Conexao, estado: str, titulo: str, corpo: str,
            agora: datetime | None = None) -> None:
    conta = db.get(Conta, conexao.conta_id)
    dia = (agora or datetime.now(UTC)).date().isoformat()
    notificacoes.criar(
        db, NotificacaoTipo.conexao_precisa_reconectar, titulo, corpo,
        f"/app/perfis/{conta.perfil_id}" if conta is not None else "/app/perfis",
        ("conexao", conexao.id), f"conexao:{conexao.id}:{estado}:{dia}",
        notificacoes.donos_ativos(db))


def token_valido(conexao_id: uuid.UUID, client: Any = None) -> str:
    """O access token válido da conexão (renova se faltar menos de 5 min).

    Sessão própria e curta, com `FOR UPDATE` na credencial: a API e o agendador podem renovar
    ao mesmo tempo, e o segundo espera, relê e encontra o token novo (a TikTok rotaciona o
    refresh). O commit sai logo depois da renovação. `ConexaoPerdida` quando o refresh não vale
    mais (a conexão vira `precisa_reconectar`); `ConexaoIndisponivel` em erro de rede ou 5xx
    (nada muda).
    """
    session = get_sessionmaker()()
    fechar = client is None
    client = client or _executor(REDE).novo_cliente()
    try:
        conexao = session.get(Conexao, conexao_id)
        if conexao is None or conexao.estado != ConexaoEstado.conectada:
            raise ConexaoPerdida("conexão não está conectada")
        cred = session.get(ConexaoCredencial, conexao_id, with_for_update=True)
        if cred is None:
            raise ConexaoPerdida("conexão sem credencial")
        agora = datetime.now(UTC)
        try:
            if cred.access_expira_em - agora > MARGEM_RENOVACAO:
                token = cifra.decifrar(cred.access_cifrado, cifra.aad(conexao_id, "access"),
                                       cred.key_id)
                session.commit()
                return token
            refresh = cifra.decifrar(cred.refresh_cifrado, cifra.aad(conexao_id, "refresh"),
                                     cred.key_id)
        except (cifra.ChaveDesconhecida, cifra.DecifraFalhou):
            # Chave perdida ou trocada sem a anterior: os tokens não decifram mais.
            session.refresh(conexao, with_for_update=True)
            _marcar_precisa_reconectar(session, conexao,
                                       "A chave dos tokens mudou; conecte a conta de novo")
            session.commit()
            raise ConexaoPerdida("credencial ilegível") from None
        try:
            tokens = _executor(conexao.rede).oauth.renovar(client, refresh)
        except ConexaoPerdida:
            session.refresh(conexao, with_for_update=True)
            _marcar_precisa_reconectar(session, conexao, MOTIVO_REFRESH)
            session.commit()
            raise
        except RecusaRede as e:
            if e.codigo in ("invalid_grant", "invalid_request", "access_token_invalid"):
                session.refresh(conexao, with_for_update=True)
                _marcar_precisa_reconectar(session, conexao, MOTIVO_REFRESH)
                session.commit()
                raise ConexaoPerdida(MOTIVO_REFRESH) from None
            raise ConexaoIndisponivel(f"renovação recusada ({e.codigo})") from None
        except SemResposta:
            raise ConexaoIndisponivel("a TikTok não respondeu à renovação") from None
        _gravar_credencial(session, conexao, tokens, agora)
        cred.renovado_em = agora
        cred.renovacoes = (cred.renovacoes or 0) + 1
        session.commit()
        return tokens.access_token
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
        if fechar:
            client.close()


def avisar_vencimentos(db: Session, agora: datetime | None = None) -> int:
    """Um aviso por conexão quando faltam 30 dias para o refresh vencer, uma vez por ciclo
    (`avisado_vencimento_em` anterior ao começo da janela do vencimento atual). Sem commit."""
    agora = agora or datetime.now(UTC)
    rows = db.scalars(select(Conexao).where(
        Conexao.estado == ConexaoEstado.conectada,
        Conexao.refresh_expira_em.is_not(None),
        Conexao.refresh_expira_em <= agora + AVISO_VENCIMENTO,
    ).with_for_update(skip_locked=True))
    n = 0
    for conexao in rows:
        janela = conexao.refresh_expira_em - AVISO_VENCIMENTO
        if conexao.avisado_vencimento_em is not None and conexao.avisado_vencimento_em >= janela:
            continue
        _avisar(db, conexao, "vencimento", f"Reconecte @{conexao.username} na TikTok",
                "A autorização da TikTok vence em 30 dias; reconecte a conta", agora)
        conexao.avisado_vencimento_em = agora
        n += 1
    return n


def conta_refs(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    """`ContaRef.conexao` de várias contas (T034): estado público por conta, numa consulta."""
    vivas = conexoes_vivas(db, ids)
    return {i: estado_publico(vivas.get(i)) for i in ids}

