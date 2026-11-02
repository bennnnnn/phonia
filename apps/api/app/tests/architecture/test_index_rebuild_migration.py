"""0123 rebuilds an index a failed CONCURRENTLY build left INVALID (no database).

``CREATE INDEX CONCURRENTLY IF NOT EXISTS`` skips an invalid index of the same name, and
the old attachments index was then dropped, leaving the table only an index the planner
never uses.
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

from .boundary_support import APP_ROOT

_MIGRATION = APP_ROOT.parent / "alembic" / "versions" / "0123_list_and_retention_indexes.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0123", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Op:
    """Alembic's ``op`` over a catalog of index name -> valid; records each statement."""

    def __init__(
        self,
        catalog: dict[str, bool],
        *,
        failing: str | None = None,
        left_invalid: str | None = None,
    ) -> None:
        self.catalog = dict(catalog)
        self.failing = failing
        self.left_invalid = left_invalid
        self.statements: list[str] = []

    def get_context(self) -> Any:
        @contextmanager
        def autocommit_block() -> Any:
            yield

        return type("Ctx", (), {"autocommit_block": staticmethod(autocommit_block)})()

    def get_bind(self) -> Any:
        catalog = self.catalog

        class _Bind:
            def execute(self, _sql: Any, params: dict[str, str]) -> Any:
                found = catalog.get(params["name"])
                return type("R", (), {"scalar": staticmethod(lambda: found)})()

        return _Bind()

    def execute(self, statement: str) -> None:
        self.statements.append(statement)
        name = statement.split()[-1] if statement.startswith("DROP") else statement.split()[6]
        if statement.startswith("DROP"):
            self.catalog.pop(name, None)
        elif name not in self.catalog:
            if name == self.failing:
                self.catalog[name] = False  # a CONCURRENTLY build that fails leaves it INVALID
                raise RuntimeError("canceling statement due to statement timeout")
            self.catalog[name] = name != self.left_invalid


def _run(op: _Op, step: str = "upgrade") -> None:
    migration = _load()
    with patch.object(migration, "op", op):
        getattr(migration, step)()


def test_an_invalid_index_from_a_failed_build_is_dropped_and_rebuilt() -> None:
    op = _Op({"ix_attachments_user": True, "ix_chats_created": False})

    _run(op)

    drop = "DROP INDEX CONCURRENTLY IF EXISTS ix_chats_created"
    create = next(s for s in op.statements if "ix_chats_created ON" in s)
    assert op.statements.index(drop) < op.statements.index(create)
    assert op.catalog["ix_chats_created"] is True
    assert "ix_attachments_user" not in op.catalog


def test_a_failed_build_keeps_the_old_attachments_index_and_a_rerun_finishes() -> None:
    op = _Op({"ix_attachments_user": True}, failing="ix_attachments_user_created")
    with pytest.raises(RuntimeError):
        _run(op)
    assert op.catalog["ix_attachments_user"] is True
    assert op.catalog["ix_attachments_user_created"] is False

    op.failing = None
    _run(op)

    assert op.catalog["ix_attachments_user_created"] is True
    assert "ix_attachments_user" not in op.catalog


def test_the_old_index_stays_while_its_replacement_is_invalid() -> None:
    op = _Op({"ix_attachments_user": True}, left_invalid="ix_attachments_user_created")
    _run(op)
    assert op.catalog["ix_attachments_user_created"] is False
    assert op.catalog["ix_attachments_user"] is True
    assert not any(s.endswith(" ix_attachments_user") for s in op.statements)


def test_a_healthy_rerun_drops_none_of_the_new_indexes() -> None:
    catalog = {name: True for name, _ in _load()._CREATE}
    op = _Op(catalog)

    _run(op)

    drops = [s for s in op.statements if s.startswith("DROP")]
    assert drops == ["DROP INDEX CONCURRENTLY IF EXISTS ix_attachments_user"]
    assert all(catalog.values()) and len(op.catalog) == len(catalog)
