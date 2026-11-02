"""Verified data pictures: box plot, frequency, stem-and-leaf, histogram, scatter, trees."""

from __future__ import annotations

import math
import statistics
from fractions import Fraction

from app.modules.math.schemas.teaching import (
    BoxPlotSpec,
    FrequencyRow,
    FrequencyTableSpec,
    HistogramBin,
    HistogramSpec,
    ProbabilityBranch,
    ProbabilityTreeSpec,
    ScatterPoint,
    ScatterSpec,
    StemLeafRow,
    StemLeafSpec,
)


def _school(value: float) -> str:
    return f"{value:.12g}"


def _numbers(payload: str, *, limit: int) -> list[float] | None:
    chunks = [chunk.strip() for chunk in payload.split(",") if chunk.strip()]
    if not 1 <= len(chunks) <= limit:
        return None
    values: list[float] = []
    for chunk in chunks:
        if any(not (char.isdigit() or char in ".-") for char in chunk):
            return None
        if chunk.count(".") > 1 or chunk.count("-") > 1:
            return None
        try:
            value = float(chunk)
        except ValueError:
            return None
        if not math.isfinite(value) or abs(value) > 1_000_000:
            return None
        values.append(value)
    return values


def box_plot_spec(payload: str, answer: str | None = None) -> BoxPlotSpec | None:
    values = _numbers(payload, limit=40)
    if values is None or len(values) < 2:
        return None
    cuts = statistics.quantiles(values, n=4, method="inclusive")
    minimum, maximum = min(values), max(values)
    q1, median, q3 = (_school(cuts[0]), _school(cuts[1]), _school(cuts[2]))
    low, high = _school(minimum), _school(maximum)
    chip = answer or ", ".join((low, q1, median, q3, high))
    speech = (
        f"The five-number summary is minimum {low}, first quartile {q1}, "
        f"median {median}, third quartile {q3}, maximum {high}."
    )
    return BoxPlotSpec(
        minimum=low,
        q1=q1,
        median=median,
        q3=q3,
        maximum=high,
        answer=chip,
        speech=speech,
    )


def frequency_table_spec(payload: str) -> FrequencyTableSpec | None:
    values = _numbers(payload, limit=40)
    if values is None:
        return None
    counts: dict[str, int] = {}
    for value in values:
        label = _school(value)
        counts[label] = counts.get(label, 0) + 1
    rows = [FrequencyRow(value=label, count=count) for label, count in counts.items()]
    if len(rows) > 20:
        return None
    listed = ", ".join(f"{row.value} appears {row.count}" for row in rows)
    return FrequencyTableSpec(
        rows=rows,
        answer=listed,
        speech=f"The frequencies are {listed}.",
    )


def stem_leaf_spec(payload: str) -> StemLeafSpec | None:
    values = _numbers(payload, limit=40)
    if values is None or any(value != int(value) or not 0 <= value <= 99 for value in values):
        return None
    grouped: dict[int, list[int]] = {}
    for value in sorted(int(item) for item in values):
        grouped.setdefault(value // 10, []).append(value % 10)
    rows = [
        StemLeafRow(stem=str(stem), leaves=" ".join(str(leaf) for leaf in leaves))
        for stem, leaves in grouped.items()
    ]
    drawn = "; ".join(f"{row.stem} | {row.leaves}" for row in rows)
    return StemLeafSpec(rows=rows, answer=drawn, speech=f"Stem and leaf: {drawn}.")


def histogram_spec(payload: str) -> HistogramSpec | None:
    values = _numbers(payload, limit=40)
    if values is None or any(value != int(value) for value in values):
        return None
    integers = [int(value) for value in values]
    low, high = min(integers), max(integers)
    if high - low > 15:
        return None
    bins = [
        HistogramBin(label=str(bucket), count=integers.count(bucket))
        for bucket in range(low, high + 1)
    ]
    listed = ", ".join(f"{bin_.label}: {bin_.count}" for bin_ in bins if bin_.count)
    return HistogramSpec(bins=bins, answer=listed, speech=f"Each integer is its own bin. {listed}.")


def scatter_spec(payload: str) -> ScatterSpec | None:
    pairs = [chunk.strip() for chunk in payload.split(";") if chunk.strip()]
    if not 2 <= len(pairs) <= 12:
        return None
    points: list[ScatterPoint] = []
    for pair in pairs:
        left, separator, right = pair.partition(",")
        if not separator:
            return None
        parsed = _numbers(f"{left},{right}", limit=2)
        if parsed is None or len(parsed) != 2:
            return None
        points.append(ScatterPoint(x=_school(parsed[0]), y=_school(parsed[1])))
    listed = ", ".join(f"({point.x}, {point.y})" for point in points)
    return ScatterSpec(
        points=points,
        answer=listed,
        speech=f"The scatter plot has the points {listed}.",
    )


def probability_tree_spec(kind: str) -> ProbabilityTreeSpec | None:
    if kind == "coin":
        branches = [
            ProbabilityBranch(label="heads", probability=r"\frac{1}{2}"),
            ProbabilityBranch(label="tails", probability=r"\frac{1}{2}"),
        ]
        speech = "A fair coin has two branches, heads and tails, each with probability 1/2."
    elif kind == "coins2":
        branches = [
            ProbabilityBranch(
                label=first,
                probability=r"\frac{1}{2}",
                children=[
                    ProbabilityBranch(label=f"{first}, {second}", probability=r"\frac{1}{4}")
                    for second in ("heads", "tails")
                ],
            )
            for first in ("heads", "tails")
        ]
        speech = "Two fair coin flips have four outcomes, each with probability 1/4."
    elif kind == "die":
        branches = [
            ProbabilityBranch(label=str(face), probability=r"\frac{1}{6}") for face in range(1, 7)
        ]
        speech = "A fair die has six branches, each with probability 1/6."
    else:
        return None
    if not _leaves_sum_to_one(branches):
        return None
    return ProbabilityTreeSpec(branches=branches, answer=speech, speech=speech)


def _leaves_sum_to_one(branches: list[ProbabilityBranch]) -> bool:
    total = Fraction(0)

    def walk(branch: ProbabilityBranch) -> None:
        nonlocal total
        if branch.children:
            for child in branch.children:
                walk(child)
            return
        total += _latex_fraction(branch.probability)

    for branch in branches:
        walk(branch)
    return total == 1


def _latex_fraction(value: str) -> Fraction:
    inside = value.removeprefix(r"\frac{").removesuffix("}")
    numerator, separator, denominator = inside.partition("}{")
    if not separator:
        raise ValueError(value)
    return Fraction(int(numerator), int(denominator))
