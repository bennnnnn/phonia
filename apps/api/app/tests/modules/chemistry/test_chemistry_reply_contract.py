"""Chemistry replies the server writes are the replies the phone and the web read.

`docs/fixtures/chemistry_replies.json` holds real direct replies. This test proves the server
still writes exactly those; the mobile (`lib/__tests__/chemistryReplyContract.test.ts`) and web
(`src/lib/chemistryReplyContract.test.ts`) tests read the same file and prove each client
handles them. To accept an intended change to the replies, regenerate the file:

    UPDATE_CHEMISTRY_FIXTURE=1 uv run pytest app/tests/modules/chemistry/test_chemistry_reply_contract.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.direct import format_direct_chemistry_reply
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.fence import CHEMISTRY_ANSWER_NOTATION

FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "chemistry_replies.json"

QUESTIONS = {
    "ph_from_hydrogen": "Find pH when [H+] = 0.001",
    "molar_mass_water": "What is the molar mass of H2O?",
    "balance_ammonia": "Balance N2 + H2 -> NH3",
    "vsepr_water": "VSEPR of H2O",
    # Two molecules, two pictures: one chem_scene fence each.
    "vsepr_water_and_co2": "Why is water bent tho, co2 isnt",
    "galvanic_zn_cu": "Galvanic cell with Zn and Cu, find the cell potential",
}


def _reply(question: str) -> str:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    verified = build_verified_chemistry(intent)
    assert verified is not None, question
    return format_direct_chemistry_reply(verified)


def _current() -> dict[str, Any]:
    return {
        "answer_notation": CHEMISTRY_ANSWER_NOTATION,
        "replies": {
            name: {"question": question, "reply": _reply(question)}
            for name, question in QUESTIONS.items()
        },
    }


def _write(document: dict[str, Any]) -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _stored() -> dict[str, Any]:
    if os.environ.get("UPDATE_CHEMISTRY_FIXTURE"):
        _write(_current())
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_covers_every_reply_shape_the_clients_read() -> None:
    replies = _stored()["replies"]
    text = "\n".join(entry["reply"] for entry in replies.values())
    assert "```answer\n" + CHEMISTRY_ANSWER_NOTATION in text
    for kind in ("balance", "vsepr", "cell"):
        assert f'"kind": "{kind}"' in text


def test_the_notation_header_is_the_one_the_clients_strip() -> None:
    assert _stored()["answer_notation"] == CHEMISTRY_ANSWER_NOTATION


@pytest.mark.parametrize("name", list(QUESTIONS))
def test_the_server_still_writes_the_stored_reply(name: str) -> None:
    stored = _stored()["replies"][name]
    assert stored["question"] == QUESTIONS[name]
    assert stored["reply"] == _reply(QUESTIONS[name])
