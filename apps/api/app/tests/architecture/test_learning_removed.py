"""The language-learning product is gone from the running app and schema."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.db import Base
from app.main import app

from .boundary_support import served_paths

REPO_ROOT = Path(__file__).resolve().parents[5]
MOBILE_ROOT = REPO_ROOT / "apps" / "mobile"
MIGRATION = REPO_ROOT / "apps" / "api" / "alembic" / "versions" / "0099_drop_learning.py"

LEARNING_TABLES = {
    "projects",
    "project_items",
    "quiz_miss_events",
    "vocab_decks",
    "vocab_entries",
    "learning_practice_events",
}


def test_learning_package_cannot_be_imported() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.modules.learning")


def test_orm_metadata_has_no_learning_tables() -> None:
    assert LEARNING_TABLES.isdisjoint(Base.metadata.tables)
    chats = Base.metadata.tables["chats"]
    todos = Base.metadata.tables["todo_items"]
    assert "project_id" not in chats.columns
    assert "quiz_mode" not in chats.columns
    assert "project_id" not in todos.columns


def test_projects_http_routes_are_absent() -> None:
    paths = served_paths()
    assert "/chats" in paths  # the check sees the live routes
    assert not any(path == "/projects" or path.startswith("/projects/") for path in paths)
    client = TestClient(app)
    assert client.get("/projects").status_code == 404
    assert client.post("/projects", json={"title": "Spanish"}).status_code == 404


def test_mobile_learning_routes_are_absent() -> None:
    assert not (MOBILE_ROOT / "features" / "learning").exists()
    assert not (MOBILE_ROOT / "app" / "projects").exists()
    assert not (MOBILE_ROOT / "hooks" / "useChatQuizContext.ts").exists()


def test_drop_learning_migration_removes_the_schema() -> None:
    source = MIGRATION.read_text()
    assert 'revision: str = "0099_drop_learning"' in source
    assert 'down_revision: Union[str, None] = "0098_memory_edited_at"' in source
    for table in LEARNING_TABLES:
        assert f'op.drop_table("{table}")' in source
    assert 'op.drop_column("chats", "project_id")' in source
    assert 'op.drop_column("chats", "quiz_mode")' in source
    assert 'op.drop_column("todo_items", "project_id")' in source
