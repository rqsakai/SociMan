"""Apoio dos testes da spec 016 (trilha C): @atavernanerd conectada com os escopos de métricas
na TikTok falsa, rascunhos entregues pela trilha da 015, lembretes, posts no fake e as voltas da
trilha `metricas` chamadas à mão. Nenhum teste chama a TikTok real."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes.tiktok_fake import ESCOPOS_016
from sqlalchemy import select, text

from integration.conexao_helpers import app_tiktok, conectar  # noqa: F401
from integration.postagem_helpers import (
    LEGENDA,
    PW,
    acao,
    aprovado,
    criar_conta,
    criar_corte,
    criar_perfil,
)
from integration.publicacao_helpers import ligar_botao, video
from sociman_api import storage
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.metricas import coleta
from sociman_api.metricas import router as metricas_router
from sociman_api.metricas.models import BuscaPost, Serie, VideoRede
from sociman_api.notificacoes.models import Notificacao
from sociman_api.perfis.models import Platform
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao import registro, trilha
from sociman_api.publicacao.models import Tentativa

HANDLE = "atavernanerd"
POST_ID = "7412345678901234567"  # acima de 2^53
OUTRA = "Uma legenda sem nada a ver com o conteúdo"


def _agora() -> datetime:
    return datetime.now(UTC)


@dataclass
class M:
    client: Any
    db: Any
    fake: Any
    h: dict
    dono: Any
    perfil: dict
    conta: dict
    _n: int = 0

    # ---- cenário ----

    def rascunho(self, legenda: str = LEGENDA) -> dict:
        """Destino `criar_rascunho` entregue na TikTok falsa (`rascunho_criado`)."""
        corte = criar_corte(self.db, self.perfil["id"])
        video(self.db, corte)
        r = self.client.post("/api/agendamentos", headers=self.h, json={
            "conteudoId": str(corte.id), "contaId": self.conta["id"],
            "plannedAt": _agora().isoformat(), "modo": "criar_rascunho",
            "textos": {"descricao": legenda}})
        assert r.status_code == 201, r.text
        d = r.json()["destino"]
        for _ in range(4):
            trilha.rodar(self.db, client=self.fake.client())
            self.db.expire_all()
        assert self.destino(d["id"]).estado == DestinoEstado.rascunho_criado
        return self.api_destino(d["id"])

    def lembrete(self) -> dict:
        """Destino `lembrete` aprovado (antes do clique)."""
        corte = criar_corte(self.db, self.perfil["id"])
        return aprovado(self.client, self.h, corte.id, self.conta["id"], descricao=LEGENDA)

    def postado(self, d: dict) -> dict:
        r = acao(self.client, self.h, self.api_destino(d["id"]), "postado")
        assert r.status_code == 200, r.text
        return r.json()["destino"]

    def post(self, id: str | None = None, *, minutos: float = 0, duracao: int = 30,
             legenda: str = LEGENDA, handle: str = HANDLE) -> str:
        """Um post público na TikTok falsa, publicado há `minutos`."""
        self._n += 1
        pid = id or str(7_400_000_000_000_000_000 + self._n)
        self.fake.video(handle, pid, _agora() - timedelta(minutes=minutos), duracao=duracao,
                        legenda=legenda)
        return pid

    def publish_id(self, d: dict) -> str:
        t = self.db.scalars(select(Tentativa).where(
            Tentativa.destino_id == uuid.UUID(d["id"])).order_by(Tentativa.numero.desc())).first()
        return t.publish_id

    # ---- voltas e leituras ----

    def coletar(self, agora: datetime | None = None) -> None:
        coleta.rodar(self.db, client=self.fake.client(), agora=agora or _agora())
        self.db.expire_all()

    def destino(self, destino_id) -> Postagem:
        self.db.expire_all()
        return self.db.get(Postagem, uuid.UUID(str(destino_id)))

    def api_destino(self, destino_id) -> dict:
        r = self.client.get(f"/api/destinos/{destino_id}", headers=self.h)
        assert r.status_code == 200, r.text
        return r.json()["destino"]

    def video_de(self, pid: str) -> VideoRede:
        self.db.expire_all()
        return self.db.scalar(select(VideoRede).where(VideoRede.rede_video_id == pid))

    def busca(self, destino_id) -> BuscaPost | None:
        self.db.expire_all()
        return self.db.get(BuscaPost, uuid.UUID(str(destino_id)))

    def vinculo(self, destino_id) -> dict:
        r = self.client.get(f"/api/destinos/{destino_id}/vinculo", headers=self.h)
        assert r.status_code == 200, r.text
        return r.json()

    def ligar(self, d: dict, h: dict | None = None, **body):
        version = self.api_destino(d["id"])["version"]
        return self.client.post(f"/api/destinos/{d['id']}/vinculo", headers=h or self.h,
                                json={"version": version, **body})

    def desfazer(self, d: dict, h: dict | None = None):
        version = self.api_destino(d["id"])["version"]
        return self.client.post(f"/api/destinos/{d['id']}/vinculo/desfazer",
                                headers=h or self.h, json={"version": version})

    def versoes(self, destino_id) -> list[EntityVersion]:
        self.db.expire_all()
        return list(self.db.scalars(select(EntityVersion).where(
            EntityVersion.entity_type == "postagem",
            EntityVersion.entity_id == uuid.UUID(str(destino_id))).order_by(
                EntityVersion.version)))

    def avisos(self, tipo: str) -> list[Notificacao]:
        self.db.expire_all()
        return list(self.db.scalars(select(Notificacao).where(
            text("tipo::text = :t").bindparams(t=tipo))))


@pytest.fixture
def m(client, db, app_tiktok, publicacao_habilitada, monkeypatch, make_user,  # noqa: F811
      login) -> M:
    """Dono, perfil e @atavernanerd conectada com os escopos de métricas; publicação ligada
    (para entregar rascunhos); a série nasce na 1ª volta da trilha `metricas`."""
    publicacao_habilitada(True)
    ligar_botao(True)
    storage.ensure_buckets()
    monkeypatch.setattr(trilha, "STATUS_PRIMEIRO", timedelta(0))
    monkeypatch.setattr(registro.executor_para(Platform.tiktok), "recuos_parte", (0.0, 0.0, 0.0))
    app.dependency_overrides[metricas_router.cliente_rede] = app_tiktok.client
    dono = make_user(role="dono", name="Dono")
    h = login(client, dono.email, PW)
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], "tiktok", HANDLE)
    conectar(client, h, conta, app_tiktok, escopos=ESCOPOS_016)
    cena = M(client, db, app_tiktok, h, dono, perfil, conta)
    cena.coletar()
    assert db.scalar(select(Serie).where(Serie.conta_id == uuid.UUID(conta["id"])))
    return cena


def err(r) -> str:
    return r.json()["error"]["code"]



# ---- semeadura direta (US4 e US5): séries, vídeos e fotos por INSERT, sem a trilha ----

@dataclass
class Semeado:
    serie_id: uuid.UUID
    videos: list[uuid.UUID]


def semear(db, conta_id, *, videos: int = 3, fotos: int = 5, inicio: datetime | None = None,
           passo_h: float = 1.0, intervalo_h: float = 24.0, views_por_h: int = 100,
           duracao: int = 30, legenda: str = "Post de teste #fyp", serie_id=None) -> Semeado:
    """Uma série viva da conta com `videos` vídeos publicados a cada `intervalo_h` a partir de
    `inicio`, cada um com `fotos` fotos a cada `passo_h` (views crescendo `views_por_h`) e uma
    foto da conta por dia. Os ids da rede passam de 2^53."""
    from sociman_api.metricas.models import FotoConta, FotoVideo

    inicio = inicio or _agora() - timedelta(days=10)
    if serie_id is None:
        serie = Serie(rede=Platform.tiktok, conta_id=uuid.UUID(str(conta_id)))
        db.add(serie)
        db.flush()
        serie_id = serie.id
    ids = []
    base = 7_450_000_000_000_000_000 + len(db.scalars(select(VideoRede.id)).all())
    for i in range(videos):
        pub = inicio + timedelta(hours=intervalo_h * i)
        v = VideoRede(serie_id=serie_id, rede_video_id=str(base + i),
                      share_url=f"https://www.tiktok.com/@x/video/{base + i}",
                      legenda=legenda, duracao_s=duracao, publicado_em=pub, descoberto_em=pub)
        db.add(v)
        db.flush()
        ids.append(v.id)
        for k in range(1, fotos + 1):
            idade_s = int(passo_h * 3600 * k)
            db.add(FotoVideo(video_id=v.id, coletado_em=pub + timedelta(seconds=idade_s),
                             idade_s=idade_s, alvo_idade_min=idade_s // 60,
                             views=views_por_h * k * (i + 1), likes=10 * k, comments=k,
                             shares=k))
    dias = int((videos * intervalo_h) // 24) + 2
    # outra semeadura na mesma série pode já ter a janela (uq_metricas_conta_fotos_janela)
    existentes = set(db.scalars(select(FotoConta.janela_em).where(FotoConta.serie_id == serie_id)))
    for d in range(dias):
        janela = (inicio + timedelta(days=d)).replace(minute=0, second=0, microsecond=0)
        if janela in existentes:
            continue
        db.add(FotoConta(serie_id=serie_id, coletado_em=janela, janela_em=janela,
                         seguidores=1000 + d, seguindo=10, curtidas=5000 + d, videos=videos))
    db.commit()
    return Semeado(serie_id, ids)
