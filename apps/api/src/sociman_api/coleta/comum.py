"""O que a ingestão, a fila e a gestão compartilham: a config efetiva (com os padrões quando a
linha não existe), a janela, o orçamento do dia (calculado, nunca gravado) e os limites que o
coletor recebe."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.coleta import schemas
from sociman_api.coleta.models import CONFIG_ID, ColetaConfig
from sociman_api.config import get_settings
from sociman_api.mercado import mercados
from sociman_api.mercado.constantes import FILA_LEASE_MIN
from sociman_api.mercado.models import ColetaItem, Imagem, ItemStatus

LINK_CONFIG = "/app/configuracoes/coleta"
ENTITY_CONFIG = "coleta_config"
CONFIG_ENTITY_ID = uuid.UUID(int=26)  # o `entity_id` do histórico do singleton


class ConfigEntidade:
    """`history.record` quer `id` e `version`; a config é a linha 1 com `entity_id` fixo."""

    def __init__(self, cfg: ColetaConfig):
        self._cfg = cfg
        self.id = CONFIG_ENTITY_ID

    @property
    def version(self) -> int:
        return self._cfg.version

    @version.setter
    def version(self, v: int) -> None:
        self._cfg.version = v


PAGINAS_QUE_CONTAM = (ItemStatus.gravado, ItemStatus.repetido, ItemStatus.erro)


def agora() -> datetime:
    return datetime.now(UTC)


def config_atual(db: Session) -> ColetaConfig:
    """A linha única, ou uma instância com os padrões (não persistida; `version` 0)."""
    cfg = db.get(ColetaConfig, CONFIG_ID)
    if cfg is None:
        cfg = ColetaConfig(id=CONFIG_ID, habilitada=False, janela_inicio=8, janela_fim=23,
                           paginas_dia=300, imagens_dia=1500, imagens_por_produto=9,
                           itens_por_coleta=40, pausa_min_s=5, pausa_max_s=40, version=0)
    return cfg


def servidor_habilitado() -> bool:
    return get_settings().coleta_habilitada


def ligada(db: Session, cfg: ColetaConfig | None = None) -> bool:
    cfg = cfg or config_atual(db)
    return servidor_habilitado() and bool(cfg.habilitada)


def pausada(cfg: ColetaConfig, em: datetime | None = None) -> bool:
    em = em or agora()
    return cfg.pausada_ate is not None and cfg.pausada_ate > em


def janela(cfg: ColetaConfig, mercado: str, em: datetime | None = None) -> schemas.Janela:
    local = mercados.agora_local(mercado, em)
    # `fim` inclusivo: 08h–23h vai de 08:00 a 23:59 (23 é o teto do CHECK).
    dentro = cfg.janela_inicio <= local.hour <= cfg.janela_fim
    return schemas.Janela(inicio=cfg.janela_inicio, fim=cfg.janela_fim, dentro=dentro)


def limites(cfg: ColetaConfig) -> schemas.LimitesColeta:
    return schemas.LimitesColeta(paginas_dia=cfg.paginas_dia, imagens_dia=cfg.imagens_dia,
                           imagens_por_produto=cfg.imagens_por_produto,
                           itens_por_coleta=cfg.itens_por_coleta, pausa_min_s=cfg.pausa_min_s,
                           pausa_max_s=cfg.pausa_max_s, lease_min=FILA_LEASE_MIN)


@dataclass(frozen=True)
class Contagem:
    paginas: int
    imagens: int


def _limites_do_dia(mercado: str, hoje: date) -> tuple[datetime, datetime]:
    zona = mercados.mercado(mercado).zona
    inicio = datetime.combine(hoje, datetime.min.time(), zona)
    return inicio, inicio + timedelta(days=1)


def contagem_hoje(db: Session, mercado: str, hoje: date | None = None) -> Contagem:
    """Páginas (itens gravados, repetidos ou com erro) e imagens recebidas no dia local."""
    hoje = hoje or mercados.hoje(mercado)
    paginas = db.scalar(select(func.count()).select_from(ColetaItem).where(
        ColetaItem.data_local == hoje, ColetaItem.status.in_(PAGINAS_QUE_CONTAM))) or 0
    inicio, fim = _limites_do_dia(mercado, hoje)
    imagens = db.scalar(select(func.count()).select_from(Imagem).where(
        Imagem.created_at >= inicio, Imagem.created_at < fim)) or 0
    return Contagem(paginas, imagens)


def orcamento(db: Session, cfg: ColetaConfig, mercado: str,
              hoje: date | None = None) -> schemas.Orcamento:
    c = contagem_hoje(db, mercado, hoje)
    return schemas.Orcamento(paginas_hoje=c.paginas,
                             paginas_restantes=max(0, cfg.paginas_dia - c.paginas),
                             imagens_hoje=c.imagens,
                             imagens_restantes=max(0, cfg.imagens_dia - c.imagens))


def item_uuid(item_id: int) -> uuid.UUID:
    """O id bigint do item como uuid, para o token de mídia do bruto (`router_midia`)."""
    return uuid.UUID(int=item_id)
