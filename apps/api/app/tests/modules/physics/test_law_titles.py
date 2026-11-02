"""Every law heads its formulas with a name a student reads as the law, not "Formula"."""

from __future__ import annotations

import re

import pytest

from app.modules.physics.catalog import CATALOG
from app.modules.physics.law_titles import law_heading, law_title
from app.services.workout import FORMULA


def test_every_catalog_law_has_a_short_heading() -> None:
    # The phone takes a bold line of up to ten words over maths as a law's heading
    # (apps/mobile/lib/markdown/workoutSection.ts lawHeading); a longer one would lose it.
    for spec in CATALOG.values():
        title = law_title(spec.law_name)
        assert 1 <= len(title.split()) <= 8, (spec.id, title)
        assert not re.search(r"[.:?!]$", title), (spec.id, title)


def test_every_catalog_law_heading_names_it() -> None:
    # The heading over the formulas is the title and "formula" (one rule for every subject);
    # it still reads as a heading on the phone, and no law falls back to a bare "Formula".
    for spec in CATALOG.values():
        heading = law_heading(spec.law_name)
        assert heading != FORMULA, spec.id
        assert len(heading.split()) <= 10, (spec.id, heading)
        assert heading.lower().startswith(law_title(spec.law_name).lower()), (spec.id, heading)


def test_no_heading_says_formula_or_hyphenates_a_noun() -> None:
    for spec in CATALOG.values():
        title = law_title(spec.law_name)
        assert not title.endswith(" formula") or title == "Rydberg formula", (spec.id, title)
        # "Kinetic-energy" is the index's spelling; a heading reads "Kinetic energy".
        if title != spec.law_name:
            assert not re.search(r"[a-z]-[a-z]", title), (spec.id, title)


@pytest.mark.parametrize(
    ("law_name", "title"),
    [
        ("SUVAT constant-acceleration equation", "Constant acceleration"),
        ("Constant-acceleration equation", "Constant acceleration"),
        ("Kinetic-energy formula", "Kinetic energy"),
        ("Moment-of-inertia formula", "Moment of inertia"),
        ("Projectile-motion equation", "Projectile motion"),
        ("Photon-energy relation", "Photon energy"),
        ("Torque formula", "Torque"),
        ("Young's modulus formula", "Young's modulus"),
        # A pair of quantities, not one compound noun.
        ("Frequency-period relation", "Frequency and period"),
        # Named for itself, or for people: kept as written.
        ("Newton's second law", "Newton's second law"),
        ("Continuity equation", "Continuity equation"),
        ("Stefan-Boltzmann law", "Stefan-Boltzmann law"),
        ("Young-Laplace equation", "Young-Laplace equation"),
        ("Vis-viva equation", "Vis-viva equation"),
        ("Rydberg formula", "Rydberg formula"),
        ("de Broglie relation", "de Broglie relation"),
    ],
)
def test_law_title(law_name: str, title: str) -> None:
    assert law_title(law_name) == title
