"""The solver's picture is the drawing: the model's own diagram and second Answer go.

"Draw a circuit with a 9V battery and two 3 ohm resistors in parallel and find the total
current" came back with a Mermaid "circuit" above the real schematic, and a plain "Answer"
line with the value above the server's **Answer** heading and card.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.fence import validate_physics_fences
from app.services.solving import VerifiedPhysicsBlock

_CIRCUIT = (
    "Draw a circuit with a 9V battery and two 3 ohm resistors in parallel "
    "and find the total current"
)
# The model's reply on the phone, before the server's fences.
_REPLY = """Here is the circuit diagram and the calculation for the total current.

```mermaid
graph TD
    Battery[9V Battery] --> NodeA
    NodeA --> R1[3 Ω]
    NodeA --> R2[3 Ω]
    R1 --> NodeB
    R2 --> NodeB
    NodeB --> Battery
```

**Given**
$V = 9\\ \\text{V}$
$R_1 = 3\\ \\Omega$
$R_2 = 3\\ \\Omega$

**Find**
Total current $I_{total}$

**Ohm's law**
$I = \\frac{V}{R_{eq}}$
$I = \\frac{9}{1.5}$
$I = 6\\ \\mathrm{A}$

Answer
$6\\ \\mathrm{A}$
"""


@pytest.fixture(scope="module")
def circuit() -> VerifiedPhysicsBlock:
    intent = extract_physics_intent(_CIRCUIT)
    assert intent is not None
    verified = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fences
    return verified


def test_the_schematic_replaces_the_models_mermaid_circuit(circuit: VerifiedPhysicsBlock) -> None:
    out = validate_physics_fences(_REPLY, verified=circuit, user_text=_CIRCUIT)
    assert "```mermaid" not in out
    assert out.count("```simulation") == 1
    assert "**Given**" in out


def test_one_answer_label_over_the_card(circuit: VerifiedPhysicsBlock) -> None:
    out = validate_physics_fences(_REPLY, verified=circuit, user_text=_CIRCUIT)
    # "Answer" once in any spelling ("```answer" is the card's language, not a label).
    assert out.count("Answer") == 1
    assert out.count("```answer") == 1
    assert "\nAnswer\n" not in out


@pytest.mark.parametrize(
    "asked",
    [
        f"{_CIRCUIT}, and a flowchart of the steps",
        f"{_CIRCUIT}. Also show it as a mermaid diagram",
    ],
)
def test_a_flowchart_the_user_asked_for_stays(circuit: VerifiedPhysicsBlock, asked: str) -> None:
    out = validate_physics_fences(_REPLY, verified=circuit, user_text=asked)
    assert "```mermaid" in out
    assert out.count("```simulation") == 1


def test_with_no_picture_the_models_diagram_stays(circuit: VerifiedPhysicsBlock) -> None:
    unpictured = replace(circuit, canonical_fences=[])
    out = validate_physics_fences(_REPLY, verified=unpictured, user_text=_CIRCUIT)
    assert "```mermaid" in out
    assert "```simulation" not in out
