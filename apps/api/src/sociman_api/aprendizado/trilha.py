"""Trilha `aprendizado` do agendador (spec 023, Clarification 3; plan, Complexity Tracking).

Cada volta, nesta ordem:
0. o casamento dos vídeos-fonte com os temas (`fonte_temas`, plano B do R9), sem IA: roda
   mesmo sem `ANTHROPIC_API_KEY`;
1. as análises da IA presas em `processando` há mais de 15 min voltam a `pendente` (uma vez);
2. **uma** análise pendente (`SKIP LOCKED`), até `pronta` ou `erro` (quadros no HD temporário);
3. a classificação dos posts pendentes dos perfis com taxonomia e `classificacao_auto` (ou com
   "classificar pendentes" pedido), até `LIMITE_DIARIO` chamadas por perfil por dia local,
   contando as com erro. Para no 1º erro de disponibilidade da IA (timeout, 5xx, sem chave).

Sem `ANTHROPIC_API_KEY`, só o passo 0 roda (o motivo vai para o log uma vez). A correção do dono nunca é sobrescrita
(`classificacao.pode_a_ia`). Cada classificação é commitada na hora: uma volta interrompida não
perde o que já foi pago.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.aprendizado import analise_ia, fonte_temas
from sociman_api.aprendizado import classificacao as cls
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import preferencias as prefs
from sociman_api.aprendizado.models import Tema
from sociman_api.config import get_settings
from sociman_api.ia.cliente import IaClient, get_ia_client
from sociman_api.metricas.models import VideoRede
from sociman_api.perfis.models import Perfil

log = logging.getLogger("sociman.aprendizado")


def ociosa() -> str | None:
    if not get_settings().anthropic_api_key.get_secret_value():
        return "ANTHROPIC_API_KEY não configurada: nada é classificado nem analisado"
    return None


def _perfis_com_taxonomia(db: Session) -> list[Perfil]:
    com_tema = select(Tema.perfil_id).where(Tema.archived_at.is_(None)).distinct()
    return list(db.scalars(select(Perfil).where(Perfil.id.in_(com_tema),
                                                Perfil.archived_at.is_(None))
                           .order_by(Perfil.created_at, Perfil.id)))


def classificar(db: Session, client: IaClient | None, agora: datetime) -> int:
    """As classificações da volta. Devolve quantas chamadas fez."""
    feitas = 0
    for perfil in _perfis_com_taxonomia(db):
        row = prefs.linha(db, perfil.id, None)
        automatica = row.classificacao_auto if row is not None else True
        pedido = row.pedido_classificacao_em if row is not None else None
        if not automatica and pedido is None:
            continue
        restantes = K.LIMITE_DIARIO - cls.usadas_hoje(db, perfil.id, agora)
        ids = cls.pendentes_ids(db, perfil.id, agora, restantes)
        temas = cls.taxonomia(db, perfil.id)
        versao = prefs.taxonomia_versao(db, perfil.id)
        parar = False
        for vid in ids:
            video = db.get(VideoRede, vid)
            if video is None:
                continue
            row = cls.classificar_um(db, client, video, perfil, temas, versao)
            db.commit()
            feitas += row is not None
            if cls.indisponivel(row):
                log.warning("classificação parada nesta volta: a IA respondeu %s",
                            row.erro_code if row else "")
                parar = True
                break
        if pedido is not None:
            row = prefs.linha(db, perfil.id, None, lock=True)
            if row is not None and row.pedido_classificacao_em == pedido:
                row.pedido_classificacao_em = None
            db.commit()
        if parar:
            break
    return feitas


_avisou_sem_ia = False


def rodar(db: Session, client: IaClient | None = None, agora: datetime | None = None) -> None:
    global _avisou_sem_ia
    agora = agora or datetime.now(UTC)
    fonte_temas.atualizar(db, agora)
    client = client or get_ia_client()
    if client is None:
        if not _avisou_sem_ia:
            log.warning("trilha aprendizado sem IA: %s", ociosa())
            _avisou_sem_ia = True
        return
    analise_ia.recuperar_presas(db, agora)
    analise_ia.processar_uma(db, client, agora)
    classificar(db, client, agora)
