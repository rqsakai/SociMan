from fastapi.testclient import TestClient

from sociman_api import db
from sociman_api.main import app


def test_health_reports_db_unavailable(monkeypatch):
    class Broken:
        def connect(self):
            raise RuntimeError("sem banco")

    monkeypatch.setattr("sociman_api.main.get_engine", lambda: Broken())
    r = TestClient(app).get("/api/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["db"] == "unavailable"


def test_health_reports_redis_unavailable(monkeypatch):
    class BrokenRedis:
        def ping(self):
            raise RuntimeError("sem redis")

    monkeypatch.setattr("sociman_api.main.get_redis", lambda: BrokenRedis())
    r = TestClient(app).get("/api/health")
    assert r.status_code == 503
    assert r.json()["redis"] == "unavailable"


def test_openapi_is_served_under_api():
    r = TestClient(app).get("/api/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "SociMan API"


def test_engine_is_cached():
    assert db.get_engine() is db.get_engine()
