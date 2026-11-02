"""Measure the model reader against today's pattern readers (docs/MODEL_READER.md).

A script, not a test: it calls the real model through the gateway (``apps/api/.env``).

    uv run python -m app.tests.behavior.reader_eval translate --per-subject 40
    uv run python -m app.tests.behavior.reader_eval run --books <sets dir> --dump rows.jsonl
    uv run python -m app.tests.behavior.reader_eval rejudge rows.jsonl

``run`` reads every STEM corpus entry (and each translated copy) three ways and judges
each card with the sweep's own checks (``stem_sweep.check_answer``):

- ``regex``: the turn as it runs today (``stem_sweep.run_entry``, model mocked);
- ``model``: ``model_reader.read_with_model`` and the same solvers;
- ``both``: a card only when the two agree on its value.

It prints, per subject and language: reach (cards on questions that have an answer),
wrong cards (a value the worked answer is not, or a number for a question with none),
the read's latency p50/p95, and tokens and cost per 1,000 turns. Two rows are held out
from the corpus the patterns were built on: the physics ``holdout.json`` (questions written
after the fixes) and, with ``--books``, textbook sets read from a path, judged on the
questions whose book answer is one value (1%, any unit of its kind; prose is skipped and
counted). ``translate`` writes ``reader_corpus/<lang>.json``, keeping a translation only
when every number survives it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pint
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.models.model_catalog import CATALOG
from app.models.routing_lanes import ROUTING
from app.modules.model_reader.checks import normalized, values_in
from app.modules.model_reader.schemas import ModelRead
from app.modules.model_reader.service import read_with_model
from app.tests.behavior.stem_sweep import (
    SUBJECT_NAMES,
    Entry,
    check_answer,
    latex_to_plain,
    load,
    run_entry,
)

CORPUS = Path(__file__).with_name("reader_corpus")
LANGUAGES = {
    "am": "Amharic",
    "es": "Spanish",
    "fr": "French",
    "ar": "Arabic",
    "hi": "Hindi",
}
_CONCURRENCY = 6
# Physics questions written after the fixes: the patterns were not tuned on them.
_HOLDOUT = Path(__file__).with_name("stem_corpus") / "physics" / "holdout.json"
_BOOK_SUBJECTS = {"physics": "physics", "chemistry": "chemistry", "maths": "math", "math": "math"}
# A book answer that is one value: "3000 N", "98.6 °F", "x = 2", "17", "5.8 x 10^7 m".
_CLEAR_ANSWER = re.compile(
    r"^(?:about |approximately |\u2248 ?)?(?:[a-z][\w()]* ?= ?)?"
    r"(?P<number>-?\d+(?:\.\d+)?)(?: ?[x\u00d7] ?10\^(?P<power>-?\d+))?"
    r"(?: ?(?P<unit>[a-z\u00b0%\u03a9\u00b5][a-z\u00b0%\u03a9\u00b5/^\d\u00b7*-]{0,11}))? ?\.?$",
    re.IGNORECASE,
)
_UNITS = pint.UnitRegistry()
_SUPERSCRIPT_POWER = re.compile("[\u2070\u00b9\u00b2\u00b3\u2074-\u2079\u207b]+")
_FROM_SUPERSCRIPT = str.maketrans(
    "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207b", "0123456789-"
)


def _caret_power(match: re.Match[str]) -> str:
    return "^" + match.group(0).translate(_FROM_SUPERSCRIPT)


_DASHES = str.maketrans({"\u2013": "-", "\u2212": "-"})
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")


@dataclass
class Row:
    """One question read three ways."""

    subject: str
    lang: str
    entry: Entry
    regex_card: str | None = None
    regex_wrong: bool = False
    model: ModelRead | None = None
    model_card: str | None = None
    model_wrong: bool = False
    both_card: str | None = None
    both_wrong: bool = False


@dataclass
class Tally:
    rows: list[Row] = field(default_factory=list)

    def line(self, label: str) -> str:
        rows = self.rows
        answerable = [row for row in rows if row.entry.expect == "answer"]

        def reach(attr: str) -> str:
            return f"{sum(1 for row in answerable if getattr(row, attr))}/{len(answerable)}"

        def wrong(attr: str) -> int:
            return sum(1 for row in rows if getattr(row, attr))

        times = sorted(row.model.ms for row in rows if row.model is not None)
        p50 = statistics.median(times) if times else 0.0
        p95 = times[min(len(times) - 1, int(0.95 * len(times)))] if times else 0.0
        reads = [row.model for row in rows if row.model is not None]
        price = _prices()
        cost = (
            1000
            * sum(read.input_tokens * price[0] + read.output_tokens * price[1] for read in reads)
            / max(len(reads), 1)
            / 1e6
        )
        return (
            f"{label:<16} n={len(rows):<4} reach regex {reach('regex_card'):>8} "
            f"model {reach('model_card'):>8} both {reach('both_card'):>8} | wrong "
            f"{wrong('regex_wrong')}/{wrong('model_wrong')}/{wrong('both_wrong')} | "
            f"read p50 {p50 / 1000:.2f}s p95 {p95 / 1000:.2f}s | ${cost:.2f}/1k turns"
        )


def _prices() -> tuple[float, float]:
    entry = next(item for item in CATALOG if item.id == ROUTING.math_extract)
    return entry.input_price_per_m or 0.0, entry.output_price_per_m or 0.0


# --- the three reads ---------------------------------------------------------------


async def _regex(row: Row) -> None:
    """The turn as it runs today, judged as the sweep judges it."""
    entry = row.entry
    try:
        outcome = await run_entry(entry, SUBJECT_NAMES[row.subject])
    except Exception as exc:  # A crash is a finding, as in the sweep.
        print(f"regex crashed on {entry.id}: {type(exc).__name__}", file=sys.stderr)
        return
    route = outcome.route
    if route is not None and route.solved:
        row.regex_card = route.verified_answer or outcome.got or "card"
    row.regex_wrong = any(problem.kind == "wrong" for problem in outcome.problems)


def _solved(subject: str, intent: Any, settings: Settings) -> str | None:
    """The card the subject's solver gives the model's intent."""
    try:
        if subject == "physics":
            from app.modules.physics import build_verified_physics_block

            block: Any = build_verified_physics_block(intent, settings)
        elif subject == "chemistry":
            from app.modules.chemistry.block import build_verified_chemistry

            block = build_verified_chemistry(intent)
        else:
            from app.modules.math.tools.block import _build_verified_block

            block = _build_verified_block(intent, settings)
    except Exception as exc:
        print(f"solve crashed: {type(exc).__name__}", file=sys.stderr)
        return None
    if block is None:
        return None
    return getattr(block, "display_answer", None) or getattr(block, "canonical_answer", None)


def _judge(row: Row, card: str | None) -> bool:
    """A wrong card: a value the worked answer is not, or any card where none belongs."""
    if card is None:
        return False
    entry = row.entry
    if entry.expect != "answer":
        return True
    _got, problems = check_answer(entry, row.subject, f"```answer\n{card}\n```", whole=False)
    return any(problem.kind == "wrong" for problem in problems)


def _same_card(first: str, second: str) -> bool:
    """The same card, spacing aside. Two operations may write one value two ways ("8 cm",
    "0.08 m"); that counts as no agreement, which can only cost a card, never add one."""

    def plain(card: str) -> str:
        return "".join(latex_to_plain(card).split()).replace("\\,", "")

    return plain(first) == plain(second)


async def _model(row: Row, settings: Settings, gate: asyncio.Semaphore) -> None:
    async with gate:
        row.model = await read_with_model(row.entry.prompt, settings)


def _finish(row: Row, settings: Settings) -> None:
    read = row.model
    if read is not None and read.reason == "ok" and read.intent is not None and read.subject:
        row.model_card = _solved(read.subject, read.intent, settings)
    _judge_row(row)


def _judge_row(row: Row) -> None:
    """Judge the model's card by its value, whichever subject's law gave it (gas laws are
    physics', and a chemistry question may be read there); and keep the patterns' card,
    the one a student would see, only when the model's is the same card."""
    row.model_wrong = _judge(row, row.model_card)
    if row.regex_card and row.model_card and _same_card(row.regex_card, row.model_card):
        row.both_card = row.regex_card
        row.both_wrong = row.regex_wrong


# --- corpora -----------------------------------------------------------------------


def _sample(entries: list[Entry], count: int, seed: int) -> list[Entry]:
    """The same entries for the same seed: a measurement others can rerun."""
    chooser = random.Random(seed)  # noqa: S311 - a reproducible sample, not a secret
    return chooser.sample(entries, count)


def _translated(lang: str) -> list[tuple[str, Entry]]:
    path = CORPUS / f"{lang}.json"
    if not path.exists():
        return []
    originals = {(subject, entry.id): entry for subject in SUBJECT_NAMES for entry in load(subject)}
    found: list[tuple[str, Entry]] = []
    for item in json.loads(path.read_text()):
        entry = originals.get((item["subject"], item["id"]))
        if entry is not None:
            found.append((item["subject"], _with_prompt(entry, item["prompt"])))
    return found


def _book_answer(expected: str) -> tuple[float, str] | None:
    """The one value a book's answer states, or None for an answer in prose, in parts,
    or as a choice. Only the text before the first bracket (its working) is read."""
    # The working follows in brackets after a space; "z = 2(cos …)" is no plain value.
    head = expected.split(" (")[0].strip().translate(_DASHES)
    head = _THOUSANDS.sub(
        "", unicodedata.normalize("NFKC", _SUPERSCRIPT_POWER.sub(_caret_power, head))
    )
    found = _CLEAR_ANSWER.match(head)
    if found is None:
        return None
    unit = found["unit"] or ""
    if unit:
        # Only a unit the judge reads: "42 students" is a count it cannot compare.
        try:
            _UNITS.Unit(unit.replace("\u00b0", "degree").replace("^", "**"))
        except Exception:
            return None
    return float(found["number"]) * 10 ** int(found["power"] or 0), unit


def _book_rows(items: list[dict[str, Any]]) -> tuple[list[Row], int]:
    """A row for each textbook question whose answer is one value; how many were skipped."""
    rows: list[Row] = []
    for item in items:
        subject = _BOOK_SUBJECTS.get(str(item.get("subject", "")).lower())
        answer = _book_answer(str(item.get("expected", "")))
        if subject is None or answer is None:
            continue
        entry = Entry(
            id=str(item["id"]),
            area="book",
            prompt=str(item["question"]),
            expect="answer",
            answers=(answer,),
        )
        rows.append(Row(subject, "book", entry))
    return rows, len(items) - len(rows)


def _with_prompt(entry: Entry, prompt: str) -> Entry:
    from dataclasses import replace

    return replace(entry, prompt=prompt, history=())


async def run(
    langs: list[str],
    subjects: list[str],
    limit: int | None,
    seed: int,
    call_seconds: float,
    dump: Path | None = None,
    books: list[dict[str, Any]] | None = None,
) -> None:
    from app.core.sympy_executor import set_sympy_executor
    from app.tests.sympy_support import ThreadSympyExecutor

    set_sympy_executor(ThreadSympyExecutor(max_workers=1))
    settings = Settings(model_reader_timeout_seconds=call_seconds)
    holdout = {item["id"] for item in json.loads(_HOLDOUT.read_text())}
    rows, skipped = _book_rows(books or [])
    if books:
        print(f"books: {len(rows)} questions with one clear value, {skipped} skipped (prose)")
    rows = [row for row in rows if row.subject in subjects]
    for lang in langs:
        if lang == "en":
            for subject in subjects:
                entries = [entry for entry in load(subject) if not entry.history]
                if limit:
                    entries = _sample(entries, min(limit, len(entries)), seed)
                rows += [
                    Row(subject, "holdout" if entry.id in holdout else "en", entry)
                    for entry in entries
                ]
        else:
            rows += [
                Row(subject, lang, entry)
                for subject, entry in _translated(lang)
                if subject in subjects
            ]
    for row in rows:
        await _regex(row)
    # Reads run side by side and each binds in the pool: a slot each, and one to spare
    # (the reader only binds with a slot to spare, as in a turn).
    set_sympy_executor(ThreadSympyExecutor(max_workers=_CONCURRENCY + 1))
    gate = asyncio.Semaphore(_CONCURRENCY)
    await asyncio.gather(*(_model(row, settings, gate) for row in rows))
    set_sympy_executor(ThreadSympyExecutor(max_workers=1))
    for row in rows:
        _finish(row, settings)
    order = ["en", "holdout", *[lang for lang in langs if lang != "en"], "book"]
    _report(rows, [lang for lang in order if any(row.lang == lang for row in rows)], subjects)
    if dump is not None:
        _dump(rows, dump)


def _dump(rows: list[Row], path: Path) -> None:
    """Every row as one JSON line: ids, cards and reasons, for reading the misses."""
    with path.open("w") as out:
        for row in rows:
            read = row.model
            out.write(
                json.dumps(
                    {
                        "lang": row.lang,
                        "subject": row.subject,
                        "id": row.entry.id,
                        "expect": row.entry.expect,
                        "answers": [list(answer) for answer in row.entry.answers],
                        "regex_card": row.regex_card,
                        "regex_wrong": row.regex_wrong,
                        "model_subject": read.subject if read else None,
                        "model_op": read.op if read else None,
                        "reason": read.reason if read else None,
                        "ms": read.ms if read else None,
                        "input_tokens": read.input_tokens if read else 0,
                        "output_tokens": read.output_tokens if read else 0,
                        "model_card": row.model_card,
                        "model_wrong": row.model_wrong,
                        "both_card": row.both_card,
                        "both_wrong": row.both_wrong,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def _report(rows: list[Row], langs: list[str], subjects: list[str]) -> None:
    print("reach = cards on questions with an answer; wrong = regex/model/both")
    for lang in langs:
        for subject in subjects:
            picked = [row for row in rows if row.lang == lang and row.subject == subject]
            if picked:
                print(Tally(picked).line(f"{subject} {lang}"))
    reasons: dict[str, int] = {}
    for row in rows:
        if row.model is not None:
            reasons[row.model.reason] = reasons.get(row.model.reason, 0) + 1
    print("model read reasons:", json.dumps(dict(sorted(reasons.items()))))
    wrong = [row for row in rows if row.model_wrong]
    for row in wrong[:40]:
        read = row.model
        print(
            f"  model wrong {row.lang} {row.subject}:{row.entry.id} "
            f"op={read.op if read else None} card={row.model_card!r}"
        )


# --- translate ---------------------------------------------------------------------


class _Translation(BaseModel):
    text: str = Field(max_length=2000)


def _numbers(text: str) -> list[float]:
    return sorted(values_in(normalized(text)))


async def translate(per_subject: int, seed: int) -> None:
    """Write ``reader_corpus/<lang>.json``: a sample of answerable entries per subject,
    translated, kept only when every number survives."""
    from app.gateways.structured_completion import complete_structured

    settings = Settings()
    CORPUS.mkdir(exist_ok=True)
    sample = [
        (subject, entry)
        for subject in SUBJECT_NAMES
        for entry in _sample(
            [entry for entry in load(subject) if entry.expect == "answer" and not entry.history],
            per_subject,
            seed,
        )
    ]
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def one(subject: str, entry: Entry, language: str) -> dict[str, str] | None:
        async with gate:
            done = await complete_structured(
                settings=settings,
                model_alias="smart-chat",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"Translate the student's question into {language}, as a "
                            "textbook in that language would write it. Keep every number "
                            "and unit value exactly; write units the way that language's "
                            'textbooks do. Return JSON {"text": "<translation>"}.'
                        ),
                    },
                    {"role": "user", "content": entry.prompt},
                ],
                schema=_Translation,
                max_tokens=600,
                timeout_seconds=30,
            )
        if done is None or _numbers(done.text) != _numbers(entry.prompt):
            return None
        return {"subject": subject, "id": entry.id, "prompt": done.text}

    for lang, language in LANGUAGES.items():
        found = await asyncio.gather(*(one(subject, entry, language) for subject, entry in sample))
        kept = sorted(
            (item for item in found if item is not None),
            key=lambda item: (item["subject"], item["id"]),
        )
        (CORPUS / f"{lang}.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1) + "\n")
        print(
            f"{lang}: kept {len(kept)}, dropped {len(found) - len(kept)} (a number did not survive)"
        )


def rejudge(path: Path) -> None:
    """The report again from a ``--dump``, judged afresh, with no model call."""
    entries = {(subject, entry.id): entry for subject in SUBJECT_NAMES for entry in load(subject)}
    rows: list[Row] = []
    for line in path.read_text().splitlines():
        item = json.loads(line)
        entry = entries.get((item["subject"], item["id"]))
        if entry is None and item["lang"] == "book":
            answers = tuple((float(value), str(unit)) for value, unit in item.get("answers", []))
            entry = Entry(item["id"], "book", "", "answer", answers=answers)
        if entry is None:
            continue
        row = Row(item["subject"], item["lang"], entry, item["regex_card"], item["regex_wrong"])
        row.model = ModelRead(
            item["model_subject"],
            item["model_op"],
            None,
            item["reason"],
            item["ms"] or 0.0,
            item.get("input_tokens", 0),
            item.get("output_tokens", 0),
        )
        row.model_card = item["model_card"]
        _judge_row(row)
        rows.append(row)
    order = ["en", "holdout", *sorted(LANGUAGES), "book"]
    langs = [lang for lang in order if any(row.lang == lang for row in rows)]
    _report(rows, langs, list(SUBJECT_NAMES))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--langs", default="en," + ",".join(LANGUAGES))
    run_parser.add_argument("--subjects", default=",".join(SUBJECT_NAMES))
    run_parser.add_argument("--limit", type=int, help="English entries per subject (sampled)")
    run_parser.add_argument("--seed", type=int, default=7)
    # Each call's limit: production's is ``model_reader_timeout_seconds``; this measures
    # how long reads take, so it waits longer and reports p50/p95.
    run_parser.add_argument("--timeout", type=float, default=5.0)
    run_parser.add_argument("--dump", type=Path, help="write every row as a JSON line here")
    # Textbook sets ({id, subject, question, expected}): the ones whose answer is one value.
    run_parser.add_argument("--books", type=Path, help="a folder of textbook question sets")
    rejudge_parser = commands.add_parser("rejudge")
    rejudge_parser.add_argument("dump", type=Path)
    translate_parser = commands.add_parser("translate")
    translate_parser.add_argument("--per-subject", type=int, default=40)
    translate_parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if args.command == "run":
        langs, subjects = args.langs.split(","), args.subjects.split(",")
        books = (
            [
                item
                for file in sorted(args.books.glob("*.json"))
                for item in json.loads(file.read_text())
            ]
            if args.books
            else None
        )
        asyncio.run(run(langs, subjects, args.limit, args.seed, args.timeout, args.dump, books))
    elif args.command == "rejudge":
        rejudge(args.dump)
    else:
        asyncio.run(translate(args.per_subject, args.seed))


if __name__ == "__main__":
    main()
