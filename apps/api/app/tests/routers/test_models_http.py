"""GET /models: the model picker's list."""

from fastapi.testclient import TestClient

from app.tests.api_support import api_user, app_with_user

# ── models ─────────────────────────────────────────────────────────────────────


def test_list_models_omits_provider_field():
    user = api_user()
    client = TestClient(app_with_user(user))
    r = client.get("/models", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0
    for model in body:
        assert "id" in model
        assert "label" in model
        assert "quota_multiplier" in model
        assert "provider" not in model
    smart = next(m for m in body if m["id"] == "smart-chat")
    assert smart["quota_multiplier"] == 3.5
    assert all(m["id"] != "max-chat" for m in body)
