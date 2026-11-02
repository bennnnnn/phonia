"""The server's geo intent readers, held to `docs/fixtures/geo_intent_cases.json`.

The phone reads the location question the same way (`lib/places/locationQuestion.ts`,
whose test `lib/places/__tests__/locationQuestion.test.ts` asserts the same file), so a
rule changed on one side alone fails a suite.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.modules.web_search.geo_intent import (
    is_ambiguous_local_places_query,
    is_distance_query,
    is_proximity_query,
)
from app.services.time_context import is_location_question

FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "geo_intent_cases.json"
CONTRACT: dict[str, Any] = json.loads(FIXTURE.read_text())
READERS: dict[str, Callable[[str], bool]] = {
    "proximity": is_proximity_query,
    "distance": is_distance_query,
    "location_question": is_location_question,
    "ambiguous_places": is_ambiguous_local_places_query,
}
CASES = [(group, case) for group, rows in CONTRACT["cases"].items() for case in rows]


def _id(entry: tuple[str, dict[str, Any]]) -> str:
    group, case = entry
    return f"{group}:{case['text'][:60]!r}"


def test_geo_intent_contract_names_every_reader() -> None:
    assert set(CONTRACT["readers"]) == set(READERS)
    for _group, case in CASES:
        assert set(case["reads"]) <= set(READERS), case["text"]


@pytest.mark.parametrize("entry", CASES, ids=_id)
def test_geo_intent_contract(entry: tuple[str, dict[str, Any]]) -> None:
    _group, case = entry
    reads = [name for name, reader in READERS.items() if reader(case["text"])]
    assert reads == case["reads"]
