"""Provedor `cena` do "onde é usado" dos assets (research R8, FR-009).

Cobre o avatar (qualquer arquivo dele), o cenário e a foto do produto. Só informa
(`bloqueia = False`): arquivar o asset continua permitido. Um rótulo "N cenas" por asset, preso à
imagem principal (ou à primeira), com link para a aba Cenas filtrada pelo asset. Cenas
arquivadas não contam.
"""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset
from sociman_api.assets.usos import UsoImagem, register
from sociman_api.cenas.models import Cena

_FILTROS = (("avatar_id", "avatarId"), ("cenario_id", "cenarioId"),
            ("produto_imagem_id", "produtoImagemId"))


def _cenas(db: Session, perfil_id: uuid.UUID) -> dict[uuid.UUID, list[UsoImagem]]:
    rows = db.execute(select(Cena.avatar_id, Cena.cenario_id, Cena.produto_imagem_id).where(
        Cena.perfil_id == perfil_id, Cena.archived_at.is_(None))).all()
    contagem: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
    for row in rows:
        for (_campo, filtro), asset_id in zip(_FILTROS, row, strict=True):
            if asset_id is not None:
                contagem[(asset_id, filtro)] += 1
    if not contagem:
        return {}
    assets = {a.id: a for a in db.scalars(select(Asset).where(
        Asset.id.in_({k[0] for k in contagem})))}
    out: dict[uuid.UUID, list[UsoImagem]] = defaultdict(list)
    for (asset_id, filtro), n in contagem.items():
        asset = assets.get(asset_id)
        if asset is None or not asset.arquivos:
            continue
        principal = next((f for f in asset.arquivos if f.id == asset.primary_file_id),
                         asset.arquivos[0])
        out[principal.image_id].append(UsoImagem(
            origem="cena", rotulo=f"{n} cena" if n == 1 else f"{n} cenas", campo=None,
            bloqueia=False, href=f"/app/perfis/{perfil_id}?aba=cenas&{filtro}={asset_id}"))
    return out


register("cena", _cenas)
