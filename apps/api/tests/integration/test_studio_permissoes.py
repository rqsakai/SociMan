"""Permissões (spec 020, T047; SC-007): o membro recebe 403 `somente_dono` nas 3 rotas de escrita;
`mcp_client`, `system:*` e token de agente recebem 403 `somente_humano` e deixam o evento
`publicacao_recusada` com `details.rota`; nada é gravado; as 2 rotas de leitura aceitam o
membro."""

import pytest
from atores import ator_fake
from sqlalchemy import select

from integration.analytics_helpers import cena, membro  # noqa: F401
from integration.studio_helpers import (
    err,
    files,
    overview_dias,
    st,  # noqa: F401
    zip_overview,
)
from sociman_api.auth.deps import current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.main import app

H = "atavernanerd"


def _escritas(st, imp: dict, previa_id: str) -> list[tuple[str, str, dict]]:  # noqa: F811
    conta = st.conta_id
    return [
        ("/api/contas/{conta_id}/studio/previa", f"/api/contas/{conta}/studio/previa",
         {"files": files(zip_overview(overview_dias(n=3), H))}),
        ("/api/contas/{conta_id}/studio/importacoes", f"/api/contas/{conta}/studio/importacoes",
         {"json": {"previaId": previa_id, "confirmoConta": True}}),
        ("/api/studio/importacoes/{importacao_id}/desfazer",
         f"/api/studio/importacoes/{imp['id']}/desfazer", {"json": {"version": imp["version"]}}),
    ]


def _eventos(db) -> list[SecurityEvent]:
    db.expire_all()
    return list(db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada").order_by(SecurityEvent.id)))


def test_membro_recebe_somente_dono_e_le(st, membro):  # noqa: F811
    imp = st.importar(zip_overview(overview_dias(n=5), H))
    p = st.previa_ok(zip_overview(overview_dias(n=2), H))
    antes = st.contar()
    for _, rota, kw in _escritas(st, imp, p["previaId"]):
        r = st.client.post(rota, headers=membro[1], **kw)
        assert (r.status_code, err(r)) == (403, "somente_dono"), rota
    assert st.contar() == antes and _eventos(st.db) == []
    assert len(st.importacoes(h=membro[1])) == 1
    assert st.cobertura(h=membro[1])["importacoesAtivas"] == 1


@pytest.mark.parametrize("kind", ["mcp_client", "system:cli", "system:agente"])
def test_nao_humano_recebe_somente_humano_e_fica_registrado(st, kind):  # noqa: F811
    imp = st.importar(zip_overview(overview_dias(n=5), H))
    p = st.previa_ok(zip_overview(overview_dias(n=2), H))
    antes = st.contar()
    dono = st.dono
    app.dependency_overrides[current_user] = lambda: ator_fake(kind, dono)
    escritas = _escritas(st, imp, p["previaId"])
    for _, rota, kw in escritas:
        r = st.client.post(rota, headers=st.h, **kw)
        assert (r.status_code, err(r)) == (403, "somente_humano"), rota
    # leitura continua aberta para quem tem sessão
    assert st.client.get(f"/api/contas/{st.conta_id}/studio/cobertura",
                         headers=st.h).status_code == 200
    app.dependency_overrides.clear()
    assert st.contar() == antes
    eventos = _eventos(st.db)
    assert [e.details["rota"] for e in eventos] == [modelo for modelo, _, _ in escritas]
    assert all(e.outcome == "denied" and e.actor_kind == kind for e in eventos)
    assert eventos[0].details["contaId"] == st.conta_id
    # a prévia do dono continua valendo (a recusa não a consumiu)
    assert st.confirmar(p["previaId"]).status_code == 201


# ---- spec 022 (T048): o envio com XLSX e público nas 3 rotas H; a leitura nova aceita membro ----

def _escritas_publico(st, imp: dict, previa_id: str) -> list[tuple[str, dict]]:  # noqa: F811
    from integration.studio_helpers import viewers_dias, xlsx_viewers, zip_viewers

    conta = st.conta_id
    return [
        (f"/api/contas/{conta}/studio/previa",
         {"files": files(zip_viewers(viewers_dias(), H))}),
        (f"/api/contas/{conta}/studio/previa",
         {"files": files(("Viewers.xlsx", xlsx_viewers()))}),
        (f"/api/contas/{conta}/studio/importacoes",
         {"json": {"previaId": previa_id, "confirmoConta": True}}),
        (f"/api/studio/importacoes/{imp['id']}/desfazer", {"json": {"version": imp["version"]}}),
    ]


def test_publico_membro_e_nao_humano(st, membro):  # noqa: F811
    from integration.studio_helpers import (
        seguidores_dias,
        viewers_dias,
        zip_seguidores,
        zip_viewers,
    )

    imp = st.importar(zip_seguidores(seguidores_dias(n=3), H, publico=True))
    p = st.previa_ok(zip_viewers(viewers_dias(), H))
    antes = st.contar()
    for rota, kw in _escritas_publico(st, imp, p["previaId"]):
        r = st.client.post(rota, headers=membro[1], **kw)
        assert (r.status_code, err(r)) == (403, "somente_dono"), rota
    dono = st.dono
    app.dependency_overrides[current_user] = lambda: ator_fake("system:agente", dono)
    for rota, kw in _escritas_publico(st, imp, p["previaId"]):
        r = st.client.post(rota, headers=st.h, **kw)
        assert (r.status_code, err(r)) == (403, "somente_humano"), rota
    app.dependency_overrides.clear()
    assert st.contar() == antes
    assert len(_eventos(st.db)) == 4
    assert st.cobertura(h=membro[1])["publico"]["fotos"]
    r = st.client.get("/api/analytics/publico", headers=membro[1])
    assert r.status_code == 200 and r.json()["contas"][0]["genero"] is not None
