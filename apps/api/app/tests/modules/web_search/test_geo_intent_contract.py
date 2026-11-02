"""The server reads geo intent exactly the way the phone does.

The phone decides before sending whether to read GPS (`lib/places/localPlacesQuery.ts`),
so it must ask for a fix on the same messages the server answers from the user's
location. `docs/fixtures/geo_intent_cases.json` holds the cases both sides must
agree on; the mobile test (`lib/places/__tests__/localPlacesQuery.test.ts`) asserts the
same file, so a rule changed on one side alone fails a suite.
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
