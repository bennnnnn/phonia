"""The photo lookup's word rules: ``docs/fixtures/photo_lookup_cases.json``.

Each phrase names the search ``extract_image_lookup_query`` runs for it, or null when
it asks for no photo ("show me my todos", "draw me a cat").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.modules.images.lookup_intent import extract_image_lookup_query

FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "photo_lookup_cases.json"
CASES: dict[str, Any] = json.loads(FIXTURE.read_text())


def _id(case: dict[str, Any]) -> str:
    return repr(case["text"])[:60]


@pytest.mark.parametrize("case", CASES["phrases"], ids=_id)
def test_lookup_case(case: dict[str, Any]) -> None:
    assert extract_image_lookup_query(case["text"]) == case["lookup"]
