"""Classic word problems read without a model: the same setup the translator writes.

A few textbook shapes are closed enough to read deterministically: consecutive
integers with a stated sum, two ages with a difference and a sum, tickets at two
prices, mixing two strengths to a target strength, and a stated rate scaled to
another amount ("3 cups of flour for 12 cookies; how many cups for 30?").
Each reader matches the whole message and builds the ``WordProblemSetup`` a
model would, so the problem still goes through ``grounded`` (every number is
stated), SymPy (exactly one solution in the domain) and the word-problem reply.
Anything else, or a problem whose numbers do not give a valid answer of the
asked kind (consecutive odd integers that come out even), is left to the
translator or the model.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from fractions import Fraction

from app.modules.math.schemas.word_problem import (
    WordEquation,
    WordProblemSetup,
    WordTarget,
    WordUnknown,
)
from app.services.number_text import DECIMAL

_MAX_CHARS = 400
_NUM = DECIMAL
_SMALL_COUNTS = {"two": 2, "three": 3, "four": 4, "five": 5}
_ORDINALS = ("first", "second", "third", "fourth", "fifth")
_END = r"\s*[?.!]?\s*"


def _plain(text: str) -> str:
    return " ".join(text.split())


def _source(text: str) -> str:
    return _plain(text).strip(" .,;:")[:160]


# --- consecutive integers -----------------------------------------------------

_COUNT = r"(?P<n>two|three|four|five|[2-5])"
_PARITY = r"(?P<parity>even\s+|odd\s+)?"
_INTEGERS = r"(?:integers|numbers|whole\s+numbers)"
_PICK = r"(?P<pick>smallest|largest|biggest|greatest|first|last|middle)"
_ASK = (
    r"(?:(?:find|what\s+are|list|name|give)\s+(?:them|they|the\s+(?:integers|numbers)|"
    r"all\s+of\s+them|the\s+\w+\s+(?:integers|numbers))"
    rf"|(?:what\s+(?:is|are)|find)\s+the\s+{_PICK}(?:\s+(?:one|integer|number))?)"
)
_CONSECUTIVE_FORMS = (
    # "the sum of three consecutive integers is 72. find them"
    re.compile(
        rf"(?P<clause>(?:the\s+)?sum\s+of\s+{_COUNT}\s+consecutive\s+{_PARITY}{_INTEGERS}\s+is\s+"
        rf"(?P<sum>-?\d+))\s*[.,;:]?\s*(?:{_ASK})?{_END}",
        re.IGNORECASE,
    ),
    # "three consecutive integers add up to 72. what are they"
    re.compile(
        rf"(?P<clause>{_COUNT}\s+consecutive\s+{_PARITY}{_INTEGERS}\s+(?:add\s+up\s+to|sum\s+to|"
        rf"have\s+a\s+sum\s+of)\s+(?P<sum>-?\d+))\s*[.,;:]?\s*(?:{_ASK})?{_END}",
        re.IGNORECASE,
    ),
    # "find three consecutive integers whose sum is 72"
    re.compile(
        rf"(?:find|what\s+are)\s+(?P<clause>(?:the\s+)?{_COUNT}\s+consecutive\s+{_PARITY}"
        rf"{_INTEGERS}\s+(?:whose\s+sum\s+is|with\s+a\s+sum\s+of|that\s+add\s+up\s+to|"
        rf"that\s+sum\s+to)\s+(?P<sum>-?\d+)){_END}",
        re.IGNORECASE,
    ),
)


def _consecutive(text: str) -> WordProblemSetup | None:
    match = next((m for form in _CONSECUTIVE_FORMS if (m := form.fullmatch(text))), None)
    if match is None:
        return None
    raw = match.group("n").lower()
    count = _SMALL_COUNTS.get(raw) or int(raw)
    parity = (match.group("parity") or "").strip().lower()
    step = 2 if parity else 1
    total = int(match.group("sum"))
    offsets = [index * step for index in range(count)]
    first = Fraction(total - sum(offsets), count)
    if first.denominator != 1:
        return None
    if parity and int(first) % 2 != (0 if parity == "even" else 1):
        # "three consecutive odd integers sum to 72" has no odd answer.
        return None
    kind = f"{parity} integer" if parity else "integer"
    terms = ["n", *(f"(n + {offset})" for offset in offsets[1:])]
    pick = (match.groupdict().get("pick") or "").lower()
    if pick:
        if pick == "middle":
            if count % 2 == 0:
                return None
            index = count // 2
        else:
            index = 0 if pick in {"smallest", "first"} else count - 1
        chosen = [index]
    elif count <= 3:
        chosen = list(range(count))
    else:
        return None
    return WordProblemSetup(
        found=True,
        unknowns=[WordUnknown(symbol="n", meaning=f"the first {kind}")],
        equations=[
            WordEquation(
                equation=f"{' + '.join(terms)} = {total}", source=_source(match.group("clause"))
            )
        ],
        targets=[
            WordTarget(
                expr="n" if offsets[index] == 0 else f"n + {offsets[index]}",
                meaning=f"the {_ORDINALS[index]} {kind}",
            )
            for index in chosen
        ],
        whole_numbers=True,
        positive=False,
    )


# --- two ages: a difference and a sum ----------------------------------------

_NAME = r"[A-Za-z]{2,15}"
_NOT_NAMES = frozenset(
    {"he", "she", "it", "they", "the", "his", "her", "my", "your", "our", "their", "me", "him"}
)
_AGES = re.compile(
    rf"(?P<relation>(?P<a>{_NAME})\s+is\s+(?P<d>\d{{1,3}})\s+years?\s+(?P<rel>older|younger)\s+"
    rf"than\s+(?P<b>{_NAME}))\s*[.,;]?\s*(?:and\s+)?"
    r"(?P<sum_clause>(?:the\s+sum\s+of\s+their\s+ages\s+is|their\s+ages\s+add\s+up\s+to|"
    r"their\s+ages\s+sum\s+to|together\s+they\s+are|their\s+combined\s+age\s+is|"
    r"their\s+total\s+age\s+is)\s+(?P<s>\d{1,3})(?:\s+years(?:\s+old)?)?)\s*[.,;]?\s*"
    rf"(?:how\s+old\s+is\s+(?P<q>{_NAME})|what\s+is\s+(?P<q2>{_NAME})'s\s+age|"
    rf"find\s+(?P<q3>{_NAME})'s\s+age|(?P<both>how\s+old\s+are\s+they|find\s+their\s+ages)){_END}",
    re.IGNORECASE,
)


def _symbols(names: list[str]) -> list[str]:
    letters = [name[0].lower() for name in names]
    if len(set(letters)) == len(letters) and not set(letters) & {"e", "i"}:
        return letters
    return ["x", "y"][: len(names)]


def _ages(text: str) -> WordProblemSetup | None:
    match = _AGES.fullmatch(text)
    if match is None:
        return None
    first, second = match.group("a"), match.group("b")
    if first.lower() == second.lower() or {first.lower(), second.lower()} & _NOT_NAMES:
        return None
    asked = match.group("q") or match.group("q2") or match.group("q3")
    if asked is not None and asked.lower() not in {first.lower(), second.lower()}:
        return None
    gap, total = int(match.group("d")), int(match.group("s"))
    sign = "+" if match.group("rel").lower() == "older" else "-"
    if (total + gap) % 2:
        # Half years: the problem is not the whole-year puzzle it looks like.
        return None
    a, b = _symbols([first, second])
    names = {first.lower(): (a, first), second.lower(): (b, second)}
    wanted = list(names.values()) if asked is None else [names[asked.lower()]]
    return WordProblemSetup(
        found=True,
        unknowns=[
            WordUnknown(symbol=a, meaning=f"{first}'s age", unit="years"),
            WordUnknown(symbol=b, meaning=f"{second}'s age", unit="years"),
        ],
        equations=[
            WordEquation(
                equation=f"{a} = {b} {sign} {gap}", source=_source(match.group("relation"))
            ),
            WordEquation(
                equation=f"{a} + {b} = {total}", source=_source(match.group("sum_clause"))
            ),
        ],
        targets=[
            WordTarget(expr=symbol, meaning=f"{name}'s age", unit="years")
            for symbol, name in wanted
        ],
        whole_numbers=False,
        positive=True,
    )


# --- tickets at two prices -----------------------------------------------------

_PRICE = rf"(?:\$\s*{_NUM}|{_NUM}\s*dollars)"
_GROUPS = {
    "adult": "adult",
    "adults": "adult",
    "child": "child",
    "children": "child",
    "kid": "child",
    "kids": "child",
    "student": "student",
    "students": "student",
    "senior": "senior",
    "seniors": "senior",
}
_GROUP_SYMBOLS = {"adult": "a", "child": "c", "student": "s", "senior": "r"}
_GROUP = r"(?:adults?|child(?:ren)?|kids?|students?|seniors?)"
_TICKETS = re.compile(
    r"(?:the\s+)?(?:(?:school|show|movie|concert|game|play|museum|zoo|fair)\s+)?tickets?\s+"
    r"(?:cost|costs|are|were|sell\s+for|sold\s+for)\s+"
    rf"(?P<p1>{_PRICE})\s+(?:for|per)\s+(?:an?\s+|each\s+)?(?P<g1>{_GROUP})\s+and\s+"
    rf"(?P<p2>{_PRICE})\s+(?:for|per)\s+(?:an?\s+|each\s+)?(?P<g2>{_GROUP})\s*[.,;]\s*"
    r"(?P<count_clause>(?:a\s+total\s+of\s+)?(?P<n>\d{1,5})\s+tickets\s+(?:were|was)\s+sold)\s+"
    rf"(?P<money_clause>(?:for|bringing\s+in|raising|making|earning)\s+(?:a\s+total\s+of\s+)?"
    rf"(?P<t>{_PRICE}))\s*[.,;]?\s*"
    rf"how\s+many\s+(?P<q>{_GROUP})(?:\s+tickets)?(?:\s+were\s+sold)?{_END}",
    re.IGNORECASE,
)


def _amount(price: str) -> str:
    return re.sub(r"[^\d.]", "", price)


def _tickets(text: str) -> WordProblemSetup | None:
    match = _TICKETS.fullmatch(text)
    if match is None:
        return None
    first, second = _GROUPS[match.group("g1").lower()], _GROUPS[match.group("g2").lower()]
    asked = _GROUPS[match.group("q").lower()]
    if first == second or asked not in {first, second}:
        return None
    p1, p2, paid = _amount(match.group("p1")), _amount(match.group("p2")), _amount(match.group("t"))
    count = int(match.group("n"))
    price1, price2 = Fraction(p1), Fraction(p2)
    if price1 == price2:
        return None
    first_count = (Fraction(paid) - price2 * count) / (price1 - price2)
    if first_count.denominator != 1 or not 0 <= first_count <= count:
        # No whole number of tickets fits the totals.
        return None
    x, y = _GROUP_SYMBOLS[first], _GROUP_SYMBOLS[second]
    return WordProblemSetup(
        found=True,
        unknowns=[
            WordUnknown(symbol=x, meaning=f"{first} tickets sold", unit="tickets"),
            WordUnknown(symbol=y, meaning=f"{second} tickets sold", unit="tickets"),
        ],
        equations=[
            WordEquation(
                equation=f"{x} + {y} = {count}", source=_source(match.group("count_clause"))
            ),
            WordEquation(
                equation=f"{p1}*{x} + {p2}*{y} = {paid}",
                source=_source(match.group("money_clause")),
            ),
        ],
        targets=[
            WordTarget(expr=_GROUP_SYMBOLS[asked], meaning=f"{asked} tickets sold", unit="tickets")
        ],
        whole_numbers=True,
        positive=False,
    )


# --- mixing two strengths to a target strength -----------------------------------

_VOLUME_UNITS = {
    "l": "litres",
    "liter": "litres",
    "liters": "litres",
    "litre": "litres",
    "litres": "litres",
    "ml": "millilitres",
    "milliliters": "millilitres",
    "millilitres": "millilitres",
    "gallon": "gallons",
    "gallons": "gallons",
    "kg": "kilograms",
    "kilograms": "kilograms",
    "g": "grams",
    "grams": "grams",
    "oz": "ounces",
    "ounces": "ounces",
    "cups": "cups",
}
_VOLUME = (
    r"(?:liters?|litres?|l|ml|milliliters|millilitres|gallons?|kg|kilograms|g|grams|oz|ounces|cups)"
)
_STUFF = (
    r"(?:\s+(?:acid|alcohol|salt|saline|sugar|juice|bleach|antifreeze))?\s+(?:solution|mixture)"
)
_MIXTURE = re.compile(
    rf"how\s+(?:many|much)\s+(?P<unit>{_VOLUME})\s+of\s+(?:an?\s+|the\s+)?(?P<p1>{_NUM})\s*%"
    rf"(?:{_STUFF})?\s+(?:must|should|would|do\s+you\s+need\s+to|need\s+to)\s+be\s+"
    rf"(?:mixed|added|combined)\s+(?:with|to)\s+(?P<v>{_NUM})\s*(?P<unit2>{_VOLUME})\s+of\s+"
    rf"(?:an?\s+|the\s+)?(?P<p2>{_NUM})\s*%(?:{_STUFF})?\s+to\s+(?:get|make|obtain|produce|give|"
    rf"form)\s+(?:an?\s+)?(?P<p3>{_NUM})\s*%(?:{_STUFF})?{_END}",
    re.IGNORECASE,
)


def _mixture(text: str) -> WordProblemSetup | None:
    match = _MIXTURE.fullmatch(text)
    if match is None:
        return None
    unit = _VOLUME_UNITS[match.group("unit").lower()]
    if _VOLUME_UNITS[match.group("unit2").lower()] != unit:
        return None
    p1, p2, p3 = (Fraction(match.group(name)) for name in ("p1", "p2", "p3"))
    if not min(p1, p2) < p3 < max(p1, p2):
        # The target strength has to lie between the two being mixed.
        return None
    volume = match.group("v")

    def rate(name: str) -> str:
        return str(float(Fraction(match.group(name)) / 100))

    return WordProblemSetup(
        found=True,
        unknowns=[
            WordUnknown(symbol="x", meaning=f"{unit} of the {match.group('p1')}% one", unit=unit)
        ],
        equations=[
            WordEquation(
                equation=f"{rate('p1')}*x + {rate('p2')}*{volume} = {rate('p3')}*(x + {volume})",
                source=_source(text),
            )
        ],
        targets=[
            WordTarget(expr="x", meaning=f"{unit} of the {match.group('p1')}% one", unit=unit)
        ],
        whole_numbers=False,
        positive=True,
    )


# --- a stated rate, scaled (direct proportion) ------------------------------------

# "Takes 12 days for 4 workers" scales inversely, and "2 drivers for 90
# passengers" rounds up: time and people are left to the translator.
_NOT_SCALED = frozenset(
    (
        "second seconds sec secs minute minutes min mins hour hours hr hrs day days week weeks "
        "month months year years people persons person worker workers men women staff drivers "
        "teachers painters builders machines pumps buses cars"
    ).split()
)
_SUBJECT = r"(?:(?:a|an|the|my|this|one)\s+(?:[a-z]+\s+){1,2}|it\s+)"
_AMOUNT = rf"(?P<a>{_NUM})\s+(?P<unit>[a-z]+)(?:\s+of\s+(?P<stuff>[a-z]+))?"
_MAKES = rf"(?P<b>{_NUM})\s+(?P<things>[a-z]+)"
_PROPORTION_GIVEN = (
    # "A recipe needs 3 cups of flour for 12 cookies", "it takes 2 eggs to make 8 pancakes"
    re.compile(
        rf"(?:if\s+)?{_SUBJECT}?(?:needs|uses|takes|requires|calls\s+for)\s+{_AMOUNT}\s+"
        rf"(?:for|per|to\s+(?:make|bake|cook|serve|feed))\s+{_MAKES}",
        re.IGNORECASE,
    ),
    # "3 cups of flour make 12 cookies"
    re.compile(
        rf"(?:if\s+)?{_AMOUNT}\s+(?:makes?|bakes?|serves?|feeds?|(?:is|are)\s+enough\s+for)\s+"
        rf"{_MAKES}",
        re.IGNORECASE,
    ),
)
_PROPORTION_ASK = re.compile(
    r"\s*[.,;]?\s*(?:so\s+|then\s+)?how\s+(?:many|much)\s+(?P<asked>[a-z]+)"
    r"(?:\s+of\s+(?P<asked_stuff>[a-z]+))?"
    r"(?:\s+(?:do|does|would|will)\s+(?:i|you|we|they|it|she|he)\s+need"
    r"|\s+(?:are|is)\s+needed)?"
    rf"\s+(?:for|to\s+(?:make|bake|cook|serve|feed))\s+(?P<c>{_NUM})(?:\s+(?P<things2>[a-z]+))?"
    rf"{_END}",
    re.IGNORECASE,
)


def _same_word(first: str | None, second: str | None) -> bool:
    """ "cookie" and "cookies" name the same thing."""
    if first is None or second is None:
        return False
    return first.lower().rstrip("s") == second.lower().rstrip("s")


def _proportion(text: str) -> WordProblemSetup | None:
    for given_form in _PROPORTION_GIVEN:
        given = given_form.match(text)
        if given is None:
            continue
        ask = _PROPORTION_ASK.fullmatch(text, given.end())
        if ask is None:
            continue
        unit, stuff, things = given.group("unit"), given.group("stuff"), given.group("things")
        if {unit.lower(), things.lower()} & _NOT_SCALED:
            return None
        if ask.group("things2") is not None and not _same_word(ask.group("things2"), things):
            return None
        asked, asked_stuff = ask.group("asked"), ask.group("asked_stuff")
        if asked_stuff is not None:
            ok = _same_word(asked, unit) and _same_word(asked_stuff, stuff)
        else:
            ok = _same_word(asked, unit) or _same_word(asked, stuff)
        if not ok:
            return None
        a, b, c = given.group("a"), given.group("b"), ask.group("c")
        if Fraction(b) == 0:
            return None
        meaning = f"{unit} of {stuff}" if stuff else unit
        wanted = f"{meaning} for {c} {things}"[:80]
        return WordProblemSetup(
            found=True,
            unknowns=[WordUnknown(symbol="x", meaning=wanted, unit=unit[:24])],
            equations=[WordEquation(equation=f"x/{c} = {a}/{b}", source=_source(text))],
            targets=[WordTarget(expr="x", meaning=wanted, unit=unit[:24])],
            whole_numbers=False,
            positive=True,
        )
    return None


_TEMPLATES: tuple[Callable[[str], WordProblemSetup | None], ...] = (
    _consecutive,
    _ages,
    _tickets,
    _mixture,
    _proportion,
)


def word_template_setup(text: str) -> WordProblemSetup | None:
    """The setup of a classic word problem that one closed template reads whole."""
    if not text or len(text) > _MAX_CHARS:
        return None
    from app.modules.math.tools.word_problem import grounded

    plain = _plain(text)
    for template in _TEMPLATES:
        setup = template(plain)
        if setup is not None:
            return setup.as_read_from_text() if grounded(setup, plain) else None
    return None
