"""Contas do perfil (T013, US2; contracts/http-api.md "Contas")."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.auth.models import User
from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Conta, Perfil

PW = "senha-forte-123"
TIKTOK_URL = "https://www.tiktok.com/@meusqueridinhos10"


@pytest.fixture
def member(make_user, login, client: TestClient) -> tuple[User, dict[str, str]]:
    user = make_user(role="membro", email="membro@teste.local", name="Membro")
    return user, login(client, user.email, PW)


@pytest.fixture
def headers(member) -> dict[str, str]:
    return member[1]


@pytest.fixture
def make_perfil(db: Session) -> Callable[..., Perfil]:
    def _make(name: str = "Queridinhos", slug: str | None = None) -> Perfil:
        perfil = Perfil(name=name, slug=slug or name.lower().replace(" ", "-"))
        db.add(perfil)
        db.commit()
        return perfil

    return _make


def _post(client: TestClient, headers: dict[str, str], perfil: Perfil, **body):
    return client.post(f"/api/perfis/{perfil.id}/contas", json=body, headers=headers)


def _create(client: TestClient, headers: dict[str, str], perfil: Perfil, **body) -> dict:
    r = _post(client, headers, perfil, **body)
    assert r.status_code == 201, r.text
    return r.json()["conta"]


def _patch(client: TestClient, headers: dict[str, str], conta: dict, **body):
    return client.patch(f"/api/contas/{conta['id']}",
                        json={"version": conta["version"], **body}, headers=headers)


def _action(client: TestClient, headers: dict[str, str], conta: dict, action: str):
    return client.post(f"/api/contas/{conta['id']}/{action}",
                       json={"version": conta["version"]}, headers=headers)


def _error(r) -> dict:
    return r.json()["error"]


# ---- criar ----

def test_adicionar_por_arroba_normaliza_e_sugere_link(
    client: TestClient, headers, member, make_perfil
) -> None:
    perfil = make_perfil()
    conta = _create(client, headers, perfil, platform="tiktok", handle=" @ MeusQueridinhos10 ")

    assert conta["handle"] == "meusqueridinhos10"
    assert conta["url"] == TIKTOK_URL
    assert conta["perfilId"] == str(perfil.id)
    assert conta["status"] == "planejada"
    assert conta["platformName"] == ""
    assert conta["archived"] is False
    assert conta["version"] == 1
    assert conta["createdBy"] == {"id": str(member[0].id), "name": "Membro"}
    assert conta["updatedBy"]["name"] == "Membro"


def test_adicionar_por_link_colado_extrai_arroba(client: TestClient, headers, make_perfil) -> None:
    perfil = make_perfil()
    conta = _create(client, headers, perfil, platform="youtube",
                    url="https://m.youtube.com/@Queridinhos.Oficial?si=abc")

    assert conta["handle"] == "queridinhos.oficial"
    assert conta["url"] == "https://m.youtube.com/@Queridinhos.Oficial?si=abc"


def test_link_que_nao_bate_com_a_plataforma_da_400(
    client: TestClient, headers, make_perfil
) -> None:
    r = _post(client, headers, make_perfil(), platform="tiktok",
              url="https://www.youtube.com/@outro")
    assert r.status_code == 400
    assert _error(r)["code"] == "validation_error"


def test_arroba_invalido_da_400(client: TestClient, headers, make_perfil) -> None:
    r = _post(client, headers, make_perfil(), platform="tiktok", handle="meu/perfil!")
    assert r.status_code == 400
    assert _error(r)["code"] == "validation_error"


def test_outra_exige_nome_e_link(client: TestClient, headers, make_perfil) -> None:
    perfil = make_perfil()
    sem_nome = _post(client, headers, perfil, platform="outra", handle="loja",
                     url="https://exemplo.com/loja")
    sem_link = _post(client, headers, perfil, platform="outra", platformName="Pinterest",
                     handle="loja")
    nome_fora_de_outra = _post(client, headers, perfil, platform="tiktok",
                               platformName="Pinterest", handle="loja")
    assert [r.status_code for r in (sem_nome, sem_link, nome_fora_de_outra)] == [400, 400, 400]

    conta = _create(client, headers, perfil, platform="outra", platformName="Pinterest",
                    url="https://br.pinterest.com/Queridinhos/")
    assert conta["platformName"] == "Pinterest"
    assert conta["handle"] == "queridinhos"
    assert conta["url"] == "https://br.pinterest.com/Queridinhos/"


def test_perfil_inexistente_da_404(client: TestClient, headers) -> None:
    r = client.post("/api/perfis/00000000-0000-0000-0000-000000000000/contas",
                    json={"platform": "tiktok", "handle": "x"}, headers=headers)
    assert r.status_code == 404


def test_exige_login(client: TestClient, make_perfil) -> None:
    r = client.post(f"/api/perfis/{make_perfil().id}/contas",
                    json={"platform": "tiktok", "handle": "x"})
    assert r.status_code == 401


# ---- unicidade (FR-005) ----

def test_arroba_repetido_em_outro_perfil_mesmo_arquivado_da_409(
    client: TestClient, headers, make_perfil
) -> None:
    dono_do_arroba = make_perfil("Queridinhos")
    outro = make_perfil("Achadinhos")
    conta = _create(client, headers, dono_do_arroba, platform="tiktok", handle="meusqueridinhos10")
    assert _action(client, headers, conta, "archive").status_code == 200

    r = _post(client, headers, outro, platform="tiktok", handle="@MeusQueridinhos10")
    assert r.status_code == 409
    assert _error(r) == {"code": "handle_in_use",
                         "message": "Esse @ já pertence ao perfil Queridinhos"}

    # Em outra plataforma, o mesmo @ é livre.
    _create(client, headers, outro, platform="youtube", handle="meusqueridinhos10")


def test_segunda_conta_ativa_na_mesma_plataforma_da_409_e_planejada_passa(
    client: TestClient, headers, make_perfil
) -> None:
    perfil = make_perfil()
    _create(client, headers, perfil, platform="tiktok", handle="principal", status="ativa")

    r = _post(client, headers, perfil, platform="tiktok", handle="reserva", status="ativa")
    assert r.status_code == 409
    assert _error(r) == {"code": "active_platform_exists",
                         "message": "Este perfil já tem uma conta ativa no TikTok"}

    planejada = _create(client, headers, perfil, platform="tiktok", handle="reserva")
    assert planejada["status"] == "planejada"

    # Outro perfil pode ter a sua ativa no TikTok.
    _create(client, headers, make_perfil("Achadinhos"), platform="tiktok", handle="achados",
            status="ativa")


def test_mudar_para_ativa_com_outra_ativa_da_409(
    client: TestClient, headers, make_perfil
) -> None:
    perfil = make_perfil()
    _create(client, headers, perfil, platform="tiktok", handle="principal", status="ativa")
    reserva = _create(client, headers, perfil, platform="tiktok", handle="reserva")

    r = _patch(client, headers, reserva, status="ativa")
    assert r.status_code == 409
    assert _error(r)["code"] == "active_platform_exists"


def test_patch_com_arroba_de_outro_perfil_da_409(
    client: TestClient, headers, make_perfil
) -> None:
    _create(client, headers, make_perfil("Queridinhos"), platform="tiktok", handle="tomado")
    conta = _create(client, headers, make_perfil("Achadinhos"), platform="tiktok",
                    handle="livre")

    r = _patch(client, headers, conta, handle="@Tomado")
    assert r.status_code == 409
    assert _error(r) == {"code": "handle_in_use",
                         "message": "Esse @ já pertence ao perfil Queridinhos"}


def test_restaurar_ativa_com_outra_ativa_da_409(client: TestClient, headers, make_perfil) -> None:
    perfil = make_perfil()
    antiga = _create(client, headers, perfil, platform="tiktok", handle="antiga", status="ativa")
    arquivada = _action(client, headers, antiga, "archive").json()["conta"]
    _create(client, headers, perfil, platform="tiktok", handle="nova", status="ativa")

    r = _action(client, headers, arquivada, "restore")
    assert r.status_code == 409
    assert _error(r)["code"] == "active_platform_exists"


def test_corrida_no_indice_vira_409(
    client: TestClient, headers, make_perfil, db: Session, monkeypatch
) -> None:
    """Checagem prévia desligada: o índice do banco decide, com o mesmo 409 e a mesma frase."""
    from sociman_api.perfis import service_contas

    perfil = make_perfil()
    _create(client, headers, perfil, platform="tiktok", handle="principal", status="ativa")
    monkeypatch.setattr(service_contas, "_check_unique", lambda db, conta: None)

    ativa = _post(client, headers, perfil, platform="tiktok", handle="reserva", status="ativa")
    assert ativa.status_code == 409
    assert _error(ativa) == {"code": "active_platform_exists",
                             "message": "Este perfil já tem uma conta ativa no TikTok"}

    repetido = _post(client, headers, make_perfil("Achadinhos"), platform="tiktok",
                     handle="principal")
    assert repetido.status_code == 409
    assert _error(repetido) == {"code": "handle_in_use",
                                "message": "Esse @ já pertence ao perfil Queridinhos"}

    assert len(db.scalars(select(Conta)).all()) == 1


# ---- editar ----

def test_patch_troca_arroba_status_e_notas(client: TestClient, headers, make_perfil) -> None:
    conta = _create(client, headers, make_perfil(), platform="tiktok", handle="antigo")

    r = _patch(client, headers, conta, handle="@Novo", status="ativa", notes=" conta principal ")
    assert r.status_code == 200, r.text
    novo = r.json()["conta"]
    assert novo["handle"] == "novo"
    assert novo["url"] == "https://www.tiktok.com/@novo"
    assert novo["status"] == "ativa"
    assert novo["notes"] == "conta principal"
    assert novo["version"] == 2


def test_patch_com_link_editado_mantem_o_link(client: TestClient, headers, make_perfil) -> None:
    conta = _create(client, headers, make_perfil(), platform="youtube", handle="canal")

    r = _patch(client, headers, conta, url="https://www.youtube.com/channel/UC123")
    assert r.status_code == 200, r.text
    assert r.json()["conta"]["url"] == "https://www.youtube.com/channel/UC123"
    assert r.json()["conta"]["handle"] == "canal"


def test_patch_nao_muda_a_plataforma(client: TestClient, headers, make_perfil) -> None:
    conta = _create(client, headers, make_perfil(), platform="tiktok", handle="x")
    r = _patch(client, headers, conta, platform="youtube")
    assert r.status_code == 400


def test_patch_com_versao_velha_da_409(client: TestClient, headers, make_perfil) -> None:
    conta = _create(client, headers, make_perfil(), platform="tiktok", handle="x")
    assert _patch(client, headers, conta, notes="primeira").status_code == 200

    r = _patch(client, headers, conta, notes="segunda")  # ainda com a versão 1
    assert r.status_code == 409
    assert _error(r) == {"code": "version_conflict",
                         "message": "Esta conta foi alterada por outra pessoa; recarregue"}


def test_conta_inexistente_da_404(client: TestClient, headers) -> None:
    conta = {"id": "00000000-0000-0000-0000-000000000000", "version": 1}
    assert _patch(client, headers, conta, notes="x").status_code == 404
    assert _action(client, headers, conta, "archive").status_code == 404
    r = client.get(f"/api/contas/{conta['id']}/versions", headers=headers)
    assert r.status_code == 404


# ---- arquivar, restaurar e histórico ----

def test_arquivar_e_restaurar(client: TestClient, headers, make_perfil, db: Session) -> None:
    conta = _create(client, headers, make_perfil(), platform="tiktok", handle="x", status="ativa")

    r = _action(client, headers, conta, "archive")
    assert r.status_code == 200, r.text
    arquivada = r.json()["conta"]
    assert arquivada["archived"] is True and arquivada["version"] == 2
    row = db.get(Conta, conta["id"])
    assert row.archived_at is not None and row.archived_by is not None

    assert _action(client, headers, conta, "restore").status_code == 409  # versão velha
    r = _action(client, headers, arquivada, "archive")
    assert r.status_code == 409
    assert _error(r) == {"code": "conflict", "message": "Esta conta já está arquivada"}

    r = _action(client, headers, arquivada, "restore")
    assert r.status_code == 200, r.text
    restaurada = r.json()["conta"]
    assert restaurada["archived"] is False and restaurada["version"] == 3
    assert restaurada["status"] == "ativa"
    r = _action(client, headers, restaurada, "restore")
    assert r.status_code == 409
    assert _error(r) == {"code": "conflict", "message": "Esta conta não está arquivada"}


def test_versoes_gravadas(client: TestClient, headers, member, make_perfil, db: Session) -> None:
    conta = _create(client, headers, make_perfil(), platform="tiktok", handle="x")
    conta = _patch(client, headers, conta, status="ativa").json()["conta"]
    conta = _action(client, headers, conta, "archive").json()["conta"]
    conta = _action(client, headers, conta, "restore").json()["conta"]
    # PATCH sem mudança não gera versão.
    assert _patch(client, headers, conta, notes="").json()["conta"]["version"] == 4

    r = client.get(f"/api/contas/{conta['id']}/versions", headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [(v["version"], v["action"]) for v in items] == [
        (4, "restored"), (3, "archived"), (2, "updated"), (1, "created"),
    ]
    updated = items[2]
    assert updated["changedFields"] == ["status"]
    assert updated["before"]["status"] == "planejada"
    assert updated["after"]["status"] == "ativa"
    assert updated["actor"] == {"id": str(member[0].id), "name": "Membro"}
    assert updated["actorKind"] == "user"
    created = items[3]
    assert created["before"] is None
    assert created["after"] == {"platform": "tiktok", "platform_name": "", "handle": "x",
                                "url": "https://www.tiktok.com/@x", "status": "planejada",
                                "notes": "", "archived": False}

    rows = db.scalars(select(EntityVersion).where(EntityVersion.entity_type == "conta")).all()
    assert len(rows) == 4


def test_plataformas_do_perfil_refletem_contas_ativas(
    client: TestClient, headers, make_perfil
) -> None:
    perfil = make_perfil()
    tiktok = _create(client, headers, perfil, platform="tiktok", handle="x", status="ativa")
    _create(client, headers, perfil, platform="youtube", handle="x")  # planejada: não conta

    def platforms() -> list[str]:
        r = client.get(f"/api/perfis/{perfil.id}", headers=headers)
        assert r.status_code == 200, r.text
        return r.json()["perfil"]["platforms"]

    assert platforms() == ["tiktok"]
    _action(client, headers, tiktok, "archive")
    assert platforms() == []
