"""Apoio dos testes de conexão da spec 015 (trilha B): app configurado, TikTok falsa nas rotas e
`conectar()` de ponta a ponta (iniciar → retorno). Nenhum teste chama a TikTok real."""

import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image
from pydantic import SecretStr

from sociman_api.config import get_settings
from sociman_api.main import app
from sociman_api.publicacao import conexoes
from sociman_api.publicacao.router import cliente_rede
from sociman_api.redis import get_redis

WEB = "https://192.168.86.47:8543/app/conexoes/retorno"
DESKTOP = "http://localhost:8180/app/conexoes/retorno"
HOST_WEB = {"Host": "192.168.86.47"}
HOST_DESKTOP = {"Host": "localhost"}


def _png(lado: int = 128) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (lado, lado), (200, 40, 90)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def app_tiktok(monkeypatch, tiktok_fake, s3):
    """App da TikTok configurado (valores só de teste), os dois endereços de login e a TikTok
    falsa como cliente das rotas. O avatar do fake vira uma imagem válida (128 px)."""
    s = get_settings()
    monkeypatch.setattr(s, "tiktok_client_key", SecretStr("chave-de-teste"))
    monkeypatch.setattr(s, "tiktok_client_secret", SecretStr("segredo-de-teste"))
    monkeypatch.setattr(s, "tiktok_redirect_web", WEB)
    monkeypatch.setattr(s, "tiktok_redirect_desktop", DESKTOP)
    import fakes.tiktok_fake as modulo

    monkeypatch.setattr(modulo, "AVATAR_PNG", _png())
    app.dependency_overrides[cliente_rede] = tiktok_fake.client
    return tiktok_fake


def state_de(url: str) -> str:
    return parse_qs(urlsplit(url).query)["state"][0]


def redis_state(state: str) -> dict:
    return json.loads(get_redis().get(conexoes.STATE_KEY.format(state)))


def iniciar(client, h, conta_id, host=None) -> str:
    r = client.post(f"/api/contas/{conta_id}/conexao/iniciar", headers={**h, **(host or HOST_WEB)})
    assert r.status_code == 200, r.text
    return r.json()["autorizarUrl"]


def conectar(client, h, conta: dict, fake, *, username: str | None = None,
             open_id: str | None = None, host=None, **usuario) -> dict:
    """Conecta a conta pelo fluxo real (iniciar → TikTok falsa → retorno); devolve a resposta."""
    url = iniciar(client, h, conta["id"], host)
    state = state_de(url)
    verifier = redis_state(state).get("codeVerifier")
    code = f"code-{state[:8]}"
    fake.usuario(code, username if username is not None else conta["handle"],
                 open_id=open_id, verifier=verifier, **usuario)
    r = client.post("/api/conexoes/retorno", headers=h, json={"state": state, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


def retorno(client, h, conta_id, fake, username, host=None, **usuario):
    """Como `conectar`, mas devolve a resposta crua (para os erros)."""
    url = iniciar(client, h, conta_id, host)
    state = state_de(url)
    verifier = redis_state(state).get("codeVerifier")
    code = f"code-{state[:8]}"
    fake.usuario(code, username, verifier=verifier, **usuario)
    return client.post("/api/conexoes/retorno", headers=h, json={"state": state, "code": code})


def destino_auto(db, perfil_id, conta_id, dono, *, estado: str = "agendado",
                 modo: str = "criar_rascunho", planned_at=None, **extra):
    """Destino automático gravado direto no banco (a API de agendar é da trilha C)."""
    from datetime import UTC, datetime, timedelta

    from integration.postagem_helpers import criar_corte
    from sociman_api.conteudos.models import Modo
    from sociman_api.postagem.models import DestinoEstado, Postagem

    corte = criar_corte(db, perfil_id)
    agora = datetime.now(UTC)
    destino = Postagem(
        conteudo_id=corte.id, conta_id=conta_id, estado=DestinoEstado(estado), modo=Modo(modo),
        planned_at=planned_at or agora + timedelta(hours=1), aprovado_por=dono.id,
        aprovado_em=agora, agendado_por=dono.id, agendado_em=agora, version=1,
        created_by=dono.id, **extra)
    db.add(destino)
    db.commit()
    return destino
