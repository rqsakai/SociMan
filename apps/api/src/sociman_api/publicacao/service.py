"""Regras humanas da publicação (spec 015): quem pode, interruptor, tentar de novo, vencidos e a
tela obrigatória do Publicar.

- `exigir_humano_dono`: a versão de `RequireHumanOwner` para dentro dos services (research R15).
  As rotas da 014 continuam `RequireUser`/`RequireOwner`; quando o modo (pedido ou atual) não é
  `lembrete`, o service chama esta função antes de mudar qualquer coisa.
- `exigir_confirmacao_incerta`: a única conferência da Clarifications Q4, usada por tentar de
  novo, reagendar (individual e em lote) e agendar de novo.
- Interruptor (R11): `config_get`/`config_update` (o botão; o nível do servidor só é lido).
- `tentar_de_novo` e `confirmar_envio`: devolvem o destino à fila da trilha, sempre por um dono
  humano. A tentativa em si é criada pela trilha ao reivindicar (`disparo` vem da última versão).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from sociman_api import history, imaging
from sociman_api.auth.deps import (
    SOMENTE_DONO,
    SOMENTE_HUMANO,
    Actor,
    registrar_recusa,
)
from sociman_api.auth.models import UserRole
from sociman_api.config import get_settings
from sociman_api.conteudos.models import Modo
from sociman_api.errors import ApiError
from sociman_api.perfis.service_perfis import user_refs, versions_out
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao import cifra, conexoes, limites, registro, schemas
from sociman_api.publicacao.executor import (
    Acao,
    ConexaoIndisponivel,
    ConexaoPerdida,
    Contexto,
    RecusaRede,
    RedeErro,
)
from sociman_api.publicacao.models import (
    FASES_ABERTAS,
    ConexaoEstado,
    PublicacaoConfig,
    Tentativa,
    TentativaFase,
)

ENTITY_CONFIG = "publicacao_config"
# `entity_versions.entity_id` é uuid; o singleton `publicacao_config` (id = 1) usa este.
CONFIG_ENTITY_ID = uuid.UUID(int=1)
ENTITY_DESTINO = "postagem"
JANELA_VENCIDO = timedelta(hours=1)
DESTINO_NAO_ENCONTRADO = "Destino não encontrado"


def exigir_humano_dono(actor: Actor, rota: str, *, conta_id: uuid.UUID | None = None,
                       destino_id: uuid.UUID | None = None) -> None:
    """Não humano → 403 `somente_humano` + evento `publicacao_recusada`; membro → 403
    `somente_dono`. O evento vai numa sessão própria: a transação de quem chama não é tocada."""
    if actor.kind != "user":
        registrar_recusa(actor, rota, conta_id=conta_id, destino_id=destino_id)
        raise ApiError(403, "somente_humano", SOMENTE_HUMANO)
    if actor.user is None or actor.user.role != UserRole.dono:
        raise ApiError(403, "somente_dono", SOMENTE_DONO)


def exigir_confirmacao_incerta(destino: Postagem, confirmo: bool | None) -> None:
    """Clarifications Q4: um destino `falhou` com falha incerta só volta à fila com
    "Conferi no app e o rascunho não chegou"."""
    if destino.estado == DestinoEstado.falhou and destino.falha_incerta and not confirmo:
        raise ApiError(409, "confirmacao_necessaria",
                       "A TikTok pode ter recebido este envio. Confira no app e marque "
                       "\"Conferi no app e o rascunho não chegou\"")


# ---- interruptor (R11) ----

class _ConfigVersao:
    """Adaptador do singleton para o `history` (o `entity_id` do histórico é uuid)."""

    __versioned_fields__ = PublicacaoConfig.__versioned_fields__

    def __init__(self, cfg: PublicacaoConfig):
        self.id = CONFIG_ENTITY_ID
        self.version = cfg.version
        self.envios_habilitados = cfg.envios_habilitados


def _config(db: Session, lock: bool = False) -> PublicacaoConfig:
    cfg = db.get(PublicacaoConfig, 1, with_for_update=lock)
    if cfg is None:  # a migration insere a linha; só por segurança
        cfg = PublicacaoConfig(id=1, envios_habilitados=False, version=1)
        db.add(cfg)
        db.flush()
    return cfg


def envios_ligados(db: Session) -> bool:
    """Os dois níveis ligados: `PUBLICACAO_HABILITADA` **e** o botão da tela."""
    return get_settings().publicacao_habilitada and _config(db).envios_habilitados


def _sem_tentativa_aberta():
    return ~exists().where(Tentativa.destino_id == Postagem.id,
                           Tentativa.fase.in_(FASES_ABERTAS))


def filtro_vencidos(agora: datetime):
    """Destino automático `agendado` há mais de 1 h, sem confirmação e sem tentativa aberta."""
    return and_(
        Postagem.estado == DestinoEstado.agendado, Postagem.modo != Modo.lembrete,
        Postagem.archived_at.is_(None), Postagem.planned_at <= agora - JANELA_VENCIDO,
        or_(Postagem.envio_confirmado_em.is_(None),
            Postagem.envio_confirmado_em < Postagem.planned_at),
        _sem_tentativa_aberta(),
    )


def _contar(db: Session, *cond) -> int:
    return db.scalar(select(func.count()).select_from(Postagem).where(*cond)) or 0


def config_out(db: Session, cfg: PublicacaoConfig | None = None) -> schemas.PublicacaoConfig:
    cfg = cfg or _config(db)
    s = get_settings()
    agora = datetime.now(UTC)
    enderecos = conexoes.enderecos_login()
    return schemas.PublicacaoConfig(
        servidor_habilitado=s.publicacao_habilitada,
        envios_habilitados=cfg.envios_habilitados,
        tokens_configurados=cifra.chave_configurada(),
        app_configurado=conexoes.app_configurado(),
        situacao_app=s.tiktok_app_situacao,
        enderecos_login=schemas.EnderecosLogin(**enderecos),
        vencidos=_contar(db, filtro_vencidos(agora)),
        em_andamento=_contar(db, Postagem.estado == DestinoEstado.enviando,
                             Postagem.archived_at.is_(None)),
        version=cfg.version,
    )


def config_update(db: Session, actor: Actor, body: schemas.PublicacaoConfigIn
                  ) -> schemas.PublicacaoConfig:
    cfg = _config(db, lock=True)
    history.check_version(cfg, body.version, "Esta configuração")
    if cfg.envios_habilitados != body.envios_habilitados:
        alvo = _ConfigVersao(cfg)
        before = history.snapshot(alvo)
        cfg.envios_habilitados = alvo.envios_habilitados = body.envios_habilitados
        cfg.updated_by = actor.user_id
        history.record(db, actor, ENTITY_CONFIG, alvo, "updated", before,
                       history.snapshot(alvo),
                       {"acao": "ligado" if body.envios_habilitados else "desligado"})
        cfg.version = alvo.version
        db.flush()
    return config_out(db, cfg)


def config_versions(db: Session):
    return versions_out(db, ENTITY_CONFIG, CONFIG_ENTITY_ID)


# ---- destinos: tentar de novo, confirmar envio, tentativas ----

def _destino(db: Session, destino_id: uuid.UUID, lock: bool = False) -> Postagem:
    destino = db.get(Postagem, destino_id, with_for_update=lock)
    if destino is None:
        raise ApiError(404, "not_found", DESTINO_NAO_ENCONTRADO)
    return destino


def tentar_de_novo(db: Session, actor: Actor, destino_id: uuid.UUID, version: int,
                   confirmo: bool) -> Postagem:
    """`falhou` → `agendado` com `planned_at = agora` (a próxima volta da trilha reivindica)."""
    destino = _destino(db, destino_id, lock=True)
    history.check_version(destino, version, "Este destino")
    if destino.archived_at is not None or destino.estado != DestinoEstado.falhou:
        raise ApiError(409, "conflict", "Só um envio que falhou pode ser tentado de novo")
    exigir_confirmacao_incerta(destino, confirmo)
    conexao = conexoes.conexao_viva(db, destino.conta_id)
    if conexao is None or conexao.estado != ConexaoEstado.conectada:
        raise ApiError(409, "conta_nao_conectada",
                       "Conecte (ou reconecte) a conta antes de tentar de novo")
    agora = datetime.now(UTC)
    before = history.snapshot(destino)
    incerta = destino.falha_incerta
    destino.estado = DestinoEstado.agendado
    destino.planned_at = agora
    destino.agendado_por = actor.user_id
    destino.agendado_em = agora
    destino.falha_motivo = None
    destino.falha_incerta = False
    destino.updated_by = actor.user_id
    details: dict[str, Any] = {"acao": "tentar_de_novo"}
    if incerta:
        details["conferidoNoApp"] = True
    history.record(db, actor, ENTITY_DESTINO, destino, "updated", before,
                   history.snapshot(destino), details)
    db.flush()
    return destino


def confirmar_envio(db: Session, actor: Actor, destino_id: uuid.UUID, version: int
                    ) -> Postagem:
    """Libera um destino `vencido` (R11) para a próxima volta: grava `envio_confirmado_por/em`."""
    agora = datetime.now(UTC)
    destino = _destino(db, destino_id, lock=True)
    history.check_version(destino, version, "Este destino")
    vencido = db.scalar(select(func.count()).select_from(Postagem).where(
        Postagem.id == destino.id, filtro_vencidos(agora)))
    if not vencido:
        raise ApiError(409, "conflict", "Este envio não está vencido")
    before = history.snapshot(destino)
    destino.envio_confirmado_por = actor.user_id
    destino.envio_confirmado_em = agora
    destino.updated_by = actor.user_id
    history.record(db, actor, ENTITY_DESTINO, destino, "updated", before,
                   history.snapshot(destino), {"acao": "envio_confirmado"})
    db.flush()
    return destino


def _acao(t: Tentativa, executor: Any) -> str | None:
    if t.fase == TentativaFase.incerta:
        return Acao.tentar_de_novo_conferido.value
    if t.fase == TentativaFase.sem_vaga:
        return Acao.esperar.value
    if t.fase == TentativaFase.recusada:
        if executor is None:
            return Acao.tentar_de_novo.value
        return executor.traduzir(t.codigo_rede).acao.value
    return None


def tentativa_out(t: Tentativa, users: dict, executor: Any = None) -> schemas.Tentativa:
    return schemas.Tentativa(
        id=t.id, numero=t.numero, modo=t.modo, fase=t.fase.value, disparo=t.disparo,
        disparado_por=users.get(t.disparado_por) if t.disparado_por else None,
        iniciada_em=t.iniciada_em, concluida_em=t.concluida_em, publish_id=t.publish_id,
        status_rede=t.status_rede, codigo_rede=t.codigo_rede, motivo=t.motivo,
        acao=_acao(t, executor), rede_post_id=t.rede_post_id,
        partes_enviadas=t.partes_enviadas, total_partes=t.total_partes,
        video=schemas.VideoEnviado(ref=t.video_ref, bytes=t.video_bytes,
                                   sha256=t.video_sha256))


def tentativas(db: Session, destino_id: uuid.UUID) -> list[schemas.Tentativa]:
    _destino(db, destino_id)
    rows = list(db.scalars(select(Tentativa).where(Tentativa.destino_id == destino_id)
                           .order_by(Tentativa.numero.desc())))
    users = user_refs(db, [t.disparado_por for t in rows])
    return [tentativa_out(t, users, registro.executor_para(t.rede)) for t in rows]


# ---- Publicar: criador na hora (R13) ----

def criador(db: Session, actor: Actor, conta_id: uuid.UUID, client: Any) -> schemas.Criador:
    """`creator_info` **na hora** (sem cache), com a taxa por token e o avatar atualizado."""
    conta = conexoes.get_conta_or_404(db, conta_id)
    # Sem trava aqui: `token_valido` trava a credencial (e a conexão, se precisar reconectar)
    # numa sessão própria.
    conexao = conexoes.conexao_viva(db, conta.id)
    if conexao is None:
        raise ApiError(409, "conta_nao_conectada", "Conecte a conta antes de publicar")
    if conexao.estado != ConexaoEstado.conectada:
        raise ApiError(409, "precisa_reconectar", "Reconecte a conta antes de publicar")
    if conexoes.ESCOPO_PUBLICAR not in (conexao.escopos or []):
        raise ApiError(409, "escopo_faltando",
                       "Reconecte a conta e autorize a permissão de publicar",
                       details={"faltando": [conexoes.ESCOPO_PUBLICAR]})
    executor = registro.executor_para(conexao.rede)
    if not limites.consumir(conexao.id, "creator_info"):
        raise _tente_em_instantes()
    try:
        token = conexoes.token_valido(conexao.id, client)
        info = executor.consultar_criador(Contexto(client=client, token=lambda: token))
    except ConexaoPerdida:
        raise ApiError(409, "precisa_reconectar",
                       "A autorização da TikTok não vale mais; reconecte a conta") from None
    except RecusaRede as e:
        if e.codigo == "rate_limit_exceeded":
            raise _tente_em_instantes() from None
        if e.codigo in ("access_token_invalid", "scope_not_authorized"):
            raise ApiError(409, "precisa_reconectar",
                           "A autorização da TikTok não vale mais; reconecte a conta") \
                from None
        raise ApiError(502, "rede_indisponivel",
                       f"A TikTok recusou a consulta (código {e.codigo})") from None
    except (ConexaoIndisponivel, RedeErro):
        raise ApiError(502, "rede_indisponivel",
                       "A TikTok não respondeu; tente de novo em instantes") from None
    db.refresh(conexao)
    conexoes.gravar_avatar(conexao, client, info.avatar_url)
    avatar = imaging.image_urls(conexao.avatar_key)["medium"] if conexao.avatar_key else None
    return schemas.Criador(
        username=info.username, display_name=info.display_name, avatar_url=avatar,
        pode_postar=info.pode_postar, privacy_level_options=list(info.privacidades),
        comentario_desligado=info.comentario_desligado, dueto_desligado=info.dueto_desligado,
        costura_desligada=info.costura_desligada, duracao_maxima_s=info.duracao_maxima_s,
        situacao_app=get_settings().tiktok_app_situacao)


def _tente_em_instantes() -> ApiError:
    return ApiError(429, "tente_em_instantes",
                    "Muitas consultas à TikTok neste minuto; tente em instantes")
