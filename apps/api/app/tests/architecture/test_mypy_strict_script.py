"""The strict ratchet lets a package go only when an override really holds all of it."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[5] / "scripts" / "check_mypy_strict.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_mypy_strict", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pyproject(modules: list[str], *, flags: tuple[str, ...]) -> str:
    listed = ", ".join(f'"{module}"' for module in modules)
    lines = [f"{flag} = true" for flag in flags]
    return "[tool.mypy]\n\n[[tool.mypy.overrides]]\nmodule = [" + listed + "]\n" + "\n".join(lines)


@pytest.mark.parametrize(
    ("modules", "drop_flag", "held"),
    [
        (["app.modules.physics", "app.modules.physics.*"], None, True),
        # 2026-11-01: listing the package alone held only its __init__, yet left the ratchet.
        (["app.modules.physics"], None, False),
        (["app.modules.physics.*"], None, False),
        (["app.modules.physics", "app.modules.physics.*"], "warn_return_any", False),
        # 2026-11-01: --strict's extra_checks was not asked for.
        (["app.modules.physics", "app.modules.physics.*"], "extra_checks", False),
    ],
)
def test_a_package_leaves_the_ratchet_only_when_wholly_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    modules: list[str],
    drop_flag: str | None,
    held: bool,
) -> None:
    script = _load()
    flags = tuple(flag for flag in script.STRICT_FLAGS if flag != drop_flag)
    (tmp_path / "pyproject.toml").write_text(_pyproject(modules, flags=flags))
    monkeypatch.setattr(script, "API", tmp_path)
    assert ("app.modules.physics" in script.strict_packages()) is held
    assert ("app.modules.physics" in script.ratcheted()) is not held


def test_the_strict_flags_are_every_per_module_flag_of_mypy_strict() -> None:
    """mypy's own --strict list, less what only the global section can set."""
    from mypy.main import define_options
    from mypy.options import PER_MODULE_OPTIONS

    _, _, assignments = define_options()
    expected = {
        dest if value else f"no_{dest}" for dest, value in assignments if dest in PER_MODULE_OPTIONS
    }
    assert set(_load().STRICT_FLAGS) == expected


def test_an_inverted_spelling_holds_its_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _load()
    flags = tuple(flag for flag in script.STRICT_FLAGS if flag != "no_implicit_reexport")
    text = _pyproject(["app.modules.physics", "app.modules.physics.*"], flags=flags)
    (tmp_path / "pyproject.toml").write_text(text + "\nimplicit_reexport = false\n")
    monkeypatch.setattr(script, "API", tmp_path)
    assert "app.modules.physics" in script.strict_packages()
