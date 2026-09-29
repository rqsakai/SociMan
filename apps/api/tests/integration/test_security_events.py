"""US3: lista de eventos de segurança do dono (T049; contracts/http-api.md, FR-017a, SC-009)."""

import base64
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from sociman_api.auth.models import SecurityEvent, User
from sociman_api.main import app

PW = "senha-forte-123"
URL = "/api/security-events"
BASE = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def owner(make_user) -> User:
    return make_user(role="dono", name="Dona")


@pytest.fixture
def headers(client: TestClient, db: Session, owner: User, login) -> dict[str, str]:
    """Sessão do dono, sem o `login_succeeded` que o login grava: cada teste parte do zero."""
    h = login(client, owner.email, PW)
    db.execute(delete(SecurityEvent))
    db.commit()
    return h


@pytest.fixture
def add_event(db: Session) -> Callable[..., SecurityEvent]:
    def _add(
        type: str = "login_succeeded",
        at: datetime = BASE,
        actor: User | None = None,
        subject: User | None = None,
        ip: str | None = None,
        details: dict | None = None,
    ) -> SecurityEvent:
        event = SecurityEvent(
            occurred_at=at,
            type=type,
            outcome="ok",
            actor_user_id=actor.id if actor else None,
            actor_kind="user" if actor else "anonymous",
            subject_user_id=subject.id if subject else None,
            ip=ip_address(ip) if ip else None,
            details=details or {},
        )
        db.add(event)
        db.commit()
        return event

    return _add


def _get(client: TestClient, headers: dict[str, str], **params) -> dict:
    r = client.get(URL, headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _ids(page: dict) -> list[int]:
    return [item["id"] for item in page["items"]]


# ---- conteúdo e ordem ----

def test_mais_recente_primeiro_com_nomes_e_ip(
    client: TestClient, headers, owner: User, make_user, add_event
) -> None:
    member = make_user(name="Membro")
    old = add_event("user_created", BASE, actor=owner, subject=member,
                    details={"after": {"name": "Membro"}})
    new = add_event("login_failed", BASE + timedelta(hours=1), subject=member, ip="203.0.113.7")
    mid = add_event("logout", BASE + timedelta(minutes=30), actor=member, subject=member,
                    ip="2001:db8::1")

    page = _get(client, headers)
    assert _ids(page) == [new.id, mid.id, old.id]
    assert page["nextCursor"] is None

    first, _, last = page["items"]
    assert first == {
        "id": new.id,
        "occurredAt": first["occurredAt"],
        "type": "login_failed",
        "outcome": "ok",
        "actorKind": "anonymous",
        "actorUserId": None,
        "actorName": None,
        "subjectUserId": str(member.id),
        "subjectName": "Membro",
        "ip": "203.0.113.7",
        "details": {},
    }
    assert datetime.fromisoformat(first["occurredAt"]) == BASE + timedelta(hours=1)
    assert page["items"][1]["ip"] == "2001:db8::1"
    assert last["actorName"] == "Dona"
    assert last["actorUserId"] == str(owner.id)
    assert last["subjectName"] == "Membro"
    assert last["details"] == {"after": {"name": "Membro"}}


def test_mesmo_instante_desempata_pelo_id(client: TestClient, headers, add_event) -> None:
    events = [add_event(at=BASE) for _ in range(3)]
    assert _ids(_get(client, headers)) == [e.id for e in reversed(events)]


def test_lista_vazia(client: TestClient, headers) -> None:
    assert _get(client, headers) == {"items": [], "nextCursor": None}


# ---- filtros ----

def test_filtro_user_id_casa_com_ator_ou_sujeito(
    client: TestClient, headers, owner: User, make_user, add_event
) -> None:
    alvo = make_user()
    outro = make_user()
    as_actor = add_event(at=BASE, actor=alvo, subject=outro)
    as_subject = add_event(at=BASE + timedelta(minutes=1), actor=owner, subject=alvo)
    add_event(at=BASE + timedelta(minutes=2), actor=owner, subject=outro)
    add_event(at=BASE + timedelta(minutes=3))

    page = _get(client, headers, userId=str(alvo.id))
    assert _ids(page) == [as_subject.id, as_actor.id]
    assert _get(client, headers, userId=str(uuid.uuid4()))["items"] == []


def test_filtro_type(client: TestClient, headers, add_event) -> None:
    add_event("login_succeeded", BASE)
    failed = [add_event("login_failed", BASE + timedelta(minutes=i)) for i in (1, 2)]
    add_event("logout", BASE + timedelta(minutes=3))

    assert _ids(_get(client, headers, type="login_failed")) == [failed[1].id, failed[0].id]
    assert _get(client, headers, type="nao_existe")["items"] == []


def test_filtro_from_e_to_inclusivos(client: TestClient, headers, add_event) -> None:
    events = [add_event(at=BASE + timedelta(days=d)) for d in range(5)]

    page = _get(client, headers, **{"from": (BASE + timedelta(days=1)).isoformat(),
                                    "to": (BASE + timedelta(days=3)).isoformat()})
    assert _ids(page) == [events[3].id, events[2].id, events[1].id]
    assert _ids(_get(client, headers, **{"from": (BASE + timedelta(days=4)).isoformat()})) == [
        events[4].id]
    assert _ids(_get(client, headers, to=BASE.isoformat())) == [events[0].id]


def test_filtros_combinados(
    client: TestClient, headers, owner: User, make_user, add_event
) -> None:
    alvo = make_user()
    hit = add_event("role_changed", BASE + timedelta(days=1), actor=owner, subject=alvo)
    add_event("role_changed", BASE + timedelta(days=3), actor=owner, subject=alvo)  # fora do to
    add_event("user_updated", BASE + timedelta(days=1), actor=owner, subject=alvo)  # outro tipo
    add_event("role_changed", BASE + timedelta(days=1), actor=owner)  # outro usuário

    page = _get(client, headers, userId=str(alvo.id), type="role_changed",
                **{"from": BASE.isoformat(), "to": (BASE + timedelta(days=2)).isoformat()})
    assert _ids(page) == [hit.id]


def test_filtros_invalidos_dao_400(client: TestClient, headers) -> None:
    for params in ({"userId": "nao-e-uuid"}, {"from": "ontem"}, {"to": "2026-13-40"}):
        r = client.get(URL, headers=headers, params=params)
        assert r.status_code == 400, params
        assert r.json()["error"]["code"] == "validation_error"


# ---- paginação ----

def test_paginacao_por_cursor_percorre_tudo_sem_repetir(
    client: TestClient, headers, add_event
) -> None:
    # Instantes repetidos: o cursor precisa do id para não pular nem repetir eventos.
    events = [add_event(at=BASE + timedelta(minutes=i // 3)) for i in range(8)]
    expected = [e.id for e in sorted(events, key=lambda e: (e.occurred_at, e.id), reverse=True)]

    seen: list[int] = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        page = _get(client, headers, **params)
        assert len(page["items"]) <= 3
        seen += _ids(page)
        pages += 1
        cursor = page["nextCursor"]
        if cursor is None:
            break
    assert seen == expected
    assert pages == 3


def test_cursor_respeita_os_filtros(client: TestClient, headers, add_event) -> None:
    hits = [add_event("logout", BASE + timedelta(minutes=i)) for i in range(4)]
    for i in range(4):
        add_event("login_succeeded", BASE + timedelta(minutes=i))

    first = _get(client, headers, type="logout", limit=2)
    second = _get(client, headers, type="logout", limit=2, cursor=first["nextCursor"])
    assert _ids(first) + _ids(second) == [e.id for e in reversed(hits)]
    assert second["nextCursor"] is None


def test_pagina_exata_nao_tem_proximo_cursor(client: TestClient, headers, add_event) -> None:
    for i in range(3):
        add_event(at=BASE + timedelta(minutes=i))
    page = _get(client, headers, limit=3)
    assert len(page["items"]) == 3
    assert page["nextCursor"] is None


def test_limit_padrao_50_e_maximo_100(client: TestClient, headers, db: Session) -> None:
    db.add_all(SecurityEvent(occurred_at=BASE + timedelta(seconds=i), type="logout",
                             outcome="ok", actor_kind="anonymous", details={})
               for i in range(120))
    db.commit()

    default = _get(client, headers)
    assert len(default["items"]) == 50
    assert default["nextCursor"] is not None
    biggest = _get(client, headers, limit=100)
    assert len(biggest["items"]) == 100
    assert _get(client, headers, limit=1)["items"] == biggest["items"][:1]


@pytest.mark.parametrize("limit", [0, -1, 101, "muitos"])
def test_limit_fora_da_faixa_da_400(client: TestClient, headers, limit) -> None:
    r = client.get(URL, headers=headers, params={"limit": limit})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


def _b64(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


@pytest.mark.parametrize("cursor", [
    "!!!",
    "a",
    _b64("sem-separador"),
    _b64("2026-01-10T12:00:00+00:00|nao-numero"),
    _b64("ontem|12"),
    _b64("2026-01-10T12:00:00|12"),  # sem fuso
    base64.urlsafe_b64encode(b"\xff\xfe|1").decode(),
])
def test_cursor_invalido_da_400(client: TestClient, headers, cursor: str) -> None:
    r = client.get(URL, headers=headers, params={"cursor": cursor})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


# ---- acesso e imutabilidade ----

def test_membro_recebe_403(client: TestClient, make_user, login) -> None:
    member = make_user()
    r = client.get(URL, headers=login(client, member.email, PW))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_sem_sessao_recebe_401(client: TestClient) -> None:
    r = client.get(URL)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_openapi_so_expoe_leitura() -> None:
    paths = app.openapi()["paths"]
    assert set(paths[URL]) == {"get"}
    assert not [p for p in paths if p.startswith(URL + "/")]
    params = {p["name"] for p in paths[URL]["get"]["parameters"]}
    assert params == {"userId", "type", "from", "to", "cursor", "limit"}


def test_eventos_nao_podem_ser_editados_nem_apagados_pela_api(
    client: TestClient, headers, db: Session, add_event
) -> None:
    event = add_event("login_failed", details={"reason": "wrong_password"})
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        for path in (URL, f"{URL}/{event.id}"):
            r = client.request(method, path, headers=headers, json={"type": "logout"})
            assert r.status_code in (404, 405), (method, path, r.status_code)

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(SecurityEvent)) == 1
    stored = db.get(SecurityEvent, event.id)
    assert stored.type == "login_failed"
    assert stored.details == {"reason": "wrong_password"}
