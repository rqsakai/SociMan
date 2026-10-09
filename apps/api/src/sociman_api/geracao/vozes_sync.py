"""Sincronização das vozes com o shop-tts (spec 025, research R12): a linha `vozes_sync` do
gerador (o único serviço na rede `gpu-local`), fora da linha da GPU (importar e remover não usam
a GPU).

A cada volta:
- importa as vozes com referência e `sincronizada_em` nula (`POST /v2/voices/import` com o
  `tts_id`, a referência, a transcrição e `meta = {origem, tom, sociman_voz_id, sha256}`), confere
  o `sha256` em `GET /voices` e grava `sincronizada_em`;
- remove as revogadas que ainda estão no shop-tts (`DELETE /v2/voices/{nome}`; 404 = já removida)
  e zera `sincronizada_em`.
Falha = só log, com espera crescente por voz (o FR-023: a voz fica aprovada e "Não sincronizada").
Sem versão no histórico: `sincronizada_em` é estado técnico, fora do snapshot.
"""

import hashlib
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import storage
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.models import Audio
from sociman_api.geracao.shoptts import ShopTtsClient
from sociman_api.vozes.models import Voz
from sociman_api.vozes.tts_id import tts_id

log = logging.getLogger(__name__)

ESPERA_MAX_S = 900.0


class Sync:
    def __init__(self) -> None:
        self.proxima: dict[uuid.UUID, float] = {}
        self.falhas: dict[uuid.UUID, int] = {}

    def _pode(self, voz_id: uuid.UUID, agora: float) -> bool:
        return self.proxima.get(voz_id, 0.0) <= agora

    def _falhou(self, voz_id: uuid.UUID, agora: float) -> None:
        n = self.falhas.get(voz_id, 0) + 1
        self.falhas[voz_id] = n
        self.proxima[voz_id] = agora + min(30.0 * 2 ** (n - 1), ESPERA_MAX_S)

    def _ok(self, voz_id: uuid.UUID) -> None:
        self.falhas.pop(voz_id, None)
        self.proxima.pop(voz_id, None)

    def volta(self, db: Session, tts: ShopTtsClient, agora: float | None = None) -> int:
        """Uma volta (cada voz numa transação). Devolve quantas vozes mudaram."""
        agora = time.monotonic() if agora is None else agora
        feitas = 0
        importar = [v.id for v in db.scalars(select(Voz).where(
            Voz.ref_audio_id.is_not(None), Voz.sincronizada_em.is_(None))) if not v.revogada]
        remover = [v.id for v in db.scalars(select(Voz).where(Voz.sincronizada_em.is_not(None)))
                   if v.revogada]
        db.rollback()
        for voz_id in importar:
            if self._pode(voz_id, agora) and self._importar(db, tts, voz_id, agora):
                feitas += 1
        for voz_id in remover:
            if self._pode(voz_id, agora) and self._remover(db, tts, voz_id, agora):
                feitas += 1
        return feitas

    def _importar(self, db: Session, tts: ShopTtsClient, voz_id: uuid.UUID, agora: float
                  ) -> bool:
        voz = db.get(Voz, voz_id, with_for_update=True)
        if voz is None or voz.ref_audio_id is None or voz.sincronizada_em is not None:
            db.rollback()
            return False
        audio = db.get(Audio, voz.ref_audio_id)
        ref_id = voz.ref_audio_id
        try:
            dados = storage.get(audio.object_key, bucket="audios")
            sha = hashlib.sha256(dados).hexdigest()
            nome = tts_id(voz.id)
            tts.importar(nome=nome, ref=dados, ref_texto=voz.ref_texto or "", meta={
                "origem": voz.origem.value, "tom": voz.tom, "sociman_voz_id": str(voz.id),
                "sha256": sha})
            remoto = (tts.voices() or {}).get(nome) or {}
            if remoto.get("sha256") and remoto["sha256"] != sha:
                raise MotorErro("servico_fora", detalhe="sha256 diferente no shop-tts")
        except (MotorErro, OSError, ValueError) as exc:
            db.rollback()
            self._falhou(voz_id, agora)
            log.warning("voz %s não sincronizada (%s)", voz_id, getattr(exc, "detalhe", exc))
            return False
        if voz.ref_audio_id != ref_id:  # a referência mudou no meio: a próxima volta importa
            db.rollback()
            return False
        voz.sincronizada_em = datetime.now(UTC)
        db.commit()
        self._ok(voz_id)
        log.info("voz %s sincronizada no shop-tts", voz_id)
        return True

    def _remover(self, db: Session, tts: ShopTtsClient, voz_id: uuid.UUID, agora: float) -> bool:
        voz = db.get(Voz, voz_id, with_for_update=True)
        if voz is None or voz.sincronizada_em is None:
            db.rollback()
            return False
        try:
            tts.apagar_voz(tts_id(voz.id))
        except MotorErro as exc:
            db.rollback()
            self._falhou(voz_id, agora)
            log.warning("voz revogada %s não removida do shop-tts (%s)", voz_id, exc.detalhe)
            return False
        voz.sincronizada_em = None
        db.commit()
        self._ok(voz_id)
        log.info("voz revogada %s removida do shop-tts", voz_id)
        return True
