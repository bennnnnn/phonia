"""The calculator fence: the contract's shape, the marker, and the card's own checks."""

from __future__ import annotations

import json
from dataclasses import replace

from app.modules.money.catalog import product
from app.modules.money.fence import calculator_fence
from app.modules.money.read import MoneyRequest
from app.modules.money.schemas import CalculatorSpec
from app.modules.money.solve import Worked, work
from app.tests.modules.money.money_support import average


def _worked(key: str, **values: float) -> Worked:
    found = work(MoneyRequest(product(key), dict(values)), None)
    assert found is not None
    return found


def _spec(text: str | None) -> CalculatorSpec:
    assert text is not None and text.startswith("```calculator\n") and text.endswith("\n```")
    return CalculatorSpec.model_validate(json.loads(text.split("\n", 1)[1].rsplit("\n", 1)[0]))


def test_a_mortgage_card_has_sliders_readouts_and_todays_marker() -> None:
    spec = _spec(calculator_fence(_worked("mortgage", amount=300000, rate=1), average(), "USD"))
    assert (spec.product, spec.title_key, spec.currency) == ("loan", "money.title.mortgage", "USD")
    controls = {control.name: control for control in spec.controls}
    assert list(controls) == ["amount", "rate", "years"]
    assert controls["amount"].min <= 300000 <= controls["amount"].max
    rate = controls["rate"]
    assert rate.value == 1 and rate.min == 0 and rate.max >= 12.54
    assert rate.marker is not None
    assert rate.marker.model_dump() == {
        "value": 6.27,
        "label_key": "money.average",
        "as_of": "2026-10-16",
        "source": "Mortgage Rates - Freddie Mac",
        "source_url": "https://www.freddiemac.com/pmms",
    }
    assert [readout.name for readout in spec.readouts] == ["payment", "interest", "total"]
    assert spec.readouts[0].primary


def test_no_average_no_marker() -> None:
    spec = _spec(calculator_fence(_worked("mortgage", amount=300000, rate=1), None, "USD"))
    assert all(control.marker is None for control in spec.controls)


def test_a_card_payoff_card_names_its_never_text() -> None:
    spec = _spec(calculator_fence(_worked("card", balance=5000, apr=24, payment=100), None, ""))
    assert spec.product == "card_payoff"
    assert all(readout.never_key == "money.never" for readout in spec.readouts)


def test_savings_from_nothing_still_has_room_to_slide() -> None:
    spec = _spec(calculator_fence(_worked("savings", deposit=200, rate=4.5, years=10), None, ""))
    start = next(control for control in spec.controls if control.name == "start")
    assert start.value == 0 and start.max > 0 and start.step > 0


def test_a_card_whose_numbers_disagree_is_not_sent() -> None:
    worked = _worked("mortgage", amount=300000, rate=1)
    wrong = replace(worked, outputs={**worked.outputs, "payment": 900.0})
    assert calculator_fence(wrong, None, "USD") is None


def test_an_asked_value_past_the_usual_range_widens_it() -> None:
    spec = _spec(calculator_fence(_worked("mortgage", amount=300000, rate=1, years=50), None, ""))
    years = next(control for control in spec.controls if control.name == "years")
    assert years.max == 50


def test_a_quarterly_card_writes_its_compounding_into_the_trees() -> None:
    """The phone's trees name only sliders: "per_year" is written in as the number 4."""
    request = MoneyRequest(
        product("savings"), {"start": 3000, "rate": 6, "years": 7}, settings={"per_year": 4}
    )
    worked = work(request, None)
    assert worked is not None
    text = calculator_fence(worked, None, "ETB")
    spec = _spec(text)
    assert "per_year" not in (text or "")
    assert [control.name for control in spec.controls] == ["start", "deposit", "rate", "years"]
