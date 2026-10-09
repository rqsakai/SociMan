"""Princípio V (spec 015, T044): um ciclo completo na TikTok falsa (conectar, renovar, enviar em
partes, consultar, uma falha com corpo de erro e desconectar) com o log em DEBUG. Nenhum token,
código, verifier, segredo do app, `upload_token`, `upload_url` nem a chave aparece nos logs, nos
`details` das tentativas, nas versões nem nos eventos de segurança."""

import json
import logging

from sqlalchemy import select, text

from integration import publicacao_helpers as ph
from integration.conexao_helpers import conectar
from integration.postagem_helpers import criar_conta, criar_perfil
from sociman_api.auth.models import SecurityEvent
from sociman_api.config import get_settings
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion
from sociman_api.publicacao import trilha
from sociman_api.publicacao.models import Tentativa

# Fixtures do apoio (o pytest as acha pelo nome no módulo).
app_tiktok = ph.app_tiktok
cena = ph.cena


def _segredos(fake) -> set[str]:
    s = get_settings()
    valores = set(fake.access) | set(fake.refresh) | fake.usados | set(fake.upload_tokens)
    valores |= {e.upload_token for e in fake.envios.values()}
    valores |= {s.tiktok_client_secret.get_secret_value(),
                s.sociman_tokens_key.get_secret_value()}
    return {v for v in valores if v}


def test_ciclo_completo_sem_segredo_no_log(cena, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(trilha, "CHUNK", 1024)
    monkeypatch.setattr(trilha, "INTEIRO_ATE", 1024)
    codigos: list[str] = []
    original = cena.fake.usuario

    def usuario(code, *args, **kwargs):
        codigos.append(code)
        return original(code, *args, **kwargs)

    cena.fake.usuario = usuario

    # outra conta, conectada pelo endereço Desktop (PKCE)
    perfil = criar_perfil(cena.client, cena.h, "Outro perfil")
    outra = criar_conta(cena.client, cena.h, perfil["id"], "tiktok", "meusqueridinhos10")
    conectar(cena.client, cena.h, outra, cena.fake, host={"Host": "localhost"})

    # renovar: o access vence e a trilha pede outro (com rotação do refresh)
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE conexao_credenciais SET access_expira_em = now()"))
    ok = cena.agendado(tamanho=2500)
    falha = cena.agendado(ignorarIntervalo=True)
    cena.fake.falhar_proximo("inbox_init", "access_token_invalid")  # corpo de erro
    cena.rodar(5)
    estados = sorted(cena.destino(d["id"]).estado.value for d in (ok, falha))
    assert estados == ["falhou", "rascunho_criado"]
    assert cena.fake.pedidos("token")  # houve refresh

    # desconectar (revoga)
    cx = cena.client.get(f"/api/contas/{outra['id']}/conexao", headers=cena.h).json()["conexao"]
    r = cena.client.post(f"/api/contas/{outra['id']}/conexao/desconectar", headers=cena.h,
                         json={"version": cx["version"]})
    assert r.status_code == 200, r.text

    segredos = _segredos(cena.fake) | set(codigos)
    assert len(segredos) >= 6
    cena.db.expire_all()
    textos = [caplog.text]
    textos += [json.dumps(t.details) for t in cena.db.scalars(select(Tentativa))]
    textos += [json.dumps([v.before, v.after, v.details])
               for v in cena.db.scalars(select(EntityVersion))]
    textos += [json.dumps(e.details) for e in cena.db.scalars(select(SecurityEvent))]
    tudo = "\n".join(textos)
    vazados = [s for s in segredos if s in tudo]
    assert not vazados, f"segredos no log/banco: {len(vazados)}"
    assert "upload_token=" not in tudo  # nem pedaço do `upload_url`
