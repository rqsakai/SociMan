"""Provedor `vozes_e_consentimento` do "em uso" da limpeza de 90 dias da 021 (spec 025, R22): a
gravação original, a referência e a prova de uma voz, e a prova de consentimento de um avatar,
nunca entram na limpeza (só a revogação as apaga)."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset
from sociman_api.geracao.uso import register
from sociman_api.vozes.models import Voz


def _vozes_e_consentimento(db: Session, image_id: uuid.UUID | None,
                           audio_id: uuid.UUID | None) -> bool:
    if audio_id is not None:
        a = str(audio_id)
        if db.scalar(select(Voz.id).where(or_(
                Voz.gravacao_audio_id == audio_id, Voz.ref_audio_id == audio_id,
                Voz.consentimento["prova"]["audio_id"].astext == a,
        )).limit(1)) is not None:
            return True
        if db.scalar(select(Asset.id).where(
                Asset.consentimento["prova"]["audio_id"].astext == a).limit(1)) is not None:
            return True
    return image_id is not None and db.scalar(select(Asset.id).where(
        Asset.consentimento["prova"]["image_id"].astext == str(image_id)).limit(1)) is not None


register("vozes_e_consentimento", _vozes_e_consentimento)
