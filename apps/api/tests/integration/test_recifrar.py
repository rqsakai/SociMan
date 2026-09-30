"""`sociman tokens recifrar` (spec 015, T024, R4): regrava com a chave atual o que foi cifrado
com a anterior, e só imprime contagens."""

import base64
import uuid
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr
from sqlalchemy import select, text
from typer.testing import CliRunner

from sociman_api.cli import app
from sociman_api.config import get_settings
from sociman_api.db import get_engine
from sociman_api.publicacao import cifra
from sociman_api.publicacao.models import ConexaoCredencial, Tentativa

runner = CliRunner()
VELHA = base64.urlsafe_b64encode(b"v" * 32).decode()
NOVA = base64.urlsafe_b64encode(b"n" * 32).decode()


def _chaves(monkeypatch, atual: str, anterior: str = "") -> None:
    s = get_settings()
    monkeypatch.setattr(s, "sociman_tokens_key", SecretStr(atual))
    monkeypatch.setattr(s, "sociman_tokens_key_anterior", SecretStr(anterior))


def _semear(dono) -> tuple[uuid.UUID, uuid.UUID]:
    perfil, conta, conexao, conteudo, destino, tentativa = (uuid.uuid4() for _ in range(6))
    agora = datetime.now(UTC)
    access, kid = cifra.cifrar("act.velho", cifra.aad(conexao, "access"))
    refresh, _ = cifra.cifrar("rft.velho", cifra.aad(conexao, "refresh"))
    link, _ = cifra.cifrar("https://up/?upload_token=velho", cifra.aad(tentativa, "upload"))
    with get_engine().begin() as conn:
        conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, 'p-rec', 'T')"),
                     {"id": perfil})
        conn.execute(text("INSERT INTO contas (id, perfil_id, platform, handle, url) VALUES "
                          "(:id, :p, 'tiktok', 'um', 'https://www.tiktok.com/@um')"),
                     {"id": conta, "p": perfil})
        conn.execute(text(
            "INSERT INTO conexoes (id, conta_id, rede, open_id, username, escopos, estado, "
            "conectado_por, conectado_em) VALUES (:id, :c, 'tiktok', 'o', 'um', "
            "ARRAY['video.upload'], 'conectada', :u, now())"), {"id": conexao, "c": conta,
                                                                  "u": dono})
        conn.execute(text(
            "INSERT INTO conexao_credenciais (conexao_id, key_id, access_cifrado, "
            "access_expira_em, refresh_cifrado, refresh_expira_em) VALUES (:c, :k, :a, :ae, "
            ":r, :re)"), {"c": conexao, "k": kid, "a": access, "ae": agora + timedelta(hours=1),
                          "r": refresh, "re": agora + timedelta(days=300)})
        conn.execute(text(
            "INSERT INTO conteudos (id, perfil_id, origem, video_key, poster_key, duration_ms) "
            "VALUES (:id, :p, 'video_proprio', 'v.mp4', 'poster.jpg', 1000)"),
            {"id": conteudo, "p": perfil})
        conn.execute(text("INSERT INTO postagens (id, conteudo_id, conta_id) VALUES (:id, :c, :k)"),
                     {"id": destino, "c": conteudo, "k": conta})
        conn.execute(text(
            "INSERT INTO publicacao_tentativas (id, destino_id, numero, conexao_id, rede, modo, "
            "fase, disparo, video_ref, video_etag, video_bytes, chunk_size, total_partes, "
            "publish_id, upload_url_cifrado) VALUES (:id, :d, 1, :c, 'tiktok', 'criar_rascunho', "
            "'enviando_partes', 'agendador', 'k', 'e', 10, 10, 1, 'p-1', :l)"),
            {"id": tentativa, "d": destino, "c": conexao, "l": link})
    return conexao, tentativa


def test_recifra_com_a_chave_atual(monkeypatch, make_user, db):
    _chaves(monkeypatch, VELHA)
    conexao, tentativa = _semear(make_user(role="dono").id)
    _chaves(monkeypatch, NOVA, anterior=VELHA)

    r = runner.invoke(app, ["tokens", "recifrar"])
    assert r.exit_code == 0, r.output
    assert "Credenciais regravadas: 1; já na chave atual: 0; links de envio regravados: 1" \
        in r.output
    assert "velho" not in r.output and NOVA not in r.output and VELHA not in r.output

    _chaves(monkeypatch, NOVA)  # a anterior sai do .env: tudo decifra só com a nova
    cred = db.scalar(select(ConexaoCredencial))
    assert cred.key_id == cifra.key_id_atual()
    assert cifra.decifrar(cred.access_cifrado, cifra.aad(conexao, "access"),
                          cred.key_id) == "act.velho"
    assert cifra.decifrar(cred.refresh_cifrado, cifra.aad(conexao, "refresh"),
                          cred.key_id) == "rft.velho"
    t = db.get(Tentativa, tentativa)
    assert cifra.decifrar(t.upload_url_cifrado, cifra.aad(tentativa, "upload")).endswith("velho")

    r = runner.invoke(app, ["tokens", "recifrar"])  # de novo: nada a fazer
    assert "Credenciais regravadas: 0; já na chave atual: 1" in r.output


def test_sem_a_chave_anterior_nao_regrava_nada(monkeypatch, make_user, db):
    _chaves(monkeypatch, VELHA)
    _semear(make_user(role="dono").id)
    antes = db.scalar(select(ConexaoCredencial.access_cifrado))
    _chaves(monkeypatch, NOVA)  # rotação sem SOCIMAN_TOKENS_KEY_ANTERIOR
    r = runner.invoke(app, ["tokens", "recifrar"])
    assert r.exit_code == 1
    assert "nada foi regravado" in r.output
    db.expire_all()
    assert db.scalar(select(ConexaoCredencial.access_cifrado)) == antes


def test_sem_chave_erro_claro(monkeypatch):
    _chaves(monkeypatch, "")
    r = runner.invoke(app, ["tokens", "recifrar"])
    assert r.exit_code == 1 and "SOCIMAN_TOKENS_KEY" in r.output
