"""A model's read of a physics question binds only through the physics binder.

The read is written back as English the binder reads (``law_binding.model_read``); a law
whose read does not come back as the same law and values gives no intent. The contract
below reads every bound law's every input set back; the laws that do not are named, so a
change that makes one readable takes it off the list and one that breaks a law fails.
"""

from __future__ import annotations

import pytest

from app.modules.physics.catalog import CATALOG
from app.modules.physics.model_read import physics_menu, physics_read_intent
from app.services.law_binding.model_read import Stated
from app.services.law_binding.spec import FormulaSpec

_VALUES = (2.5, 4.0, 7.5, 12.0, 3.2, 9.0, 1.7)

# Read back as another law or other values today: each declines, by name.
NOT_READ_BACK = frozenset(
    {
        "center_of_mass_three:m1+m2+m3+x1+x2+x3",
        "energy_speed_from_moving_start:g+h+u",
        "gravitational_force_at_surface:M+m+radius_body",
        "heat_energy:c_heat+delta_temp+m",
        "heat_energy:c_heat+m+temp_final+temp_initial",
        "impact_speed:angle+g+h0+v0",
        "latent_heat:latent_heat+m+temp_phase",
        "lens_power_sum:p1+p2",
        "lift_normal_force:accel+downward+g+m",
        "lift_normal_force:accel+g+m",
        "radiation_pressure_absorbed:intensity",
        "radiation_pressure_reflected:intensity",
        "range:angle+g+h0+v0",
        "resonance_frequency:L+harmonic+mode_factor+pipe+v_wave",
        "resonance_frequency:L+harmonic+mode_factor+v_wave",
        "rod_center_inertia:m+rod_length",
        "rod_end_inertia:m+rod_length",
        "rolling_body_kinetic_energy:m+r+shape_k+v",
        "rolling_body_kinetic_energy:m+shape_k+v",
        "sound_level:i_ref+intensity",
        "time_of_flight:angle+g+h0+v0",
        "weight_at_height:M+altitude+m+radius_body",
        "work_energy:m+v1+v2",
    }
)


def sample(spec: FormulaSpec, inputs: frozenset[str]) -> list[Stated]:
    """Distinct values for one input set, each in its own SI unit (angles in degrees)."""
    variables = {variable.name: variable for variable in spec.variables}
    stated = []
    for index, name in enumerate(sorted(inputs)):
        variable = variables[name]
        if not variable.visible:
            continue
        if name.startswith("angle") or "theta" in variable.symbol:
            stated.append(Stated(name, 30.0 + index, "deg"))
        else:
            unit = "" if variable.dimensionless else variable.dimension or ""
            stated.append(Stated(name, _VALUES[index % len(_VALUES)], unit))
    return stated


def test_every_bound_law_reads_back_but_the_named_ones() -> None:
    missed = {
        f"{spec.id}:{'+'.join(sorted(inputs))}"
        for spec in CATALOG.values()
        if spec.binding is not None
        for inputs in spec.binding.inputs
        if physics_read_intent(spec.id, sample(spec, inputs)) is None
    }
    assert missed - NOT_READ_BACK == set(), "a law that read back no longer does"
    assert NOT_READ_BACK - missed == set(), "reads back now: take it off NOT_READ_BACK"


def test_a_read_in_other_units_keeps_them_as_the_binder_does() -> None:
    intent = physics_read_intent("rate_speed", [Stated("d", 3.0, "km"), Stated("t", 0.5, "h")])
    assert intent is not None and intent.physics_op == "rate_speed"
    assert intent.physics_params == pytest.approx({"d": 3.0, "t": 0.5})
    assert intent.physics_units == {"d": "km", "t": "h"}


@pytest.mark.parametrize(
    "stated",
    [
        # A unit of another kind, an input the law has not, a value given twice.
        [Stated("d", 3.0, "kg"), Stated("t", 2.0, "s")],
        [Stated("d", 3.0, "m"), Stated("mass", 2.0, "kg")],
        [Stated("d", 3.0, "m"), Stated("d", 4.0, "m")],
    ],
)
def test_a_read_the_law_cannot_take_binds_to_nothing(stated: list[Stated]) -> None:
    assert physics_read_intent("rate_speed", stated) is None


def test_an_unknown_law_binds_to_nothing() -> None:
    assert physics_read_intent("no_such_law", [Stated("d", 3.0, "m")]) is None


def test_the_menu_is_every_bound_law_by_kind() -> None:
    menu = physics_menu()
    bound = {spec.id for spec in CATALOG.values() if spec.binding is not None}
    assert {card.op for cards in menu.values() for card in cards} == bound
    card = next(card for card in menu["kinematics"] if card.op == "rate_speed")
    assert {item.name for item in card.inputs} >= {"d", "t"}


def test_the_message_rules_a_law_out_as_it_does_for_the_binder() -> None:
    water = [
        Stated("m1", 2.0, "kg", "2 kg"),
        Stated("m2", 3.0, "kg", "3 kg"),
        Stated("temp_a", 20.0, "degC", "20 °C"),
        Stated("temp_b", 80.0, "degC", "80 °C"),
    ]
    only_water = "2 kg of water at 20 °C is mixed with 3 kg of water at 80 °C. Final temperature?"
    with_alcohol = (
        "2 kg of water at 20 °C is mixed with 3 kg of alcohol at 80 °C. Final temperature?"
    )
    assert physics_read_intent("water_mixture_temperature", water, only_water) is not None
    assert physics_read_intent("water_mixture_temperature", water, with_alcohol) is None
    # A word the law's binding excludes: a falling body's speed is no average speed.
    speed = [Stated("d", 20.0, "m", "20 m"), Stated("t", 2.0, "s", "2 s")]
    assert physics_read_intent("rate_speed", speed, "A car goes 20 m in 2 s.") is not None
    assert physics_read_intent("rate_speed", speed, "A stone falls 20 m in 2 s.") is None


@pytest.mark.parametrize(
    ("unit", "quote", "reads"),
    [
        ("m", "8 cm", False),  # read at another scale than the quote writes
        ("cm", "8 cm", True),
        ("m", "8 m", True),
        ("m", "٨ ሜትር", True),  # a unit the table cannot read in the quote: not checked
    ],
)
def test_a_unit_must_be_the_one_its_quote_writes(unit: str, quote: str, reads: bool) -> None:
    stated = [Stated("d", 8.0, unit, quote), Stated("t", 2.0, "s", "2 s")]
    assert (physics_read_intent("rate_speed", stated) is not None) is reads
