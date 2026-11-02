"""A fact op the model types loosely is kept, typed by its topic; a dropped op is counted."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.memory import instruct as instruct_service
from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult, MemoryUpdate
from app.tests.modules.memory.test_instruct import _patches


@pytest.mark.parametrize(
    ("op", "kind"),
    [
        ({"topic": "goals"}, "focus"),  # no type: the topic's
        ({"type": "goal"}, "focus"),  # a word for a type
        ({"type": "goal", "topic": "preferences"}, "preference"),  # the topic wins
        ({"type": "hobby", "topic": "area:recall"}, "project"),  # an area stores projects
        ({"type": "Preference"}, "preference"),
        ({"type": "hobby"}, "fact"),
        ({}, "fact"),
    ],
)
def test_a_loosely_typed_op_is_kept(op: dict[str, str], kind: str) -> None:
    parsed = MemoryFactOp.model_validate(
        {"op": "add", "text": "User is training for a marathon", "confidence": 0.9, **op}
    )
    assert parsed.type == kind


def test_salvage_counts_every_op_it_could_not_keep() -> None:
    result = MemoryFactUpdateResult.salvage_partial(
        {
            "ops": [
                {"op": "add", "text": "User likes tea", "confidence": 0.9},
                {"op": "add", "text": "no confidence"},
                "not an op",
            ],
            "reply": "Saved three things.",
        }
    )
    assert result is not None and len(result.ops) == 1 and result.dropped == 2
    assert "dropped" not in MemoryFactUpdateResult.model_json_schema()["properties"]


@pytest.mark.asyncio
async def test_an_edit_whose_ops_were_all_dropped_says_nothing_changed() -> None:
    # The model said it added the goal, but its op did not validate.
    result = MemoryFactUpdateResult.salvage_partial(
        {"ops": [{"op": "add", "text": "Run a marathon"}], "reply": "Added your goal."}
    )
    assert result is not None
    with _patches(result=result) as (apply, _instruct, _release):
        outcome = await instruct_service.apply_memory_instruction(
            Settings(), user_id=uuid4(), instruction="Remember my goal is a marathon"
        )
    assert outcome.applied == 0 and outcome.dropped == 1
    assert outcome.reply == instruct_service.NOTHING_CHANGED_REPLY
    apply.assert_not_awaited()


def test_a_fact_cannot_be_set_to_superseded_by_hand() -> None:
    with pytest.raises(ValidationError):
        MemoryUpdate.model_validate({"status": "superseded"})
    assert MemoryUpdate.model_validate({"status": "muted"}).status == "muted"
