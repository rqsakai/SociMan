"""Ingredientes da cena para o Flow (research R3): até 3 imagens, nesta ordem.

1. o arquivo do avatar (o look ou a pose escolhidos; padrão: a imagem principal);
2. a foto do produto (arquivo principal do asset `imagem`);
3. a imagem do cenário (a escolhida ou a principal).

Cada item leva o link de mídia `imagem` da 007 (sem validade) para baixar o original. A cena tem
no máximo um de cada, então o limite de 3 do Flow vale pela estrutura.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from sociman_api import imaging, midia
from sociman_api.assets.models import Asset, AssetFile
from sociman_api.cenas import schemas
from sociman_api.perfis.models import Image


@dataclass(frozen=True)
class Assets:
    """Os assets referenciados pela cena, já carregados."""

    avatar: Asset | None = None
    cenario: Asset | None = None
    produto: Asset | None = None


def arquivo(asset: Asset | None, arquivo_id: uuid.UUID | None) -> AssetFile | None:
    """O arquivo escolhido (se ainda é do asset) ou o principal."""
    if asset is None:
        return None
    wanted = arquivo_id or asset.primary_file_id
    return next((f for f in asset.arquivos if f.id == wanted), None)


def _nome(asset: Asset, f: AssetFile) -> str:
    detalhe = f.look or f.label
    return f"{asset.name}, {detalhe}" if detalhe else asset.name


def thumb_url(image: Image) -> str:
    return imaging.image_urls(image.object_key)["thumb"]


def listar(db: Session, assets: Assets, avatar_arquivo_id: uuid.UUID | None,
           cenario_arquivo_id: uuid.UUID | None) -> list[schemas.Ingrediente]:
    itens = (("avatar", assets.avatar, arquivo(assets.avatar, avatar_arquivo_id)),
             ("produto", assets.produto, arquivo(assets.produto, None)),
             ("cenario", assets.cenario, arquivo(assets.cenario, cenario_arquivo_id)))
    out: list[schemas.Ingrediente] = []
    for papel, asset, f in itens:
        if asset is None or f is None:
            continue
        image = db.get(Image, f.image_id)
        if image is None:  # pragma: no cover — FK
            continue
        link = midia.link("imagem", image.id, ttl=None).url
        out.append(schemas.Ingrediente(
            papel=papel, asset_id=asset.id, arquivo_id=f.id, nome=_nome(asset, f),
            largura=image.width, altura=image.height, download_url=f"{link}?download=1",
            thumb_url=thumb_url(image)))
    return out
