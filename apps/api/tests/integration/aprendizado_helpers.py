"""Apoio dos testes da spec 023 (aprendizado). Reaproveita a cena da 019 (`analytics_helpers`:
dono, perfil, @atavernanerd e a cadeia do SociMan) e semeia posts com a medida de 24 h por
INSERT (vídeos e fotos), temas pela API do dono e classificações direto no banco.

`semear_aprendizado` monta o cenário de referência:
- @atavernanerd (TikTok) com 20 posts: Marvel (8, ~1.000 views, sempre com o bloco
  #multiversomarvel #vingadoresdoomsday #geek), Games (8, ~100 views, #games) e Anime (4, com 1
  viral);
- @segundaconta (YouTube, mesmo perfil) com 16 posts, 12 deles com até 1 view (a "travada";
  a estagnação vem de `fatores.estagnados`, trocada pelo teste quando precisa);
- vídeos-fonte com palavras-chave dos temas.

Nenhum teste chama serviço real.
"""

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from integration.analytics_helpers import Cena, agora, local
from integration.postagem_helpers import PW, criar_conta, criar_perfil, membro
from sociman_api.aprendizado import fatores
from sociman_api.aprendizado.models import Classificacao, EstiloGancho, Origem
from sociman_api.canais.models import CanalDireito, CanalPerfil
from sociman_api.ia.cliente import get_ia_client
from sociman_api.main import app
from sociman_api.metricas.models import FotoVideo, Serie, VideoRede
from sociman_api.perfis.models import Conta, Platform

IDADES_H = (1, 6, 12, 24, 30)
BLOCO = "#multiversomarvel #vingadoresdoomsday #geek"
_seq = itertools.count(1)


@dataclass
class Ap:
    c: Cena
    conta_b: dict | None = None
    temas: dict[str, dict] = field(default_factory=dict)
    posts: dict[str, list[uuid.UUID]] = field(default_factory=dict)

    @property
    def client(self):
        return self.c.client

    @property
    def db(self):
        return self.c.db

    @property
    def h(self) -> dict:
        return self.c.h

    @property
    def perfil_id(self) -> str:
        return self.c.perfil["id"]

    @property
    def url(self) -> str:
        return f"/api/perfis/{self.perfil_id}/aprendizado"

    # ---- semeadura ----

    def serie(self, conta: dict) -> uuid.UUID:
        conta_id = uuid.UUID(conta["id"])
        sid = self.db.scalar(select(Serie.id).where(Serie.conta_id == conta_id,
                                                    Serie.anonimizada_em.is_(None)))
        if sid is None:
            rede = self.db.get(Conta, conta_id).platform
            serie = Serie(rede=Platform(rede), conta_id=conta_id,
                          criada_em=agora() - timedelta(days=60))
            self.db.add(serie)
            self.db.flush()
            sid = serie.id
        return sid

    def post(self, conta: dict | None = None, *, dias: int = 3, hora: int = 12,
             views: int = 100, legenda: str = "Post de teste", duracao: int = 30,
             publicado: datetime | None = None) -> uuid.UUID:
        """Um post com fotos até 30 h (a medida de 24 h = `views`)."""
        conta = conta or self.c.conta
        sid = self.serie(conta)
        pub = publicado or local(dias, hora)
        n = next(_seq)
        v = VideoRede(serie_id=sid, rede_video_id=str(7_460_000_000_000_000_000 + n),
                      share_url=f"https://www.tiktok.com/@x/video/{n}", legenda=legenda,
                      duracao_s=duracao, publicado_em=pub, descoberto_em=pub,
                      largura=1080, altura=1920)
        self.db.add(v)
        self.db.flush()
        for h in IDADES_H:
            if pub + timedelta(hours=h) > agora():
                break
            idade = h * 3600
            self.db.add(FotoVideo(video_id=v.id, coletado_em=pub + timedelta(hours=h),
                                  idade_s=idade, alvo_idade_min=idade // 60,
                                  views=round(views * min(h, 24) / 24), likes=1, comments=0,
                                  shares=0))
        self.db.commit()
        return v.id

    def tema(self, nome: str, palavras: list[str] | None = None, h: dict | None = None) -> dict:
        r = self.client.post(f"{self.url}/temas", headers=h or self.h,
                             json={"nome": nome, "palavrasChave": palavras or []})
        assert r.status_code == 201, r.text
        self.temas[nome] = r.json()
        return r.json()

    def classificar(self, video_id: uuid.UUID, tema: str | None,
                    estilo: str | None = "pergunta", origem: Origem = Origem.ia) -> None:
        """Uma classificação direta (a trilha é testada à parte)."""
        tema_id = uuid.UUID(self.temas[tema]["id"]) if tema else None
        self.db.add(Classificacao(video_id=video_id, perfil_id=uuid.UUID(self.perfil_id),
                                  tema_id=tema_id, origem=origem, evidencia_parcial=True,
                                  estilo_gancho=EstiloGancho(estilo) if estilo else None,
                                  taxonomia_versao=1))
        self.db.commit()

    def casar(self) -> None:
        """A volta da trilha que casa os vídeos-fonte com os temas (plano B do R9)."""
        from sociman_api.aprendizado import fonte_temas

        fonte_temas.atualizar(self.db)
        self.db.expire_all()

    # ---- leitura ----

    def get(self, rota: str, h: dict | None = None, status: int = 200, **params) -> Any:
        r = self.client.get(f"{self.url}/{rota}", headers=h or self.h, params=params)
        assert r.status_code == status, r.text
        return r.json()

    def efeito(self, analise: dict, fator: str, valor: str, parte: str = "rendimento") -> dict:
        return next(e for e in analise["efeitos"]
                    if e["fator"] == fator and e["valor"] == valor and e["parte"] == parte)


def semear_aprendizado(ap: Ap, com_classificacao: bool = True, conta_b: bool = True) -> Ap:
    for nome, palavras in (("Marvel", ["marvel", "vingadores"]), ("Games", ["games", "jogo"]),
                           ("Anime", ["anime"])):
        ap.tema(nome, palavras)
    a = ap.c.conta
    marvel = [ap.post(a, dias=d, hora=18, views=1000 + 50 * d, legenda=f"Marvel {d} {BLOCO}")
              for d in range(2, 10)]
    games = [ap.post(a, dias=d, hora=9, views=100 + 5 * d, legenda=f"Games {d} #games")
             for d in range(10, 18)]
    anime = [ap.post(a, dias=d, hora=12, views=v, legenda=f"Anime {d}")
             for d, v in zip(range(18, 22), (300, 300, 300, 30000), strict=True)]
    ap.posts = {"Marvel": marvel, "Games": games, "Anime": anime}
    if com_classificacao:
        for nome, ids in ap.posts.items():
            for vid in ids:
                ap.classificar(vid, nome)
    if conta_b:
        ap.conta_b = ap.c.segunda_conta(platform="youtube")
        ap.posts["b_altos"] = [ap.post(ap.conta_b, dias=d, views=1000, legenda="B alto")
                               for d in range(2, 6)]
        ap.posts["b_baixos"] = [ap.post(ap.conta_b, dias=d, views=1, legenda="B baixo")
                                for d in range(6, 18)]
    return ap


def canal_do_perfil(ap: Ap, direito: CanalDireito = CanalDireito.sem_acordo,
                    titulo: str = "Canal Fonte"):
    canal = ap.c.canal(direito=direito, titulo=titulo)
    ap.db.add(CanalPerfil(canal_id=canal.id, perfil_id=uuid.UUID(ap.perfil_id)))
    ap.db.commit()
    return canal


@pytest.fixture
def ap(cena) -> Ap:
    return Ap(cena)


@pytest.fixture
def fake(anthropic_fake):
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    return anthropic_fake


@pytest.fixture
def estagnados(monkeypatch):
    """Troca a estagnação da 019 por um conjunto escolhido pelo teste (a regra tem teste
    próprio na 019); `set()` = ninguém estagnado."""
    escolhidos: set[uuid.UUID] = set()
    monkeypatch.setattr(fatores, "estagnados", lambda db, posts, agora: set(escolhidos))
    return escolhidos


def err(r) -> str:
    return r.json()["error"]["code"]


__all__ = [
    "PW",
    "Ap",
    "ap",
    "canal_do_perfil",
    "criar_conta",
    "criar_perfil",
    "err",
    "estagnados",
    "fake",
    "membro",
    "semear_aprendizado",
]
