"""Apoio dos testes da execução da spec 015 (trilha C): conta TikTok conectada na TikTok falsa,
corte pronto com o vídeo no MinIO de teste, agendamento pela API e voltas da trilha.

Nenhum teste chama a TikTok real: o cliente da trilha é o `TikTokCliente` com o transporte do
fake (`tiktok_fake.client()`).
"""

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

from integration.conexao_helpers import app_tiktok, conectar  # noqa: F401
from integration.postagem_helpers import LEGENDA, PW, criar_conta, criar_corte, criar_perfil
from sociman_api import storage
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Platform
from sociman_api.postagem.models import Postagem
from sociman_api.publicacao import registro, trilha
from sociman_api.publicacao.models import Tentativa

MUSICA = "Ao postar, você concorda com a Confirmação de Uso de Música da TikTok."
MARCA = ("Ao postar, você concorda com a Política de Conteúdo de Marca e com a Confirmação de "
         "Uso de Música da TikTok.")


def opcoes(**kw) -> dict:
    """As escolhas da tela obrigatória do Publicar (US3), válidas no sandbox."""
    base = {"privacidade": "SELF_ONLY", "permitirComentario": True, "permitirDueto": False,
            "permitirCostura": False, "comercial": "nenhum", "conteudoIa": False,
            "consentimento": {"texto": MUSICA, "aceitoEm": datetime.now(UTC).isoformat()}}
    return {**base, **kw}


def ligar_botao(valor: bool = True) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE publicacao_config SET envios_habilitados = :v WHERE id = 1"),
                     {"v": valor})


def video(db, corte, tamanho: int = 3000) -> bytes:
    """Grava bytes de vídeo (conteúdo qualquer: a TikTok falsa não decodifica) no
    `result_key` do corte, no bucket de vídeos de teste."""
    dados = os.urandom(tamanho)
    storage.put(corte.result_key, dados, "video/mp4", bucket="videos")
    return dados


@dataclass
class Cena:
    client: Any
    db: Any
    fake: Any
    h: dict
    dono: Any
    perfil: dict
    conta: dict

    def corte(self, tamanho: int = 3000):
        corte = criar_corte(self.db, self.perfil["id"])
        video(self.db, corte, tamanho)
        return corte

    def agendar(self, corte, quando: datetime | None = None, h: dict | None = None,
                conta: dict | None = None, **body):
        body["textos"] = {"descricao": LEGENDA, **(body.get("textos") or {})}
        return self.client.post("/api/agendamentos", headers=h or self.h, json={
            "conteudoId": str(corte.id), "contaId": (conta or self.conta)["id"],
            "plannedAt": (quando or datetime.now(UTC)).isoformat(), "modo": "criar_rascunho",
            **body})

    def agendado(self, tamanho: int = 3000, **body) -> dict:
        r = self.agendar(self.corte(tamanho), **body)
        assert r.status_code == 201, r.text
        return r.json()["destino"]

    def rodar(self, voltas: int = 1) -> None:
        for _ in range(voltas):
            trilha.rodar(self.db, client=self.fake.client())
            self.db.expire_all()

    def destino(self, destino_id) -> Postagem:
        self.db.expire_all()
        return self.db.get(Postagem, uuid.UUID(str(destino_id)))

    def tentativas(self, destino_id) -> list[Tentativa]:
        self.db.expire_all()
        return list(self.db.scalars(select(Tentativa).where(
            Tentativa.destino_id == uuid.UUID(str(destino_id))).order_by(Tentativa.numero)))

    def versoes(self, destino_id) -> list[EntityVersion]:
        self.db.expire_all()
        return list(self.db.scalars(select(EntityVersion).where(
            EntityVersion.entity_type == "postagem",
            EntityVersion.entity_id == uuid.UUID(str(destino_id))).order_by(
                EntityVersion.version)))


@pytest.fixture
def cena(client, db, app_tiktok, publicacao_habilitada, monkeypatch, make_user,  # noqa: F811
         login) -> Cena:
    """Dono, perfil e @atavernanerd conectada na TikTok falsa; os dois níveis do interruptor
    ligados; status consultado sem espera e partes sem recuo (testes rápidos)."""
    publicacao_habilitada(True)
    ligar_botao(True)
    storage.ensure_buckets()
    monkeypatch.setattr(trilha, "STATUS_PRIMEIRO", timedelta(0))
    monkeypatch.setattr(registro.executor_para(Platform.tiktok), "recuos_parte", (0.0, 0.0, 0.0))
    dono = make_user(role="dono", name="Dono")
    h = login(client, dono.email, PW)
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], "tiktok", "atavernanerd")
    conectar(client, h, conta, app_tiktok)
    return Cena(client, db, app_tiktok, h, dono, perfil, conta)
