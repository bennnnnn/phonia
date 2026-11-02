"""Structural guard: a domain lives in one package, not a package plus siblings.

Every split this repo has had started the same way — a domain got a package,
then the next module landed next to it as `services/<domain>_<thing>.py`
because that was one line cheaper than moving in. Math reached three sibling
packages and six loose files that way; chemistry and notifications
each grew a second copy of themselves as compatibility aliases.

These tests fail on the first module that starts it again.
"""

from __future__ import annotations

import pathlib

import pytest

SERVICES = pathlib.Path(__file__).resolve().parents[2] / "services"

# Packages whose domain is also spelled differently in module prefixes.
PREFIX_ALIASES = {
    "attachments": ("attachment",),
    "images": ("image",),
    # "reminder" is deliberately absent: reminder_timing.py is shared by
    # notifications/ and home/, so it belongs at services/ root.
    "notifications": ("notification", "push"),
    "physics": ("physic",),
}


def _domain_packages() -> list[str]:
    return sorted(
        p.name for p in SERVICES.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
    )


def _flat_modules() -> list[str]:
    return sorted(p.stem for p in SERVICES.glob("*.py") if p.stem != "__init__")


def _claimed_prefixes(package: str) -> tuple[str, ...]:
    return (package, *PREFIX_ALIASES.get(package, ()))


@pytest.mark.parametrize("module", _flat_modules())
def test_flat_module_does_not_shadow_a_domain_package(module: str) -> None:
    """`services/math_fence.py` next to `services/math/` is the split starting."""
    for package in _domain_packages():
        for prefix in _claimed_prefixes(package):
            assert not module.startswith(f"{prefix}_"), (
                f"services/{module}.py belongs inside services/{package}/ "
                f"as {module[len(prefix) + 1 :]}.py — a domain with a package "
                f"does not also keep modules beside it."
            )


def test_no_flat_module_family_large_enough_to_be_a_package() -> None:
    """Three modules sharing a prefix are a domain that has not been named yet."""
    families: dict[str, list[str]] = {}
    for module in _flat_modules():
        prefix, sep, _ = module.partition("_")
        if sep:
            families.setdefault(prefix, []).append(module)

    too_big = {p: sorted(m) for p, m in families.items() if len(m) >= 3}
    assert not too_big, "these flat modules want a package under services/: " + "; ".join(
        f"{p}_* -> services/{p}/ ({', '.join(m)})" for p, m in sorted(too_big.items())
    )
