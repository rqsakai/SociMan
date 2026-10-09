"""Onde cada imagem da biblioteca é usada (research R5, FR-005, FR-007).

Um registro de provedores: cada um recebe `(db, perfil_id)` e devolve
`{image_id: [UsoImagem, …]}`. O asset está em uso se algum arquivo dele está. Provedores:
- **kit** (`bloqueia = True`): `watermark.imagem_id`, `hook.fundo_imagem_id` e
  `endCard.fundo_imagem_id` não nulos nos tokens vigentes, mesmo com a seção desligada;
- **corte** (`bloqueia = False`, Q1 = A): cortes do perfil cuja `kit_tokens` tem a
  `object_key` da imagem; só informa, porque o corte guardou os tokens resolvidos e o arquivo
  nunca é apagado.

Specs futuras (roteiros, cenas) registram o próprio provedor com `register`, sem mudar aqui.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset, AssetFile
from sociman_api.cortes.models import Corte
from sociman_api.perfis.models import Image


@dataclass(frozen=True)
class UsoImagem:
    origem: str  # "kit" | "corte" | futuros
    rotulo: str  # "Card final (kit v3)", "12 cortes"
    campo: str | None
    bloqueia: bool
    href: str | None


Provider = Callable[[Session, uuid.UUID], dict[uuid.UUID, list[UsoImagem]]]
_PROVIDERS: dict[str, Provider] = {}


def register(origem: str, fn: Provider) -> None:
    _PROVIDERS[origem] = fn


def usos_do_perfil(db: Session, perfil_id: uuid.UUID) -> dict[uuid.UUID, list[UsoImagem]]:
    """Todos os usos das imagens do perfil, na ordem de registro dos provedores."""
    out: dict[uuid.UUID, list[UsoImagem]] = defaultdict(list)
    for fn in _PROVIDERS.values():
        for image_id, usos in fn(db, perfil_id).items():
            out[image_id].extend(usos)
    return dict(out)


def archived_image_ids(db: Session, perfil_id: uuid.UUID) -> frozenset[uuid.UUID]:
    """Imagens do perfil em arquivo arquivado ou em asset arquivado (o kit as recusa)."""
    rows = db.scalars(
        select(AssetFile.image_id).join(Asset, Asset.id == AssetFile.asset_id).where(
            Asset.perfil_id == perfil_id,
            or_(AssetFile.archived_at.is_not(None), Asset.archived_at.is_not(None)),
        )
    )
    return frozenset(rows)


# ---- provedor do kit (bloqueia) ----

_KIT_LABELS = {"watermark.imagem_id": "Marca d'água", "hook.fundo_imagem_id": "Gancho",
               "endCard.fundo_imagem_id": "Card final"}


def _kit(db: Session, perfil_id: uuid.UUID) -> dict[uuid.UUID, list[UsoImagem]]:
    from sociman_api.marca.service_kit import current_tokens  # evita import circular
    from sociman_api.marca.tokens import image_fields

    tokens, row = current_tokens(db, perfil_id)
    version = row.version if row is not None else 0
    href = f"/app/perfis/{perfil_id}?aba=marca"
    out: dict[uuid.UUID, list[UsoImagem]] = defaultdict(list)
    for field, image_id in image_fields(tokens):
        out[image_id].append(UsoImagem(
            origem="kit", rotulo=f"{_KIT_LABELS[field]} (kit v{version})", campo=field,
            bloqueia=True, href=href,
        ))
    return out


# ---- provedor de cortes (só informa) ----

RECENT_CORTES = 5
_CORTE_KEYS = (("watermark", "imagem_key"), ("hook", "fundo_imagem_key"),
               ("end_card", "fundo_imagem_key"))


def _cortes(db: Session, perfil_id: uuid.UUID) -> dict[uuid.UUID, list[UsoImagem]]:
    keys = dict(db.execute(select(Image.object_key, Image.id).where(
        Image.perfil_id == perfil_id)).all())
    if not keys:
        return {}
    by_image: dict[uuid.UUID, list[Corte]] = defaultdict(list)
    cortes = db.execute(
        select(Corte.id, Corte.created_at, Corte.kit_tokens)
        .where(Corte.perfil_id == perfil_id)
        .order_by(Corte.created_at.desc(), Corte.id)
    ).all()
    for corte in cortes:
        tokens = corte.kit_tokens or {}
        used = {(tokens.get(section) or {}).get(key) for section, key in _CORTE_KEYS}
        for key in used:
            if key in keys:
                by_image[keys[key]].append(corte)
    out: dict[uuid.UUID, list[UsoImagem]] = {}
    for image_id, rows in by_image.items():
        n = len(rows)
        usos = [UsoImagem(origem="corte", rotulo=f"{n} corte" if n == 1 else f"{n} cortes",
                          campo=None, bloqueia=False,
                          href=f"/app/perfis/{perfil_id}?aba=cortes")]
        usos += [UsoImagem(origem="corte", rotulo=f"Corte de {c.created_at:%d/%m/%Y %H:%M}",
                           campo=None, bloqueia=False, href=f"/app/cortes/{c.id}")
                 for c in rows[:RECENT_CORTES]]
        out[image_id] = usos
    return out


register("kit", _kit)
register("corte", _cortes)
