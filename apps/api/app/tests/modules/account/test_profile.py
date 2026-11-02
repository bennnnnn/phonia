"""Tests for profile name normalization."""

import pytest

from app.core.validation import normalize_avatar_url
from app.models.schemas import UserUpdate
from app.modules.account.profile import (
    effective_location_label,
    normalize_client_coordinates,
    normalize_client_location,
    normalize_display_name,
    user_location_label,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Ada   Lovelace  ", "Ada Lovelace"),
        ("Cher", "Cher"),
        ("", None),
        ("   ", None),
        ("x" * 81, None),
        (None, None),
    ],
)
def test_normalize_display_name(raw: str | None, expected: str | None):
    assert normalize_display_name(raw) == expected


def test_user_update_normalizes_name():
    update = UserUpdate(name="  Grace   Hopper  ")
    assert update.name == "Grace Hopper"


def test_user_update_rejects_blank_name():
    with pytest.raises(ValueError):
        UserUpdate(name="   ")


def test_user_update_accepts_uploaded_avatar_path():
    attachment_id = "11111111-1111-1111-1111-111111111111"
    update = UserUpdate(avatar_url=f"/attachments/{attachment_id}/file")
    assert update.avatar_url == f"/attachments/{attachment_id}/file"


@pytest.mark.parametrize(
    "raw",
    [
        "https://evil.example/pic.png",
        "javascript:alert(1)",
        "/attachments/not-a-uuid/file",
        "/attachments/11111111-1111-1111-1111-111111111111/files",
        " /attachments/11111111-1111-1111-1111-111111111111/file/../x",
    ],
)
def test_user_update_rejects_non_upload_avatar(raw: str):
    with pytest.raises(ValueError):
        UserUpdate(avatar_url=raw)
    with pytest.raises(ValueError):
        normalize_avatar_url(raw)


def test_user_update_accepts_iana_timezone():
    update = UserUpdate(timezone="America/New_York")
    assert update.timezone == "America/New_York"


def test_user_update_rejects_invalid_timezone():
    with pytest.raises(ValueError):
        UserUpdate(timezone="Not/A/Zone")


def test_user_location_label_requires_enabled():
    class U:
        location_enabled = False
        location = "Oakland, CA"

    assert user_location_label(U()) is None


def test_user_location_label_when_enabled():
    class U:
        location_enabled = True
        location = "  Oakland, CA  "

    assert user_location_label(U()) == "Oakland, CA"


def test_normalize_client_location():
    assert normalize_client_location("  San Francisco, CA  ") == "San Francisco, CA"
    assert normalize_client_location("") is None
    assert normalize_client_location("x" * 201) is None


def test_effective_location_label_ignores_client_when_disabled():
    class U:
        location_enabled = False
        location = None

    assert effective_location_label(U(), "San Francisco, CA") is None


def test_effective_location_label_prefers_client_when_enabled():
    class U:
        location_enabled = True
        location = "Oakland, CA"

    assert effective_location_label(U(), "San Francisco, CA") == "San Francisco, CA"


def test_effective_location_label_falls_back_to_profile():
    class U:
        location_enabled = True
        location = "Oakland, CA"

    assert effective_location_label(U(), None) == "Oakland, CA"


def test_normalize_client_coordinates():
    assert normalize_client_coordinates(37.8, -122.4) == (37.8, -122.4)
    assert normalize_client_coordinates(None, None) is None
    assert normalize_client_coordinates(37.8, None) is None
    assert normalize_client_coordinates(91.0, 0.0) is None


# Web search can be turned off (Settings → Data controls): one narrowed copy of the
# server's switches covers every search path for that user's turns.
def test_web_search_setting_is_on_by_default_and_can_be_turned_off():
    from app.models.orm import User

    column = User.__table__.c.web_search_enabled
    assert column.default.arg is True and column.server_default is not None
    assert UserUpdate(web_search_enabled=False).web_search_enabled is False


@pytest.mark.parametrize("enabled", [True, None])
def test_settings_for_user_keeps_the_server_switches_when_search_is_on(enabled):
    from types import SimpleNamespace

    from app.core.config import Settings
    from app.modules.account.profile import settings_for_user

    settings = Settings(web_search_enabled=True, image_search_enabled=True)
    # None: a row built in code and not saved yet, which takes the column's default.
    user = SimpleNamespace(web_search_enabled=enabled)
    assert settings_for_user(settings, user) is settings


def test_settings_for_user_turns_every_search_off_for_that_user():
    from types import SimpleNamespace

    from app.core.config import Settings
    from app.modules.account.profile import settings_for_user

    settings = Settings(web_search_enabled=True, image_search_enabled=True)
    narrowed = settings_for_user(settings, SimpleNamespace(web_search_enabled=False))
    assert narrowed.web_search_enabled is False and narrowed.image_search_enabled is False
    # The server's own settings are untouched for everyone else.
    assert settings.web_search_enabled is True and settings.image_search_enabled is True


# Consent to outside AI services (Apple 5.1.2(i)): the server stamps the time.
@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"ai_data_consent": True, "name": "Ada"}, {"name": "Ada", "ai_data_consent_at": "NOW"}),
        ({"ai_data_consent": False}, {"ai_data_consent_at": None}),
        ({"ai_data_consent": None, "job": "x"}, {"job": "x"}),
        ({"job": "x"}, {"job": "x"}),
    ],
)
def test_with_ai_data_consent_turns_the_answer_into_the_column(fields, expected):
    from datetime import UTC, datetime

    from app.modules.account.profile import with_ai_data_consent

    now = datetime(2026, 10, 19, tzinfo=UTC)
    snapshot = dict(fields)
    resolved = {key: now if value == "NOW" else value for key, value in expected.items()}
    assert with_ai_data_consent(fields, now=now) == resolved
    assert fields == snapshot


def test_ai_data_consent_column_is_nullable_without_a_default():
    from app.models.orm import User

    column = User.__table__.c.ai_data_consent_at
    assert column.nullable is True
    assert column.default is None and column.server_default is None
    assert UserUpdate(ai_data_consent=True).ai_data_consent is True
