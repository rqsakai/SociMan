"""Registro dos executores por rede (research R20 da spec 015, FR-013).

O **único** módulo de `src/` que importa `publicacao.<rede>` (guarda R16.2): a trilha, as
conexões, o service e as capacidades chegam ao executor, ao OAuth e ao cliente HTTP da rede por
aqui. Os erros tipados são os genéricos de `publicacao/executor.py` (os do cliente da TikTok são
subclasses deles). YouTube e Instagram entram aqui, cada um com a sua pasta, em specs próprias.

Spec 016: o `metricas/` chega ao leitor (`leitor_para`) e aos tipos da leitura (`Contexto`,
`VideoLido`, `StatsConta`, `PostId`/`Pendente`/`Falhou`, os erros) **só** por aqui; ele não
importa `publicacao.executor` (guarda 2).
"""

from types import ModuleType
from typing import Any

from sociman_api.perfis.models import Platform
from sociman_api.publicacao.executor import (  # noqa: F401 — reexportados para quem chama
    ConexaoIndisponivel,
    ConexaoPerdida,
    Contexto,
    ExecutorRede,
    Falhou,
    LeitorRede,
    PedidoProibido,
    Pendente,
    PostId,
    RecusaRede,
    RedeErro,
    SemPermissaoLeitura,
    SemResposta,
    StatsConta,
    VideoLido,
)
from sociman_api.publicacao.executor import RedeErro as TikTokErro  # noqa: F401
from sociman_api.publicacao.tiktok.executor import TikTokExecutor

EXECUTORES: dict[Platform, ExecutorRede] = {Platform.tiktok: TikTokExecutor()}


def executor_para(platform: Platform | str) -> ExecutorRede | None:
    """O executor da rede, ou None (a rede não tem execução automática)."""
    try:
        return EXECUTORES.get(Platform(platform))
    except ValueError:
        return None


def oauth_para(platform: Platform | str = Platform.tiktok) -> ModuleType:
    executor = executor_para(platform)
    if executor is None:
        raise ValueError(f"rede sem executor: {platform}")
    return executor.oauth


def get_cliente(platform: Platform | str = Platform.tiktok,
                transport: Any = None) -> Any:
    """Cliente HTTP da rede (os testes injetam o transporte do fake)."""
    executor = executor_para(platform)
    if executor is None:
        raise ValueError(f"rede sem executor: {platform}")
    return executor.novo_cliente(transport)


def leitor_para(platform: Platform | str) -> LeitorRede | None:
    """Spec 016 (R2): o leitor da rede (só leitura), ou None (a rede não tem métricas). O
    `metricas/` chega à rede só por aqui."""
    executor = executor_para(platform)
    return getattr(executor, "leitor", None) if executor is not None else None
