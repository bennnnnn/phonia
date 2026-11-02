"""Google Calendar and Gmail are gone from the running app, schema, and prompts."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import CheckConstraint

from app.background import handlers
from app.core.config import Settings
from app.core.db import Base
from app.core.jobs import queue
from app.main import app
from app.modules.chat.prompt_constants import (
    CAPABILITIES_FORMAT_HINT,
    DAY_PLANNING_ANSWER_HINT,
    PRIVACY_HINT,
)
from app.modules.chat.stream_status import StreamStatusPhase
from app.modules.todos import TODO_HINT

from .boundary_support import served_paths

REPO_ROOT = Path(__file__).resolve().parents[5]
APP_ROOT = REPO_ROOT / "apps" / "api" / "app"
MIGRATION = REPO_ROOT / "apps" / "api" / "alembic" / "versions" / "0106_drop_google_integrations.py"

INTEGRATION_TABLES = {
    "suggested_reminders",
    "user_gmail_connections",
    "user_calendar_connections",
}
RETIRED_USER_COLUMNS = ("push_email_suggestions_enabled", "push_calendar_enabled")


@pytest.mark.parametrize(
    "module",
    [
        "app.modules.integrations",
        "app.gateways.google_calendar_gateway",
        "app.gateways.google_gmail_gateway",
        "app.gateways.google_oauth",
        "app.gateways.google_oauth_revoke",
        "app.core.secrets",
        "app.services.ics_parser",
        "app.modules.chat.tools",
        "app.modules.chat.turn_prep.integrations",
    ],
)
def test_integration_modules_cannot_be_imported(module: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_integration_source_trees_are_absent() -> None:
    """A stale ``__pycache__`` left by a checkout must not look like a live package."""
    package = APP_ROOT / "modules" / "integrations"
    assert not any(package.rglob("*.py")), f"{package} has Python source"
    assert not (APP_ROOT / "tests" / "modules" / "integrations").exists()


def test_orm_metadata_has_no_integration_schema() -> None:
    assert INTEGRATION_TABLES.isdisjoint(Base.metadata.tables)
    users = Base.metadata.tables["users"]
    for column in RETIRED_USER_COLUMNS:
        assert column not in users.columns
    todos = Base.metadata.tables["todo_items"]
    (source_check,) = [
        constraint
        for constraint in todos.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_todo_items_source"
    ]
    assert str(source_check.sqltext) == "source IN ('user')"


def test_integration_http_routes_are_absent() -> None:
    paths = served_paths()
    assert "/chats" in paths  # the check sees the live routes
    assert not any(path.startswith("/integrations") for path in paths)
    client = TestClient(app)
    assert client.get("/integrations/google-calendar/status").status_code == 404
    assert client.get("/integrations/google-gmail/status").status_code == 404


def test_no_gmail_job_type_is_registered() -> None:
    handlers.register_all()
    assert "gmail_sync" not in queue._HANDLERS


def test_settings_have_no_integration_flags() -> None:
    fields = set(Settings.model_fields)
    for name in (
        "google_calendar_enabled",
        "gmail_enabled",
        "google_client_secret",
        "oauth_token_encryption_key",
        "mcp_tools_enabled",
    ):
        assert name not in fields
    assert not any(name.startswith(("calendar_", "gmail_")) for name in fields)


def test_stream_has_no_calendar_or_inbox_status() -> None:
    assert "loading_calendar" not in get_args(StreamStatusPhase)
    assert "checking_inbox" not in get_args(StreamStatusPhase)


def test_prompts_say_recall_has_no_calendar_or_inbox() -> None:
    assert "does not connect to the user's calendar or email inbox" in PRIVACY_HINT  # safety phrase
    assert (
        "does not connect to calendars or email inboxes" in CAPABILITIES_FORMAT_HINT
    )  # safety phrase
    assert (
        "does not connect to the user's calendar or email" in DAY_PLANNING_ANSWER_HINT
    )  # safety phrase
    assert "does not connect to any calendar" in TODO_HINT  # safety phrase


def test_no_runtime_code_points_users_to_connect_google() -> None:
    pitches = ("Settings → Google Calendar", "Settings → Gmail", "Connect your calendar")
    offenders = [
        str(path.relative_to(APP_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if "tests" not in path.parts
        and "__pycache__" not in path.parts
        and any(pitch in path.read_text() for pitch in pitches)
    ]
    assert offenders == []


def test_drop_migration_removes_the_schema() -> None:
    source = MIGRATION.read_text()
    assert 'revision: str = "0106_drop_google_integrations"' in source
    assert 'down_revision: Union[str, None] = "0105_push_types_and_voice"' in source
    for table in INTEGRATION_TABLES:
        assert f"DROP TABLE IF EXISTS {table} CASCADE" in source
    for column in RETIRED_USER_COLUMNS:
        assert f"ALTER TABLE users DROP COLUMN IF EXISTS {column}" in source
    assert "UPDATE todo_items SET source = 'user' WHERE source = 'gmail'" in source
    assert "CHECK (source IN ('user'))" in source
