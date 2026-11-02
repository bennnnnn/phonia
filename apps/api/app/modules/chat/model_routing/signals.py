"""Cheap text signals that a turn needs Auto's strong lane: no model call, linear scans.

Each signal is narrow on purpose. The strong lane costs about five times the
everyday one and 3.5x the user's daily quota, so an everyday message that only
shares a word with a hard one ("plan my week", "review my essay", "drive
carefully", "all my friends are busy") must stay on the cheap lane.
``app/tests/services/test_routing_signals.py`` holds each signal's look-alikes.
"""

from __future__ import annotations

import json
import re

# Hard triggers only: broad words like "why/explain" route too often to the
# strong model. "compare" alone is too broad (it fires on "compare these two
# files"), so comparison routing uses the explicit "X vs Y" / "versus" cues.
SMART_TRIGGERS = (
    "prove ",
    "derive ",
    "debug ",
    "algorithm",
    "complexity",
    "architecture",
    "refactor",
    "trade-off",
    "tradeoff",
    "step by step",
    "design a system",
    "design a distributed",
    "optimize this",
    "big-o",
    "time complexity",
    "space complexity",
    # "X vs Y" comparisons are genuinely hard; a weak model answered them unhelped.
    " vs ",
    " versus ",
    # Coding asks with no ``` fence ("write a function") need the strong model too.
    "write a function",
    "write a script",
    "write a program",
    "write a method",
    "write a class",
    "write a regex",
    "write a snippet",
    "implement a",
    "implement the",
    "code a",
    "leetcode",
)

# ── Careful reasoning asked for in so many words ───────────────────────────────
# A verb of reasoning, then "carefully" in the same clause: "drive carefully" and
# "listen carefully" have no reasoning verb.
_CAREFUL = re.compile(
    r"\b(?:explain|think|reason|justify|analy[sz]e)\b[^.?!\n]{0,40}?\b(?:carefully|rigorously)\b"
    r"|\b(?:carefully|rigorously)\s+(?:explain|think|reason|justify|analy[sz]e)\b",
    re.IGNORECASE,
)

# ── Logic puzzles ─────────────────────────────────────────────────────────────
_PUZZLE_TERMS = (
    "logic puzzle",
    "syllogism",
    "knights and knaves",
    "zebra puzzle",
    "einstein's riddle",
    "einstein's puzzle",
    "truth-teller",
    "truth teller",
)
# "All A are B" / "No B is C": two of these plus a question about what follows.
_QUANTIFIED = re.compile(
    r"\b(?:all|some|no|every)\s+[a-z]+(?:\s+[a-z]+)?\s+(?:are|is)\b", re.IGNORECASE
)
_DEDUCTION = re.compile(
    r"\b(?:does it follow|must be true|necessarily|logically|valid argument|is (?:this|it) valid"
    r"|can we conclude|what can (?:we|you) conclude|deduce|who is lying|which (?:one )?is lying)\b",
    re.IGNORECASE,
)

# ── Planning or designing a system ─────────────────────────────────────────────
# Only words that mean software infrastructure: "tables", "servers" and "queues"
# also mean a restaurant or a bank, so they are left out.
_SYSTEM_NOUNS = re.compile(
    r"\b(?:schemas?|databases?|postgres(?:ql)?|mysql|sql|shard(?:s|ed|ing)?|monolith(?:ic)?"
    r"|micro-?services?|clusters?|kubernetes|k8s|replicas?|replication|backend|infrastructure"
    r"|pipelines?|distributed|caching|kafka|redis|latency|throughput|concurrency|failover"
    r"|load balanc(?:er|ing)|apis?)\b",
    re.IGNORECASE,
)
# Asking for the plan, not telling of one: "we finished migrating to postgres with
# zero downtime" (a tweet to write) has no ask.
_SYSTEM_VERBS = re.compile(
    r"\b(?:plan|design|architect|migrate|shard|scale|partition|re-?platform)\b"
    r"|\bhow (?:do|would|should|can|could) (?:i|we|you)\b",
    re.IGNORECASE,
)
_DOWNTIME = re.compile(
    r"\b(?:zero[- ]downtime|no downtime|without (?:any )?downtime|high[- ]availability)\b",
    re.IGNORECASE,
)

# ── Several constraints at once ────────────────────────────────────────────────
_CONSTRAINTS = (
    " must ",
    " must not ",
    " cannot ",
    " can't ",
    " at most ",
    " at least ",
    " no more than ",
    " exactly ",
    " only if ",
    " unless ",
    " without ",
    " such that ",
    " subject to ",
    " no two ",
    " each ",
    " every ",
    " constraint",
)
# One of these marks a puzzle or an optimisation, not a to-do list with a "must".
_FORMAL_CONSTRAINTS = (
    " no two ",
    " such that ",
    " subject to ",
    " constraint",
    " exactly one ",
    " exactly two ",
    " exactly three ",
    " at most one ",
    " at least one of ",
)
_MIN_CONSTRAINTS = 3

# ── Reviewing or debugging code with no fence ──────────────────────────────────
# Terms that only mean code. Bare "code" (a promo or zip code), "script" (a film),
# "program" (a TV show) and "class" (a lesson) count only beside a code-only symptom.
_CODE_TERMS = re.compile(
    r"\b(?:codebase|source code|regex|pull request|linked list|binary tree|recursion|recursive"
    r"|segfault|null pointer|stack trace|traceback|compiler|syntax error|runtime error"
    r"|infinite loop|off-by-one|race condition|deadlock|unit tests?|python|javascript"
    r"|typescript|golang|kotlin|sql|html|css|bash script|shell script)\b|c\+\+",
    re.IGNORECASE,
)
_MY_CODE = re.compile(
    r"\b(?:my|this|the|our)\s+(?:[a-z+#]+\s+)?(?:code|function|loop|script|program|query"
    r"|recursion|method)\b",
    re.IGNORECASE,
)
# "review my code", "code review", "look over this function". Not "query"
# (a query letter) or "class" (class notes).
_REVIEW = re.compile(
    r"\b(?:review|critique|audit|look over|go over)\s+(?:my|this|the|our)\s+"
    r"(?:[a-z+#]+\s+)?(?:code|function|implementation|pull request|regex|loop)\b"
    r"|\bcode review\b",
    re.IGNORECASE,
)
# Symptoms only code has.
_CODE_BUG = re.compile(
    r"\b(?:keeps? looping|loops? forever|never (?:ends?|stops?|returns?|terminates?|finishes)"
    r"|infinite|throws?|exception|return(?:s|ing)? (?:none|null|undefined|nan|the wrong|wrong)"
    r"|(?:won't|doesn't|does not|can't) compile|stack overflow|segfault|out of range"
    r"|off by one|typeerror|valueerror|keyerror|indexerror)\b",
    re.IGNORECASE,
)
# Symptoms anything can have: they count only with a code-only term.
_ANY_BUG = re.compile(
    r"\b(?:crash(?:es|ing)?|(?:doesn't|does not|won't) work|not working|stuck|hangs?|bugs?"
    r"|buggy|wrong (?:output|result|answer)|errors?|fails?|failing)\b",
    re.IGNORECASE,
)
# "write a python function", "implement a recursive function", "write me a bash
# script". A bare script, program or class only counts with a language before it:
# "write a script for my video" and "create a class schedule" are not code.
_LANGUAGE = (
    r"(?:python|javascript|js|typescript|ts|java|kotlin|swift|golang|rust|ruby|php|c\+\+|c#"
    r"|bash|shell|sql|powershell)"
)
_WRITE_CODE = re.compile(
    rf"\b(?:write|implement|code|create|build)\s+(?:me\s+)?(?:a|an|the)\s+"
    rf"(?:(?:[a-z]+\s+){{0,2}}?(?:function|method|regex|snippet)\b"
    rf"|(?:[a-z]+\s+)?{_LANGUAGE}\s+(?:script|program|class)\b)",
    re.IGNORECASE,
)

# ── Pasted structured data ─────────────────────────────────────────────────────
_MIN_RECORDS = 3  # rows of a CSV, records of a JSON array or keys of an object


def is_hard_reasoning(content: str) -> bool:
    """A careful-reasoning ask, a logic puzzle, a system design or a constraint problem."""
    if _CAREFUL.search(content):
        return True
    lower = content.lower()
    if any(term in lower for term in _PUZZLE_TERMS):
        return True
    if len(_QUANTIFIED.findall(content)) >= 2 and _DEDUCTION.search(content):
        return True
    return _plans_a_system(content) or _several_constraints(lower)


def _plans_a_system(content: str) -> bool:
    nouns = {match.lower() for match in _SYSTEM_NOUNS.findall(content)}
    if not nouns or _SYSTEM_VERBS.search(content) is None:
        return False
    return len(nouns) >= 2 or _DOWNTIME.search(content) is not None


def _several_constraints(lower: str) -> bool:
    padded = f" {' '.join(lower.split())} "
    found = sum(1 for marker in _CONSTRAINTS if marker in padded)
    return found >= _MIN_CONSTRAINTS and any(marker in padded for marker in _FORMAL_CONSTRAINTS)


def is_code_review(content: str) -> bool:
    """Writing, reviewing or debugging code the user describes without a fence."""
    if _REVIEW.search(content) or _WRITE_CODE.search(content):
        return True
    code_bug = _CODE_BUG.search(content) is not None
    if _CODE_TERMS.search(content):
        return code_bug or _ANY_BUG.search(content) is not None
    return code_bug and _MY_CODE.search(content) is not None


def has_structured_data(content: str) -> bool:
    """Pasted JSON or CSV with a few records: a data task, whatever its length."""
    return _has_json_records(content) or _has_csv_rows(content)


def _has_json_records(content: str) -> bool:
    """A JSON array of three or more objects, or an object with three or more keys.

    "My scores were [90, 85, 77]" is a sentence with a list in it, and
    "[[1,2],[3,4]]" is a matrix for the maths lane, not records.
    """
    starts = [index for index in (content.find("["), content.find("{")) if index >= 0]
    end = max(content.rfind("]"), content.rfind("}"))
    if not starts or end <= min(starts):
        return False
    try:
        data = json.loads(content[min(starts) : end + 1])
    except ValueError:
        return False
    if isinstance(data, dict):
        return len(data) >= _MIN_RECORDS
    if not isinstance(data, list):
        return False
    return sum(1 for item in data if isinstance(item, dict)) >= _MIN_RECORDS


def _has_csv_rows(content: str) -> bool:
    """Three or more consecutive lines with the same number of separators, like a table.

    A verse ending its lines in commas and a short list of pairs with no figure
    in it ("eggs, milk") are not data.
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for separator in (",", "\t", ";"):
        run: list[str] = []
        for line in [*lines, ""]:
            count = line.count(separator)
            if run and count == run[0].count(separator) and count > 0:
                run.append(line)
                continue
            if _is_table(run, separator):
                return True
            run = [line] if count > 0 else []
    return False


def _is_table(rows: list[str], separator: str) -> bool:
    if len(rows) < _MIN_RECORDS or any(row.endswith(separator) for row in rows):
        return False
    columns = rows[0].count(separator) + 1
    return columns >= 3 or any(ch.isdigit() for row in rows for ch in row)


def needs_strong_model(content: str) -> bool:
    """Any signal that the strong lane should answer this message."""
    return is_hard_reasoning(content) or is_code_review(content) or has_structured_data(content)
