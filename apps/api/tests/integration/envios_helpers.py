"""Auxiliares dos testes da Trilha B da 006 (envios, OpenShorts, importação e revisão).

Canais e vídeos entram direto pelo modelo (sem a API da Trilha A). Os testes importam as
fixtures explicitamente: `from integration.envios_helpers import owner, member, perfil  # noqa`.
"""

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from sociman_api import storage
from sociman_api.canais.models import CanalDireito, CanalFonte, VideoFonte
from sociman_api.db import get_sessionmaker
from sociman_api.envios.models import Envio

PW = "senha-forte-123"
_seq = itertools.count(1)


@pytest.fixture(scope="module", autouse=True)
def _buckets():
    storage.ensure_buckets()


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def member(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


def criar_perfil(client, h, slug: str = "taverna") -> dict:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


@pytest.fixture
def perfil(client, owner) -> dict:
    return criar_perfil(client, owner[1])


def _id(prefix: str, size: int) -> str:
    n = str(next(_seq))
    return (prefix + "x" * size)[: size - len(n)] + n


def criar_canal(direito: CanalDireito = CanalDireito.sem_acordo, title: str = "Canal") -> CanalFonte:
    with get_sessionmaker()() as s:
        canal = CanalFonte(youtube_channel_id="UC" + _id("canal", 22), title=title,
                           uploads_playlist_id="UU" + _id("up", 22), direito=direito)
        s.add(canal)
        s.commit()
        s.refresh(canal)
        s.expunge(canal)
        return canal


def criar_video(canal: CanalFonte, *, disponivel: bool = True, title: str = "Vídeo legal",
                duration_s: int = 1200) -> VideoFonte:
    with get_sessionmaker()() as s:
        video = VideoFonte(canal_id=canal.id, youtube_video_id=_id("vid", 11), title=title,
                           published_at=datetime.now(UTC) - timedelta(days=3),
                           duration_s=duration_s, disponivel=disponivel,
                           next_metrics_at=datetime.now(UTC))
        s.add(video)
        s.commit()
        s.refresh(video)
        s.expunge(video)
        return video


def selecionar(client, h, perfil_id: str, **body: Any):
    return client.post(f"/api/perfis/{perfil_id}/envios", json=body, headers=h)


def selecionado(client, h, perfil_id: str, video: VideoFonte | None = None, **body: Any) -> dict:
    if video is not None:
        body["videoFonteId"] = str(video.id)
    r = selecionar(client, h, perfil_id, **body)
    assert r.status_code == 201, r.text
    return r.json()["envio"]


def enviar(client, h, envios: list[dict], **body: Any):
    items = [{"envioId": e["id"], "version": e["version"]} for e in envios]
    return client.post("/api/envios/enviar", json={"items": items} | body, headers=h)


def enviado(client, h, perfil_id: str, video: VideoFonte | None = None, **body: Any) -> dict:
    """Seleciona e envia (confirmando o aviso), devolvendo o envio `na_fila`."""
    e = selecionado(client, h, perfil_id, video, **body)
    r = enviar(client, h, [e], confirmarAviso=True)
    assert r.status_code == 200, r.text
    return r.json()["items"][0]


def envio_row(db: Session, envio_id: str | uuid.UUID) -> Envio:
    db.expire_all()
    envio = db.get(Envio, uuid.UUID(str(envio_id)))
    assert envio is not None
    return envio
