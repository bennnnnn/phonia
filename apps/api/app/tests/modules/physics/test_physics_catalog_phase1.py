"""Verified coverage for the first master-catalog physics expansion."""

from __future__ import annotations

import re

import pytest

from app.core.config import Settings
from app.modules.physics.law_titles import law_heading
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    maybe_direct_physics_reply,
    needs_physics,
)

_SETTINGS = Settings(math_tools_enabled=True)


CASES: list[tuple[str, str, str, str, str]] = [
    (
        "Two point masses, 2 kg at 0 m and 3 kg at 4 m, have what center of mass?",
        "momentum",
        "center_of_mass",
        "2.4 m",
        "Center-of-mass equation:",
    ),
    (
        "Two masses of 2 kg and 3 kg are at x = 0 m and x = 10 m. Find the center of mass.",
        "momentum",
        "center_of_mass",
        "6 m",
        "Center-of-mass equation:",
    ),
    (
        "A machine outputs 80 J from 100 J input. Find its mechanical efficiency.",
        "energy",
        "mechanical_efficiency",
        "0.8 (80%)",
        "Mechanical-efficiency formula:",
    ),
    (
        "Find the speed of a wave on a string with tension 100 N and linear density 0.01 kg/m.",
        "waves",
        "string_wave_speed",
        "100 m/s",
        "Wave speed on a string:",
    ),
    (
        "A 0.5 m open pipe has sound speed 340 m/s. Find its fundamental standing-wave frequency.",
        "waves",
        "resonance_frequency",
        "340 Hz",
        "Standing-wave resonance:",
    ),
    (
        "A 0.5 m closed pipe has sound speed 340 m/s. Find its fundamental "
        "standing-wave frequency.",
        "waves",
        "resonance_frequency",
        "170 Hz",
        "Standing-wave resonance:",
    ),
    (
        "Two tones at 440 Hz and 444 Hz produce what beat frequency?",
        "waves",
        "beat_frequency",
        "4 Hz",
        "Beat-frequency relation:",
    ),
    (
        "Find the sound intensity 2 m from a 10 W point source.",
        "waves",
        "sound_intensity",
        "0.199 W/m²",
        "Spherical-wave intensity:",
    ),
    (
        "A hydraulic press has input force 100 N, piston areas 0.01 m^2 and "
        "0.2 m^2. Find output force.",
        "fluids",
        "hydraulic_force",
        "2000 N",
        "Pascal's principle:",
    ),
    (
        "Use Bernoulli for horizontal water flow: P1 is 100000 Pa, density "
        "1000 kg/m^3, v1 is 2 m/s and v2 is 6 m/s. Find P2.",
        "fluids",
        "bernoulli_pressure",
        "84000 Pa",
        "Bernoulli's equation:",
    ),
    (
        "A 2 m rod has coefficient of linear expansion 12e-6 /K and is heated "
        "by 50 K. Find its linear expansion.",
        "thermal",
        "linear_expansion",
        "0.0012 m",
        "Linear thermal-expansion law:",
    ),
    (
        "Find the latent heat energy for 2 kg with latent heat 334000 J/kg.",
        "thermal",
        "latent_heat",
        "6.68 × 10⁵ J",
        "Latent-heat equation:",
    ),
    (
        "Using the first law of thermodynamics, heat added is 500 J and work "
        "done by the gas is 200 J. Find the change in internal energy.",
        "thermal",
        "first_law_internal_energy",
        "300 J",
        "First law of thermodynamics:",
    ),
]


@pytest.mark.parametrize("query,kind,operation,answer,law_name", CASES)
def test_new_catalog_problem_is_verified_and_explained(
    query: str, kind: str, operation: str, answer: str, law_name: str
) -> None:
    assert needs_physics(query)
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    assert intent.kind == kind
    assert intent.physics_op == operation

    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    assert verified.canonical_answer == answer
    reply = maybe_direct_physics_reply(verified, query)
    assert reply is not None
    # The law's name heads its formulas.
    law = f"**{law_heading(law_name.rstrip(':'))}**"
    headings = ["**Given**", "**Required**", law, "**Substitution**", "**Answer**"]
    assert all(reply.count(heading) == 1 for heading in headings)
    assert [reply.index(heading) for heading in headings] == sorted(
        reply.index(heading) for heading in headings
    )
    assert re.search(r"\d+\.\d*00(?=\D|$)", reply) is None
    assert "*" not in verified.canonical_answer
    if operation == "beat_frequency":
        assert "$f_1 = 440\\,\\mathrm{Hz}$" in reply
        assert "$f_2 = 444\\,\\mathrm{Hz}$" in reply


@pytest.mark.parametrize(
    "query,answer",
    [
        (
            "Two point masses, 2000 g at 0 cm and 3 kg at 400 cm, have what center of mass?",
            "2.4 m",
        ),
        (
            "Find the speed of a wave on a string with tension 100 N and linear density 10 g/m.",
            "100 m/s",
        ),
        (
            "Find the sound intensity 200 cm from a 10 W point source.",
            "0.199 W/m²",
        ),
        (
            "A hydraulic press has input force 100 N, piston areas 100 cm^2 "
            "and 2000 cm^2. Find output force.",
            "2000 N",
        ),
        (
            "Find the latent heat energy for 2 kg with latent heat 334 kJ/kg.",
            "6.68 × 10⁵ J",
        ),
        (
            "Using the first law of thermodynamics, heat added is 0.5 kJ and "
            "work done by the gas is 200 J. Find the change in internal energy.",
            "300 J",
        ),
    ],
)
def test_new_catalog_operations_convert_mixed_units(query: str, answer: str) -> None:
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    assert verified.canonical_answer == answer


@pytest.mark.parametrize(
    ("query", "answer"),
    [
        ("A machine uses 100 J and produces 80 J. Find its efficiency.", "80 %"),
        (
            "A light bulb converts 60 J of electrical energy into 9 J of light. "
            "What is its efficiency?",
            "15 %",
        ),
    ],
)
def test_efficiency_reads_output_over_input(query: str, answer: str) -> None:
    # Efficiency is at most 100%, so the two energies have one reading.
    intent = extract_physics_intent(query)
    assert isinstance(intent, PhysicsIntent)
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None
    assert verified.canonical_answer == answer


@pytest.mark.parametrize(
    "query",
    [
        "Find the fourth harmonic of a 0.5 m closed pipe with sound speed 340 m/s.",
        "Use Bernoulli for water with pressure 100000 Pa and speeds 2 m/s and 6 m/s.",
        "Using the first law, heat is 500 J and work is 200 J. Find internal energy.",
    ],
)
def test_new_catalog_operations_refuse_ambiguous_or_unsupported_shapes(query: str) -> None:
    intent = extract_physics_intent(query)
    if isinstance(intent, PhysicsIntent):
        assert build_verified_physics_block(intent, _SETTINGS) is None
    else:
        assert intent is None
