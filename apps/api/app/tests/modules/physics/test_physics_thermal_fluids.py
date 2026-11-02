"""Gas laws, heat, buoyancy and capillarity read from the catalog, worked by hand."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.bodies import names_only_water
from app.modules.physics.direct import maybe_direct_physics_reply
from app.modules.physics.solvers.si import to_si

_SETTINGS = Settings(math_tools_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(
    ("text", "operation", "answer"),
    [
        (
            "A gas at 300 K and 100 kPa occupies 2 m^3. Find the number of moles.",
            "ideal_gas_amount",
            "80.2 mol",  # 1e5·2 / (8.314·300)
        ),
        (
            "A gas of 2 mol at 300 K occupies 0.05 m^3. Find the pressure.",
            "ideal_gas_pressure",
            "99774 Pa",
        ),
        (
            "A gas occupies 4 L at 2 atm. If the pressure is increased to 4 atm at constant "
            "temperature, find the new volume.",
            "boyle_volume",
            "2 L",
        ),
        (
            "A gas at 2 atm occupies 4 L. At constant temperature it is compressed to 2 L. "
            "Find the new pressure.",
            "boyle_pressure",
            "4 atm",
        ),
        (
            # Celsius is converted to kelvin first: 2 · 400.15 / 300.15.
            "A gas occupies 2 L at 27 °C. It is heated to 127 °C at constant pressure. "
            "Find the new volume.",
            "charles_volume",
            "2.67 L",
        ),
        (
            # "at 100 kPa and 300 K" share "at"; "to" names 450 K, not 300 K.
            "A sealed container of gas at 100 kPa and 300 K is heated to 450 K. "
            "Find the new pressure.",
            "gay_lussac_pressure",
            "150 kPa",
        ),
        (
            "A gas occupies 2 L at 100 kPa and 300 K. It changes to 200 kPa and 400 K. "
            "Find the new volume.",
            "combined_gas_volume",
            "1.33 L",  # 2·100·400 / (300·200)
        ),
        (
            "An ideal gas has an initial pressure of 2.00e5 Pa, an initial volume of "
            "0.00300 m^3, and an initial temperature of 300 K. The new pressure is "
            "1.00e5 Pa and the new temperature is 400 K. Find the new volume.",
            "combined_gas_volume",
            "0.008 m³",  # 2e5·0.003·400 / (300·1e5)
        ),
        (
            "An ideal gas has an initial pressure of 2.00e5 Pa, an initial volume of "
            "0.00300 m^3, and an initial temperature of 300 K. The new volume is "
            "0.00600 m^3 and the new temperature is 600 K. Find the new pressure.",
            "combined_gas_pressure",
            "2 × 10⁵ Pa",
        ),
        (
            "Find the rms speed of oxygen molecules at 300 K. The molar mass of oxygen is 32 g/mol.",
            "rms_speed",
            "484 m/s",  # √(3·8.314·300/0.032)
        ),
        (
            "Find the average kinetic energy of a gas molecule at 300 K.",
            "mean_molecular_kinetic_energy",
            "6.21 × 10⁻²¹ J",
        ),
        (
            # "of 2 mol" in the question is the gas's amount, not the energy.
            "Find the internal energy of 2 mol of a diatomic gas at 300 K.",
            "diatomic_internal_energy",
            "12472 J",  # 5/2·2·8.314·300
        ),
        (
            "How much energy is needed to raise the temperature of 2 kg of water by 10 °C?",
            "heat_energy",
            "83720 J",  # water's c; a rise of 10 °C is 10 K
        ),
        (
            # "specific heat of" is the capacity, not the heat being asked for.
            "A 0.500 kg block has a specific heat of 900 J/kg/K. The temperature rises "
            "by 20.0 K. Find the heat energy.",
            "heat_energy",
            "9000 J",
        ),
        (
            "A 0.500 kg block has a specific heat of 900 J/kg/K. It goes from 290 K to "
            "310 K. Find the heat energy.",
            "heat_energy",
            "9000 J",
        ),
        (
            "5000 J of heat raises the temperature of 2 kg of a metal by 10 K. "
            "Find its specific heat capacity.",
            "specific_heat_from_energy",
            "250 J/(kg·K)",
        ),
        (
            "200 g of water at 80 °C is mixed with 300 g of water at 20 °C. "
            "Find the final temperature.",
            "water_mixture_temperature",
            "44 °C",  # (0.2·80 + 0.3·20) / 0.5
        ),
        (
            "It takes 668000 J to melt 2 kg of ice. Find the specific latent heat of fusion.",
            "latent_heat_from_energy",
            "3.34 × 10⁵ J/kg",
        ),
        (
            "A steel rod 2 m long is heated by 50 K. The expansion coefficient is "
            "12 × 10^-6 per K. Find the change in length.",
            "linear_expansion",
            "0.0012 m",
        ),
        (
            "Find the absolute pressure at a depth of 10 m in water.",
            "absolute_pressure_at_depth",
            "199425 Pa",  # 101325 + 1000·9.81·10
        ),
        (
            "A 5 kg block of volume 0.002 m^3 is fully submerged in water. "
            "Find its apparent weight.",
            "apparent_weight_submerged",
            "29.4 N",  # 49.05 - 19.62
        ),
        (
            "A 2.00 kg object of volume 0.00100 m^3 is submerged in water of density "
            "1000 kg/m^3. Find the apparent weight.",
            "apparent_weight_submerged",
            "9.81 N",  # 19.62 - 9.81
        ),
        (
            "Ice of density 917 kg/m^3 floats in water of density 1000 kg/m^3. "
            "What fraction of the ice is submerged?",
            "floating_fraction",
            "0.917",
        ),
        (
            "Water with surface tension 0.072 N/m rises in a capillary tube of radius 0.5 mm. "
            "Find the height of the rise.",
            "capillary_rise",
            "29.4 mm",  # 2·0.072 / (1000·9.81·0.0005), contact angle 0
        ),
    ],
)
def test_a_stated_law_is_read_and_verified(text: str, operation: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    assert _answer(text) == answer
    block = build_verified_physics_block(intent, _SETTINGS)
    assert block is not None and maybe_direct_physics_reply(block, text) is not None


@pytest.mark.parametrize(
    "text",
    [
        # Was 167 kJ: "at 20 °C" is a temperature, not the change.
        "How much energy is needed to heat 2 kg of water at 20 °C?",
        "A 2 m rod at 20 °C has an expansion coefficient of 1.2 × 10^-5 per K. Find the expansion.",
        # Copper is not water, and its c is not stated.
        "A 2 kg copper block is heated by 10 °C. Find the heat energy.",
        "200 g of water at 80 °C is poured into a 300 g copper cup at 20 °C. "
        "Find the final temperature.",
        # Nothing says the temperature is constant.
        "A gas occupies 4 L at 2 atm. The pressure is increased to 4 atm. Find the new volume.",
        # The object's density is not the water's.
        "A 5 kg block of density 2700 kg/m^3 and volume 0.002 m^3 is fully submerged in water. "
        "Find its apparent weight.",
        # Denser than water: it sinks, so no fraction floats.
        "A block of density 1200 kg/m^3 floats in water of density 1000 kg/m^3. "
        "What fraction is submerged?",
        # A diameter is not the radius.
        "Water with surface tension 0.072 N/m rises in a capillary tube of diameter 1 mm. "
        "Find the height of the rise.",
    ],
)
def test_a_question_the_catalog_cannot_read_exactly_declines(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("value", "unit", "key", "si"),
    [
        (50.0, "°C", "delta_temp", 50.0),  # a rise of 50 °C is 50 K
        (50.0, "°C", "temp", 323.15),  # a temperature of 50 °C is 323.15 K
        (90.0, "degF", "delta_temp", 50.0),
        (2.0e20, "nuclei", "n_nuclei", 2.0e20),  # a count
        (0.5, "c", "v", 0.5 * 299792458.0),  # the speed of light, not a coulomb
    ],
)
def test_to_si_reads_differences_counts_and_c(value: float, unit: str, key: str, si: float) -> None:
    assert to_si(value, unit, expected_key=key) == pytest.approx(si)


@pytest.mark.parametrize(
    ("text", "water"),
    [
        ("2 kg of water", True),
        ("a copper block in water", False),
        ("sea water", False),
        ("ice melts into water", False),
        ("a 2 kg block", False),
        ("200 g of hot water and 300 g of cold water", True),
        ("100 grams of the water at 80 °c", True),
        ("100 g of water and 50 g of ethanol", False),
        ("seawater and 200 g of water", False),
        ("150 g of milk and 100 g of water", False),
        ("2 kg of a liquid in water", False),
    ],
)
def test_water_numbers_apply_only_when_water_is_the_substance(text: str, water: bool) -> None:
    assert names_only_water(text) is water


@pytest.mark.parametrize(
    "second",
    ["ethanol", "alcohol", "milk", "oil", "mercury", "glycerin", "honey"],
)
def test_water_mixed_with_another_liquid_is_not_answered_as_water(second: str) -> None:
    text = (
        f"100 g of water at 80 °C is mixed with 50 g of {second} at 20 °C. "
        "What is the final temperature?"
    )
    assert _answer(text) is None


def test_every_water_only_law_is_in_the_catalog() -> None:
    from app.modules.physics.catalog import CATALOG, WATER_ONLY

    assert WATER_ONLY <= CATALOG.keys()
