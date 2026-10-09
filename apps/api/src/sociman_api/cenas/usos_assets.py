"""Provedor `cena` do "onde é usado" dos assets (research R8, FR-009; spec 029, FR-015).

Cobre o avatar (qualquer arquivo dele), o cenário e a foto do produto. Só informa
(`bloqueia = False`): arquivar o asset continua permitido. Um rótulo "N cenas" por asset e por
perfil base da cena (029: as cenas de todos os perfis, e as sem perfil base), preso à imagem
principal (ou à primeira), com link para a lista de cenas do AI Studio filtrada pelo perfil base
e pelo asset. Cenas arquivadas não contam.
"""

import uuid
from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset, AssetFile
from sociman_api.assets.usos import UsoImagem, nomes_perfis, register
from sociman_api.cenas.models import Cena

_FILTROS = (("avatar_id", "avatarId"), ("cenario_id", "cenarioId"),
            ("produto_imagem_id", "produtoImagemId"))


def _cenas(db: Session, image_ids: frozenset[uuid.UUID]) -> dict[uuid.UUID, list[UsoImagem]]:
    assets = {a.id: a for a in db.scalars(select(Asset).where(Asset.arquivos.any(
        AssetFile.image_id.in_(image_ids))))}
    if not assets:
        return {}
    ids = list(assets)
    rows = db.execute(select(Cena.perfil_id, Cena.avatar_id, Cena.cenario_id,
                             Cena.produto_imagem_id).where(
        Cena.archived_at.is_(None),
        or_(Cena.avatar_id.in_(ids), Cena.cenario_id.in_(ids),
            Cena.produto_imagem_id.in_(ids)))).all()
    contagem: dict[tuple[uuid.UUID, str, uuid.UUID | None], int] = defaultdict(int)
    for perfil_id, *refs in rows:
        for (_campo, filtro), asset_id in zip(_FILTROS, refs, strict=True):
            if asset_id in assets:
                contagem[(asset_id, filtro, perfil_id)] += 1
    nomes = nomes_perfis(db, [k[2] for k in contagem])
    out: dict[uuid.UUID, list[UsoImagem]] = defaultdict(list)
    for (asset_id, filtro, perfil_id), n in contagem.items():
        asset = assets[asset_id]
        if not asset.arquivos:
            continue
        principal = next((f for f in asset.arquivos if f.id == asset.primary_file_id),
                         asset.arquivos[0])
        perfil = perfil_id if perfil_id is not None else "sem"
        out[principal.image_id].append(UsoImagem(
            origem="cena", rotulo=f"{n} cena" if n == 1 else f"{n} cenas", campo=None,
            bloqueia=False, href=f"/app/estudio/cenas?perfil={perfil}&{filtro}={asset_id}",
            perfil_id=perfil_id, perfil_nome=nomes.get(perfil_id)))
    return out


register("cena", _cenas)
