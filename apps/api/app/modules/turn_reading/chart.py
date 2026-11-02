"""Whether a message asks for a chart, and the data a chart follow-up holds."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Protocol

from app.modules.turn_reading.routing import is_short_confirmation
from app.services.diagram_kinds import names_diagram_kind, names_idea_curve
from app.services.prompt_safety import text_before_attachment_markers

_CHART_KINDS = ("bar", "line", "pie", "area", "scatter", "donut", "dot", "box")


_CHART_TURN = re.compile(
    r"(?:"
    r"\b(?:bar|line|pie|area|scatter|donut)\s+charts?\s+(?:of|for|with|from|using)\b|"
    r"\bcharts?\s+(?:of|for|my)\b|"
    r"\bhistograms?\b|"
    r"\bvega(?:-lite)?\b|"
    r"```(?:chart|vega|vega-lite|plot)\b|"
    r"\b(?:make|draw|show|create|render|plot)\s+a\s+"
    r"(?:bar\s+|line\s+|pie\s+|area\s+)?charts?\b"
    r")",
    re.IGNORECASE,
)


# A plot of data named by its kind ("scatter plot", "bar graph", "box-and-whisker plot"),
# asked for: "make a bar graph", "a scatterplot of …". Not "my bar graph homework", and
# not "a box of plots" or "plot the boxes".
_PLOT_KIND = (
    r"(?:(?:scatter|dot|bar|pie|donut|line|area)\s*(?:plots?|graphs?)"
    r"|box(?:[\s-]+and[\s-]+whiskers?)?[\s-]*(?:plots?|charts?|graphs?))\b"
)


_PLOT_REQUEST = re.compile(
    r"\b(?:make|draw|create|plot|show|give|build|render|generate)\b[^.?!\n]{0,40}?\b"
    + _PLOT_KIND
    + r"|\b"
    + _PLOT_KIND
    + r"\s+(?:of|for|with|from|showing)\b",
    re.IGNORECASE,
)


# The verb that asks for a drawing; what follows it may name a curve of an idea.
_DRAW_VERB = re.compile(
    r"\b(?:make|draw|create|plot|show|give|build|render|generate|sketch)\b(?:\s+(?:me|us)\b)?",
    re.IGNORECASE,
)


# "a line graph of my sales" is a chart; "the line graph of y = 2x + 1" is a curve.
_LINE_PLOT = re.compile(r"\b(?:line|area)\s*(?:graphs?|plots?)\b", re.IGNORECASE)


_CURVE = re.compile(r"\bf\s*\(\s*x\s*\)|\by\s*=\s*[^,;\n]*?x", re.IGNORECASE)


_DEFINITION = re.compile(
    r"\bwhat(?:\s+is|'s|\s+are)\s+(?:a\s+|an\s+)?"
    rf"(?:(?:{'|'.join(_CHART_KINDS)})\s*)?(?:charts?|plots?|graphs?)\b",
    re.IGNORECASE,
)


# A picture of data asked for in other words (2026-10-24: 15 of 30 live chart requests
# matched none of the above, and "Show me the income in graph month by month", "plot my
# test scores 72, 85, 90" and "graph it" after a list of marks went to maths, which asked
# for a function, or got a chart in a made-up format).
_KIND = r"(?:bar|line|pie|area|scatter|donut|column|stacked|grouped)"


_VISUAL = r"(?:graphs?|charts?|plots?|visuali[sz]ations?)"


_POLITE = (
    r"(?:(?:can|could|would|will)\s+you\s+|please\s+|pls\s+|now\s+|ok(?:ay)?,?\s+"
    r"|and\s+|also\s+|just\s+)*"
)


# "Show this in a graph", "put that in a chart", "compare … prices in a chart", "show that
# as a bar chart". The verb asks for one: "the highest value in the chart" asks about one.
_IN_A_VISUAL = re.compile(
    r"\b(?:show|put|display|turn|make|draw|present|give|convert|compare|plot|graph|"
    r"visuali[sz]e|want|need)\b[^.?!\n]{0,80}?\b(?:in|as|into|on|onto)\s+"
    rf"(?:a\s+|an\s+|the\s+|one\s+)?(?:{_KIND}\s+)?{_VISUAL}\b",
    re.IGNORECASE,
)


# "Graph it", "visualize this", "plot my test scores", "chart the top 5 languages": the
# message opens with the verb. "Plot of the movie", "graph theory" are nouns.
# The chart word naming something else: "a plot twist", "a graph problem", "a chart-topper".
_VISUAL_AS_MODIFIER = (
    r"(?![\s-]+(?:twist|summary|line|holes?|armou?r|theory|paper|database|neural|"
    r"topp(?:ing|ers?)|positions?|tops|points?|problems?|traversals?|questions?|algorithms?|"
    r"puzzles?)\b)"
)


_OPENS_WITH_VERB = re.compile(
    rf"^{_POLITE}(?:graph|chart|plot|visuali[sz]e)\b(?![\s-]+of\b){_VISUAL_AS_MODIFIER}",
    re.IGNORECASE,
)


# "Make a graph of the exchange rate", "show me a graph of how compound interest grows".
_MAKE_A_VISUAL = re.compile(
    r"\b(?:make|draw|create|show|give|build|render|generate|sketch|display|add)\b"
    rf"(?:\s+(?:me|us))?\s+(?:a\s+|an\s+|the\s+|some\s+)?(?:{_KIND}\s+)?{_VISUAL}\b"
    + _VISUAL_AS_MODIFIER,
    re.IGNORECASE,
)


# "bar graph: apples 30".
_KIND_OPENS = re.compile(rf"^{_POLITE}{_KIND}\s*{_VISUAL}\b", re.IGNORECASE)


# The chat's numbers recast: "make that a bar chart", "make these numbers a pie chart"
# (2026-10-24: read as no chart, so the model got no format and wrote YAML the phone could
# not draw). "Make it a plot twist", "make it a graph problem" and "make it a chart-topper"
# name something else.
_MAKE_IT_A_VISUAL = re.compile(
    r"\b(?:make|remake|redo)\s+(?:it|this|that|these|those|them)(?:\s+(?!an?\b)\w+){0,2}"
    rf"\s+an?\s+(?:{_KIND}\s+){{0,2}}{_VISUAL}\b{_VISUAL_AS_MODIFIER}",
    re.IGNORECASE,
)


# Another kind for the same numbers: "what about a pie chart?", "same but as a line graph".
# "In a pie chart, what does each slice mean?" asks about one.
_ANOTHER_KIND = re.compile(
    rf"^{_POLITE}(?:(?:what|how)\s+about\s+(?:(?:as|in)\s+)?|(?:the\s+)?same(?:\s+thing)?"
    r"\s+(?:but\s+)?(?:as|in)\s+|but\s+(?:as|in)\s+|as\s+)an?\s+"
    rf"{_KIND}\s+{_VISUAL}(?:\s+(?:instead|please|pls|too|then|now))*\W*$",
    re.IGNORECASE,
)


# "Help me visualize my spending: rent 1200, food 300": with the numbers to draw.
# "How do I visualize my goals?" is no chart.
_VISUALIZE = re.compile(r"\bvisuali[sz]e\b", re.IGNORECASE)


_TWO_NUMBERS = re.compile(r"\d[^\d]+\d")


# A formula is maths' curve, not data: "graph y = 2x + 3", "plot sin(x)", "graph x^2".
_FORMULA = re.compile(
    r"\bf\s*\(\s*x\s*\)|\by\s*=|=\s*[-+]?(?:\d+(?:\.\d+)?\s*)?x\b|"
    r"\b(?:sin|cos|tan|log|ln|sqrt|exp)\s*\(|\bx\s*(?:\^|\*\*|\u00b2|\u00b3)|"
    r"\b\d+(?:\.\d+)?\s*x\b(?!\s*\d)",
    re.IGNORECASE,
)


# A curve or shape named in words is maths' too: "graph the parabola", "graph a circle of
# radius 5", "a graph of the sine function", "graph the inequality x > 3".
_CURVE_WORDS = re.compile(
    r"\b(?:parabolas?|hyperbolas?|ellipses?|circles?|sine|cosine|tangent|quadratics?|cubics?|"
    r"polynomials?|absolute\s+value|exponential|logarithm(?:ic)?|inequalit(?:y|ies)|slopes?|"
    r"intercepts?|asymptotes?|functions?|equations?|line\s+through)\b",
    re.IGNORECASE,
)


# "Plot the points (1, 2), (3, 4)" is a coordinate plane, maths' to draw.
_COORDINATE_PAIR = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)")


# Code that draws a chart is a code answer: "plot this in matplotlib", "a chart in React",
# "write python code to plot my sales". A language as the chart's subject is not ("a bar
# chart of Python vs JavaScript popularity", "my excel expenses: rent 1200").
_CODE_ASK = re.compile(
    r"\b(?:matplotlib|seaborn|plotly|pandas|d3\.js|chart\.js|chartjs|recharts|ggplot2?)\b"
    r"|\b(?:in|with|using|via)\s+(?:python|r|javascript|typescript|react|swift|kotlin|java|"
    r"excel|google\s+sheets|d3)\b"
    r"|\b(?:write|give\s+me|show\s+me|need)\b[^.?!\n]{0,40}?\b(?:code|script|program|snippet)\b",
    re.IGNORECASE,
)


# A story's plot or a graph in computing: "the plot of Inception", "a graph database".
_NOT_DATA = re.compile(
    r"\bplots?\b[^.?!\n]{0,40}\b(?:movie|film|book|story|novel|episode|season|series|anime|"
    r"manga|game|play|musical|sitcom)s?\b|\b(?:knowledge|social|dependency|call|scene|"
    r"directed|undirected|weighted|bipartite|acyclic|computational)\s+graphs?\b",
    re.IGNORECASE,
)


def _asks_for_a_visual_in_other_words(cleaned: str) -> bool:
    """The phrasings beyond ``_CHART_TURN``: a picture of data, not of a formula."""
    if _FORMULA.search(cleaned) or _CURVE_WORDS.search(cleaned) or _NOT_DATA.search(cleaned):
        return False
    asked = (
        _IN_A_VISUAL.search(cleaned)
        or _OPENS_WITH_VERB.search(cleaned)
        or _MAKE_A_VISUAL.search(cleaned)
        or _MAKE_IT_A_VISUAL.search(cleaned)
        or _ANOTHER_KIND.search(cleaned)
        or _KIND_OPENS.search(cleaned)
        or (_VISUALIZE.search(cleaned) and _TWO_NUMBERS.search(cleaned))
    )
    if asked is None:
        return False
    # Points on a plane with no chart kind named are maths' coordinate graph.
    return not (_COORDINATE_PAIR.search(cleaned) and not re.search(_KIND, cleaned, re.I))


def _is_chart_definition(cleaned: str) -> bool:
    return bool(_DEFINITION.search(cleaned))


def _chart_request_negated(cleaned: str) -> bool:
    lower = cleaned.lower()
    if "chart" not in lower:
        return False
    for neg in ("do not", "don't", "dont", "never", "without"):
        start = 0
        while True:
            idx = lower.find(neg, start)
            if idx < 0:
                break
            window = lower[idx : idx + 80]
            if "chart" in window and any(
                verb in window for verb in ("make", "draw", "create", "render", "plot")
            ):
                return True
            start = idx + len(neg)
    return False


def is_chart_question(text: str) -> bool:
    """True when the user asked to draw a numeric chart (Vega), not define one."""
    cleaned = text.strip()
    if not cleaned:
        return False
    if _is_chart_definition(cleaned) or _chart_request_negated(cleaned):
        return False
    # "An org chart" or "a Gantt chart" is a Mermaid diagram, not numbers.
    if names_diagram_kind(cleaned):
        return False
    # Code that draws a chart is a code answer.
    if _CODE_ASK.search(cleaned):
        return False
    if _CHART_TURN.search(cleaned):
        return True
    if _asks_for_a_visual_in_other_words(cleaned):
        return True
    # "Draw the learning curve": an idea's curve, as a chart with sample data.
    asked = _DRAW_VERB.search(cleaned)
    if asked is not None and names_idea_curve(cleaned[asked.end() :]):
        return True
    if not _PLOT_REQUEST.search(cleaned):
        return False
    return not (_LINE_PLOT.search(cleaned) and _CURVE.search(cleaned))


# A number the chart request also asks for: "find the mean", "what's the total".
_COMPUTES = re.compile(
    r"\b(?:find|calculate|compute|work\s+out|determine|what(?:'s|\s+is|\s+are)\s+the)\b"
    r"[^.?!\n]{0,40}\b(?:mean|median|mode|average|standard\s+deviation|variance|range|total|"
    r"sum|percent(?:age)?)\b|\b(?:mean|median|mode|average|standard\s+deviation)\s+of\b",
    re.IGNORECASE,
)


class MathRead(Protocol):
    """What ``chart_names_no_curve`` asks of maths' reading: its kind and expression."""

    @property
    def kind(self) -> str: ...

    @property
    def expr(self) -> str | None: ...


def chart_names_no_curve(text: str, read_math: Callable[[str], MathRead | None]) -> bool:
    """A chart request in which maths reads no curve y = f(x).

    The user's own numbers ("a scatter plot of x = 1, 2, 3 and y = …"), or a formula
    maths cannot read: either way there is nothing to verify, so the turn is the
    chart contract's (a formula chart is sampled after the reply). A curve maths reads
    ("line chart of y = x^2") stays maths'. Runs where subjects are read, off the loop.
    ``read_math`` is maths' own reader, which the dispatcher passes in: this module reads
    the user's words and imports no subject.
    """
    if not is_chart_question(text):
        return False
    intent = read_math(text)
    if intent is None:
        return True
    if intent.kind in {"graph", "graph_pair"}:
        return not intent.expr
    # A statistic it asks for ("make a bar chart of these and find the mean") is maths' to
    # verify. The user's points alone are not: "scatter plot of hours vs score: (1, 50),
    # (2, 55)" was read as an arithmetic lesson, and the reply listed the points back.
    return _COMPUTES.search(text) is None


# Numbers the user gave as data: three or more, or any after a colon ("bar graph: apples 30").
# Years and "top 5" are not data.
_NUMBER = re.compile(r"(?<![\w.])\d[\d,.]*")


_YEAR = re.compile(r"\b(?:19|20)\d\d\b")


# "This year" names a time, not the chat's data.
_OWN_DATA = re.compile(
    r"\b(?:my|our|mine|ours|these|those|it|them|above|below|following|"
    r"(?:this|that)(?!\s+(?:year|month|week|quarter|season|decade|century|time)\b))\b",
    re.IGNORECASE,
)


_SAMPLE = re.compile(
    r"\b(?:example|sample|dummy|fake|made[- ]up|random|hypothetical|imaginary)\b", re.IGNORECASE
)


# What only a search knows: populations, prices, rates, rankings.
_FACT_WORDS = re.compile(
    r"\b(?:population|prices?|rates?|exchange|gdp|inflation|temperatures?|weather|stocks?|"
    r"shares?|bitcoin|crypto|popularity|rank(?:ing|ings)?|top|most|largest|biggest|world|"
    r"global|countries|cities|elections?|results|records?|revenue\s+of|sales\s+of)\b",
    re.IGNORECASE,
)


# A name after the first word: "Ethiopia", "iPhone 18 Pro", "USD to ETB".
_PROPER_NOUN = re.compile(r"(?<=\S\s)(?:[A-Z][a-z]+|[a-z]+[A-Z]\w*|[A-Z]{2,})\b")


def chart_of_public_facts(text: str) -> bool:
    """A chart of facts the user did not give, which only a search finds.

    "Graph the population of Ethiopia over the last 10 years" and "compare iPhone 18 Pro
    and Pixel 11 prices in a chart" were drawn from memory or refused ("those models
    haven't been released") without a search (2026-10-24). It names a thing ("Ethiopia",
    "USD") or a fact only a search knows ("population", "prices"). The user's own
    numbers, a word for the chat's data ("graph it", "my sales"), a sample or an idea's
    curve is not one, nor is "show me the income in graph" after a salary question.
    """
    cleaned = text.strip()
    if not is_chart_question(cleaned) or _OWN_DATA.search(cleaned) or _SAMPLE.search(cleaned):
        return False
    asked = _DRAW_VERB.search(cleaned)
    if asked is not None and names_idea_curve(cleaned[asked.end() :]):
        return False
    numbers = _NUMBER.findall(_YEAR.sub(" ", cleaned))
    if len(numbers) >= 3 or (numbers and ":" in cleaned):
        return False
    named = _PROPER_NOUN.search(cleaned)
    # "Put the results in a chart", "show the prices in a bar chart": the chat's data, unless
    # it names something ("compare iPhone 18 Pro and Pixel 11 prices in a chart").
    if _IN_A_VISUAL.search(cleaned) and not named:
        return False
    return bool(named or _FACT_WORDS.search(cleaned))


# How far back a chart follow-up looks for the numbers it draws, in user messages.
_FOLLOWUP_LOOKBACK = 3


# "Graph it", "visualize this", "put that in a chart", or the verb alone ("chart").
_BACK_REFERENCE = re.compile(
    r"\b(?:it|these|those|them|above|(?:this|that)(?!\s+(?:year|month|week|quarter|season|"
    r"decade|century|time)\b))\b",
    re.IGNORECASE,
)


_BARE_VERB = re.compile(rf"^{_POLITE}(?:graph|chart|plot|visuali[sz]e)\W*$", re.IGNORECASE)


def _holds_data(text: str) -> bool:
    """Three numbers or more, or a list of them ("rent 1500, groceries 400") that asks
    nothing: "Compare iPhone 15 and Pixel 8 prices?" holds model names, not data."""
    count = len(_NUMBER.findall(_YEAR.sub(" ", text)))
    if _FORMULA.search(text) or count < 2:
        return False
    return count >= 3 or (bool(re.search(r"[:,]", text)) and "?" not in text)


# The last reply's closing question offers to draw the numbers: "Want a chart of the yearly
# pattern?", "Want me to sketch a quick bar chart of the monthly totals?", "Shall I graph
# them?". Not "Should I chart a course?", "Want me to plot your route?", "Want me to
# summarize the plot?", "Want an org chart?", "Does the chart look right?".
_OFFER_LEAD = re.compile(
    r"^(?:so|ok(?:ay)?|sure|great|also)?[,!.]?\s*(?:want|would\s+you\s+like|do\s+you\s+want|"
    r"should\s+i|shall\s+i|can\s+i|could\s+i|i\s+can|happy\s+to|how\s+about)\b",
    re.IGNORECASE,
)


_OFFERED_CHART = re.compile(
    rf"\b(?:a|an|the|this|that|quick|simple|small|visual|{_KIND})\s+(?:{_KIND}\s+)?"
    rf"(?:chart|graph)s?\b{_VISUAL_AS_MODIFIER}"
    r"|\b(?:graph|chart|plot|visuali[sz]e)\s+(?:it|this|that|these|those|them|the\s+(?:data|"
    r"numbers|values|results|totals))\b",
    re.IGNORECASE,
)


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n")


def _offered_a_chart(prior_messages: Sequence[tuple[str, str]] | None) -> bool:
    last = next((text for role, text in reversed(prior_messages or ()) if role == "assistant"), "")
    question = _SENTENCE_END.split(last.strip()[-400:])[-1].strip()
    return (
        question.endswith("?")
        and _OFFER_LEAD.match(question) is not None
        and _OFFERED_CHART.search(question) is not None
        and not names_diagram_kind(question)
        and not (_FORMULA.search(question) or _CURVE_WORDS.search(question))
    )


def chart_followup_data(query: str, prior_messages: Sequence[tuple[str, str]] | None) -> str | None:
    """The user's earlier message whose numbers a chart follow-up draws, or None.

    "Graph it" after "Here are my exam marks: math 85, physics 78, chemistry 92" was answered
    "You didn't specify which function to graph!" (2026-10-24): the chart hint was there, but
    the numbers were a turn back. A follow-up that names no numbers and points back ("it",
    "that", the verb alone) gets that message quoted: only what the user typed, never a
    file's text after it, which reaches the model wrapped as untrusted. A chart of facts a
    search finds ("plot bitcoin prices") is a new subject, not the earlier numbers.

    "Yes" to the last reply's offer of a chart is a chart turn too; with no numbers of the
    user's to quote (the reply offered to chart its own), it is "": the chart format alone.
    """
    cleaned = query.strip()
    accepts = is_short_confirmation(cleaned) and _offered_a_chart(prior_messages)
    if not cleaned or _NUMBER.search(cleaned) or not (accepts or is_chart_question(cleaned)):
        return None
    if chart_of_public_facts(cleaned):
        return None
    # "What about a pie chart?" names no subject: it is the earlier numbers as another kind.
    if not (
        accepts
        or _BACK_REFERENCE.search(cleaned)
        or _BARE_VERB.match(cleaned)
        or _ANOTHER_KIND.match(cleaned)
    ):
        return None
    earlier = [
        typed
        for role, text in prior_messages or ()
        if role == "user"
        and (typed := text_before_attachment_markers(text).strip())
        and typed != cleaned
    ]
    # "Yes" answers the last reply, so only the message that reply answered holds its numbers.
    for text in reversed(earlier[-1:] if accepts else earlier[-_FOLLOWUP_LOOKBACK:]):
        if _holds_data(text):
            return " ".join(text.split())[:600]
    # "Want me to graph it?" after "y = 2x + 3" offers maths' graph of a curve, not a chart.
    curve = any(_FORMULA.search(text) or _CURVE_WORDS.search(text) for text in earlier[-1:])
    return "" if accepts and not curve else None
