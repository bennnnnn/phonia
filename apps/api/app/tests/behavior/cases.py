"""The behavior battery: prompts a real user sends, and how Recall should handle each.

One list feeds two runs:

- ``test_battery.py`` (CI) sends every prompt through the real turn routing with
  external services stubbed and checks the ``Expect`` fields.
- ``scripts/battery.py`` (``./scripts/dev.sh battery``) sends the same prompts to a
  running API and writes the replies, photos and sources to one report.

``gap`` names something Recall should do and does not yet. Its routing check is an
expected failure until the gap is fixed; then the check passes, the test says so, and
the ``gap`` line comes out. ``good`` says what a good reply looks like, for whoever
reads the replay report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Search = Literal["yes", "ask", "no"]
"""``yes``: searched with no model asked. ``ask``: a model decides. ``no``: no search."""

CATEGORIES = (
    "math",
    "physics",
    "chemistry",
    "web search",
    "photos and maps",
    "time and location",
    "teaching",
    "format",
    "code",
    "tone and emoji",
    "personal",
    "multi-intent",
    "money",
)


@dataclass(frozen=True)
class Expect:
    """What routing must do. ``None`` (or an empty tuple) leaves a signal unchecked."""

    search: Search | None = None
    # The reference-photo search the turn runs; "" means no photo lookup.
    photo: str | None = None
    # Words the photo search must not carry ("new": find the model's name first).
    photo_not: tuple[str, ...] = ()
    image_gen: bool | None = None
    # "math" / "physics" / "chemistry", or "" for none.
    subject: str | None = None
    # A solver checked the answer before the model wrote it.
    solved: bool | None = None
    # "clock", "location", "solver" or "" for a model-written reply.
    instant: str | None = None
    lightweight: bool | None = None
    # Prompt hints that must be present / absent (names from harness.HINTS).
    hints: tuple[str, ...] = ()
    no_hints: tuple[str, ...] = ()
    # A real photo above the model's answer (it opened with ```photo). Routing can
    # only check the hint that offers it; the live replay checks the photo.
    answer_photo: bool | None = None
    # A whole subject ("teach me python") gets its topics in order and one question,
    # never a lesson yet (prompt_constants.teaching._SUBJECT_OUTLINE).
    outline: bool = False
    # The model the case's plan gets on Auto (``model_choice.resolve_user_model``).
    model: str | None = None
    # A multi-part message's picture, drawn above the model's answer to the rest.
    picture: bool | None = None
    # A multi-part message's settings card, under the model's answer to the rest.
    settings_card: bool | None = None
    # Saved memory is read for the turn, and which scope ("work", "query", "profile",
    # "self"; see modules/chat/prompt_memory.py).
    memory: bool | None = None
    memory_scope: str | None = None


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    prompt: str
    expect: Expect
    good: str
    gap: str | None = None
    # Earlier turns as (role, text), oldest first.
    history: tuple[tuple[str, str], ...] = ()
    pro: bool = False
    location: str | None = None
    tags: tuple[str, ...] = field(default=())
    # The user's memory switch (Settings → Memory).
    memory_enabled: bool = True
    # The user's app language: how they write numbers ("1.200" is 1200 in Spanish).
    locale: str = "en"


NO_PHOTO = ""
NONE = ""

# A story cut off mid-sentence, and code with its bug report, for the follow-up turns.
_STORY = (
    ("user", "tell me a long story about a dragon who is afraid of fire"),
    (
        "assistant",
        "Ember was the only dragon in the Ashen Peaks who flinched at sparks. Every spring the "
        "young dragons lit the valley torches, and every spring Ember hid behind the waterfall.\n\n"
        "One night a storm knocked out every torch in the village below, and the elders came "
        'to the waterfall looking for her. "We need fire," they said, and Ember',
    ),
)
_AVERAGE_CODE = (
    ("user", "write a python function that averages a list of numbers"),
    ("assistant", "```python\ndef average(numbers):\n    return sum(numbers) / len(numbers)\n```"),
    ("user", "it crashes on an empty list"),
    (
        "assistant",
        "Right: `len([])` is `0`, so `sum([]) / 0` raises `ZeroDivisionError`.",
    ),
)

# A reply that starts an answer and asks what "best" means with a tap card.
_BEST_COUNTRY = (
    ("user", "What is the best country"),
    (
        "assistant",
        "Strong contenders: Switzerland, Norway, Singapore.\n\n**But let me ask you one "
        "thing.**\n\nWhat do you mean by *best*?\n\n```clarify\n"
        '{"request":"Recommend the best country for me.","questions":[{"id":"priority",'
        '"label":"Main priority","question":"What matters most to you?","options":'
        '["💰 Making money","🌿 Quality of life","🛡️ Safety"]},{"id":"region","label":'
        '"Geographic preference","question":"Which region are you considering?","options":'
        '["🌍 Anywhere","🇪🇺 Europe","🌎 The Americas"]}],"closing":"Compare the strongest '
        'options with practical pros and cons.","submit":"Find my best country"}\n```',
    ),
)

CASES: tuple[Case, ...] = (
    # ── Math ────────────────────────────────────────────────────────────────
    Case(
        "math-linear",
        "math",
        "solve 2x + 5 = 17",
        Expect(subject="math", solved=True, photo=NO_PHOTO),
        "x = 6, with the two steps shown.",
    ),
    Case(
        "math-do-it-after-word-problem",
        "math",
        "Do it",
        Expect(solved=False, instant=""),
        "Works the sled problem it just set: a = 4 m/s², v = 12 m/s, s = 18 m. Never a "
        "verified 'no solution' for the F = ma in its hint.",
        history=(
            ("user", "Give me a problem"),
            (
                "assistant",
                "**Problem:** A 5 kg sled is pulled across a frictionless ice surface by a "
                "horizontal rope that exerts a constant force of 20 N. The sled starts from "
                "rest.\n\n1. Find the sled's acceleration.\n2. Determine its speed after 3 "
                "seconds.\n3. Compute the distance it travels in those 3 seconds.\n\n*Hint:* "
                "Use $F = ma$ for (a), $v = at$ for (b), and $s = \\frac12 a t^2$ for (c).",
            ),
        ),
    ),
    Case(
        "math-derivative",
        "math",
        "what is the derivative of x^3 sin x",
        Expect(subject="math", solved=True),
        "3x² sin x + x³ cos x by the product rule.",
    ),
    Case(
        "math-integral",
        "math",
        "integrate x e^x dx",
        Expect(subject="math", solved=True),
        "(x − 1)eˣ + C by parts.",
    ),
    Case(
        "math-graph",
        "math",
        "graph y = x^2 - 4x + 3",
        Expect(subject="math", photo=NO_PHOTO),
        "A graph of the parabola with roots 1 and 3 and vertex (2, −1).",
    ),
    Case(
        "math-graph-pair-pi",
        "math",
        "Graph y = sin(x) and y = cos(x) from 0 to 2π",
        Expect(subject="math", solved=True, no_hints=("chart",)),
        "One verified graph with both curves on [0, 2π]; no chart fence.",
    ),
    Case(
        "math-line-graph-curve",
        "math",
        "draw the line graph of y = 2x+1",
        Expect(subject="math", solved=True, no_hints=("chart",)),
        "A verified graph of the line, not a chart of made-up points.",
    ),
    Case(
        "math-percent",
        "math",
        "what is 15% of 240",
        Expect(subject="math", search="no"),
        "36.",
    ),
    Case(
        "math-check-work",
        "math",
        "I got x = 4 for 3x - 2 = 10, is that right?",
        Expect(subject="math", solved=True, search="no"),
        "Yes: 3·4 − 2 = 10.",
    ),
    Case(
        "math-word-problem",
        "math",
        "A train travels 120 km in 1.5 hours. What is its average speed?",
        Expect(search="no", photo=NO_PHOTO),
        "80 km/h.",
    ),
    Case(
        "math-proportion-recipe",
        "math",
        "A recipe needs 3 cups of flour for 12 cookies. How many cups for 30 cookies?",
        Expect(subject="math", solved=True, search="no", no_hints=("advice",)),
        "7.5 cups (3/12 of a cup per cookie, times 30). A proportion, not a recipe pick.",
    ),
    Case(
        "math-triangle-area",
        "math",
        "a triangle has sides 3, 4 and 5. what is its area?",
        Expect(subject="math", search="no"),
        "6 square units (a right triangle, ½·3·4).",
    ),
    Case(
        "math-vertex",
        "math",
        "find the vertex of y = x^2 - 6x + 5",
        Expect(subject="math", solved=True, instant="solver", search="no"),
        "(3, −4), from h = −b/2a. Never the equation solved for x.",
    ),
    Case(
        "math-line-through-point",
        "math",
        "find the equation of the line parallel to y = 3x + 1 through (2, 5)",
        Expect(subject="math", solved=True, search="no"),
        "y = 3x − 1: the same slope 3, through (2, 5).",
    ),
    Case(
        "math-claimed-answer",
        "math",
        "check my answer: x = 6",
        Expect(subject="math", solved=True, search="no"),
        "Not quite: 4(6) − 7 = 17, not 21. The answer is x = 7. Never a ✓ for x = 6.",
        history=(("user", "Solve 4x - 7 = 21"), ("assistant", "```answer\nx = 7\n```")),
    ),
    Case(
        "math-bare-claim",
        "math",
        "x = 6",
        Expect(solved=False, instant=""),
        "Asks what x = 6 is the answer to. Never a verified card that only repeats it.",
    ),
    Case(
        "math-simplify-it",
        "math",
        "simplify it",
        # The message alone is not maths; the thread supplies the expression.
        Expect(solved=True, search="no"),
        "x + 1, from the rational expression the user sent. Never the product i·t.",
        history=(("user", "(x^2-1)/(x-1)"), ("assistant", "That is a rational expression in x.")),
    ),
    Case(
        "math-restated-equation",
        "math",
        "what about 2x + 5 = 21",
        # The lead kept the equation from reading as maths at all.
        Expect(solved=True, instant="solver", search="no"),
        "x = 8, worked the same way as the last equation.",
        history=(
            ("user", "solve 2x + 5 = 17"),
            ("assistant", "```answer\nverified: true\nx = 6\n```"),
        ),
    ),
    Case(
        "math-percent-thousands",
        "math",
        "what is 20% of 1,000",
        Expect(subject="math", solved=True, search="no"),
        "200. The comma groups the thousands.",
    ),
    Case(
        "math-divide-by-zero",
        "math",
        "what is 5/0",
        Expect(subject="math", solved=True, search="no"),
        "Undefined: nothing times 0 makes 5. Never NaN or complex infinity.",
    ),
    Case(
        "math-lookalike-differentiate",
        "math",
        "differentiate between weather and climate",
        Expect(subject="", solved=False),
        "Weather is the short term, climate the long-term pattern. Not maths.",
    ),
    # ── Physics ─────────────────────────────────────────────────────────────
    Case(
        "physics-drop",
        "physics",
        "a ball is dropped from 20 m. how long until it hits the ground?",
        Expect(subject="physics", solved=True, search="no"),
        "About 2.02 s from t = √(2h/g).",
    ),
    Case(
        "physics-force",
        "physics",
        "what force is needed to accelerate a 10 kg mass at 3 m/s^2?",
        Expect(subject="physics", solved=True),
        "30 N from F = ma.",
    ),
    Case(
        "physics-ohm",
        "physics",
        "a 12 V battery is connected to a 4 ohm resistor. what is the current?",
        Expect(subject="physics", solved=True),
        "3 A from I = V/R.",
    ),
    Case(
        "physics-concept",
        "physics",
        "explain Newton's third law",
        Expect(search="ask", solved=False, photo=NO_PHOTO),
        "Equal and opposite forces on two different bodies, with an everyday example.",
    ),
    Case(
        "physics-followup-how-far",
        "physics",
        "how far does it go?",
        # The car, not the user: never "I don't have your location".
        Expect(solved=True, instant="", search="no"),
        "37.5 m from s = ½at², the same car and numbers.",
        history=(
            ("user", "A car accelerates from rest at 3 m/s^2 for 5 s. What is its final velocity?"),
            ("assistant", "**Answer**\n\n```answer\nverified: true\n15\\,\\mathrm{m/s}\n```"),
        ),
    ),
    Case(
        "physics-followup-unit",
        "physics",
        "in km/h please",
        Expect(solved=True, instant="", search="no"),
        "54 km/h: the verified 15 m/s converted, never worked again unchecked.",
        history=(
            ("user", "A car accelerates from rest at 3 m/s^2 for 5 s. What is its final velocity?"),
            ("assistant", "**Answer**\n\n```answer\nverified: true\n15\\,\\mathrm{m/s}\n```"),
        ),
    ),
    Case(
        "physics-followup-new-time",
        "physics",
        "and after 10 s?",
        Expect(solved=True, instant="", search="no"),
        "30 m/s: the same car after 10 s.",
        history=(
            ("user", "A car accelerates from rest at 3 m/s^2 for 5 s. What is its final velocity?"),
            ("assistant", "**Answer**\n\n```answer\nverified: true\n15\\,\\mathrm{m/s}\n```"),
        ),
    ),
    Case(
        "physics-unverified-self-check",
        "physics",
        "A 4 ohm and a 6 ohm resistor are in series, and that pair is in parallel with a "
        "12 ohm resistor across a 12 V battery. Find the current from the battery.",
        # A network the server does not read stays with the model: it uses the same
        # layout and checks its own answer, since no server check stands behind it.
        Expect(subject="physics", solved=False, hints=("self_check", "worked")),
        "A ```worked block the server lays out as Given/Required/Formula/Substitution/Answer: "
        "R = (4 + 6) ∥ 12 = 120/22 ≈ 5.45 Ω, I = 12/5.45 ≈ 2.2 A, its card not checked. "
        "Never a ✓ and never 'verified'.",
    ),
    Case(
        "physics-verified-no-self-check",
        "physics",
        "a ball is dropped from 45 m. how long until it hits the ground?",
        Expect(subject="physics", solved=True, no_hints=("self_check", "worked")),
        "About 3.03 s from t = √(2h/g), copied from the verified card.",
    ),
    Case(
        "physics-unread-exercise-worked",
        "physics",
        "A car moves at a speed of 20m/s for 120 seconds due East. What is the displacement "
        "of the car?",
        # No subject reader reads it, but it is a school exercise with numbers: its parts
        # come in a ```worked block, laid out as a verified reply (2026-11-01).
        Expect(solved=False, hints=("worked",)),
        "Given v = 20 m/s, t = 120 s; Required s; s = vt; s = 20 × 120 = 2400 m; Answer "
        "2400 m east in a card marked not checked.",
    ),
    Case(
        "chem-word-cue-no-worked",
        "chemistry",
        "remind me to study chemistry tomorrow at 7pm",
        # Chemistry named by a word and a time, no calculation: no ```worked block.
        Expect(no_hints=("worked",)),
        "A reminder card for 7 pm tomorrow.",
    ),
    Case(
        "physics-explain-no-worked",
        "physics",
        "Why is displacement a vector but distance is not?",
        Expect(no_hints=("worked",)),
        "A short explanation in prose: direction. No worked layout.",
    ),
    # ── Chemistry ───────────────────────────────────────────────────────────
    Case(
        "chem-balance",
        "chemistry",
        "balance H2 + O2 -> H2O",
        Expect(subject="chemistry", search="no"),
        "2H₂ + O₂ → 2H₂O.",
    ),
    Case(
        "chem-molar-mass",
        "chemistry",
        "what is the molar mass of H2SO4",
        Expect(subject="chemistry", search="no"),
        "About 98.08 g/mol.",
    ),
    Case(
        "chem-moles",
        "chemistry",
        "how many moles are in 36 g of water",
        Expect(subject="chemistry", search="no"),
        "2 mol (36 ÷ 18.02).",
    ),
    Case(
        "chem-ph",
        "chemistry",
        "what is the pH of 0.01 M HCl",
        Expect(subject="chemistry", search="no"),
        "pH 2 for a strong acid.",
    ),
    Case(
        "chem-structure",
        "chemistry",
        "show me the structure of caffeine",
        Expect(subject="chemistry", photo=NO_PHOTO),
        "The caffeine molecule drawn from its SMILES, not a stock photo.",
    ),
    Case(
        "chemistry-unverified-self-check",
        "chemistry",
        "Balance the redox reaction MnO4- + Fe2+ -> Mn2+ + Fe3+ in acidic solution.",
        Expect(subject="chemistry", solved=False, hints=("self_check",)),
        "Half-reactions, electrons balanced, then a Check that atoms and charge match on "
        "both sides. Never a ✓.",
    ),
    # ── Web search ──────────────────────────────────────────────────────────
    Case(
        "search-world-cup",
        "web search",
        "who won the last world cup",
        Expect(search="yes", photo=NO_PHOTO),
        "The most recent winner, with a source chip.",
    ),
    Case(
        "search-stock",
        "web search",
        "what is tesla stock price today",
        Expect(search="yes"),
        "Today's price with the time it was quoted and a source.",
    ),
    Case(
        "search-new-model",
        "web search",
        "tell me about the new tesla model",
        Expect(search="yes"),
        "The newest Tesla model by name, from a search, not from training data.",
    ),
    Case(
        "search-ai-news",
        "web search",
        "latest news on AI",
        Expect(search="yes"),
        "A few current headlines with sources.",
    ),
    Case(
        "search-weather-city",
        "web search",
        "what's the weather in Addis Ababa",
        Expect(search="yes"),
        "Current conditions and temperature, with a source.",
    ),
    Case(
        "search-explicit",
        "web search",
        "search for the best laptop for programming",
        Expect(search="yes", photo=NO_PHOTO),
        "Current picks from the search, with sources.",
    ),
    Case(
        "search-static-fact",
        "web search",
        "what is the capital of Kenya",
        # A question about the world: the reply's model has web_search, and needs none here.
        Expect(search="ask", photo=NO_PHOTO),
        "Nairobi, in one line.",
    ),
    Case(
        "search-bare-command",
        "web search",
        "do a search",
        Expect(search="yes"),
        "Searches the topic of the chat (Jeanne Calment), not the words 'do a search'.",
        history=(
            ("user", "Who lived the longest?"),
            ("assistant", "Jeanne Calment, who reached 122 years and 164 days."),
        ),
    ),
    Case(
        "search-world-fact",
        "web search",
        "what's the population of Ethiopia",
        # No live word, yet the answer is a number that changes: the reply's model searches.
        Expect(search="ask"),
        "A recent figure from a search with its year, never a remembered guess.",
    ),
    Case(
        "search-claim-about-a-leader",
        "web search",
        "But Ahmed is a genocider. He caused all the war",
        Expect(search="ask"),
        "Even-handed: what is documented and what is disputed about Abiy Ahmed and the "
        "Tigray war, from sources; never 'I don't have information in my memory'.",
        history=(
            ("user", "tell me about the war in ethiopia"),
            ("assistant", "The Tigray war began in November 2020 and ended with a 2022 truce."),
        ),
    ),
    Case(
        "search-officeholder-followup",
        "web search",
        "What is the president?",
        Expect(search="yes"),
        "Searches who is President of Ethiopia now (Taye Atske Selassie since October 2024), "
        "never a name from memory.",
        history=(
            ("user", "tell me about the war in ethiopia"),
            ("assistant", "The Tigray war began in November 2020 and ended with a 2022 truce."),
        ),
    ),
    Case(
        "search-newest-phone",
        "web search",
        "what's the newest iphone",
        Expect(search="yes"),
        "The current newest iPhone by name, from a search.",
    ),
    Case(
        "search-no-new-to",
        "web search",
        "I'm new to python, where should I start?",
        Expect(search="ask"),
        "A starting path; nothing about new products.",
    ),
    Case(
        "search-no-new-year",
        "web search",
        "happy new year!",
        Expect(search="ask"),
        "A warm reply.",
    ),
    Case(
        "search-no-weather-concept",
        "web search",
        "what causes weather",
        Expect(search="ask"),
        "Sun, air pressure, water vapor and the earth's rotation, explained simply.",
    ),
    Case(
        "search-no-weather-poem",
        "web search",
        "write a poem about the weather",
        Expect(search="no"),
        "A short poem.",
    ),
    Case(
        "search-no-under-the-weather",
        "web search",
        "I feel under the weather today",
        Expect(search="no"),
        "Sympathy and simple care tips; no forecast.",
    ),
    Case(
        "search-no-boiling-point-idiom",
        "web search",
        "the boiling point of my patience is low today",
        Expect(search="no", subject=NONE, instant=""),
        "A short, warm reply about a rough day; no lookup and no chemistry.",
    ),
    # ── Photos and maps ─────────────────────────────────────────────────────
    Case(
        "photo-landmark",
        "photos and maps",
        "show me the eiffel tower",
        Expect(photo="eiffel tower"),
        "A real photo of the Eiffel Tower.",
    ),
    Case(
        "photo-animal",
        "photos and maps",
        "what does a capybara look like",
        Expect(photo="capybara"),
        "A real photo of a capybara.",
    ),
    Case(
        "photo-person",
        "photos and maps",
        "show me a picture of Albert Einstein",
        Expect(photo="Albert Einstein"),
        "A real photo of Albert Einstein.",
    ),
    Case(
        "photo-new-product",
        "photos and maps",
        "show me the new tesla model",
        Expect(photo_not=("new",)),
        "A photo of the newest Tesla model: the search asks for this year's, not 'new'.",
    ),
    Case(
        "map-where-is",
        "photos and maps",
        "where is kenya",
        Expect(
            hints=("answer_photo", "where_is_photo"),
            photo=NO_PHOTO,
            search="ask",
            answer_photo=True,
        ),
        "A real map of Kenya above: East Africa on the equator, on the Indian Ocean.",
    ),
    Case(
        "map-show-where",
        "photos and maps",
        "show me where nepal is",
        Expect(hints=("where_is_photo",), photo=NO_PHOTO, search="ask", answer_photo=True),
        "A real map of Nepal above: between India and China in the Himalayas.",
    ),
    Case(
        "map-not-a-place",
        "photos and maps",
        "where is the error in my code",
        Expect(no_hints=("where_is_photo",), photo=NO_PHOTO, search="ask", answer_photo=False),
        "Asks for the code (none was shared); no photo.",
    ),
    Case(
        "auto-photo-animal",
        "photos and maps",
        "what is a capybara",
        Expect(hints=("answer_photo", "subject_photo"), photo=NO_PHOTO, answer_photo=True),
        "A real capybara photo above a short answer: the largest rodent, South American.",
    ),
    Case(
        "auto-photo-landmark",
        "photos and maps",
        "tell me about Lalibela",
        Expect(hints=("answer_photo", "subject_photo"), photo=NO_PHOTO, answer_photo=True),
        "A photo of the rock-hewn churches above the answer.",
    ),
    Case(
        "auto-photo-person",
        "photos and maps",
        "who is Haile Gebrselassie",
        Expect(hints=("answer_photo", "subject_photo"), photo=NO_PHOTO, answer_photo=True),
        "A photo of him above: the Ethiopian distance runner and his records.",
    ),
    Case(
        "auto-photo-none",
        "photos and maps",
        "what is recursion",
        # A programming concept: no photo is offered at all.
        Expect(no_hints=("answer_photo", "subject_photo"), photo=NO_PHOTO, answer_photo=False),
        "A plain explanation with a tiny example; no photo.",
    ),
    Case(
        "map-explicit",
        "photos and maps",
        "show me a map of kenya",
        Expect(photo="map of kenya"),
        "A map of Kenya.",
    ),
    Case(
        "image-gen",
        "photos and maps",
        "draw me a cat wearing a hat",
        Expect(image_gen=True, photo=NO_PHOTO),
        "A generated picture (Pro).",
        pro=True,
    ),
    Case(
        "image-gen-free",
        "photos and maps",
        "generate an image of a sunset over mountains",
        Expect(image_gen=True, photo=NO_PHOTO),
        "On the free plan too: a generated picture, within the free daily images.",
    ),
    Case(
        "image-gen-es",
        "photos and maps",
        "Dibuja un gato con sombrero",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-fr",
        "photos and maps",
        "Dessine-moi un mouton",
        Expect(image_gen=True, photo=NO_PHOTO),
        'A generated picture, as for "draw a cat" in English.',
        pro=True,
    ),
    Case(
        "image-gen-de",
        "photos and maps",
        "Zeichne eine Katze mit Hut",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-it",
        "photos and maps",
        "Disegna un gatto con il cappello",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-pt",
        "photos and maps",
        "Desenhe um gato com chapéu",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-tr",
        "photos and maps",
        "Şapkalı bir kedi çiz",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-ru",
        "photos and maps",
        "Нарисуй кошку в шляпе",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-am",
        "photos and maps",
        "ድመት ሳልልኝ",
        Expect(image_gen=True, photo=NO_PHOTO),
        'A generated picture, as for "draw a cat" in English.',
        pro=True,
    ),
    Case(
        "image-gen-draw-me-es",
        "photos and maps",
        "¿Me dibujas un dragón?",
        Expect(image_gen=True, photo=NO_PHOTO),
        "A generated picture: a draw verb addressed with 'me', as 'draw me a dragon'.",
        pro=True,
    ),
    Case(
        "image-gen-draw-me-it",
        "photos and maps",
        "Mi disegni un panda?",
        Expect(image_gen=True, photo=NO_PHOTO),
        "A generated picture: a draw verb addressed with 'me', as 'draw me a dragon'.",
        pro=True,
    ),
    Case(
        "image-gen-draw-me-de",
        "photos and maps",
        "Zeichne mir einen Drachen",
        Expect(image_gen=True, photo=NO_PHOTO),
        "A generated picture: a draw verb addressed with 'me', as 'draw me a dragon'.",
        pro=True,
    ),
    Case(
        "image-gen-create-tr",
        "photos and maps",
        "Bana bir panda çizer misin?",
        Expect(image_gen=True, photo=NO_PHOTO),
        "A generated picture: a draw verb addressed with 'me', as 'draw me a dragon'.",
        pro=True,
    ),
    Case(
        "image-gen-lookalike-teaching-es",
        "photos and maps",
        "Ilustra con un ejemplo",
        Expect(image_gen=False, photo=NO_PHOTO),
        "An example in words: 'ilustrar' explains here.",
        pro=True,
    ),
    Case(
        "image-gen-lookalike-chemistry-de",
        "photos and maps",
        "Zeichne Koffein",
        Expect(image_gen=False, photo=NO_PHOTO),
        "The caffeine structure in words, not an AI picture.",
        pro=True,
    ),
    Case(
        "image-gen-lookalike-looks-es",
        "photos and maps",
        "¡Pinta bien!",
        Expect(image_gen=False, photo=NO_PHOTO),
        "A reply to 'looks good': no picture of 'bien'.",
        pro=True,
    ),
    Case(
        "image-gen-lookalike-points-back-pt",
        "photos and maps",
        "Pinta isso",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Asks what to paint; 'isso' names nothing in the line.",
        pro=True,
    ),
    Case(
        "image-gen-draw-me-detail-en",
        "photos and maps",
        "draw me a robot and tell me its name",
        Expect(image_gen=True, photo=NO_PHOTO),
        "A robot picture, as on main: 'tell me its name' is about the picture.",
        pro=True,
    ),
    Case(
        "image-gen-draw-me-same-topic-en",
        "photos and maps",
        "Draw me a dog and tell me about dog breeds",
        Expect(image_gen=True, photo=NO_PHOTO),
        "A dog picture of the whole line, as on main: the plan keeps one request when "
        "both halves are about dogs (round 6).",
        pro=True,
    ),
    Case(
        "image-gen-not-listed-es",
        "photos and maps",
        "Dibújame un cuadro comparativo entre iPhone y Android",
        Expect(image_gen=False, photo=NO_PHOTO),
        "A comparison in words: 'cuadro' is no listed drawable thing (round 6).",
        pro=True,
    ),
    Case(
        "image-gen-parts-fr",
        "photos and maps",
        "Dessine-moi un volcan avec ses parties",
        Expect(image_gen=False, photo=NO_PHOTO),
        "A labelled school figure, answered in words: 'parties' asks for the parts (round 6).",
        pro=True,
    ),
    Case(
        "image-gen-ascii-es",
        "photos and maps",
        "Dibújame un gato en ASCII",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Characters, not a picture: 'ASCII' is no listed word, so the line is answered (round 7).",
        pro=True,
    ),
    Case(
        "image-gen-binary-tree-de",
        "photos and maps",
        "Zeichne mir einen binären Baum",
        Expect(image_gen=False, photo=NO_PHOTO),
        "A data structure, answered: 'binären' is no listed descriptor (round 7).",
        pro=True,
    ),
    Case(
        "image-gen-second-ask-es",
        "photos and maps",
        "Dibújame un perro y sugiéreme nombres",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered, not a picture of 'perro y sugiéreme nombres': the second request is no "
        "listed word, so the line is not one picture (round 7).",
        pro=True,
    ),
    Case(
        "image-gen-scene-es",
        "photos and maps",
        "Dibújame un gato negro en la playa",
        Expect(image_gen=True, photo=NO_PHOTO),
        "A black cat on a beach: every word is a listed noun, descriptor or function word "
        "(round 7).",
        pro=True,
    ),
    Case(
        "image-gen-squirrel-ru",
        "photos and maps",
        "Нарисуй белку с орехом",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-calculator-tr",
        "photos and maps",
        "Bir hesap makinesi çiz",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-cell-es",
        "photos and maps",
        "Dibuja una célula",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answered in words, as on main: a bare draw verb (no 'me') draws nothing in other "
        "languages (round 5).",
        pro=True,
    ),
    Case(
        "image-gen-lookalike-es",
        "photos and maps",
        "dibuja la gráfica de y = x^2",
        Expect(image_gen=False, photo=NO_PHOTO),
        "The parabola's graph card, not a generated picture.",
        pro=True,
    ),
    Case(
        "image-gen-lookalike-de",
        "photos and maps",
        "Zeichne mir eine Tabelle der Ergebnisse",
        Expect(image_gen=False, photo=NO_PHOTO),
        "A table in the reply, not a generated picture.",
        pro=True,
    ),
    Case(
        "image-gen-lookalike-ru",
        "photos and maps",
        "Нарисуй график функции y = x^2",
        Expect(image_gen=False, photo=NO_PHOTO),
        "The parabola's graph card, not a generated picture.",
        pro=True,
    ),
    Case(
        "image-gen-lookalike-tr",
        "photos and maps",
        "önemli yerlerin altını çiz",
        Expect(image_gen=False, photo=NO_PHOTO),
        "The important parts in bold: 'altını çiz' underlines, it draws nothing.",
        pro=True,
    ),
    # ── Time and location ───────────────────────────────────────────────────
    Case(
        "time-now",
        "time and location",
        "what time is it",
        Expect(instant="clock", search="no"),
        "The live clock card for the user's time zone.",
    ),
    Case(
        "time-remote",
        "time and location",
        "what time is it in Tokyo",
        Expect(search="no"),
        "Tokyo's current time, computed from the user's clock.",
    ),
    Case(
        "time-date",
        "time and location",
        "what's today's date",
        Expect(search="no"),
        "Today's date.",
    ),
    Case(
        "time-weekday",
        "time and location",
        "what day of the week is christmas this year",
        Expect(search="no"),
        "The weekday of December 25 this year.",
    ),
    Case(
        "location-nearby-unset",
        "time and location",
        "find a coffee shop near me",
        Expect(instant="location"),
        "Asks to turn on location, since none is set.",
    ),
    Case(
        "location-nearby-set",
        "time and location",
        "find a coffee shop near me",
        Expect(search="yes", hints=("local_places",)),
        "A short list of nearby coffee shops around Nairobi, with sources.",
        location="Westlands, Nairobi, Kenya",
    ),
    Case(
        "location-where-am-i",
        "time and location",
        "where am I",
        Expect(search="no"),
        "The saved location (Westlands, Nairobi), or how to set one.",
        location="Westlands, Nairobi, Kenya",
    ),
    Case(
        "location-weather-here",
        "time and location",
        "what's the weather like here",
        Expect(search="yes"),
        "The weather in Nairobi from a search.",
        location="Westlands, Nairobi, Kenya",
    ),
    Case(
        "location-weather-unset",
        "time and location",
        "will it rain tomorrow",
        Expect(instant="location"),
        "Asks to turn on location (or name a city), since none is set.",
    ),
    Case(
        "location-trip-minutes-unset",
        "time and location",
        "how many minutes to drive to the airport",
        Expect(instant="location"),
        "Asks to turn on location: a drive time needs a starting point.",
    ),
    Case(
        "location-duration-not-a-trip",
        "time and location",
        "how many minutes in a good nap",
        Expect(instant="", search="ask"),
        "About 10–20 minutes for a power nap, or 90 for a full cycle. No location needed.",
    ),
    # ── Teaching ────────────────────────────────────────────────────────────
    Case(
        "teach-python",
        "teaching",
        "teach me python",
        Expect(hints=("teaching", "programming_lesson"), search="no", outline=True),
        "One line on what Python opens up, 5-8 topics in order, then where they are and where "
        "to start. No lesson, no code, no quiz yet.",
    ),
    Case(
        "teach-python-scratch",
        "teaching",
        "I want to learn python from scratch",
        Expect(hints=("teaching",), outline=True),
        "The same outline as 'teach me python', tailored to starting from nothing.",
    ),
    Case(
        "teach-two-sum-understand",
        "teaching",
        "help me understand two sum in python",
        Expect(hints=("walkthrough",), no_hints=("teaching",), search="no"),
        "Lesson 1: Two Sum: index boxes, brute force line by line, the dictionary idea traced in "
        "step cards, a cost table, a quiz card.",
    ),
    Case(
        "teach-two-sum-explain",
        "teaching",
        "explain two sum in python",
        Expect(search="ask", photo=NO_PHOTO),
        "Same walkthrough, shorter; ends with the O(n) solution and its trace.",
    ),
    Case(
        "teach-history-know",
        "teaching",
        "I want to know american history",
        Expect(hints=("teaching",), search="ask", outline=True),
        "The same outline as 'teach me american history': the eras in order, then where to start.",
    ),
    Case(
        "teach-no-know-fact",
        "teaching",
        "I want to know if it will rain tomorrow",
        Expect(no_hints=("teaching",)),
        "A forecast, not a lesson.",
    ),
    Case(
        "teach-walkthrough-recursion",
        "teaching",
        "I don't understand recursion",
        Expect(hints=("walkthrough",), search="no"),
        "Lesson 1: Recursion: the idea, a call-by-call trace in step cards, the base case, a quiz.",
    ),
    Case(
        "teach-walkthrough-curly",
        "teaching",
        "I don\u2019t understand recursion",
        Expect(hints=("walkthrough",), search="no"),
        "The iPhone keyboard's apostrophe: the same lesson as \"I don't understand recursion\".",
    ),
    Case(
        "teach-walkthrough-confused",
        "teaching",
        "I'm confused about pointers in C",
        Expect(hints=("walkthrough",), search="no"),
        "Lesson 1: Pointers: what an address is, * and &, a trace, a quiz.",
    ),
    Case(
        "teach-walkthrough-no-sense",
        "teaching",
        "recursion makes no sense to me",
        Expect(hints=("walkthrough",), search="no"),
        'The same lesson as "I don\'t understand recursion".',
    ),
    Case(
        "teach-not-a-topic",
        "teaching",
        "I don't understand why she left",
        Expect(no_hints=("walkthrough", "teaching")),
        "A person, not a topic: a kind reply, no lesson.",
    ),
    Case(
        "teach-history",
        "teaching",
        "teach me american history",
        Expect(hints=("teaching",), search="no", outline=True),
        "The eras in order as an outline, then where to start. No lesson yet.",
    ),
    Case(
        "teach-eli10",
        "teaching",
        "explain recursion like I'm 10",
        Expect(search="no"),
        "A simple analogy (Russian dolls, mirrors), then a tiny example.",
    ),
    Case(
        "teach-plan",
        "teaching",
        "give me a 30 day plan to learn javascript",
        Expect(hints=("learning_plan",), search="no"),
        "Day 1 to Day 30, one line each, with phases, code examples and milestones.",
    ),
    Case(
        "teach-preference",
        "teaching",
        "When teaching me, explain one concept at a time, use practical examples, and ask me "
        "to solve a short exercise before moving on.",
        Expect(
            hints=("standing_preference",),
            no_hints=("answer_photo", "teaching", "personal_disclosure"),
            search="no",
            photo=NO_PHOTO,
        ),
        "Agrees in a sentence, lists the plan (one concept at a time, a practical example, a "
        "short exercise first), asks what to learn first. Never mentions an image.",
    ),
    Case(
        "teach-preference-after-code",
        "teaching",
        "When teaching me, explain one concept at a time, use practical examples, and ask me "
        "to solve a short exercise before moving on.",
        Expect(
            hints=("standing_preference",),
            no_hints=("answer_photo", "teaching", "code_debug"),
            search="no",
        ),
        "Agrees, lists the plan, and offers to go on with lists and indexes that way.",
        history=(
            (
                "user",
                "Why does this code fail, and how would you fix it?\nnumbers = [1, 2, 3]\n"
                "print(numbers[3])",
            ),
            (
                "assistant",
                "This code fails with an `IndexError`: `numbers` has indexes `0` to `2`.",
            ),
        ),
    ),
    Case(
        "teach-preference-from-now-on",
        "teaching",
        "From now on, always give me a practical example before the theory.",
        Expect(hints=("standing_preference",), no_hints=("answer_photo",), search="no"),
        "Agrees in a sentence and says examples will come first.",
    ),
    Case(
        "teach-preference-learner",
        "teaching",
        "I learn best when you quiz me after each step.",
        Expect(
            hints=("standing_preference",),
            no_hints=("answer_photo", "personal_disclosure"),
            search="no",
        ),
        "Agrees, restates it (a quick question after each step), asks what to learn first.",
    ),
    Case(
        "teach-preference-hints",
        "teaching",
        "Don't give me the answer, give me hints.",
        Expect(hints=("standing_preference",), no_hints=("answer_photo",), search="no"),
        "Agrees to hint first and asks what they are working on.",
    ),
    Case(
        "teach-preference-teach-by",
        "teaching",
        "Please teach me by asking questions instead of lecturing.",
        Expect(hints=("standing_preference",), no_hints=("teaching", "answer_photo")),
        "Agrees to teach through questions and asks what to learn first; no lesson yet.",
    ),
    Case(
        "teach-preference-not-yesterday",
        "teaching",
        "When teaching me yesterday you used a great example with lists, can you show it again?",
        Expect(no_hints=("standing_preference",)),
        "Recalls or rebuilds the list example; not a new preference.",
    ),
    Case(
        "teach-preference-not-reminder",
        "teaching",
        "always remind me to drink water",
        Expect(no_hints=("standing_preference",)),
        "A reminder (or a question for when), not a teaching preference.",
    ),
    # ── Format ──────────────────────────────────────────────────────────────
    Case(
        "format-compare",
        "format",
        "compare python and javascript",
        Expect(hints=("comparison",), search="ask"),
        "A short comparison table, then when to pick each.",
    ),
    Case(
        "format-numbers-only",
        "format",
        "Monthly rainfall in Addis Ababa: Jan 15, Feb 30, Mar 60, Apr 85, May 80, Jun 135, "
        "Jul 280, Aug 290, Sep 190, Oct 30, Nov 6, Dec 5 mm",
        Expect(hints=("shared_numbers",), lightweight=False),
        "One or two sentences on the numbers (wettest August at 290 mm, driest December at "
        "5 mm), then an offer such as a chart. Never a greeting or 'How's it going?'.",
    ),
    Case(
        "format-what-after-spanish",
        "format",
        "What?",
        Expect(hints=("reply_missed",), no_hints=("lightweight",)),
        "The photosynthesis answer again, simpler and in English: never 'Gd: good, or "
        "something else?' or a question about what they meant.",
        history=(
            ("user", "Explícame la fotosíntesis en dos frases"),
            (
                "assistant",
                "La fotosíntesis es el proceso por el cual las plantas convierten la luz.",
            ),
        ),
    ),
    Case(
        "format-tips",
        "format",
        "give me 5 tips to sleep better",
        Expect(search="no"),
        "Exactly five short, scannable tips.",
    ),
    Case(
        "format-json-planets",
        "format",
        "give me the list of the planets as valid JSON",
        Expect(search="ask", hints=("json_output",), model="qwen-3.7-flash"),
        "One ```json fence holding a valid array of the eight planets, at most a line "
        "around it; the server checks that it parses.",
    ),
    Case(
        "format-checklist",
        "format",
        "give me a packing checklist for a 3-day hiking trip, grouped by category",
        Expect(hints=("checklist",), no_hints=("howto", "steps")),
        "`###` category headings over `- [ ]` task lines, which the phone draws as checkboxes.",
    ),
    Case(
        "format-checklist-app",
        "format",
        "write a checklist component in React",
        Expect(no_hints=("checklist",)),
        "Code for a component, not a Markdown checklist.",
    ),
    Case(
        "format-howto",
        "format",
        "how do I make tea",
        Expect(hints=("steps",), search="no"),
        "Numbered steps.",
    ),
    Case(
        "format-howto-walkthrough",
        "format",
        "walk me through changing a flat tire",
        Expect(hints=("steps",), no_hints=("howto", "teaching")),
        "Numbered steps in order, the safety step before the jack; no week or phase headings.",
    ),
    Case(
        "format-howto-feeling",
        "format",
        "how do I know if I'm ready to change jobs",
        Expect(no_hints=("steps",), search="no"),
        "Honest signs to weigh, not a numbered procedure.",
    ),
    Case(
        "format-email",
        "format",
        "write an email to my landlord about a broken heater",
        Expect(hints=("email",), search="no"),
        "An email draft card with a subject, signed with the user's name.",
    ),
    Case(
        "format-text-landlord",
        "format",
        "text my landlord that the heater is broken",
        Expect(hints=("email",), no_hints=("ask_purpose", "no_draft"), search="no"),
        "A message card saying the heater is broken and asking for a repair; no question "
        "about what it should say.",
    ),
    Case(
        "format-send-boss-email",
        "format",
        "send my boss an email asking for Friday off",
        Expect(hints=("email",), no_hints=("ask_purpose", "no_draft")),
        "An email card asking for Friday off, signed with the user's name; never 'I can't "
        "send emails'.",
    ),
    Case(
        "format-email-what-to-say",
        "format",
        "the heater stopped working and the kitchen tap is leaking",
        Expect(hints=("draft_now",), no_hints=("no_draft", "answer_photo"), memory=True),
        "The message card the user was asked about, saying both problems.",
        history=(
            ("user", "write a message to my landlord"),
            ("assistant", "Sure, what should the message say?"),
        ),
    ),
    Case(
        "format-email-translate",
        "format",
        "translate to Spanish",
        Expect(hints=("draft_revision",), no_hints=("no_draft",)),
        "The same email card, in Spanish (Asunto:), every name and date kept.",
        history=(
            ("user", "write an email to my boss asking for Friday off"),
            (
                "assistant",
                "```email\nSubject: Friday off\n\nHi Sara,\n\nCould I take this Friday "
                "off for a family event?\n\nThanks,\nBini\n```",
            ),
        ),
    ),
    Case(
        "format-resume",
        "format",
        "write my resume",
        Expect(
            hints=("personal_record",),
            no_hints=("no_draft", "format_contract", "answer_photo", "clarify"),
            memory=True,
            memory_scope="profile",
        ),
        "A résumé from what memory holds (job, skills, education), asking once for what is "
        "missing; never an invented employer, degree or number.",
    ),
    Case(
        "format-cover-letter",
        "format",
        "write a cover letter for a junior data analyst job at a hospital",
        Expect(hints=("personal_record",), memory=True, memory_scope="profile"),
        "A cover letter from the user's saved background; asks once for experience when "
        "memory has none, never invents it.",
    ),
    Case(
        "format-social",
        "format",
        "write a tweet about my new app",
        Expect(search="no"),
        "Asks what the app is, or one tweet-length draft; no invented stats.",
    ),
    Case(
        "format-brief",
        "format",
        "summarize the french revolution in 3 sentences",
        Expect(hints=("brevity",), subject=NONE, search="no"),
        "Exactly three sentences.",
    ),
    Case(
        "format-chart",
        "format",
        "make a bar chart of the population of the 5 largest countries",
        Expect(hints=("chart",)),
        "A bar chart of the five, with the year of the figures.",
    ),
    Case(
        "format-scatter-fit",
        "format",
        "Plot this experiment as a scatter plot with a best-fit line: "
        "x = 1,2,3,4,5 and y = 2.1,3.9,6.2,7.8,10.1",
        Expect(hints=("chart",), subject=NONE, image_gen=False),
        "A scatter chart of the five points with a regression-line layer.",
    ),
    Case(
        "format-histogram",
        "format",
        "Make a histogram of these test scores: 55, 62, 68, 70, 71, 75, 78, 80, 82, 85, 88, 90, 95",
        Expect(hints=("chart",), subject=NONE),
        "A histogram: the raw scores binned on x, counts on y.",
    ),
    # A chart asked for in other words (2026-10-24: 15 of 30 live chart requests got no
    # chart, a made-up chart format, or maths asking which function to graph). The user's
    # own data forces no search ("ask": the reply may still look something up).
    Case(
        "chart-income-in-graph-followup",
        "format",
        "Show me the income in graph month by month",
        Expect(hints=("chart",), subject=NONE, search="ask"),
        "A bar chart of $12,500 for each of the twelve months.",
        history=(
            ("user", "I earn $150k a year, what's my hourly pay?"),
            ("assistant", "About **$72.12** an hour, at 40 hours a week for 52 weeks."),
        ),
    ),
    Case(
        "chart-graph-it-after-marks",
        "format",
        "graph it",
        Expect(hints=("chart",), subject=NONE, search="ask"),
        "A bar chart of the four marks, not a question about which function to graph.",
        history=(
            ("user", "Here are my exam marks: math 85, physics 78, chemistry 92, biology 88"),
            ("assistant", "Nice marks! Chemistry is your strongest subject."),
        ),
    ),
    Case(
        "chart-plot-my-scores",
        "format",
        "plot my test scores 72, 85, 90, 68, 95",
        Expect(hints=("chart",), subject=NONE, search="ask"),
        "A line or bar chart of the five scores in order.",
    ),
    Case(
        "chart-visualize-sales",
        "format",
        "can you visualize my sales: Q1 10k, Q2 15k, Q3 12k, Q4 20k",
        Expect(hints=("chart",), subject=NONE, search="no"),
        "A bar chart of the four quarters.",
    ),
    Case(
        "chart-show-in-a-graph",
        "format",
        "show this in a graph: Mon 5h, Tue 7h, Wed 6h, Thu 8h, Fri 4h of sleep",
        Expect(hints=("chart",), subject=NONE, search="ask"),
        "A chart of the five nights of sleep.",
    ),
    Case(
        "chart-scatter-of-points",
        "format",
        "scatter plot of hours studied vs score: (1, 50), (2, 55), (3, 65), (4, 70), (5, 85)",
        Expect(hints=("chart",), subject=NONE),
        "A scatter chart of the five points, not an answer card listing them back.",
    ),
    Case(
        "chart-population-searches",
        "format",
        "graph the population of Ethiopia over the last 10 years",
        Expect(hints=("chart",), subject=NONE, search="yes"),
        "A line chart of the yearly figures a search found, with its source.",
    ),
    Case(
        "chart-prices-search",
        "format",
        "compare iPhone 18 Pro and Pixel 11 prices in a chart",
        Expect(hints=("chart",), subject=NONE, search="yes"),
        "A bar chart of the two prices a search found.",
    ),
    Case(
        "format-box-plot",
        "format",
        "Make a box plot of these test scores: 55, 62, 68, 70, 71, 75, 78, 80, 82, 85, 88, 90, 95",
        Expect(hints=("chart",), subject=NONE),
        "A box plot from the raw scores; the app computes the quartiles.",
    ),
    Case(
        "format-line-graph-data",
        "format",
        "make a line graph of my monthly sales: jan 10, feb 12, mar 9, apr 15",
        Expect(hints=("chart",), subject=NONE),
        "A line chart of the four months in order.",
    ),
    Case(
        "format-flowchart",
        "format",
        "draw a flowchart of how a bill becomes law in the US",
        Expect(hints=("mermaid",), image_gen=False, photo=NO_PHOTO),
        "A flowchart diagram, not a generated picture.",
    ),
    Case(
        "format-decision-tree",
        "format",
        "Draw a decision tree for choosing a first programming language",
        Expect(hints=("diagram",), no_hints=("chart",), image_gen=False, photo=NO_PHOTO),
        "A Mermaid flowchart; an AI picture of a tree garbles every label.",
    ),
    Case(
        "format-state-machine",
        "format",
        "Draw a state machine for a traffic light",
        Expect(hints=("diagram",), image_gen=False, photo=NO_PHOTO),
        "A Mermaid stateDiagram-v2, not a picture of a machine.",
    ),
    Case(
        "format-mind-map",
        "format",
        "Make a mind map of renewable energy sources",
        Expect(hints=("diagram",), image_gen=False, photo=NO_PHOTO),
        "A Mermaid mindmap, not a picture of a map.",
    ),
    Case(
        "format-org-chart",
        "format",
        "Draw an org chart for a small startup: CEO, CTO, two engineers and a designer",
        Expect(hints=("diagram",), no_hints=("chart",), image_gen=False, photo=NO_PHOTO),
        "An org chart is a Mermaid diagram of people, not a numeric Vega chart.",
    ),
    Case(
        "format-quiz",
        "format",
        "Quiz me on the planets of the solar system",
        Expect(hints=("quiz",), image_gen=False, photo=NO_PHOTO),
        "One ```quiz card per question; the answers stay hidden until checked.",
    ),
    Case(
        "format-flashcards",
        "format",
        "Make flashcards for 5 common Spanish verbs",
        Expect(hints=("quiz",), image_gen=False, photo=NO_PHOTO),
        "Flashcards are ```quiz cards with no options: the back behind Show answer.",
    ),
    Case(
        "format-true-false",
        "format",
        "Give me 5 true/false questions about World War II",
        Expect(hints=("quiz",), no_hints=("comparison",)),
        "True/false questions are ```quiz cards with True and False as the options.",
    ),
    Case(
        "format-quiz-mentioned",
        "format",
        "I have a quiz tomorrow on cell biology, can you explain mitosis?",
        Expect(no_hints=("quiz",)),
        "A quiz they mention is not one they asked for.",
    ),
    Case(
        "clarify-vague-ask",
        "format",
        "What is the best country",
        Expect(hints=("clarify",), image_gen=False),
        "The strongest few countries, one bold line each with a short why, then a bold "
        "'But let me ask you one thing.', what 'best' means to them, and a tap card (main "
        "priority, region) with a 'Find my best country' button; never questions in prose.",
    ),
    Case(
        "clarify-vague-study",
        "format",
        "how can I understand integrals",
        Expect(hints=("clarify",), image_gen=False),
        "May ask with a tap card (level, goal) after a short start; never a list of questions "
        "in prose.",
    ),
    Case(
        "clarify-not-on-a-problem",
        "format",
        "solve 2x + 5 = 17",
        Expect(no_hints=("clarify",)),
        "A problem is solved, never answered with questions.",
    ),
    Case(
        "clarify-not-on-a-greeting",
        "format",
        "good morning!",
        Expect(no_hints=("clarify",)),
        "A greeting is answered in kind.",
    ),
    Case(
        "clarify-not-in-a-lesson",
        "format",
        "teach me python",
        Expect(no_hints=("clarify",)),
        "A lesson has its own outline and question.",
    ),
    Case(
        "clarify-picks-answer-the-card",
        "format",
        "Recommend the best country for me. Main priority: Making money. Geographic "
        "preference: Anywhere. Compare the strongest options with practical pros and cons.",
        # No card rule to ask again with, and the card's "compare" closing leads no table.
        Expect(
            hints=("clarify_picks",),
            no_hints=("clarify_unanswered", "clarify", "comparison"),
            lightweight=False,
        ),
        "Opens with the one country that fits best for making money and why (using memory when "
        "it fits), then the top options ranked, each with what it is best for, pros and cons; "
        "no new card.",
        history=_BEST_COUNTRY,
    ),
    Case(
        "clarify-picks-from-an-older-phone",
        "format",
        "Studied it before: No, never",
        Expect(
            hints=("clarify_picks",), no_hints=("clarify_unanswered", "clarify"), lightweight=False
        ),
        "The whole answer to how to understand integrals, pitched at a beginner; no new card.",
        history=(
            ("user", "how can I understand integrals"),
            (
                "assistant",
                'Two quick questions:\n\n```clarify\n{"when":"first","questions":[{"id":"level","label":"Studied it before","question":"Have you studied integrals before?","options":["No, never","A little","Yes, I\'m revising"],"multi":false}]}\n```',
            ),
        ),
    ),
    Case(
        "clarify-picks-plan-my-week",
        "format",
        "Primary focus: Finish my thesis",
        Expect(hints=("clarify_picks",), no_hints=("clarify", "clarify_unanswered")),
        "The week's plan built around the thesis now; never a second card or more questions.",
        history=(
            ("user", "plan my week"),
            (
                "assistant",
                'To build a plan that fits, one quick question:\n\n```clarify\n{"when":"first","questions":[{"id":"focus","label":"Primary focus","question":"What is the main goal for your week?","options":["Work projects","Study or exams","Health and fitness","Rest"],"multi":false}]}\n```',
            ),
        ),
    ),
    Case(
        "clarify-skip",
        "format",
        "Just answer",
        Expect(hints=("clarify_unanswered",), lightweight=False),
        "A general answer to which country is best, with the strongest options; no new card.",
        history=_BEST_COUNTRY,
    ),
    Case(
        "format-in-detail",
        "format",
        "explain in detail how Raft handles split votes and network partitions",
        Expect(hints=("detail",), no_hints=("fit_length",), search="ask"),
        "A thorough answer: randomized election timeouts and terms for split votes, what a "
        "minority partition can and cannot commit, and a short example timeline.",
    ),
    Case(
        "format-mixed-length",
        "format",
        "in one sentence what is DNS? Also explain in detail how a TLS handshake works",
        # Two requests: the cap binds request 1 only, and each part keeps its own length.
        Expect(hints=("mixed_length", "multi_intent", "part1_brevity")),
        "DNS in exactly one sentence, then a detailed walk through the TLS handshake.",
    ),
    Case(
        "format-continue-story",
        "format",
        "continue",
        Expect(hints=("continue",), no_hints=("answer_photo",), photo=NO_PHOTO),
        'Picks up mid-sentence where the story stopped ("…and Ember"), with no recap and no '
        "fresh start.",
        history=_STORY,
    ),
    # ── Code ────────────────────────────────────────────────────────────────
    Case(
        "code-function",
        "code",
        "write a python function to reverse a string",
        # The free plan has no smart tier: its strongest model takes the coding ask.
        Expect(search="no", photo=NO_PHOTO, model="glm-5.3-flash"),
        "A short tagged python block and one line on how it works.",
    ),
    Case(
        "code-function-pro",
        "code",
        "write a python function to reverse a string",
        Expect(search="no", photo=NO_PHOTO, model="smart-chat"),
        "A short tagged python block and one line on how it works.",
        pro=True,
    ),
    Case(
        "code-review-no-fence",
        "code",
        "can you review my function that reverses a linked list, it keeps looping forever",
        Expect(search="no", photo=NO_PHOTO, model="smart-chat"),
        "Names the likely cause (the next pointer never advances, or the list has a cycle), "
        "shows the fixed loop in a python fence and asks for the code if it needs it.",
        pro=True,
    ),
    Case(
        "code-hard-migration-plan",
        "code",
        "plan a zero-downtime migration of a monolith Postgres schema to sharded tables",
        Expect(photo=NO_PHOTO, model="smart-chat"),
        "A phased plan: dual writes or logical replication, a backfill, verification, the "
        "cut-over and a rollback path, with the trade-offs of the shard key.",
        pro=True,
    ),
    Case(
        "code-json-duplicates",
        "code",
        'find the duplicate ids: [{"id": 7, "name": "Ana"}, {"id": 9, "name": "Ben"}, '
        '{"id": 7, "name": "Cy"}, {"id": 12, "name": "Di"}, {"id": 9, "name": "Ed"}]',
        Expect(photo=NO_PHOTO, model="smart-chat"),
        "Ids 7 and 9, each with the names that share it.",
        pro=True,
    ),
    Case(
        "code-html",
        "code",
        "make a simple calculator in html",
        Expect(search="no"),
        "One html block that runs in the preview.",
    ),
    Case(
        "code-run",
        "code",
        "run this python code: print(1+1)",
        Expect(search="no", hints=("code_run",), no_hints=("answer_photo",)),
        "Says Recall can't run Python, and that it would print 2.",
    ),
    Case(
        "code-explain-trace",
        "code",
        "Explain this code line by line, then show the value of total after each iteration:\n"
        "total = 0\nfor n in [2, 4, 6]:\n    total += n\nprint(total)",
        Expect(
            hints=("code_explain", "code_ink"),
            no_hints=("answer_photo", "walkthrough", "teaching"),
            subject=NONE,
            search="no",
            photo=NO_PHOTO,
        ),
        "One lead sentence; ### 1. The code in a python fence; ### 2. Explain each line with "
        "**Line N:** `line` and short bullets; ### 3. a steps card or table of total per "
        "iteration (2, 6, 12); **Output:** 12. Every value in backticks, no $ signs.",
    ),
    Case(
        "code-explain-one-line",
        "code",
        "Explain this code line by line, then show the value of total after each iteration: "
        "total = 0 for n in [2, 4, 6]: total += n print(total)",
        Expect(hints=("code_explain",), no_hints=("answer_photo",), subject=NONE, search="no"),
        "Same shape; the code fence puts the pasted line back on four indented lines.",
    ),
    Case(
        "code-explain-java",
        "code",
        "What does this Java code print? int sum = 0; for (int i = 1; i <= 3; i++) "
        "{ sum += i; } System.out.println(sum);",
        Expect(hints=("code_explain",), no_hints=("answer_photo",), subject=NONE, search="no"),
        "The code in a java fence, each line explained, sum after each pass (1, 3, 6), "
        "**Output:** 6.",
    ),
    Case(
        "code-explain-js",
        "code",
        "Walk me through this JavaScript: const nums = [1, 2, 3]; "
        "const doubled = nums.map(n => n * 2); console.log(doubled);",
        Expect(
            hints=("code_explain",),
            no_hints=("answer_photo", "walkthrough"),
            subject=NONE,
            search="no",
        ),
        "A javascript fence, each line explained (map makes a new array), **Output:** [2, 4, 6].",
    ),
    Case(
        "code-debug-index",
        "code",
        "Why does this code fail, and how would you fix it? numbers = [1, 2, 3] print(numbers[3])",
        Expect(
            hints=("code_debug", "code_ink"),
            no_hints=("answer_photo", "code_explain"),
            subject=NONE,
            search="no",
        ),
        "IndexError on line 2; ### Why it fails (indexes 0 to 2); ### The fix with "
        "numbers[2] or numbers[-1] in a python fence; **Output:** 3.",
    ),
    Case(
        "code-debug-traceback",
        "code",
        "I get this error, what's wrong?\nTraceback (most recent call last):\n"
        '  File "app.py", line 3, in <module>\n    print(user["name"])\nKeyError: \'name\'',
        Expect(hints=("code_debug",), no_hints=("answer_photo",), search="no"),
        "KeyError: the dict has no 'name' key; why; the fix with user.get('name').",
    ),
    Case(
        "code-debug-js-undefined",
        "code",
        "why does this return undefined? function add(a, b) { a + b } console.log(add(2, 3))",
        Expect(hints=("code_debug",), no_hints=("answer_photo",), subject=NONE, search="no"),
        "The function has no return; the fix adds return a + b; **Output:** 5.",
    ),
    Case(
        "code-fix-that",
        "code",
        "fix that",
        Expect(no_hints=("answer_photo",), search="ask", photo=NO_PHOTO),
        "The fixed average() in one python fence that handles an empty list (returns 0 or "
        "raises a clear ValueError), and one line on the change.",
        history=_AVERAGE_CODE,
    ),
    Case(
        "code-correction-python-2",
        "code",
        "actually I meant Python 2, not 3",
        Expect(hints=("correction",), search="no"),
        'print "hello" as a Python 2 statement, a few words of acknowledgement at most, and '
        "nothing about Python 3 again.",
        history=(
            ("user", "how do I print hello in python"),
            ("assistant", '```python\nprint("hello")\n```'),
        ),
    ),
    Case(
        "code-not-pasted",
        "code",
        "explain the code of conduct",
        Expect(no_hints=("code_explain", "code_debug")),
        "What a code of conduct is; no code layout.",
    ),
    # ── Tone and emoji ──────────────────────────────────────────────────────
    Case(
        "tone-hi",
        "tone and emoji",
        "hi",
        Expect(lightweight=True, search="no", photo=NO_PHOTO, model="qwen-3.7-flash"),
        "A short greeting back.",
    ),
    Case(
        "tone-emoji-greeting",
        "tone and emoji",
        "hi 👋",
        Expect(lightweight=True, search="no"),
        "A short greeting back, as fast as a plain 'hi'.",
    ),
    Case(
        "tone-emoji-mirror",
        "tone and emoji",
        "hey! 😊 how are you?",
        Expect(search="no", photo=NO_PHOTO),
        "A short friendly reply; an emoji back is fine since the user used one.",
    ),
    Case(
        "tone-plain",
        "tone and emoji",
        "what are the benefits of drinking water",
        Expect(hints=("emoji_rule",), search="ask", model="qwen-3.7-flash"),
        "A clear answer; at most a fitting emoji beside a heading or a list label.",
    ),
    Case(
        "tone-birthday",
        "tone and emoji",
        "write a birthday message for my mom",
        Expect(search="no"),
        "A warm message card; an emoji or two is fine in a personal message.",
    ),
    Case(
        "tone-hi-again",
        "tone and emoji",
        "Hi",
        Expect(lightweight=True, hints=("greeting_again",), no_hints=("lightweight",), search="no"),
        'Notices the second hi in one light line ("Hi again! What\'s up?"), not a fresh greeting.',
        history=(("user", "Hi"), ("assistant", "Hey bini! How's your Friday evening going?")),
    ),
    Case(
        "tone-thanks",
        "tone and emoji",
        "thanks!",
        Expect(lightweight=True, search="no"),
        "A one-line welcome.",
    ),
    Case(
        "tone-good-morning",
        "tone and emoji",
        "good morning!",
        Expect(
            hints=("compact",),
            no_hints=("answer_photo", "format_contract"),
            search="no",
            photo=NO_PHOTO,
        ),
        "A short good morning back; no essay, no photo, no list of things it can do.",
    ),
    Case(
        "tone-hello-there",
        "tone and emoji",
        "hello there",
        Expect(hints=("compact",), no_hints=("answer_photo", "format_contract"), search="no"),
        "A short hello back.",
    ),
    Case(
        "tone-how-are-you",
        "tone and emoji",
        "how are you?",
        Expect(hints=("compact",), no_hints=("answer_photo", "format_contract"), search="no"),
        "One or two friendly sentences, maybe asking what's up.",
    ),
    Case(
        "tone-greeting-then-question",
        "tone and emoji",
        "good morning, what's the capital of Peru?",
        Expect(hints=("format_contract",), no_hints=("compact",)),
        "Lima, after at most a word of good morning.",
    ),
    # ── Personal ────────────────────────────────────────────────────────────
    Case(
        "personal-name",
        "personal",
        "what's my name",
        Expect(search="no", photo=NO_PHOTO),
        "Bini.",
    ),
    Case(
        "personal-reminder",
        "personal",
        "remind me to call mom tomorrow at 5pm",
        Expect(search="no"),
        "Confirms a reminder for tomorrow 5 pm.",
    ),
    Case(
        "personal-reminder-clock-no-day",
        "personal",
        "remind me to plate the dinner at 7pm",
        Expect(search="no", photo=NO_PHOTO, image_gen=False, subject=NONE),
        "A reminder card for 7 pm today (the next 7 pm) to tap; never 'I didn't change your "
        "reminders'. The sweep checks the card (sweep_corpus/routing_gaps.json).",
        pro=True,
    ),
    Case(
        "personal-food-recommendation",
        "personal",
        "what should I cook tonight?",
        Expect(hints=("advice",), subject=NONE),
        "A couple of dinner ideas shaped by what it knows the user likes.",
    ),
    Case(
        "personal-correction-vegetarian",
        "personal",
        "no, I said I'm vegetarian",
        Expect(hints=("correction",), search="no"),
        "Vegetarian dinner ideas, no meat or fish, without a long apology.",
        history=(
            ("user", "I'm vegetarian. what should I cook tonight?"),
            ("assistant", "How about **lemon garlic chicken** or a quick **beef stir-fry**?"),
        ),
    ),
    Case(
        "personal-thanks-is-not-a-correction",
        "personal",
        "no, I said it was fine — thanks",
        Expect(no_hints=("correction",), search="no"),
        "A short you're welcome; nothing rewritten.",
        history=(
            ("user", "here's my cover letter intro, is it ok?"),
            ("assistant", "It reads well. Want me to tighten the second sentence?"),
        ),
    ),
    Case(
        "personal-capabilities",
        "personal",
        "what can you do",
        Expect(hints=("capabilities",), search="no"),
        "A short list, including web search, photos, reminders and read-aloud.",
    ),
    # ── Multi-intent ────────────────────────────────────────────────────────
    # One message, several requests: every one answered in one reply, each with its
    # own tool, and related questions kept together (turn_prep/intents.py).
    Case(
        "multi-laptop-jobs",
        "multi-intent",
        "I need a new laptop, and I also want to find remote backend engineering jobs",
        Expect(hints=("multi_intent",), search="yes"),
        "One reply, two ### sections: 2-3 laptop picks with the budget or use it assumed, "
        "then remote backend roles from the search results, with links.",
    ),
    Case(
        "multi-two-questions",
        "multi-intent",
        "what's the capital of Australia? and how do I boil an egg?",
        Expect(hints=("multi_intent", "steps")),
        "### Capital of Australia: Canberra, one line. ### Boiling an egg: numbered steps.",
    ),
    Case(
        "multi-weather-and-solve",
        "multi-intent",
        "what's the weather in Paris tomorrow and also solve 2x + 5 = 17",
        Expect(subject="math", solved=True, search="yes", hints=("multi_intent",)),
        "Tomorrow's Paris forecast from the results, and x = 6 from the verified solve.",
    ),
    Case(
        "multi-solve-then-weather",
        "multi-intent",
        "solve 2x + 5 = 17 and also what's the weather in Paris tomorrow",
        Expect(subject="math", solved=True, search="yes", hints=("multi_intent",)),
        "x = 6 (verified), then tomorrow's Paris forecast from the results.",
    ),
    Case(
        "multi-teach-and-price",
        "multi-intent",
        "teach me python dictionaries, and what is the current price of bitcoin?",
        Expect(search="yes", hints=("multi_intent", "teaching")),
        "A short lesson opener on dictionaries, then today's bitcoin price from the results.",
    ),
    Case(
        "multi-code-and-score",
        "multi-intent",
        "write a function to reverse a list, and who won the champions league final last night",
        Expect(search="yes", hints=("multi_intent",)),
        "A short python function, then last night's final result from the results.",
    ),
    Case(
        "multi-reminder-and-weather",
        "multi-intent",
        "remind me to buy milk at 5pm and what's the weather in Nairobi today?",
        Expect(search="yes", hints=("multi_intent",)),
        "A reminder card for 5 pm to tap, and today's Nairobi weather from the results.",
    ),
    Case(
        "multi-settings-and-joke",
        "multi-intent",
        "switch to dark mode and tell me a joke",
        Expect(settings_card=True, instant="", hints=("multi_intent",)),
        "A joke, and the dark-mode card under it to tap.",
    ),
    Case(
        "multi-settings-and-question",
        "multi-intent",
        "switch to dark mode, and also what is the capital of France?",
        Expect(settings_card=True, instant="", hints=("multi_intent",)),
        "Paris, and the dark-mode card under it to tap.",
    ),
    Case(
        "multi-draw-and-explain",
        "multi-intent",
        "draw a cat wearing a hat and also explain what a black hole is",
        Expect(image_gen=False, picture=True, hints=("multi_intent",)),
        "The cat picture above a short black-hole explanation, or one line saying why "
        "the picture could not be drawn.",
        pro=True,
    ),
    Case(
        "multi-draw-me-and-explain",
        "multi-intent",
        "draw me a cat and also explain black holes",
        Expect(image_gen=False, picture=True, hints=("multi_intent",)),
        "The cat above a short black-hole explanation; the whole line was drawn as one "
        "picture of 'cat and also explain black holes' before.",
        pro=True,
    ),
    Case(
        "multi-draw-me-and-suggest",
        "multi-intent",
        "Draw me a dog and suggest names",
        Expect(image_gen=False, picture=True, hints=("multi_intent",)),
        "The dog above a few name ideas; the whole line was drawn as one picture of 'dog "
        "and suggest names' before, though the plan cut it (round 7).",
        pro=True,
    ),
    Case(
        "multi-explain-and-draw-es",
        "multi-intent",
        "Explica qué es un agujero negro y dibuja un gato",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-explain-and-draw-de",
        "multi-intent",
        "Erkläre, was ein schwarzes Loch ist, und zeichne auch eine Katze",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-explain-and-draw-ru",
        "multi-intent",
        "Объясни, что такое чёрная дыра, и нарисуй кошку",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-draw-and-explain-es",
        "multi-intent",
        "Dibuja un gato con sombrero y también explica qué es un agujero negro",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-draw-and-explain-de",
        "multi-intent",
        "Zeichne eine Katze mit Hut und erkläre auch, was ein schwarzes Loch ist",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-draw-and-explain-ru",
        "multi-intent",
        "Нарисуй кошку в шляпе, а также объясни, что такое чёрная дыра",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-draw-and-explain-tr",
        "multi-intent",
        "Şapkalı bir kedi çiz ve ayrıca kara deliğin ne olduğunu açıkla",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-draw-and-explain-fr",
        "multi-intent",
        "Dessine un chat avec un chapeau et explique aussi ce qu'est un trou noir",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-draw-and-explain-it",
        "multi-intent",
        "Disegna un gatto con il cappello e spiega anche cos'è un buco nero",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-draw-and-explain-pt",
        "multi-intent",
        "Desenhe um gato com chapéu e também explique o que é um buraco negro",
        Expect(image_gen=False, picture=False),
        "One answer, no picture: the picture clause is a bare draw verb, no draw-me form "
        "(round 5).",
        pro=True,
    ),
    Case(
        "multi-draw-and-explain-am",
        "multi-intent",
        "ድመት ሳልልኝ እንዲሁም ጥቁር ቀዳዳ ምን እንደሆነ አስረዳኝ",
        Expect(image_gen=False, picture=False, no_hints=("multi_intent",)),
        "One answer in the message's language, no picture: no other-language message is "
        "cut into a picture and a request (round 9).",
        pro=True,
    ),
    Case(
        "multi-draw-me-and-explain-es",
        "multi-intent",
        "Dibújame un gato con sombrero y también explica qué es un agujero negro",
        Expect(image_gen=False, picture=False, no_hints=("multi_intent",)),
        "One answer in the message's language, no picture: no other-language message is "
        "cut into a picture and a request (round 9).",
        pro=True,
    ),
    Case(
        "multi-draw-me-and-explain-de",
        "multi-intent",
        "Zeichne mir eine Katze mit Hut und erkläre auch, was ein schwarzes Loch ist",
        Expect(image_gen=False, picture=False, no_hints=("multi_intent",)),
        "One answer in the message's language, no picture: no other-language message is "
        "cut into a picture and a request (round 9).",
        pro=True,
    ),
    Case(
        "multi-explain-and-draw-me-ru",
        "multi-intent",
        "Объясни, что такое чёрная дыра, и нарисуй мне кошку",
        Expect(image_gen=False, picture=False, no_hints=("multi_intent",)),
        "One answer in the message's language, no picture: no other-language message is "
        "cut into a picture and a request (round 9).",
        pro=True,
    ),
    Case(
        "multi-question-then-draw-me-fr",
        "multi-intent",
        "Quelle est la capitale de l'Italie ? Dessine-moi un chat",
        Expect(image_gen=False, picture=False, no_hints=("multi_intent",)),
        "One answer in the message's language, no picture: no other-language message is "
        "cut into a picture and a request (round 9).",
        pro=True,
    ),
    Case(
        "multi-translate-draw-me-line-es",
        "multi-intent",
        "Traduce al inglés: dibújame un gato",
        Expect(image_gen=False, picture=False, photo=NO_PHOTO),
        "The draw-me line is the text to translate: answered, no picture, as English "
        "'Translate to Spanish: draw me a cat' is (round 8).",
        pro=True,
    ),
    Case(
        "multi-quoted-draw-me-line-de",
        "multi-intent",
        "„Zeichne mir ein Schaf“: Wer hat das gesagt?",
        Expect(image_gen=False, picture=False, photo=NO_PHOTO),
        "Who said a quoted draw-me line: answered, no picture (round 8).",
        pro=True,
    ),
    Case(
        "multi-dropped-it-draw-me-line-es",
        "multi-intent",
        "Dime si es educado. Dibújame un gato",
        Expect(image_gen=False, picture=False, photo=NO_PHOTO),
        "Whether the draw-me line is polite, 'it' dropped: answered, no picture (review 8).",
        pro=True,
    ),
    Case(
        "multi-english-about-draw-me-line-es",
        "multi-intent",
        "Dibújame un gato. Why is the me at the end?",
        Expect(image_gen=False, picture=False, photo=NO_PHOTO),
        "An English question about a Spanish draw-me line: answered, no picture (review 8).",
        pro=True,
    ),
    Case(
        "multi-compare-and-install",
        "multi-intent",
        "compare python and javascript, and how do I install node on mac?",
        Expect(hints=("multi_intent", "comparison", "steps"), no_hints=("howto",)),
        "### A python/javascript compare table, then ### numbered install steps.",
    ),
    Case(
        "multi-brief-and-detail",
        "multi-intent",
        "in one sentence what is DNS? Also explain in detail how TLS handshakes work",
        Expect(hints=("multi_intent", "part1_brevity", "mixed_length")),
        "One sentence on DNS, then a full TLS handshake walk-through.",
    ),
    Case(
        "multi-lookalike-tcp-udp",
        "multi-intent",
        "difference between TCP and UDP and when to use each",
        Expect(no_hints=("multi_intent",)),
        "One answer: a compare table and when to use each, no sections per clause.",
    ),
    Case(
        "multi-lookalike-solve-and-graph",
        "multi-intent",
        "solve 2x+5=17 and graph it",
        Expect(subject="math", no_hints=("multi_intent",)),
        "x = 6 with the line drawn, one answer.",
    ),
    Case(
        "multi-lookalike-which-is-faster",
        "multi-intent",
        "compare python and javascript and tell me which is faster",
        Expect(hints=("comparison",), no_hints=("multi_intent",)),
        "One compare table that ends with which is faster.",
    ),
    Case(
        "search-remote-jobs",
        "web search",
        "find remote backend engineering jobs",
        Expect(search="yes"),
        "Current remote backend openings from the results, each with a link.",
    ),
    Case(
        "search-jobs-today",
        "web search",
        "find software jobs posted today",
        Expect(search="yes"),
        "Today's software postings from the results, with links.",
    ),
    Case(
        "search-product-price",
        "web search",
        "how much does the iPhone 17 Pro cost?",
        Expect(search="yes"),
        "The current price from the results, with the storage tier it is for.",
    ),
    Case(
        "search-job-lookalike",
        "web search",
        "I got the job!",
        Expect(search="no"),
        "Congratulations, one or two warm lines.",
    ),
    # ── Memory: what a turn reads, and what it says when memory can't help ──
    Case(
        "personal-stack-carries",
        "personal",
        "How should I structure auth in my app?",
        Expect(memory=True, memory_scope="work"),
        "With 'User builds Recall with React Native and FastAPI' saved: tokens in Expo "
        "SecureStore on the phone, FastAPI JWT on the server, without asking the stack. "
        "Never the user's city or job.",
    ),
    Case(
        "personal-stack-deploy",
        "personal",
        "How should I deploy my backend?",
        Expect(memory=True, memory_scope="work"),
        "Deploy steps for the saved backend (FastAPI), not a survey of every framework.",
    ),
    Case(
        "personal-stack-library",
        "personal",
        "Which state management library should I use?",
        Expect(memory=True, memory_scope="work"),
        "A pick for the saved stack (React Native: Zustand or Redux Toolkit), with why.",
    ),
    Case(
        "personal-stack-login-screen",
        "personal",
        "Write a login screen for me",
        Expect(memory=True, memory_scope="work"),
        "A React Native login screen when that is the saved stack.",
    ),
    Case(
        "personal-irrelevant-memory",
        "personal",
        "explain recursion with an example",
        Expect(memory_scope="work"),
        "A clear recursion example. A saved cat or marathon never appears: the work scope "
        "reads the stack and what the user builds, nothing else.",
    ),
    Case(
        "personal-general-no-memory",
        "personal",
        "what is the capital of France",
        Expect(memory=False),
        "Paris. No saved memory is read for a general question.",
    ),
    Case(
        "personal-where-live",
        "personal",
        "where do I live?",
        Expect(instant="text", search="no"),
        "With 'User lives in Addis Ababa' saved: 'You live in Addis Ababa.' Never 'I don't "
        "have that saved' when it is.",
    ),
    Case(
        "personal-remember-memory-off",
        "personal",
        "remember that I'm vegetarian",
        Expect(hints=("memory_off",), memory=False),
        "Says memory is off and that it can be turned on in Settings → Memory; never "
        "'I'll remember that'.",
        memory_enabled=False,
    ),
    Case(
        "personal-profile-memory-off",
        "personal",
        "where am I from?",
        Expect(instant="", hints=("memory_off",)),
        "Memory is off: says so (or answers from this chat), never a saved fact.",
        memory_enabled=False,
    ),
    Case(
        "personal-past-decision-missing",
        "personal",
        "What did we decide about the database last time?",
        Expect(hints=("no_past_record",), memory=True),
        "No earlier chat found: says it can't find that conversation and asks, never "
        "invents a decision.",
    ),
    Case(
        "personal-recall-earlier-detail",
        "personal",
        "what was the hotel I mentioned earlier?",
        Expect(hints=("no_past_record",), memory=True),
        "Names the hotel from this chat (the window, its summary, or an earlier snippet the "
        "turn searched for); says it can't find it only when none of them has it.",
        history=(
            ("user", "We're staying at the Memmo Alfama in Lisbon, any tips for the area?"),
            ("assistant", "Great pick: Alfama is walkable, hilly and full of fado bars."),
        ),
    ),
    Case(
        "personal-said-to-someone-else",
        "personal",
        "I said hello to my neighbour and he ignored me, what should I do?",
        Expect(memory=False, no_hints=("no_past_record",)),
        "Ordinary advice about the neighbour; no saved memory or earlier chats are read.",
    ),
    Case(
        "personal-memory-not-config",
        "personal",
        "You know which models Recall uses. Tell me what to fix",
        Expect(search="ask", memory=True),
        "States any recalled aliases as possibly out of date and asks for the current "
        "config before prescribing changes.",
    ),
    Case(
        "personal-forget-everything",
        "personal",
        "forget everything you know about me",
        Expect(instant="text", search="no"),
        "A card to delete everything saved, with a Confirm button; nothing is deleted "
        "until it is tapped.",
    ),
    Case(
        "money-mortgage-low-rate",
        "money",
        "what is my mortgage for 300k dollars house if mr rate is 1 percent",
        Expect(hints=("money", "money_reply"), solved=False, image_gen=False, photo=NO_PHOTO),
        "$964.92 a month over an assumed 30 years, a calculator card, and a note that 1% is "
        "not a realistic rate next to today's average (when the lookup finds one).",
    ),
    Case(
        "money-car-loan",
        "money",
        "what would my car payment be on a $32,000 car at 7.5% APR for 72 months",
        Expect(hints=("money", "money_reply"), image_gen=False, photo=NO_PHOTO),
        "About $553 a month, total interest and total paid, and the card with three sliders.",
    ),
    Case(
        "money-card-payoff",
        "money",
        "I owe 5000 on my credit card at 22% apr and pay 200 a month, how long to pay off",
        Expect(hints=("money", "money_reply"), solved=False),
        "About 34 months and the interest paid, with a card to try other payments.",
    ),
    Case(
        "money-savings",
        "money",
        "if I save 200 a month at 4.5% for 10 years how much will I have",
        Expect(hints=("money", "money_reply")),
        "About $30,200, what was deposited and the interest earned.",
    ),
    Case(
        "money-rates-now",
        "money",
        "what are mortgage rates right now",
        Expect(hints=("money", "money_rates")),
        "Today's average with its date and a link, or a plain 'could not find today's figure'.",
    ),
    Case(
        "money-no-rate",
        "money",
        "monthly payment on a 250000 mortgage",
        Expect(hints=("money", "money_ask_rate")),
        "Offline there is no average to assume: one question for the rate their lender quoted.",
    ),
    Case(
        "money-what-if-term",
        "money",
        "hmm what if i only do 3 years instead",
        Expect(hints=("money", "money_reply"), solved=False, image_gen=False, photo=NO_PHOTO),
        "The same $11,000 at 7.16% over 36 months: $340.45 a month and $1,256.32 interest, "
        "worked by the server with a new card (live 2026-10-25 the model did it: $340.58).",
        history=(
            (
                "user",
                "i'm buying a used car for 14000 at 7.16%, i can put 3000 down. what would my "
                "monthly payment be over 5 years?",
            ),
            ("assistant", "About $218.64 a month over 60 months, $2,118.67 in interest."),
        ),
    ),
    Case(
        "money-what-if-lookalike",
        "money",
        "what if i only do 3 sets instead",
        Expect(no_hints=("money",)),
        "Adjusts the workout; a what-if after a workout changes no loan.",
        history=(
            ("user", "give me a 4 day workout plan with 4 sets of each exercise"),
            ("assistant", "Day 1: squats, lunges and calf raises, 4 sets of 10 each."),
        ),
    ),
    Case(
        "money-what-if-tax-lookalike",
        "money",
        "what if sales tax is 7%",
        Expect(no_hints=("money",)),
        "Adds the tax to the price in words; a percent beside a tax is no new loan rate.",
        history=(
            ("user", "car loan 20000 at 7% for 5 years, what's the monthly payment"),
            ("assistant", "About $396.02 a month for 60 months."),
        ),
    ),
    Case(
        "money-what-if-miles-lookalike",
        "money",
        "what if it's 40k miles",
        Expect(no_hints=("money",)),
        "Talks about the mileage; a sum beside miles is no new price.",
        history=(
            ("user", "car loan 20000 at 7% for 5 years, what's the monthly payment"),
            ("assistant", "About $396.02 a month for 60 months."),
        ),
    ),
    Case(
        "money-lookalike",
        "money",
        "rate my essay out of 10, I tried to make the interest of the story build slowly",
        Expect(no_hints=("money",)),
        "Feedback on the essay; rate and interest are not money here.",
    ),
    Case(
        "money-homework-stays-math",
        "money",
        "compound interest on 1000 at 5% for 3 years",
        Expect(subject="math", no_hints=("money",)),
        "School compound interest is maths' worked answer, not a calculator card.",
    ),
    Case(
        "money-two-lines",
        "money",
        "20k with 6 percent",
        Expect(hints=("money", "money_reply"), image_gen=False, photo=NO_PHOTO),
        "A $20,000 car loan at 6% over an assumed 60 months, worked by the server with its "
        "card (live 2026-10-25 no card came and the model's totals were off).",
        history=(
            ("user", "I am planing to buy a car"),
            ("assistant", "Nice! Are you looking at new or used, and what's your budget?"),
        ),
    ),
    Case(
        "money-two-lines-down",
        "money",
        "60k at 6 percent",
        Expect(hints=("money",)),
        "The live line (2026-10-25): after a $400k house and a question for the down payment "
        "and the rate, 60k is a sixth of the price, read as the down payment with a note "
        "saying so; the model's own payment was 27 cents off.",
        history=(
            ("user", "House buying for 400k"),
            ("assistant", "How much are you putting down, and what rate have you been quoted?"),
        ),
    ),
    Case(
        "money-two-lines-ambiguous",
        "money",
        "150k at 6 percent",
        Expect(no_hints=("money",)),
        "The model answers: after a $400k house, 150k may be the loan or the down payment, so "
        "the server works no numbers it cannot be sure of.",
        history=(
            ("user", "House buying for 400k"),
            ("assistant", "How much are you putting down, and what rate have you been quoted?"),
        ),
    ),
    Case(
        "money-down-follow-up",
        "money",
        "Down payment 3k",
        Expect(hints=("money",)),
        "The live line (2026-10-25): a down payment after a car loan of 20k at 6% comes off "
        "the 20k; the model's own payment was 50 cents off.",
        history=(
            ("user", "I am planing to buy a car"),
            ("assistant", "Nice! Are you looking at new or used, and what's your budget?"),
            ("user", "20k with 6 percent"),
            ("assistant", "About $386.66 a month over 60 months."),
        ),
    ),
    Case(
        "confirmed-figures",
        "personal",
        "Yes",
        Expect(hints=("confirmed",), lightweight=False),
        "Goes ahead with $100k take-home and $50k essentials: the budget, never another "
        "request to confirm (live 2026-10-25 it asked to double-check again).",
        history=(
            (
                "user",
                "My monthly take-home is $100k and my essentials are $50k. How should I "
                "split the rest?",
            ),
            ("assistant", "Those are large figures for a month. Could you confirm both figures?"),
        ),
    ),
    Case(
        "clarify-plain-words",
        "format",
        "Don't uses want to see clean food?",
        Expect(image_gen=False, photo=NO_PHOTO),
        "Answers with a view on whether users want clean-food scores (the typo is 'users'); "
        "never a card asking what 'clean food' means (live 2026-10-25).",
        history=(
            ("user", "I'm building a grocery app that shows a score for each food"),
            ("assistant", "Nice idea: a clear score helps shoppers compare products at a glance."),
        ),
    ),
)


def by_id(case_id: str) -> Case:
    for case in CASES:
        if case.id == case_id:
            return case
    raise KeyError(case_id)
