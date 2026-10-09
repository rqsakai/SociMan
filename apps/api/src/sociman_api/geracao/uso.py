""""Em uso" de uma imagem ou de um áudio de candidato (research R12): a limpeza de 90 dias só
apaga o que nada mais usa (FR-032: "qualquer arquivo em uso por outra entidade NUNCA").

Provedores (`register`, aberto para a 025 e a 012):
- `asset_files`: a imagem está em algum arquivo de asset (mesmo arquivado);
- `escolhido`: a imagem ou o áudio é de um candidato escolhido de qualquer geração;
- `params`: o id aparece no `params` de uma geração não terminada ou terminada há menos de 90
  dias (referência de outra geração);
- `biblioteca`: os provedores do "onde é usado" da 007 (tokens do kit, cortes e cenas da 010).
"""

import uuid
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import Text, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from sociman_api.assets.models import AssetFile
from sociman_api.assets.usos import usos_do_perfil
from sociman_api.cenas import usos_assets as _cenas_usos  # noqa: F401 — registra o provedor
from sociman_api.geracao.models import TERMINADOS, Geracao, GeracaoCandidato
from sociman_api.perfis.models import Image

JANELA = timedelta(days=90)

Provedor = Callable[[Session, uuid.UUID | None, uuid.UUID | None], bool]
_PROVEDORES: dict[str, Provedor] = {}


def register(nome: str, fn: Provedor) -> None:
    _PROVEDORES[nome] = fn


def _asset_files(db: Session, image_id: uuid.UUID | None, audio_id: uuid.UUID | None) -> bool:
    return image_id is not None and bool(db.scalar(select(exists().where(
        AssetFile.image_id == image_id))))


def _escolhido(db: Session, image_id: uuid.UUID | None, audio_id: uuid.UUID | None) -> bool:
    conds = []
    if image_id is not None:
        conds += [GeracaoCandidato.image_id == image_id, GeracaoCandidato.image_par_id == image_id]
    if audio_id is not None:
        conds.append(GeracaoCandidato.audio_id == audio_id)
        conds.append(GeracaoCandidato.metricas["teste_audio_id"].astext == str(audio_id))
    return bool(conds) and bool(db.scalar(select(exists().where(
        Geracao.escolhido_id == GeracaoCandidato.id, or_(*conds)))))


def _params(db: Session, image_id: uuid.UUID | None, audio_id: uuid.UUID | None) -> bool:
    ids = [str(i) for i in (image_id, audio_id) if i is not None]
    vivo = or_(Geracao.status.not_in(TERMINADOS), Geracao.finished_at.is_(None),
               Geracao.finished_at >= func.now() - JANELA)
    return any(db.scalar(select(exists().where(vivo, cast(Geracao.params, Text).contains(i))))
               for i in ids)


def _biblioteca(db: Session, image_id: uuid.UUID | None, audio_id: uuid.UUID | None) -> bool:
    if image_id is None:
        return False
    img = db.get(Image, image_id)
    return img is not None and bool(usos_do_perfil(db, img.perfil_id).get(image_id))


register("asset_files", _asset_files)
register("escolhido", _escolhido)
register("params", _params)
register("biblioteca", _biblioteca)


def midia_em_uso(db: Session, *, image_id: uuid.UUID | None = None,
                 audio_id: uuid.UUID | None = None) -> str | None:
    """O nome do 1º provedor que usa a mídia, ou None (pode apagar)."""
    for nome, fn in _PROVEDORES.items():
        if fn(db, image_id, audio_id):
            return nome
    return None
