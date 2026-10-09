"""Dados de teste das postagens (spec 006, US5) e dos destinos (spec 014): perfil e contas pela
API e cortes direto pelo modelo (sem MinIO: o calendário só precisa das linhas), cada um com o
seu conteúdo (mesmo id, como no `create_corte`)."""

import itertools
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.cortes.models import Corte, CorteStatus

PW = "senha-forte-123"
_seq = itertools.count(1)


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


def criar_perfil(client, h, nome: str = "A Taverna Nerd") -> dict:
    n = next(_seq)
    r = client.post("/api/perfis", headers=h,
                    json={"name": nome, "slug": f"taverna-{n}", "niche": "tecnologia"})
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def criar_conta(client, h, perfil_id: str, platform: str = "tiktok",
                handle: str | None = None) -> dict:
    handle = handle or f"conta{next(_seq)}"
    r = client.post(f"/api/perfis/{perfil_id}/contas", headers=h,
                    json={"platform": platform, "handle": handle, "status": "ativa"})
    assert r.status_code == 201, r.text
    return r.json()["conta"]


def criar_corte(db, perfil_id, status: CorteStatus = CorteStatus.pronto, **extra) -> Corte:
    n = next(_seq)
    pid = uuid.UUID(str(perfil_id))
    kit = {} if status != CorteStatus.revisao else None
    campos = {
        "perfil_id": pid, "hook_text": "Você usa isso?",
        "kit_version": 0 if kit is not None else None, "kit_tokens": kit, "status": status,
        "original_filename": "clipe.mp4",
        "original_key": f"cortes/{pid}/{uuid.uuid4()}/original.mp4",
        "original_content_type": "video/mp4", "original_bytes": 10, "duration_ms": 30000,
        "width": 1080, "height": 1920, "fps": Decimal(30), "video_codec": "h264",
        "original_sha256": "0" * 64,
        "result_key": f"cortes/{pid}/{n}-{uuid.uuid4()}/marcado.mp4"
        if status == CorteStatus.pronto else None,
        "finished_at": datetime.now(UTC) if status == CorteStatus.pronto else None,
    }
    campos.update(extra)
    corte = Corte(**campos)
    db.add(corte)
    db.flush()
    titulo = corte.openshorts_title or corte.hook_text or corte.original_filename
    db.add(Conteudo(id=corte.id, perfil_id=pid, origem=ConteudoOrigem.corte, corte_id=corte.id,
                    titulo=(titulo or "")[:100], created_by=corte.created_by))
    db.commit()
    return corte


# ---- spec 014: destinos e agendamentos pela API ----

# Spec 015 (T101): na TikTok a descrição (legenda) é obrigatória para agendar; os dados de
# teste já nascem com uma.
LEGENDA = "Legenda de teste"


def add_destino(client, h, conteudo_id, conta_id, **body) -> dict:
    r = client.post(f"/api/conteudos/{conteudo_id}/destinos", headers=h,
                    json={"contaId": str(conta_id), **body})
    assert r.status_code == 201, r.text
    return r.json()["destino"]


def acao(client, h, destino: dict, nome: str, **body):
    """`POST /api/destinos/{id}/{nome}` com a versão do destino."""
    return client.post(f"/api/destinos/{destino['id']}/{nome}", headers=h,
                       json={"version": destino["version"], **body})


def aprovado(client, h, conteudo_id, conta_id, **body) -> dict:
    """Destino novo, aprovado por `h` (dono)."""
    d = add_destino(client, h, conteudo_id, conta_id, **body)
    r = acao(client, h, d, "aprovar")
    assert r.status_code == 200, r.text
    return r.json()["destino"]


def agendar(client, h, conteudo_id, conta_id, planned_at, **body):
    body["textos"] = {"descricao": LEGENDA, **(body.get("textos") or {})}
    return client.post("/api/agendamentos", headers=h, json={
        "conteudoId": str(conteudo_id), "contaId": str(conta_id),
        "plannedAt": planned_at.isoformat(), "modo": "lembrete", **body})
