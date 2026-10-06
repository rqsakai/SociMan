"""Ordem das contas para a cor fixa (spec 019, FR-006): todas as contas, na ordem de criação (e
id), inclusive as arquivadas e as de perfis arquivados; o membro também lê."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from integration.analytics_helpers import cena, membro  # noqa: F401
from sociman_api.perfis.models import Conta, Perfil


def test_ordem_estavel_com_arquivadas(cena, membro):  # noqa: F811
    outra = cena.segunda_conta("segunda", outro_perfil=True)
    terceira = cena.segunda_conta("terceira", platform="youtube")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # a criação manda: a principal vira a mais nova; segunda e terceira empatam (o id desempata)
    for conta_id, dias in ((cena.conta["id"], 3), (outra["id"], 1), (terceira["id"], 1)):
        cena.db.execute(update(Conta).where(Conta.id == conta_id)
                        .values(created_at=base + timedelta(days=dias)))
    # a terceira arquivada; o perfil da segunda arquivado
    cena.db.execute(update(Conta).where(Conta.id == terceira["id"])
                    .values(archived_at=base + timedelta(days=5)))
    cena.db.execute(update(Perfil).where(Perfil.id == outra["perfilId"])
                    .values(archived_at=base + timedelta(days=5)))
    cena.db.commit()

    empate = sorted([outra["id"], terceira["id"]])
    esperado = [*empate, cena.conta["id"]]
    corpo = cena.ok("ordem-contas")
    assert [c["contaId"] for c in corpo["contas"]] == esperado
    por_id = {c["contaId"]: c for c in corpo["contas"]}
    assert por_id[cena.conta["id"]] == {"contaId": cena.conta["id"], "rotulo": "@atavernanerd",
                                        "rede": "tiktok", "perfilId": cena.perfil["id"]}
    assert por_id[terceira["id"]]["rede"] == "youtube"

    _, h = membro
    r = cena.get("ordem-contas", h)
    assert r.status_code == 200 and r.json() == corpo
    assert cena.client.get("/api/analytics/ordem-contas").status_code == 401
