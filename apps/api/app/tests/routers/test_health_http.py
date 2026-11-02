"""GET /health over HTTP."""

from fastapi.testclient import TestClient

from app.main import create_app

# ── health ─────────────────────────────────────────────────────────────────────


def test_health():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
