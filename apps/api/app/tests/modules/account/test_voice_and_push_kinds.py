"""PATCH /auth/me saves the voice and the reminder push switch."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.tests.api_support import api_user, app_with_user


def _patch_me(body: dict, **updated_fields):
    user = api_user()
    update = AsyncMock(return_value=api_user(**updated_fields))
    with patch("app.modules.account.lifecycle.users_repo.update", update):
        response = TestClient(app_with_user(user)).patch(
            "/auth/me", headers={"Authorization": "Bearer tok"}, json=body
        )
    return response, update


def test_me_reports_the_new_settings_with_defaults() -> None:
    client = TestClient(app_with_user(api_user()))
    body = client.get("/auth/me", headers={"Authorization": "Bearer tok"}).json()
    assert body["push_reminders_enabled"] is True
    assert "push_email_suggestions_enabled" not in body
    assert "push_calendar_enabled" not in body
    assert body["tts_voice"] is None


def test_patch_turns_reminder_pushes_off() -> None:
    response, update = _patch_me({"push_reminders_enabled": False}, push_reminders_enabled=False)
    assert response.status_code == 200
    assert response.json()["push_reminders_enabled"] is False
    assert update.await_args.kwargs["push_reminders_enabled"] is False


def test_patch_ignores_retired_email_and_calendar_push_switches() -> None:
    """An older app still sends the two switches; they are dropped, not saved."""
    response, update = _patch_me(
        {"push_email_suggestions_enabled": False, "push_calendar_enabled": False}
    )
    assert response.status_code == 200
    assert "push_email_suggestions_enabled" not in update.await_args.kwargs
    assert "push_calendar_enabled" not in update.await_args.kwargs


def test_patch_saves_a_voice() -> None:
    response, update = _patch_me({"tts_voice": "cedar"}, tts_voice="cedar")
    assert response.status_code == 200
    assert response.json()["tts_voice"] == "cedar"
    assert update.await_args.kwargs["tts_voice"] == "cedar"


def test_patch_null_voice_puts_the_default_back() -> None:
    response, update = _patch_me({"tts_voice": None})
    assert response.status_code == 200
    assert update.await_args.kwargs["tts_voice"] is None


@pytest.mark.parametrize("voice", ["fable", "onyx", "Kore", ""])
def test_patch_rejects_a_voice_live_talk_cannot_speak(voice: str) -> None:
    response, update = _patch_me({"tts_voice": voice})
    assert response.status_code == 422
    update.assert_not_awaited()
