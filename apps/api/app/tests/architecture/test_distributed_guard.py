"""A local run spread over workers is refused: every worker would share the dev database."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.tests.conftest import _distributed


@pytest.mark.parametrize(
    ("options", "distributed"),
    [
        ({}, False),
        ({"numprocesses": None, "tx": [], "dist": "no"}, False),
        ({"numprocesses": 2, "tx": [], "dist": "load"}, True),
        # 2026-11-01: `--tx 2*popen --dist load` ran two workers on the shared database.
        ({"numprocesses": None, "tx": ["2*popen"], "dist": "load"}, True),
        ({"numprocesses": None, "tx": [], "dist": "loadgroup"}, True),
    ],
)
def test_any_xdist_distribution_is_distributed(options: dict[str, Any], distributed: bool) -> None:
    config = cast("pytest.Config", SimpleNamespace(option=SimpleNamespace(**options)))
    assert _distributed(config) is distributed
