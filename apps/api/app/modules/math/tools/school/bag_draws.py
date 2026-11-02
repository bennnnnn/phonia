"""Several draws from a bag of colours, all of one colour, with or without replacement.

"a bag has 3 red and 5 blue marbles, pick 2 without replacement, probability both
red" is (3/8)(2/7) = 3/28. The whole message has to be the bag, the draw, how it
is drawn and the one event; anything else ("the first is red and the second blue",
"at least one", "one of each") stays with the model. Whether the marbles go back
is never assumed: a draw with neither "with" nor "without replacement" (or "at the
same time") is declined.
"""

from __future__ import annotations

import re
from dataclasses import replace
from fractions import Fraction

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import count_value
from app.modules.math.tools.school.single_draw import fraction_tex
from app.services.number_text import count_word_pattern
from app.services.workout import Workout, math_line, render_workout

_COUNT = r"(?:\d{1,3}|" + count_word_pattern() + ")"
_COLOUR = r"(?:red|blue|green|yellow|white|black|orange|purple|pink|brown|gr[ae]y)"
_ITEM = (
    r"(?:marbles?|balls?|counters?|beads?|sweets?|candies|candy|socks?|chips?|cubes?|"
    r"tokens?|discs?|disks?|tiles?)"
)
_HOLDER = r"(?:bag|box|jar|urn|bowl|drawer|basket|tin|hat|pot|container)"
_GROUP = rf"{_COUNT}\s+{_COLOUR}(?:\s+{_ITEM})?"
_GROUP_PARTS = re.compile(rf"({_COUNT})\s+({_COLOUR})", re.IGNORECASE)
_CONTENTS = rf"{_GROUP}(?:\s*,\s*{_GROUP})*\s*,?\s+and\s+{_GROUP}"
_MANNER = (
    r"(?P<manner>without\s+replacement|with\s+replacement|without\s+replacing(?:\s+(?:it|them))?"
    r"|at\s+the\s+same\s+time|at\s+once|simultaneously|together)"
)
_DRAW_VERB = (
    r"(?:pick(?:s|ed)?|draw(?:s|n)?|take(?:s|n)?|choose(?:s)?|chosen|select(?:s|ed)?"
    r"|remove(?:s|d)?|pull(?:s|ed)?(?:\s+out)?)"
)
_QUESTION = (
    r"(?:what\s+is\s+|what's\s+|whats\s+|find\s+|calculate\s+|work\s+out\s+)?"
    r"(?:the\s+)?(?:probability|chance)\s+(?:that\s+|of\s+)?"
)
_EVENT = (
    rf"(?:(?:they|the\s+{_ITEM}|both\s+of\s+them|all\s+of\s+them)\s+(?:are|is)\s+)?"
    r"(?:getting\s+|drawing\s+|picking\s+|choosing\s+|selecting\s+)?"
    rf"(?:(?P<both>both)|all(?:\s+(?P<all_count>{_COUNT}))?|(?P<event_count>{_COUNT}))?"
    rf"\s*(?:are\s+|is\s+|being\s+|of\s+them\s+(?:are\s+)?)?"
    rf"(?P<colour>{_COLOUR})s?(?:\s+{_ITEM}|\s+ones?)?"
)
_END = r"\s*[?.!]?\s*"
# "a bag has 3 red and 5 blue marbles. pick 2 without replacement. probability both red"
_BAG_FIRST = re.compile(
    rf"(?:an?|one|the)\s+{_HOLDER}\s+(?:has|contains|holds|with|containing|that\s+has)\s+"
    rf"(?P<contents>{_CONTENTS})\s*[.,;]?\s*"
    rf"(?:(?:(?:if\s+)?(?:you|i|we|someone|a\s+student|he|she)\s+)?(?:randomly\s+)?{_DRAW_VERB}\s+"
    rf"(?P<draws>{_COUNT})(?:\s+{_ITEM})?"
    rf"|(?:if\s+)?(?P<draws_passive>{_COUNT})\s+(?:{_ITEM}|of\s+them)\s+(?:are|is)\s+{_DRAW_VERB})"
    rf"(?:\s+(?:at\s+random|randomly))?\s*,?\s*"
    rf"{_MANNER}\s*[.,;]?\s*{_QUESTION}{_EVENT}{_END}",
    re.IGNORECASE,
)
# "2 marbles are drawn without replacement from a bag of 3 red and 5 blue. probability ..."
_DRAW_FIRST = re.compile(
    rf"(?:if\s+)?(?P<draws>{_COUNT})\s+{_ITEM}\s+(?:are|is)\s+{_DRAW_VERB}"
    rf"(?:\s+(?:at\s+random|randomly))?\s*,?\s*(?:{_MANNER}\s+)?"
    rf"(?:from|out\s+of)\s+(?:an?|the)\s+{_HOLDER}\s+"
    rf"(?:of|with|containing|that\s+(?:has|contains)|holding)\s+"
    rf"(?P<contents>{_CONTENTS})\s*,?\s*(?:(?P<manner_after>without\s+replacement"
    rf"|with\s+replacement)\s*)?[.,;]?\s*{_QUESTION}{_EVENT}{_END}",
    re.IGNORECASE,
)
_MAX_DRAWS = 6
_MAX_ITEMS = 200


def _contents(text: str) -> dict[str, int] | None:
    bag: dict[str, int] = {}
    for count, colour in _GROUP_PARTS.findall(text):
        name = colour.lower().replace("grey", "gray")
        if name in bag:
            return None
        bag[name] = count_value(count)
    return bag if len(bag) >= 2 else None


def extract_bag_draws_intent(cleaned: str) -> MathIntent | None:
    if len(cleaned) > 400:
        return None
    text = " ".join(cleaned.split())
    match = _BAG_FIRST.fullmatch(text) or _DRAW_FIRST.fullmatch(text)
    if match is None:
        return None
    groups = match.groupdict()
    manner = (groups.get("manner") or groups.get("manner_after") or "").lower()
    if not manner or (groups.get("manner") and groups.get("manner_after")):
        return None
    replaced = manner == "with replacement"
    bag = _contents(match.group("contents"))
    draws = count_value(groups.get("draws") or groups["draws_passive"])
    if bag is None or not 2 <= draws <= _MAX_DRAWS:
        return None
    colour = match.group("colour").lower().replace("grey", "gray")
    if colour not in bag:
        return None
    if groups.get("both") and draws != 2:
        return None
    for named in (groups.get("all_count"), groups.get("event_count")):
        if named is not None and count_value(named) != draws:
            return None
    total = sum(bag.values())
    if not 0 < total <= _MAX_ITEMS or (not replaced and draws > total):
        return None
    return MathIntent(
        kind="probability",
        school_op="bag_draws_with_replacement" if replaced else "bag_draws",
        # vec_a: how many of the colour, how many in the bag, how many drawn.
        vec_a=[float(bag[colour]), float(total), float(draws)],
        trial_outcome=colour,
        operation="solve",
    )


def bag_draw_factors(
    favourable: int, total: int, draws: int, *, replaced: bool
) -> list[tuple[int, int]]:
    """Each draw's chance as (colour left, bag left): c/N, then (c-1)/(N-1) without replacement."""
    factors: list[tuple[int, int]] = []
    for index in range(draws):
        taken = 0 if replaced else index
        factors.append((max(favourable - taken, 0), total - taken))
    return factors


def bag_draws_probability(favourable: int, total: int, draws: int, *, replaced: bool) -> Fraction:
    """Every draw the colour: (c/N)^k with replacement, c/N · (c-1)/(N-1) · … without."""
    probability = Fraction(1)
    for top, bottom in bag_draw_factors(favourable, total, draws, replaced=replaced):
        probability *= Fraction(top, bottom)
    return probability


def bag_draws_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math.tools.school.single_draw import probability_answer

    if not intent.vec_a or len(intent.vec_a) != 3 or not intent.trial_outcome:
        return None
    favourable, total, draws = (int(value) for value in intent.vec_a)
    replaced = intent.school_op == "bag_draws_with_replacement"
    probability = bag_draws_probability(favourable, total, draws, replaced=replaced)
    colour = intent.trial_outcome
    factors = bag_draw_factors(favourable, total, draws, replaced=replaced)
    unreduced_top = 1
    unreduced_bottom = 1
    for top, bottom in factors:
        unreduced_top *= top
        unreduced_bottom *= bottom
    working = r" \times ".join(rf"\frac{{{top}}}{{{bottom}}}" for top, bottom in factors)
    unreduced = rf"\frac{{{unreduced_top}}}{{{unreduced_bottom}}}"
    exact = fraction_tex(probability)
    chain = working if unreduced == working else rf"{working} = {unreduced}"
    if exact != unreduced:
        chain = rf"{chain} = {exact}"
    answer = probability_answer(probability)
    how = "with replacement" if replaced else "without replacement"
    lines.append(
        f"P(all {draws} {colour}) = {probability} drawing {draws} of {total} "
        f"({favourable} {colour}) {how}"
    )
    rule = (
        "the bag is the same for every draw"
        if replaced
        else "one fewer of the colour and of the bag after each draw"
    )
    worked = render_workout(
        Workout(
            given=(
                math_line(f"{favourable}", f"{colour} in the bag"),
                math_line(f"{total}", "in the bag altogether"),
                math_line(f"{draws}", f"drawn {how}"),
            ),
            find=(math_line(rf"P(\text{{all {draws} {colour}}})"),),
            formula=(math_line(r"P = P(1\text{st}) \times P(2\text{nd}) \times \cdots", rule),),
            substitution=(math_line(rf"P = {chain}"),),
        ),
        answer,
    )
    return replace(finish_with_answer(lines, answer), worked_reply=worked)
