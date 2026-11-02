"""Pin the mobile unit pad's ``toSi`` factors against Pint.

``apps/mobile/features/chat/model/unitConverter.ts`` is a keystroke preview. It keeps display
symbols and prompt tokens that Pint does not own. The shared fact is the
scale: for each non-temperature unit, Pint converts ``1 <prompt>`` into the
category SI base and that magnitude matches ``toSi``. Temperature is an
offset conversion, so it stays out of this check.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services.units import get_unit_registry

_CONVERTER = (
    Path(__file__).resolve().parents[6]
    / "apps"
    / "mobile"
    / "features"
    / "chat"
    / "model"
    / "unitConverter.ts"
)

# Prompt tokens that are not Pint identifiers. The magnitude still comes from Pint.
_PROMPT_UNIT = {
    "AU": "astronomical_unit",
    "light-year": "light_year",
    "fl-oz": "fluid_ounce",
    "Torr": "torr",
}

_SI_BASE = {
    "length": "meter",
    "area": "meter ** 2",
    "volume": "meter ** 3",
    "mass": "kilogram",
    "time": "second",
    "speed": "meter / second",
    "angle": "radian",
    "force": "newton",
    "energy": "joule",
    "power": "watt",
    "pressure": "pascal",
    "frequency": "hertz",
    "density": "kilogram / meter ** 3",
    "amount": "mole",
    "charge": "coulomb",
    "current": "ampere",
    "voltage": "volt",
    "resistance": "ohm",
    "data": "byte",
}


@dataclass(frozen=True)
class PadUnit:
    id: str
    prompt: str
    category: str
    to_si: float


def _eval_factor(expr: str) -> float:
    tree = ast.parse(expr.replace("Math.PI", "pi"), mode="eval")

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id == "pi":
            return math.pi
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        if isinstance(node, ast.BinOp):
            left = walk(node.left)
            right = walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left**right
        raise ValueError(f"unsupported factor expression: {expr}")

    return walk(tree.body)


def _unquote(token: str) -> str:
    if len(token) < 2 or token[0] != '"' or token[-1] != '"':
        raise ValueError(token)
    return token[1:-1]


def _pad_units() -> list[PadUnit]:
    text = _CONVERTER.read_text()
    units: list[PadUnit] = []
    cursor = 0
    while True:
        start = text.find("u(", cursor)
        if start < 0:
            break
        depth = 0
        end = start + 1
        while end < len(text):
            if text[end] == "(":
                depth += 1
            elif text[end] == ")":
                depth -= 1
                if depth == 0:
                    break
            end += 1
        body = text[start + 2 : end]
        parts: list[str] = []
        buf: list[str] = []
        nested = 0
        for ch in body:
            if ch == "(":
                nested += 1
            elif ch == ")":
                nested -= 1
            if ch == "," and nested == 0:
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        parts.append("".join(buf).strip())
        if len(parts) == 6 and parts[0].startswith('"'):
            units.append(
                PadUnit(
                    id=_unquote(parts[0]),
                    prompt=_unquote(parts[3]),
                    category=_unquote(parts[4]),
                    to_si=_eval_factor(parts[5]),
                )
            )
        cursor = end + 1
    return units


_UNITS = _pad_units()
_SCALED = [unit for unit in _UNITS if unit.category != "temperature"]


def test_pad_catalog_parsed() -> None:
    assert len(_UNITS) >= 100
    assert {unit.id for unit in _UNITS if unit.category == "temperature"} == {"c", "f", "k"}


def _pint_magnitude(unit: PadUnit) -> float:
    registry = get_unit_registry()
    if unit.prompt == "rpm":
        # Pint's ``rpm`` is angular (2π rad/min). The frequency pad is cyclic.
        quantity = registry.Quantity(1, "1/minute")
    elif unit.id == "acre":
        foot = registry.Quantity(1, "foot").to("meter").magnitude
        return float(43560 * foot**2)
    else:
        quantity = registry.Quantity(1, _PROMPT_UNIT.get(unit.prompt, unit.prompt))
    return float(quantity.to(_SI_BASE[unit.category]).magnitude)


@pytest.mark.parametrize("unit", _SCALED, ids=lambda unit: unit.id)
def test_pad_to_si_matches_pint(unit: PadUnit) -> None:
    got = _pint_magnitude(unit)
    scale = max(abs(unit.to_si), 1e-30)
    assert abs(got - unit.to_si) / scale < 1e-9
