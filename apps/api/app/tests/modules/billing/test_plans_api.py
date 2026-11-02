"""What the app reads about plans: the user's features and the paywall catalog."""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.main import create_app
from app.models.schemas import UserOut
from app.tests.api_support import api_user


@pytest.mark.parametrize(
    "plan_id, has_live_talk, has_voice",
    [("free", False, False), ("plus", False, True), ("pro", True, True)],
)
def test_user_payload_lists_plan_features(plan_id, has_live_talk, has_voice):
    out = UserOut(
        id=uuid4(),
        email="a@b.c",
        name=None,
        avatar_url=None,
        default_model="auto",
        plan=plan_id,
        memory_enabled=True,
        created_at=datetime(2026, 1, 1),
    )
    body = out.model_dump()
    assert ("live_talk" in body["features"]) is has_live_talk
    assert ("speech_transcription" in body["features"]) is has_voice
    assert "image_generation" in body["features"]


def test_plans_endpoint_returns_the_catalog_and_current_plan():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: api_user(plan="plus")
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    r = TestClient(app).get("/billing/plans", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["current"] == "plus"
    plans = {item["id"]: item for item in body["plans"]}
    assert set(plans) == {"free", "plus", "pro"}
    assert plans["pro"]["allowances"]["monthly_live_talk_minutes"] == 60
    assert plans["plus"]["allowances"]["daily_image_generations"] == 10
    assert "live_talk" not in plans["plus"]["features"]
    # Prices are the store's: never in the server catalog.
    assert "price" not in str(body).lower()


def test_plans_endpoint_requires_sign_in():
    r = TestClient(create_app()).get("/billing/plans")
    assert r.status_code in (401, 403)
