"""Onde cada imagem da biblioteca é usada (research R5, FR-005, FR-007; spec 029, FR-015).

Um registro de provedores: cada um recebe `(db, image_ids)` e devolve
`{image_id: [UsoImagem, …]}` com os usos dessas imagens **em todos os perfis** (029), cada uso
com o perfil onde ele está. O asset está em uso se algum arquivo dele está. Provedores:
- **kit** (`bloqueia = True`): `watermark.imagem_id`, `hook.fundo_imagem_id` e
  `endCard.fundo_imagem_id` não nulos nos tokens vigentes de qualquer kit, mesmo com a seção
  desligada;
- **corte** (`bloqueia = False`, Q1 = A): cortes cuja `kit_tokens` tem a `object_key` da
  imagem; só informa, porque o corte guardou os tokens resolvidos e o arquivo nunca é apagado.

Specs futuras (roteiros, cenas) registram o próprio provedor com `register`, sem mudar aqui.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable, Collection
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset, AssetFile
from sociman_api.cortes.models import Corte
from sociman_api.perfis.models import Image, Perfil


@dataclass(frozen=True)
class UsoImagem:
    origem: str  # "kit" | "corte" | futuros
    rotulo: str  # "Card final (kit v3)", "12 cortes"
    campo: str | None
    bloqueia: bool
    href: str | None
    perfil_id: uuid.UUID | None = None  # 029: o perfil onde está o uso
    perfil_nome: str | None = None


Provider = Callable[[Session, frozenset[uuid.UUID]], dict[uuid.UUID, list[UsoImagem]]]
_PROVIDERS: dict[str, Provider] = {}


def register(origem: str, fn: Provider) -> None:
    _PROVIDERS[origem] = fn


def nomes_perfis(db: Session, ids: Collection[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return dict(db.execute(select(Perfil.id, Perfil.name).where(Perfil.id.in_(wanted))).all())


def usos_das_imagens(db: Session, image_ids: Collection[uuid.UUID]
                     ) -> dict[uuid.UUID, list[UsoImagem]]:
    """Os usos dessas imagens em todos os perfis, na ordem de registro dos provedores."""
    wanted = frozenset(image_ids)
    if not wanted:
        return {}
    out: dict[uuid.UUID, list[UsoImagem]] = defaultdict(list)
    for fn in _PROVIDERS.values():
        for image_id, usos in fn(db, wanted).items():
            out[image_id].extend(usos)
    return dict(out)


def usos_do_perfil(db: Session, perfil_id: uuid.UUID | None
                   ) -> dict[uuid.UUID, list[UsoImagem]]:
    """Os usos de todas as imagens da biblioteca, em todos os perfis. 029: o kit e as cenas de
    qualquer perfil usam itens da agência, então `perfil_id` é ignorado (fica por
    compatibilidade); para poucas imagens, prefira `usos_das_imagens`."""
    ids = db.scalars(select(Image.id))
    return usos_das_imagens(db, set(ids))


def archived_image_ids(db: Session, perfil_id: uuid.UUID | None = None) -> frozenset[uuid.UUID]:
    """Imagens em arquivo arquivado ou em asset arquivado, na biblioteca inteira (o kit as
    recusa). 029: o kit escolhe da biblioteca da agência; `perfil_id` fica só por
    compatibilidade."""
    rows = db.scalars(
        select(AssetFile.image_id).join(Asset, Asset.id == AssetFile.asset_id).where(
            or_(AssetFile.archived_at.is_not(None), Asset.archived_at.is_not(None)),
        )
    )
    return frozenset(rows)


# ---- provedor do kit (bloqueia) ----

_KIT_LABELS = {"watermark.imagem_id": "Marca d'água", "hook.fundo_imagem_id": "Gancho",
               "endCard.fundo_imagem_id": "Card final"}


def _kit(db: Session, image_ids: frozenset[uuid.UUID]) -> dict[uuid.UUID, list[UsoImagem]]:
    from sociman_api.marca.models import KIT_SECTIONS, BrandKit  # evita import circular
    from sociman_api.marca.tokens import KitTokens, image_fields

    # Sem linha, o kit é o padrão do código, sem imagem.
    rows = list(db.scalars(select(BrandKit).order_by(BrandKit.perfil_id)))
    nomes = nomes_perfis(db, [r.perfil_id for r in rows])
    out: dict[uuid.UUID, list[UsoImagem]] = defaultdict(list)
    for row in rows:
        tokens = KitTokens.from_sections({s: getattr(row, s) for s in KIT_SECTIONS})
        for field, image_id in image_fields(tokens):
            if image_id not in image_ids:
                continue
            out[image_id].append(UsoImagem(
                origem="kit", rotulo=f"{_KIT_LABELS[field]} (kit v{row.version})", campo=field,
                bloqueia=True, href=f"/app/perfis/{row.perfil_id}?aba=marca",
                perfil_id=row.perfil_id, perfil_nome=nomes.get(row.perfil_id),
            ))
    return out


# ---- provedor de cortes (só informa) ----

RECENT_CORTES = 5
_CORTE_KEYS = (("watermark", "imagem_key"), ("hook", "fundo_imagem_key"),
               ("end_card", "fundo_imagem_key"))


def _cortes(db: Session, image_ids: frozenset[uuid.UUID]) -> dict[uuid.UUID, list[UsoImagem]]:
    keys = dict(db.execute(select(Image.object_key, Image.id).where(
        Image.id.in_(image_ids))).all())
    if not keys:
        return {}
    cortes = db.execute(
        select(Corte.id, Corte.perfil_id, Corte.created_at, Corte.kit_tokens)
        .where(or_(*(Corte.kit_tokens[section][key].astext.in_(list(keys))
                     for section, key in _CORTE_KEYS)))
        .order_by(Corte.created_at.desc(), Corte.id)
    ).all()
    by_image: dict[tuple[uuid.UUID, uuid.UUID], list] = defaultdict(list)
    for corte in cortes:
        tokens = corte.kit_tokens or {}
        used = {(tokens.get(section) or {}).get(key) for section, key in _CORTE_KEYS}
        for key in used:
            if key in keys:
                by_image[(keys[key], corte.perfil_id)].append(corte)
    nomes = nomes_perfis(db, [p for _i, p in by_image])
    out: dict[uuid.UUID, list[UsoImagem]] = defaultdict(list)
    for (image_id, perfil_id), rows in by_image.items():
        n, nome = len(rows), nomes.get(perfil_id)
        out[image_id].append(UsoImagem(
            origem="corte", rotulo=f"{n} corte" if n == 1 else f"{n} cortes", campo=None,
            bloqueia=False, href=f"/app/perfis/{perfil_id}?aba=cortes", perfil_id=perfil_id,
            perfil_nome=nome))
        out[image_id] += [UsoImagem(
            origem="corte", rotulo=f"Corte de {c.created_at:%d/%m/%Y %H:%M}", campo=None,
            bloqueia=False, href=f"/app/cortes/{c.id}", perfil_id=perfil_id, perfil_nome=nome)
            for c in rows[:RECENT_CORTES]]
    return out


register("kit", _kit)
register("corte", _cortes)
