#!/usr/bin/env python3
"""Compare two battery runs and fail on regressions.

``scripts/battery.py`` writes one record per run, ``tmp/battery/<model>-<sha>.json``:
each case's routing, the model that answered, time to first token, reply length,
tokens and estimated cost. Run the battery before and after a model or prompt
change, then:

    python3 scripts/battery_compare.py tmp/battery/auto-3db7f6d.json tmp/battery/auto-9a1c2e0.json

A regression, which makes the exit status 1:

- a case that answered before now errors, or a check it passed now misses;
- a case routes differently (search, photo, card, status) or another model answers;
- the first token comes much later: over ``--latency-ratio`` times the old time and
  more than ``--latency-floor`` seconds later, so a 0.4s to 0.9s wobble does not count.

Cases only one run has, and cost changes, are reported but do not fail.
No third-party imports: it runs with any Python 3.11+.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_LATENCY_RATIO = 1.5
DEFAULT_LATENCY_FLOOR_S = 2.0
# A per-case cost change worth a line in the report (not a failure).
COST_CHANGE_RATIO = 1.25


@dataclass
class Comparison:
    regressions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.regressions)


def _cases(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = run.get("cases")
    if not isinstance(cases, dict):
        raise ValueError("not a battery run record: no 'cases' object")
    return cases


def _latency(
    case_id: str, old: dict[str, Any], new: dict[str, Any], ratio: float, floor: float
) -> str | None:
    before, after = old.get("first_token_s"), new.get("first_token_s")
    if not isinstance(before, int | float) or not isinstance(after, int | float):
        return None
    if after > before * ratio and after - before > floor:
        return f"{case_id}: first token {before:.1f}s -> {after:.1f}s"
    return None


def _cost_note(case_id: str, old: dict[str, Any], new: dict[str, Any]) -> str | None:
    before, after = old.get("est_cost_usd"), new.get("est_cost_usd")
    if not isinstance(before, int | float) or not isinstance(after, int | float) or before <= 0:
        return None
    if after > before * COST_CHANGE_RATIO or after < before / COST_CHANGE_RATIO:
        return f"{case_id}: est. cost ${before:.5f} -> ${after:.5f}"
    return None


def _compare_case(
    case_id: str, old: dict[str, Any], new: dict[str, Any], ratio: float, floor: float
) -> tuple[list[str], list[str]]:
    regressions: list[str] = []
    if new.get("error") and not old.get("error"):
        regressions.append(f"{case_id}: now errors ({new['error']})")
    new_misses = sorted(set(new.get("misses") or []) - set(old.get("misses") or []))
    if new_misses:
        regressions.append(f"{case_id}: now misses {', '.join(new_misses)}")
    if not new.get("error") and not old.get("error"):
        if old.get("route") != new.get("route"):
            regressions.append(f"{case_id}: routing {old.get('route')!r} -> {new.get('route')!r}")
        elif old.get("model") != new.get("model"):
            regressions.append(f"{case_id}: model {old.get('model')} -> {new.get('model')}")
        slower = _latency(case_id, old, new, ratio, floor)
        if slower:
            regressions.append(slower)
    cost = _cost_note(case_id, old, new)
    return regressions, [cost] if cost else []


def compare(
    base: dict[str, Any],
    new: dict[str, Any],
    *,
    latency_ratio: float = DEFAULT_LATENCY_RATIO,
    latency_floor_s: float = DEFAULT_LATENCY_FLOOR_S,
) -> Comparison:
    """What changed from ``base`` to ``new``: regressions fail, notes inform."""
    result = Comparison()
    old_cases, new_cases = _cases(base), _cases(new)
    for case_id in sorted(old_cases.keys() - new_cases.keys()):
        result.notes.append(f"{case_id}: not in the new run")
    for case_id in sorted(new_cases.keys() - old_cases.keys()):
        result.notes.append(f"{case_id}: new case")
    for case_id in sorted(old_cases.keys() & new_cases.keys()):
        regressions, notes = _compare_case(
            case_id, old_cases[case_id], new_cases[case_id], latency_ratio, latency_floor_s
        )
        result.regressions += regressions
        result.notes += notes
    return result


def _load(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a battery run record")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail on regressions between two battery runs.")
    parser.add_argument("base", help="the earlier run's tmp/battery/<model>-<sha>.json")
    parser.add_argument("new", help="the later run's record")
    parser.add_argument("--latency-ratio", type=float, default=DEFAULT_LATENCY_RATIO)
    parser.add_argument("--latency-floor", type=float, default=DEFAULT_LATENCY_FLOOR_S)
    args = parser.parse_args(argv)
    try:
        base, new = _load(args.base), _load(args.new)
        result = compare(
            base, new, latency_ratio=args.latency_ratio, latency_floor_s=args.latency_floor
        )
    except (OSError, ValueError) as exc:
        print(f"Cannot compare: {exc}", file=sys.stderr)
        return 2
    for line in result.regressions:
        print(f"REGRESSION {line}")
    for line in result.notes:
        print(f"note       {line}")
    shared = len(_cases(base).keys() & _cases(new).keys())
    print(f"\n{shared} cases compared, {len(result.regressions)} regression(s).")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
