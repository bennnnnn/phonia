"""The parts of a short subject follow-up that do not depend on the subject.

Physics and chemistry each replay their previous problem when a line only
continues it: explain the result, ask for another quantity of the same setup,
give the result in another unit, or replace or scale one given. Each subject
keeps its own asks, units and check that the rewrite verifies; the message
reading, the adjacent exchange, the follow-up phrases and the text rewrites
are the same for both and live here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.law_binding.fit import read_givens
from app.services.law_binding.givens import Given
from app.services.law_binding.units import UnitTable

# A line that asks only to have the previous result explained, read lowercase.
EXPLAIN_RE = re.compile(
    r"^(?:"
    r"why(?: is (?:it|that)(?: [-+]?\d+(?:\.\d+)?(?: [a-zμµ°/^0-9.]+)?)?)?"
    r"|how(?: come| did you get (?:that|it)| does that work)?"
    r"|i (?:didn't|did not|don't|do not) (?:get|understand)(?: it)?"
    r"|help me understand(?: it)?"
    r"|(?:that(?:'s| is)|this is|i(?:'m| am)) confus(?:ed|ing)"
    r"|(?:(?:can|could) you )?(?:show|give) (?:me )?(?:the )?(?:steps|working|work|solution)"
    r"(?: please)?"
    r"|explain(?: (?:it|that|this|the answer))?(?: please)?"
    r"|(?:walk me through|break down) (?:it|that|this)(?: please)?"
    r"|step by step(?: please)?"
    r")$"
)

_LEAD = r"(?:(?:and|but|so|ok(?:ay)?|now|then|please|can you|could you)[ ,]+)*"

# "in km/h", "what is that in mph", "convert it to feet please".
_IN_UNIT = re.compile(
    _LEAD + r"(?:(?:what(?:'s| is) (?:that|it|this|the answer)|convert (?:that|it|this|the answer)"
    r"|give (?:it|that|me (?:that|it)|the answer)|(?:put|write|show) (?:it|that|the answer))[ ]+)?"
    r"(?:in|into|to)[ ]+(?P<unit>[a-zμµ°/][a-zμµ°/^0-9.]{0,11})"
    r"(?:[ ,]+(?:please|pls|instead|too))*",
    re.IGNORECASE,
)

# "what if the mass doubles", "what if the height is halved".
_SCALED = re.compile(
    _LEAD + r"(?:what )?if (?:the |its |her |his |their )?(?P<name>[a-z][a-z ]{0,30}?) "
    r"(?:(?:is|was|were|gets|got) )?"
    r"(?P<how>doubled|doubles|double|halved|halves|tripled|triples|quadrupled|quadruples)"
    r"(?: instead)?",
    re.IGNORECASE,
)
_FACTORS = {
    "double": 2.0,
    "doubles": 2.0,
    "doubled": 2.0,
    "halves": 0.5,
    "halved": 0.5,
    "triples": 3.0,
    "tripled": 3.0,
    "quadruples": 4.0,
    "quadrupled": 4.0,
}

# "and after 10 s", "what if it's dropped from 80 m", "and 0.001 M": one new value.
_NEW_VALUE = re.compile(
    _LEAD + r"(?:(?:what about|how about|what if|try|with|instead)[ ,]+)?"
    r"(?:(?:it|she|he|they)(?:'s|'re| is| was| were| are)? )?"
    r"(?:[a-z]+ )?"
    r"(?:(?:after|for|from|at|with|over|of|to|in) )?"
    r"(?P<value>[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?) ?"
    r"(?P<unit>[a-zμµ°/][a-zμµ°/^0-9.]{0,11})"
    r"(?: instead)?",
    re.IGNORECASE,
)

_ASK_SENTENCE = re.compile(r"\b(?:find|what|calculate|determine|how)\b", re.IGNORECASE)
_NAME_FILLER = re.compile(r"\b(?:final|initial|the|its|a|an)\b")


def message_role_content(message: Any) -> tuple[str | None, str | None]:
    """(role, content) of a chat message: a pair, a mapping, or a row with attributes."""
    if isinstance(message, tuple) and len(message) == 2:
        role, content = message
        if isinstance(role, str) and isinstance(content, str):
            return role, content
        return None, None
    if isinstance(message, Mapping):
        role = message.get("role")
        content = message.get("content")
    else:
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
    if not isinstance(role, str) or not isinstance(content, str):
        return None, None
    return role, content


def adjacent_problem(recent: Sequence[Any], is_subject: Callable[[str], bool]) -> str | None:
    """The user's problem in the last exchange, when it was answered and is this subject's."""
    if len(recent) < 2:
        return None
    role, prior = message_role_content(recent[-2])
    answer_role, answer = message_role_content(recent[-1])
    if role != "user" or answer_role != "assistant":
        return None
    if not prior or not prior.strip() or not answer or not answer.strip():
        return None
    if not is_subject(prior):
        return None
    return prior


def asked_unit(line: str) -> str | None:
    """The unit a line asks the previous result in: ``in km/h please`` → ``km/h``."""
    match = _IN_UNIT.fullmatch(line)
    return None if match is None else match.group("unit")


def scaled_given(line: str) -> tuple[str, float] | None:
    """``what if the mass doubles`` → ``("mass", 2.0)``."""
    match = _SCALED.fullmatch(line)
    if match is None:
        return None
    return match.group("name"), _FACTORS[match.group("how").lower()]


# A clock time is not a quantity: "and at 5 pm?" is never 5 picometres.
_CLOCK_UNITS = frozenset({"am", "pm", "a.m", "p.m", "a.m.", "p.m.", "oclock", "o'clock"})


def new_value(line: str) -> tuple[str, str] | None:
    """``and after 10 s`` → ``("10", "s")``: one value with its unit, nothing else."""
    match = _NEW_VALUE.fullmatch(line)
    if match is None or match.group("unit").lower() in _CLOCK_UNITS:
        return None
    return match.group("value"), match.group("unit")


def scaled_value(value: float, factor: float) -> str:
    """The scaled number as a student would write it: 2 kg doubled is ``4``, not ``4.0``."""
    return f"{value * factor:.6g}"


def in_unit(prior: str, unit: str) -> str:
    """The prior problem asking for its answer in ``unit``."""
    return prior.rstrip() + f" Give the answer in {unit}."


def followup_line(query: str | None) -> str | None:
    """The line with its quotes, outer punctuation and repeated spaces taken off."""
    if not query or not query.strip():
        return None
    text = " ".join(query.replace("\u2019", "'").split()).strip(" \"'`")
    text = text.strip(".,!?:;")
    return text or None


def ask_replaced(prior: str, phrase: str) -> str:
    """The prior problem asking "Find the <phrase>." in place of its own ask sentence."""
    parts = re.split(r"(?<=[.?!])\s+", prior.strip())
    replacement = f"Find the {phrase}."
    if parts and _ASK_SENTENCE.search(parts[-1]):
        parts[-1] = replacement
        return " ".join(parts)
    return prior.rstrip(".?! ") + ". " + replacement


def given_name(name: str) -> str:
    """The quantity a changed given names, without "the", "its", "final" and the like."""
    return " ".join(_NAME_FILLER.sub(" ", name).split())


def replace_given(text: str, given: Given, value: str, unit: str) -> str:
    """The text with one given, and the unit written after it, replaced."""
    end = given.end
    tail = text[end:]
    old_unit = re.match(r"[ \t]*" + re.escape(given.unit), tail, re.IGNORECASE)
    if old_unit is not None:
        end += old_unit.end()
    return text[: given.start] + f"{value} {unit}" + text[end:]


@dataclass(frozen=True)
class GivenRewriter:
    """One subject's way to replace or scale one given of its previous problem.

    The subject brings its unit table, how it reads a unit's and a quantity name's
    dimension, and the check that a rewritten problem still verifies. A rewrite
    needs exactly one given of the asked kind, changes the text, and verifies.
    """

    units: UnitTable
    unit_dimension: Callable[[str], str | None]
    phrase_dimension: Callable[[str], str | None]
    verifies: Callable[[str], bool]

    def changed(self, prior: str, name: str | None, value: str, unit: str | None) -> str | None:
        """``and after 10 s``, ``what if the mass was 4 kg``: that given replaced."""
        if not unit or not unit.strip():
            return None
        written_unit = " ".join(unit.split())
        new_dim = self.unit_dimension(written_unit)
        if new_dim is None:
            return None
        if name:
            named_dim = self.phrase_dimension(given_name(name))
            if named_dim is None or named_dim != new_dim:
                return None
        matches = self._of_dimension(prior, new_dim)
        if len(matches) != 1:
            return None
        rewritten = replace_given(prior, matches[0], value, written_unit)
        if rewritten == prior:
            return None
        return rewritten if self.verifies(rewritten) else None

    def scaled(self, prior: str, name: str, factor: float) -> str | None:
        """``what if the mass doubles``: the one given of that kind, times the factor."""
        named_dim = self.phrase_dimension(given_name(name))
        if named_dim is None:
            return None
        matches = self._of_dimension(prior, named_dim)
        if len(matches) != 1:
            return None
        given = matches[0]
        rewritten = replace_given(prior, given, scaled_value(given.value, factor), given.unit)
        return rewritten if rewritten != prior and self.verifies(rewritten) else None

    def _of_dimension(self, prior: str, dimension: str) -> list[Given]:
        return [given for given in read_givens(prior, self.units) if given.dimension == dimension]
