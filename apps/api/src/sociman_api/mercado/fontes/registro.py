"""Registro dos adaptadores de fonte por rede (molde `publicacao/registro.py`): o **único**
módulo que importa um adaptador concreto. A ingestão, os interesses e a fila chegam ao
adaptador por `fonte_para`."""

from sociman_api.mercado.fontes.base import CampoInvalido, FonteMercado, ProdutoRef  # noqa: F401
from sociman_api.mercado.fontes.tiktok_shop import FonteTikTokShop
from sociman_api.perfis.models import Platform

FONTES: dict[Platform, FonteMercado] = {Platform.tiktok: FonteTikTokShop()}


def fonte_para(rede: Platform | str) -> FonteMercado | None:
    """O adaptador da rede, ou None (a rede não tem coleta de mercado)."""
    try:
        return FONTES.get(Platform(rede))
    except ValueError:
        return None


def esquemas() -> frozenset[str]:
    return frozenset(f.esquema_versao for f in FONTES.values())
