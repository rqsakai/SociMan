"""Apoio dos testes da spec 019 (analytics): reusa a semeadura da 016 (`metricas_helpers.semear`,
séries, vídeos e fotos por INSERT) e acrescenta a cadeia do SociMan por trás de um vídeo
(canal → envio → corte → conteúdo → destino), uma segunda conta, custo de IA e vídeos-fonte.

Datas sempre relativas a "agora" no fuso da casa (`local(dias_atras, hora)`). Os testes importam
as fixtures explicitamente: `from integration.analytics_helpers import cena, membro  # noqa`.
Nenhum teste chama serviço real.
"""

import itertools
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import update

from integration.metricas_helpers import Semeado, semear
from integration.postagem_helpers import (  # noqa: F401 — fixture `membro` reexportada
    PW,
    criar_conta,
    criar_corte,
    criar_perfil,
    membro,
)
from sociman_api.canais.models import CanalDireito, CanalFonte, VideoFonte
from sociman_api.conteudos.models import Conteudo, Modo
from sociman_api.cortes.models import CorteOrigem
from sociman_api.envios.models import DireitoEnvio, Envio, EnvioOrigem, EnvioStatus
from sociman_api.ia.models import IaChamada
from sociman_api.metricas.models import Serie, VideoRede, VinculoMetodo
from sociman_api.perfis.models import Conta
from sociman_api.postagem.models import DestinoEstado, Postagem

HANDLE = "atavernanerd"
TZ = ZoneInfo("America/Sao_Paulo")
CONFIG = {"clip_min_s": 15, "clip_max_s": 60, "quantidade": None, "layout": "auto",
          "formato": "vertical", "legenda": "kit"}
_seq = itertools.count(1)


def agora() -> datetime:
    return datetime.now(UTC)


def hoje_sp():
    return datetime.now(TZ).date()


def local(dias_atras: int = 0, hora: int = 12, minuto: int = 0) -> datetime:
    """`hora:minuto` de `dias_atras` dias antes de hoje, no fuso de São Paulo."""
    return datetime.combine(hoje_sp() - timedelta(days=dias_atras), time(hora, minuto), TZ)


def _id_youtube() -> str:
    n = str(next(_seq))
    return ("v" * 11)[: 11 - len(n)] + n


@dataclass
class Cena:
    client: Any
    db: Any
    h: dict
    dono: Any
    perfil: dict
    conta: dict

    # ---- métricas (016) ----

    def semear(self, conta: dict | None = None, **kw) -> Semeado:
        """`metricas_helpers.semear` na conta (padrão: a principal). Para mais vídeos na mesma
        série, passe `serie_id`."""
        return semear(self.db, (conta or self.conta)["id"], **kw)

    # ---- a cadeia do SociMan ----

    def canal(self, direito: CanalDireito = CanalDireito.sem_acordo,
              titulo: str = "Canal Fonte") -> CanalFonte:
        n = next(_seq)
        canal = CanalFonte(youtube_channel_id=f"UC{n:022d}", title=titulo,
                           uploads_playlist_id=f"UU{n:022d}", direito=direito)
        self.db.add(canal)
        self.db.commit()
        return canal

    def envio(self, perfil_id, *, canal: CanalFonte | None = None,
              status: EnvioStatus = EnvioStatus.pronto, config: dict | None = None,
              sent_at: datetime | None = None, started_at: datetime | None = None,
              finished_at: datetime | None = None) -> Envio:
        """Envio já enviado (com `config` e `direito_no_envio`); com canal, nasce de um vídeo-fonte
        dele."""
        video_fonte_id = None
        if canal is not None:
            [vf] = self.videos_fonte(1, canal=canal)
            video_fonte_id = vf.id
        momento = sent_at or agora() - timedelta(days=1)
        envio = Envio(
            perfil_id=uuid.UUID(str(perfil_id)),
            origem=EnvioOrigem.canal if canal is not None else EnvioOrigem.avulso_link,
            video_fonte_id=video_fonte_id, canal_fonte_id=canal.id if canal else None,
            source_url="https://www.youtube.com/watch?v=" + _id_youtube(),
            source_title="Vídeo de origem", status=status, config=config or dict(CONFIG),
            direito_no_envio=DireitoEnvio(canal.direito.value) if canal else DireitoEnvio.avulso,
            aviso_confirmado=True, sent_at=momento, started_at=started_at or momento,
            finished_at=finished_at or momento + timedelta(minutes=20),
            created_by=self.dono.id)
        self.db.add(envio)
        self.db.commit()
        return envio

    def vincular(self, video_id, *, corte=None, canal: CanalFonte | None = None,
                 modo: Modo = Modo.lembrete, hashtags: list[str] | None = None,
                 aprovado_em: datetime | None = None, posted_at: datetime | None = None,
                 estado: DestinoEstado | None = None, score: int | None = 70,
                 gancho: str = "Você usa isso?", config: dict | None = None) -> Postagem:
        """Liga o vídeo a um destino da conta da série dele, criando envio → corte → conteúdo →
        destino (o corte e o conteúdo têm o mesmo id). `corte` existente pula envio e corte."""
        video = self.db.get(VideoRede, uuid.UUID(str(video_id)))
        serie = self.db.get(Serie, video.serie_id)
        conta_id = serie.conta_id
        perfil_id = self.db.get(Conta, conta_id).perfil_id
        if corte is None:
            envio = self.envio(perfil_id, canal=canal, config=config)
            corte = criar_corte(self.db, perfil_id, origem=CorteOrigem.openshorts,
                                envio_id=envio.id, clip_index=next(_seq),
                                openshorts_score=score, hook_text=gancho)
        momento = aprovado_em or video.publicado_em - timedelta(hours=1)
        if estado is None:
            estado = DestinoEstado.postado if modo == Modo.lembrete else DestinoEstado.publicado
        destino = Postagem(conteudo_id=corte.id, conta_id=conta_id, estado=estado, modo=modo,
                           hashtags=list(hashtags or []), aprovado_por=self.dono.id,
                           aprovado_em=momento, posted_at=posted_at or video.publicado_em,
                           version=1, created_by=self.dono.id)
        self.db.add(destino)
        self.db.flush()
        self.db.execute(update(VideoRede).where(VideoRede.id == video.id).values(
            destino_id=destino.id, vinculo_metodo=VinculoMetodo.escolha,
            vinculado_em=agora()))
        self.db.commit()
        return destino

    def segunda_conta(self, handle: str = "segundaconta", *, outro_perfil: bool = False,
                      platform: str = "tiktok") -> dict:
        """Mais uma conta, no mesmo perfil (padrão) ou num perfil novo. O perfil só tem uma
        conta ativa por rede (409 `active_platform_exists`): outra TikTok no mesmo perfil não
        dá; use `outro_perfil=True` ou outra `platform`."""
        perfil_id = criar_perfil(self.client, self.h, "Outro Perfil")["id"] if outro_perfil \
            else self.perfil["id"]
        return criar_conta(self.client, self.h, perfil_id, platform, handle)

    def custo_ia(self, conteudo_id, usd: str | float | Decimal,
                 quando: datetime | None = None) -> IaChamada:
        """Uma chamada do assistente ligada ao conteúdo, com o custo dado."""
        conteudo_id = uuid.UUID(str(conteudo_id))
        conteudo = self.db.get(Conteudo, conteudo_id)
        chamada = IaChamada(tipo_campo="postagem.textos", perfil_id=conteudo.perfil_id,
                            entity_type="postagem", conteudo_id=conteudo_id,
                            model="claude-fake", prompt_version="ia/2", duration_ms=1,
                            custo_usd=Decimal(str(usd)), created_at=quando or agora(),
                            created_by=self.dono.id)
        self.db.add(chamada)
        self.db.commit()
        return chamada

    def videos_fonte(self, n: int, *, canal: CanalFonte | None = None,
                     publicado_em: datetime | None = None, views: int | None = 1000,
                     vph_recente: Decimal | float | None = None, **campos) -> list[VideoFonte]:
        """`n` vídeos-fonte do canal (um novo se não vier), publicados em `publicado_em`
        (padrão: há 2 dias)."""
        canal = canal or self.canal()
        out = []
        for _ in range(n):
            v = VideoFonte(canal_id=canal.id, youtube_video_id=_id_youtube(),
                           title="Vídeo de origem",
                           published_at=publicado_em or agora() - timedelta(days=2),
                           duration_s=1200, views=views,
                           vph_recente=Decimal(str(vph_recente)) if vph_recente is not None
                           else None, next_metrics_at=agora(), **campos)
            self.db.add(v)
            out.append(v)
        self.db.commit()
        return out

    # ---- leitura ----

    def get(self, aba: str, h: dict | None = None, **params):
        return self.client.get(f"/api/analytics/{aba}", headers=h or self.h, params=params)

    def ok(self, aba: str, h: dict | None = None, **params) -> dict:
        r = self.get(aba, h, **params)
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def cena(client, db, make_user, login) -> Cena:
    """Dono, um perfil e @atavernanerd (sem conexão: a semeadura é direta)."""
    dono = make_user(role="dono", name="Dono")
    h = login(client, dono.email, PW)
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], "tiktok", HANDLE)
    return Cena(client, db, h, dono, perfil, conta)


def err(r) -> str:
    return r.json()["error"]["code"]
