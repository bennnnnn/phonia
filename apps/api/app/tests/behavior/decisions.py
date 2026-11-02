"""The decision diff: what every corpus turn decided, compared before and after a change.

A structure change must change no behaviour (docs/STRUCTURE_TICKETS.md, ST-00). The battery and
the sweeps check what a turn produced (a card, a route, a saved reminder); this records why it
did: each turn's ``turn_trace`` record (the route reason, the plan's parts, the prompt rules, the
tools, the checked subject and its operation, the money product, the finalize passes that
changed the text) for the behaviour battery, the behaviour sweep and the three STEM corpora.

    uv run python -m app.tests.behavior.decisions dump before.json    # on main
    uv run python -m app.tests.behavior.decisions dump after.json     # on the change
    uv run python -m app.tests.behavior.decisions diff before.json after.json

Timings are dropped, the clock is frozen (``SWEEP_NOW``) and SymPy runs in one thread, so two
dumps of one commit are the same file. ``diff`` prints the turns that changed, grouped by field,
and exits 1 when any did.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.modules.chat.turn_trace import turn_record
from app.tests.behavior import stem_sweep, sweep
from app.tests.behavior.cases import CASES
from app.tests.behavior.harness import Route, route_case

CORPORA = ("battery", "sweep", *sorted(stem_sweep.SUBJECT_NAMES))
# How long a turn took is no decision.
_VOLATILE = ("transport",)


def decision_record(route: Route | None) -> dict[str, Any]:
    """One turn's decisions: its trace record without timings. A turn that crashed says so."""
    if route is None or route.trace is None:
        return {"crashed": True}
    record = turn_record(route.trace, route.context, outcome=None)
    return {
        key: value
        for key, value in record.items()
        if not key.endswith("_ms") and key not in _VOLATILE
    }


async def _battery(only: set[str] | None) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for case in CASES:
        if only is None or case.id in only:
            try:
                route: Route | None = await route_case(case)
            except Exception:  # A crash is a decision too; the battery itself reports it.
                route = None
            records[case.id] = decision_record(route)
    return records


async def _sweep(only: set[str] | None) -> dict[str, dict[str, Any]]:
    entries = [entry for entry in sweep.load() if only is None or entry.id in only]
    return {
        outcome.entry.id: decision_record(outcome.route) for outcome in await sweep.run(entries)
    }


async def _stem(subject: str, only: set[str] | None) -> dict[str, dict[str, Any]]:
    entries = [entry for entry in stem_sweep.load(subject) if only is None or entry.id in only]
    outcomes = await stem_sweep.run(entries, stem_sweep.SUBJECT_NAMES[subject])
    return {outcome.entry.id: decision_record(outcome.route) for outcome in outcomes}


async def collect(
    corpora: Iterable[str] = CORPORA, only: set[str] | None = None
) -> dict[str, dict[str, dict[str, Any]]]:
    """Every turn of ``corpora`` (ids in ``only``, when given), corpus -> id -> record."""
    found: dict[str, dict[str, dict[str, Any]]] = {}
    with sweep.frozen_clock():
        for corpus in corpora:
            if corpus == "battery":
                found[corpus] = await _battery(only)
            elif corpus == "sweep":
                found[corpus] = await _sweep(only)
            else:
                found[corpus] = await _stem(corpus, only)
    return found


def diff(
    before: Mapping[str, Mapping[str, Mapping[str, Any]]],
    after: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, list[str]]:
    """field -> ``corpus:id: before -> after`` for every turn whose field changed. A turn only
    one side has is listed under ``(turn)``."""
    changed: dict[str, list[str]] = {}
    for corpus in sorted(set(before) | set(after)):
        old_turns, new_turns = before.get(corpus, {}), after.get(corpus, {})
        for turn in sorted(set(old_turns) | set(new_turns)):
            name = f"{corpus}:{turn}"
            if turn not in old_turns or turn not in new_turns:
                side = "after" if turn in new_turns else "before"
                changed.setdefault("(turn)", []).append(f"{name}: only {side}")
                continue
            old, new = old_turns[turn], new_turns[turn]
            for key in sorted(set(old) | set(new)):
                if old.get(key) != new.get(key):
                    line = f"{name}: {_shown(old.get(key))} -> {_shown(new.get(key))}"
                    changed.setdefault(key, []).append(line)
    return changed


def _shown(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def report(changed: Mapping[str, list[str]], *, limit: int) -> str:
    if not changed:
        return "no decision changed"
    turns = {line.split(": ", 1)[0] for lines in changed.values() for line in lines}
    lines = [f"{len(turns)} turns changed, in {len(changed)} fields"]
    for key, rows in sorted(changed.items(), key=lambda item: (-len(item[1]), item[0])):
        lines.append(f"\n{key} ({len(rows)})")
        lines.extend(f"  {row}" for row in rows[:limit])
        if len(rows) > limit:
            lines.append(f"  … and {len(rows) - limit} more (--limit)")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    dump_args = commands.add_parser("dump", help="write every turn's decisions")
    dump_args.add_argument("out", type=Path)
    dump_args.add_argument("--corpus", help=f"comma-separated, of {', '.join(CORPORA)}")
    dump_args.add_argument("--only", help="comma-separated turn ids")
    diff_args = commands.add_parser("diff", help="compare two dumps")
    diff_args.add_argument("before", type=Path)
    diff_args.add_argument("after", type=Path)
    diff_args.add_argument("--limit", type=int, default=20, help="turns shown per field")
    diff_args.add_argument(
        "--added",
        action="append",
        default=[],
        help="a field the change adds to the trace: no turn has it before; its values are listed",
    )
    args = parser.parse_args()
    if args.command == "diff":
        before, after = _read(args.before), _read(args.after)
        print(report_added(before, after, args.added))
        changed = diff(before, _without(after, args.added))
        print(report(changed, limit=args.limit))
        sys.exit(1 if changed else 0)
    from app.core.sympy_executor import set_sympy_executor
    from app.tests.sympy_support import ThreadSympyExecutor

    set_sympy_executor(ThreadSympyExecutor(max_workers=1))
    corpora = [name.strip() for name in args.corpus.split(",")] if args.corpus else CORPORA
    only = {item.strip() for item in args.only.split(",")} if args.only else None
    started = time.monotonic()
    found = asyncio.run(collect(corpora, only))
    args.out.write_text(json.dumps(found, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    counts = ", ".join(f"{corpus} {len(turns)}" for corpus, turns in found.items())
    print(f"{counts} turns in {time.monotonic() - started:.0f}s -> {args.out}")


def report_added(
    before: Mapping[str, Mapping[str, Mapping[str, Any]]],
    after: Mapping[str, Mapping[str, Mapping[str, Any]]],
    fields: Iterable[str],
) -> str:
    """Each added field's values over the turns, and any turn that had it before (an error:
    an added field is new on every turn)."""
    lines = []
    for field in fields:
        had = sum(field in record for turns in before.values() for record in turns.values())
        values = collections.Counter(
            _shown(record.get(field)) for turns in after.values() for record in turns.values()
        )
        shown = ", ".join(f"{value} ×{count}" for value, count in values.most_common())
        lines.append(
            f"added {field}: {shown}" + (f" (ERROR: {had} turns had it before)" if had else "")
        )
    return "\n".join(lines)


def _without(
    found: Mapping[str, Mapping[str, Mapping[str, Any]]], fields: Iterable[str]
) -> dict[str, dict[str, dict[str, Any]]]:
    dropped = set(fields)
    return {
        corpus: {
            turn: {key: value for key, value in record.items() if key not in dropped}
            for turn, record in turns.items()
        }
        for corpus, turns in found.items()
    }


def _read(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    loaded: dict[str, dict[str, dict[str, Any]]] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


if __name__ == "__main__":
    main()
