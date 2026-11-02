"""The ``calculator`` fence: sliders over the asked inputs, live readouts from the formulas.

Each readout is the catalog's own formula as a tree (``expression.to_tree``), the same
one the server worked the reply's numbers with. Before it is sent the card checks itself:
only declared names, the server's numbers at the asked values, and no failure at any
corner of the slider ranges other than "no number" (a card payment that never clears).
A card that fails is not sent; the reply keeps its worked numbers.
"""

from __future__ import annotations

import itertools
import json
import logging
import math

from pydantic import ValidationError

from app.modules.money.catalog import Input, Span
from app.modules.money.rates import MarketRate
from app.modules.money.schemas import CalculatorSpec, Control, Marker, Readout
from app.modules.money.solve import Worked, output_value, rate_name
from app.services.law_binding.expression import names, to_tree
from app.services.md_fence_scan import iter_closed_fences

logger = logging.getLogger(__name__)

_NICE = (1.0, 2.0, 2.5, 5.0, 10.0)
# About this many steps from one end of a money slider to the other.
_STEPS = 200
_CORNER_LIMIT = 64


def calculator_fence(worked: Worked, average: MarketRate | None, currency: str) -> str | None:
    """The card's fence text, or None when the card fails its own checks."""
    product = worked.product
    expressions = worked.expressions()
    try:
        spec = CalculatorSpec(
            product=product.family,
            title_key=product.title_key,
            currency=currency,
            controls=[_control(item, worked, average) for item in product.inputs],
            readouts=[
                Readout(
                    name=item.name,
                    label_key=item.label_key,
                    format=item.format,
                    tree=to_tree(expressions[item.name]),
                    primary=item.primary,
                    never_key=item.never_key,
                )
                for item in product.outputs
            ],
        )
    except (ValidationError, ValueError):
        logger.warning("money card for %s did not build", product.key, exc_info=True)
        return None
    if not card_checks(spec, worked):
        logger.warning("money card for %s failed its checks", product.key)
        return None
    body = json.dumps(spec.model_dump(exclude_none=True), separators=(",", ":"))
    return f"```calculator\n{body}\n```"


def card_checks(spec: CalculatorSpec, worked: Worked) -> bool:
    """Declared names only, the worked numbers at the asked values, no failure at a corner."""
    declared = {control.name for control in spec.controls} | {"pi"}
    expressions = worked.expressions()
    for readout in spec.readouts:
        expression = expressions[readout.name]
        if not names(expression) <= declared:
            return False
        asked, worked_value = output_value(expression, worked.values), worked.outputs[readout.name]
        if (asked is None) != (worked_value is None):
            return False
        if asked is not None and worked_value is not None:
            if not math.isclose(asked, worked_value, rel_tol=1e-9, abs_tol=1e-9):
                return False
    return _corners_hold(spec, list(expressions.values()))


def _corners_hold(spec: CalculatorSpec, expressions: list[str]) -> bool:
    ends = [(control.name, (control.min, control.max)) for control in spec.controls]
    for count, choice in enumerate(itertools.product(*(pair for _, pair in ends))):
        if count >= _CORNER_LIMIT:
            break
        values = dict(zip((name for name, _ in ends), choice, strict=True))
        for expression in expressions:
            # output_value turns a domain error into "no number"; anything else is a fault.
            try:
                output_value(expression, values)
            except Exception:
                return False
    return True


def _control(item: Input, worked: Worked, average: MarketRate | None) -> Control:
    value = worked.values[item.name]
    is_rate = item.name == rate_name(worked.product)
    low, high, step = slider_range(
        item.span, value, average.value if (is_rate and average) else None
    )
    marker = None
    if is_rate and average is not None:
        marker = Marker(
            value=average.value,
            as_of=average.as_of.isoformat(),
            source=average.source_title,
            source_url=average.source_url,
        )
    return Control(
        name=item.name,
        label_key=item.label_key,
        format=item.format,
        min=min(low, value),
        max=max(high, value),
        step=step,
        value=value,
        marker=marker,
    )


def slider_range(span: Span, value: float, average: float | None) -> tuple[float, float, float]:
    """The slider's ends and step for ``value`` under ``span``; a follow-up's new value
    must lie within the ends of the slider its asked value had (``follow_up``)."""
    if span.kind == "fixed":
        return span.low, span.high, span.step
    if span.kind == "rate":
        reach = 2 * max(value, average or 0.0)
        high = max(span.high, math.ceil(reach / 5) * 5)
        return 0.0, high, span.step
    base = value if value > 0 else span.base
    low = _nice(base * span.low, up=False) if span.low > 0 else 0.0
    high = _nice(base * span.high, up=True)
    if span.ceiling:
        high = min(high, span.ceiling)
    step = span.step or _nice((high - low) / _STEPS, up=False)
    return low, high, step


def _nice(value: float, *, up: bool) -> float:
    """The nearest 1, 2, 2.5 or 5 times a power of ten, above (``up``) or below ``value``."""
    if value <= 0:
        return 0.0
    power = 10 ** math.floor(math.log10(value))
    steps = [power * factor for factor in _NICE]
    if up:
        return next(step for step in steps if step >= value - 1e-9)
    return max(step for step in steps if step <= value + 1e-9)


def card_values(reply: str) -> dict[str, float]:
    """The asked values of the last calculator card in ``reply`` (control name -> value).

    A follow-up compares its rate with the one the last reply showed. A card that does not
    parse gives nothing.
    """
    bodies = [body for _, _, body in iter_closed_fences(reply, "calculator")]
    if not bodies:
        return {}
    try:
        spec = CalculatorSpec.model_validate(json.loads(bodies[-1]))
    except (ValueError, ValidationError):
        return {}
    return {control.name: control.value for control in spec.controls}
