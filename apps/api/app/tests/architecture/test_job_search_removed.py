"""The My Job search product is gone from the running app, schema, and phone."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.background import handlers
from app.core.db import Base
from app.core.jobs import queue
from app.main import app

from .boundary_support import served_paths

REPO_ROOT = Path(__file__).resolve().parents[5]
APP_ROOT = REPO_ROOT / "apps" / "api" / "app"
MOBILE_ROOT = REPO_ROOT / "apps" / "mobile"
MIGRATION = REPO_ROOT / "apps" / "api" / "alembic" / "versions" / "0104_drop_job_search.py"

JOB_SEARCH_TABLES = {
    "job_notification_events",
    "job_search_runs",
    "job_matches",
    "job_manual_allowances",
    "job_search_profiles",
}


@pytest.mark.parametrize(
    "module",
    ["app.modules.job_search", "app.services.job_search", "app.routers.job_search"],
)
def test_job_search_packages_cannot_be_imported(module: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_job_search_source_trees_are_absent() -> None:
    """A stale ``__pycache__`` left by a checkout must not look like a live package."""
    for tree in ("modules", "services"):
        package = APP_ROOT / tree / "job_search"
        assert not any(package.rglob("*.py")), f"{package} has Python source"
    assert not (APP_ROOT / "tests" / "modules" / "job_search").exists()


def test_orm_metadata_has_no_job_search_tables() -> None:
    assert JOB_SEARCH_TABLES.isdisjoint(Base.metadata.tables)


def test_job_search_http_routes_are_absent() -> None:
    paths = served_paths()
    assert "/chats" in paths  # the check sees the live routes
    assert not any(path.startswith("/job-search") for path in paths)
    assert TestClient(app).get("/job-search").status_code == 404


def test_no_job_search_job_type_is_registered() -> None:
    handlers.register_all()
    assert not any("job" in name for name in queue._HANDLERS)


def test_mobile_job_search_routes_are_absent() -> None:
    assert not (MOBILE_ROOT / "features" / "job-search").exists()
    assert not (MOBILE_ROOT / "app" / "my-job").exists()


def test_drop_job_search_migration_removes_the_schema() -> None:
    source = MIGRATION.read_text()
    assert 'revision: str = "0104_drop_job_search"' in source
    for table in JOB_SEARCH_TABLES:
        assert f"DROP TABLE IF EXISTS {table} CASCADE" in source
