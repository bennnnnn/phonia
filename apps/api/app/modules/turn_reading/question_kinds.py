"""What a message is about, for the notes beside it: someone's own matter, or the world.

A school exercise and a question about the world get notes asking for the textbook's
answer (``school_question``). A message about the asker, their team or app, the
assistant, code, anything that changes (news, prices, forecasts, travel) or a matter of
taste never does: "Calculate my BMI", "Determine the root cause of the 502s on our nginx
server", "Mark says Bitcoin will hit 200k. Is he right?" and "Which neighbourhood is
safer: (a) Brooklyn (b) Queens (c) Bronx?" were read as exercises in review
(2026-10-30), and an exercise is offered no web search.
"""

from __future__ import annotations

import re

from app.modules.turn_reading.coding import has_code_syntax
from app.modules.turn_reading.conversation import is_social_opener

# The asker: "I", "my", "me". Not "(i)", a part's label, a book's "we observe", or the
# "I" of World War I, Charles I or a grammar exercise's example sentence.
OWN = re.compile(
    r"(?<!\()\b(?:i'm|i've|i'd|my|me|mine)\b"
    r"|\b(?-i:I)\s+(?:want|need|have|should|plan|bought|got|own|work|live|feel|think|weigh"
    r"|am\s+(?:trying|looking|planning|going)|was\s+(?:wondering|told))\b"
    r"|\b(?:can|do|should|could|would|will|did|shall)\s+(?-i:I)\b",
    re.IGNORECASE,
)
# The asker's group, not a textbook's "our Earth" or "Why do we need a fuse": "our nginx
# server", "we should refactor", "What did we decide".
_OURS = re.compile(
    r"\bour\s+(?:app|apps|team|company|business|servers?|code|codebase|site|website|product"
    r"|database|startup|budget|trip|family|kids|children|house|home|wedding|clients?"
    r"|customers?|users?|project|office|landlord|salary)\b"
    r"|\bwe\s+(?:should|decided|did|could|are\s+going|plan)\b|\b(?:did|shall)\s+we\b",
    re.IGNORECASE,
)
# Talk with the assistant, or the clock: "how are you?", "Can you set a reminder",
# "Justify your previous answer", "Indicate your availability", "what time is it".
_ASSISTANT = re.compile(
    r"\b(?:how\s+are\s+you|who\s+are\s+you|are\s+you|can\s+you|could\s+you|what\s+can\s+you"
    r"|your\s+(?:previous|last|earlier|availability|opinion|name|thoughts)"
    r"|whether\s+you\s+can|you\s+can\s+access|what\s+time|what\s+day|today'?s\s+date"
    r"|tick\s+tock|thoughts\s*\?)",
    re.IGNORECASE,
)
# A matter of taste or judgement: "Which is better for a beginner", "Which neighbourhood is
# safer", "Is a 5-star hotel worth it", "a good investment", "Which headline is stronger".
TASTE = re.compile(
    r"\b(?:(?:better|best)\s+(?:for|than|to|choice|option|pick)|prefer\w*|favou?rite"
    r"|sounds\s+(?:more|better|nicer|best)|go\s+well|should\s+(?:i|we|our)"
    r"|would\s+you\s+(?:rather|prefer|recommend|choose|pick|buy|use)"
    r"|recommend\w*|nicer|cuter|cooler|tastier|safer|safest|popular|worth\s+it|realistic"
    r"|reliable|stronger\s*:|prioriti[sz]e|good\s+(?:idea|name|choice|gift|place|time|investment"
    r"|with\s+kids)|enough\s*\?|legit"
    # "What is the best country", not "the best conductor of heat".
    r"|(?:best|worst)\s+(?!conductors?|insulators?|examples?|answer|options?|describes|explains)"
    r"\w+)\b|\bstronger\s*:",
    re.IGNORECASE,
)
# What changes, so no textbook holds it: news, prices, forecasts, people in office, travel.
# Each word is the changing sense only: "the current" of a circuit, "the cost of fencing a
# field", "the first President" and a book's hypothetical ("What will happen if we remove
# all the decomposers?") are no news; "What will happen if the volcano erupts?" is.
CURRENT = re.compile(
    r"\b(?:currently|current\s+(?:events?|news|affairs|price|status|president|ceo|rate|score"
    r"|weather|state\s+of)|right\s+now|as\s+of\s+now|today|latest\s+(?:news|version|model"
    r"|update|release|iphone|price)|newest|this\s+(?:week|year|month)|price\s+of\s+(?!\d)"
    r"|prices|how\s+much\s+(?:is|are|does|do)\b[^?]*\bcost|stocks?|share\s+price|market\s+cap"
    r"|ceo|(?:current|new|next)\s+president|prime\s+minister\s+of|airlines?|flights?|visa"
    r"|open(?:ing)?\s+hours|forecast|weather\s+(?:today|tomorrow|now|in|this|like|for)"
    r"|will\s+it\s+(?:rain|snow)|buy|cheapest|cheaper|tomorrow|tonight|yesterday|this\s+weekend"
    r"|next\s+(?:week|month|year|quarter|monday|tuesday|wednesday|thursday|friday|saturday"
    r"|sunday)|on\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|who\s+won|won\s+the|will\s+(?:win|hit|happen(?!\s+if\s+(?:we|you|one|all|some|any|a|an)\b)|crash|do)|by\s+20\d\d|in\s+20[2-9]\d"
    r"|inflation|bitcoin|crypto\w*|elections?|super\s*bowl|world\s+(?:cup|series)|nba|fed"
    r"|rate\s+cut|mortgages?|taxes|tax\s+(?:return|rate)s?|drive\s+from|driving\s+to|commute"
    r"|hotels?|vacation|what\s+happened\s+to|going\s+on\s+with|erupting|variant"
    # A named place: "a trip to Bali", "move to Austin", not "the wave takes to travel to
    # the obstacle".
    r"|(?:trip|travel(?:l?ing)?|move|moving|holiday|fly|flying)\s+to\s+(?-i:[A-Z])\w*"
    r"|last\s+(?:\w+\s+)?(?:cup|final|election|year|week|month|night|season|match|game|time))\b"
    r"|\$\d",
    re.IGNORECASE,
)
# Code, an error, a system or a programming word: a developer's question, whatever its shape.
# A chemical formula (NaHCO3, CuSO4) and a unit (kHz) are camel-cased words too, and no code;
# so is a science term, lower case then capitals to its end (pH, mRNA, hsCRP, oxLDL, pKa). A
# name runs on in lower case after its capital: getUser, iPhone, jQuery, eBay. One ending in
# a programming acronym is code too: toJSON, innerHTML, userID, parseURL, isNaN (2026-11-01:
# a developer's question about innerHTML got a textbook note).
CODE_TALK = re.compile(
    r"`|\b(?![A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)+\b|[kmMGµ][A-Z]\w?\b)"
    r"(?:[a-z]+[A-Z](?![A-Z]*[a-z]?\b)\w*|[A-Z][a-z]+[A-Z]\w*)\b"
    r"|\b[a-z]+(?:JSON|HTML|XML|URLs?|URIs?|IDs?|APIs?|CSS|SQL|DOM|UUIDs?|HTTPS?|CSV|SVG|JWT"
    r"|SDK|NaN|UI|DB|IO)\b"
    r"|\b(?:iOS|iPadOS|macOS|watchOS|tvOS|visionOS)\b"
    r"|\b(?i:error|exception|code|javascript|typescript|python|java|sql|api|bug|compile\w*"
    r"|emails?|tweets?|nginx|ssh|servers?|deploy\w*|database|repo|git|github|docker"
    r"|kubernetes|linux|regex|css|html|npm|frontend|backend|postgres\w*|mysql|mongo\w*|redis"
    r"|cpu|replica|aws|font|logo|excel|spreadsheets?|vlookup|xlookup)\b|\b(?:Rust|Golang|Kotlin)\b"
    r"|\bprint\(|\w\(\)"
)
# Health advice for someone, which changes with the person and the research.
_ADVICE = re.compile(
    r"\b(?:fasting|keto|diabetics?|supplements?|dosage|medications?|side\s+effects|warfarin"
    r"|ozempic|weight\s+loss|seed\s+oils?|vaccines?)\b",
    re.I,
)
# How someone feels: "Is it normal to feel anxious before a job interview?"
_FEELING = re.compile(
    r"\b(?:(?:i|to)\s+feel(?:ing)?|feeling|anxious|nervous|sad|lonely|stressed|depressed|upset"
    r"|scared)\b",
    re.IGNORECASE,
)


def anyones(text: str) -> bool:
    """About the asker or their group, the assistant, code, anything current or taste."""
    patterns = (OWN, _OURS, _ASSISTANT, CODE_TALK, CURRENT, TASTE, _ADVICE)
    return any(pattern.search(text) is not None for pattern in patterns) or has_code_syntax(text)


# A question, or an order to explain, opening the message or any sentence of it.
_QUESTION = re.compile(
    r"\?|(?:^|[.!:]\s+)(?:why|how|what|which|who|whom|whose|where|when|is|are|was|were|does"
    r"|do|did|can|could|will|explain|describe|define|state|name|list|compare|discuss"
    r"|identify|justify|suggest|predict|find|calculate|determine)\b",
    re.IGNORECASE,
)
# A task to do, not a question to answer: "Write a poem about rain", "Translate …",
# "Find remote backend jobs", "do a search".
_TASK = re.compile(
    r"^\s*(?:write|draft|make|create|generate|plan|translate|summari[sz]e|rewrite|edit|fix"
    r"|help|remind|set|search|look\s+up|do\s+a|find\s+(?!the\b)|tell\s+me\s+a\s+(?:joke|story))"
    r"\b",
    re.IGNORECASE,
)


def is_factual_question(query: str) -> bool:
    """A question about the world: not a task, small talk, feelings or anyone's own matter."""
    text = query.strip()
    return (
        3 <= len(text.split()) <= 150
        and _QUESTION.search(text) is not None
        and _TASK.search(text) is None
        and _FEELING.search(text) is None
        and not anyones(text)
        and not is_social_opener(text)
    )


# What a science textbook explains, so a question about it has nothing to look up:
# "Why is phosphorus preserved in water?" was answered from a YouTube comment
# (2026-10-30). Main's rule kept these from searching; a question about the population of
# Tokyo still may.
_SCIENCE = re.compile(
    r"\b(?:forces?|friction|pressure|gravity|gravitational|weight|motion|speed|velocity"
    r"|accelerat\w+|energy|heat|temperature|sound|pitch|vibrat\w+|echo|loudness"
    r"|light|mirrors?|reflect\w*|refract\w*|lens|shadow|magnet\w*|electric\w*|circuit"
    r"|conductors?|insulators?|electrolyt\w+|electroplat\w+|metals?|non-?metals?|alloys?"
    r"|(?-i:rust\w*)|corrosion|oxides?|acids?|bases?|salts?|plastics?|fibres?|fibers?|fuels?"
    r"|combust\w+|flames?|burn\w*|oxygen|carbon|hydrogen|nitrogen|atoms?|molecules?|ions?"
    r"|elements?|compounds?|mixtures?|solutions?|planets?|stars?|moon|orbit\w*|eclipse"
    r"|earthquakes?|lightning|thunder\w*|evaporat\w+|condens\w+|boiling|melting|density"
    r"|reactive|reactivity|phosphorus|sodium|potassium|calcium|magnesium|iron|copper|zinc"
    r"|alumin\w+|sulph\w+|sulfur|mercury|silver|gold|chlorine|helium|neon|electrons?|protons?|neutrons?|cells?|tissues?|organs?|photosynthe\w+"
    r"|respiration|chloroplasts?|mitochondria|nucleus|membranes?|organelles?|ribosom\w*|reticulum"
    r"|plastids?|vacuoles?|golgi|cytoplasm|dna|chromosomes?|genes?|osmosis"
    r"|diffusion|pollinat\w+|reproduc\w+|seeds?|plants?|roots?|leaves|stems?|xylem|phloem"
    r"|species|ecosystems?|food\s+chain|bacteria|fungi|viruses|kingdoms?|classification"
    r"|digest\w+|blood|heart|lungs?|kidneys?|hormones?|enzymes?|climate|atmosphere"
    r"|greenhouse|albedo|erosion|volcano\w*|rocks?|minerals?|tides?|sweat\w*)\b",
    re.IGNORECASE,
)


def mentions_science(text: str) -> bool:
    """Words a science textbook explains: an atom, a cell, a force, the climate."""
    return _SCIENCE.search(text) is not None


# A named thing or a date: "an earthquake in Japan", "Is Ozempic safe", "Starlink
# satellites", "sold in 2025". A capital inside a sentence names something in the world,
# which may have news; the Earth, the Moon and the Sun are a book's.
_NAMED = re.compile(r"(?<=[a-z,;]\s)(?!(?:Earth|Moon|Sun|I)\b)[A-Z][a-z]+|\b(?:19|20)\d\d\b")
_NEW = re.compile(r"\b(?:next|new|newly|recent\w*|just|latest|so\s+far|been\s+discovered)\b", re.I)


def names_or_news(text: str) -> bool:
    """Names something in the world or something new: there may be news about it."""
    return _NAMED.search(text) is not None or _NEW.search(text) is not None


def is_science_question(query: str) -> bool:
    """A question a science textbook explains, about nothing named or new, so there is
    nothing to look up."""
    text = query.strip()
    return (
        len(text.split()) <= 60
        and is_factual_question(text)
        and _SCIENCE.search(text) is not None
        and not names_or_news(text)
    )
