"""Import seams for the packaged service domains.

Every subject and feature domain lives in its own package under
``app/services/``. The flat ``services/<domain>_<thing>.py`` modules they
replaced are gone, aliases included.
"""

from __future__ import annotations

import importlib

import pytest

# Flat `services/<domain>_<thing>.py` modules that were folded into a domain
# package. The compatibility aliases are gone; importing the old name must fail
# so a future edit cannot quietly reintroduce the split-brain layout.
RETIRED_FLAT_MODULES = (
    "app.services.chemistry_service",
    "app.services.chemistry_context",
    "app.services.chemistry_fence",
    "app.services.push_notifications",
    "app.services.transactional_email",
    "app.services.reminder_emails",
    "app.services.daily_learning",
    "app.services.sm2",
)


@pytest.mark.parametrize("legacy_name", RETIRED_FLAT_MODULES)
def test_retired_flat_modules_are_gone(legacy_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(legacy_name)


def test_packaged_domains_expose_their_public_api() -> None:
    assert callable(importlib.import_module("app.modules.notifications.push").collect_push_page)


def test_language_learning_module_is_gone() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.modules.learning")


def test_chemistry_package_exposes_its_public_api() -> None:
    chemistry = importlib.import_module("app.modules.chemistry")

    assert callable(chemistry.validate_smiles)
    assert callable(chemistry.balance_equation)
    assert callable(chemistry.stoichiometry)
    assert callable(chemistry.molar_mass)
    assert callable(chemistry.solve_chemistry)
    assert callable(
        importlib.import_module("app.modules.chemistry.context").build_chemistry_augmentation
    )
    assert callable(importlib.import_module("app.modules.chemistry.block").build_verified_chemistry)
    assert callable(importlib.import_module("app.modules.chemistry.fence").enrich_chemistry_fences)


def test_math_extraction_public_seam_uses_focused_extractors() -> None:
    extract = importlib.import_module("app.modules.math.tools.extract")

    assert extract.extract_math_intent("solve x + 2 = 5").kind == "equation"
    assert extract.extract_math_intent("draw a square with side 4").kind == "square"
    assert extract.extract_math_intent("differentiate x^2").kind == "calculus"
    assert extract.extract_math_intent("mean of 1, 2, 3").kind == "statistics"


def test_physics_modules_import_cold_in_isolation() -> None:
    """physics.block and math.tools.block reference each other's primitives.

    math.tools.block defers its physics import into the function that uses it;
    without that, importing physics first raises on a partially initialized
    module. Import each one in a fresh interpreter to keep that honest.
    """
    import subprocess
    import sys

    for module in (
        "app.modules.physics.block",
        "app.modules.physics.direct",
        "app.modules.math.tools.block",
        "app.modules.math.tools",
    ):
        result = subprocess.run(  # noqa: S603 - fixed argv, module names are literals above
            [sys.executable, "-c", f"import {module}"], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{module} failed to import cold:\n{result.stderr}"
