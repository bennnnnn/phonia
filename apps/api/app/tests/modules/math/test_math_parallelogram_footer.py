"""The diagram footer follows an explicit perimeter-only measurement request."""

import json

import pytest

from app.core.config import Settings
from app.modules.math.fence import validate_math_fences
from app.modules.math.schemas import MathIntent, ParallelogramGeometryBlockSpec
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quantity,answer,show_perimeter", [("perimeter", "26", True), ("area", "32", False)]
)
@pytest.mark.parametrize("unit", ["", " cm"])
async def test_parallelogram_footer_flag_survives_direct_finalization(
    quantity: str, answer: str, show_perimeter: bool, unit: str
) -> None:
    query = f"Find the {quantity} of a parallelogram base 8{unit} height 4{unit} side 5{unit}"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_answer == answer
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    finalized = validate_math_fences(reply, verified=verified)
    geometry = json.loads(finalized.split("```geometry\n", 1)[1].split("\n```", 1)[0])
    assert geometry["show_perimeter"] is show_perimeter
    assert geometry["area"] == 32
    assert geometry["perimeter"] == 26
    assert geometry["unit"] == ("cm" if unit else "units")


@pytest.mark.parametrize(
    "wants_area,wants_perimeter", [(False, False), (True, False), (True, True)]
)
def test_other_intents_retain_existing_area_footer(wants_area: bool, wants_perimeter: bool) -> None:
    verified = _build_verified_block(
        MathIntent(
            kind="parallelogram",
            base=8,
            height=4,
            side=5,
            wants_area=wants_area,
            wants_perimeter=wants_perimeter,
        ),
        Settings(math_tools_enabled=True),
    )
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_fence["show_perimeter"] is False


def test_existing_parallelogram_payload_defaults_to_area_footer() -> None:
    spec = ParallelogramGeometryBlockSpec.model_validate(
        {"type": "parallelogram", "base": 8, "height": 4, "side": 5, "area": 32, "perimeter": 26}
    )
    assert spec.show_perimeter is False
