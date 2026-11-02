# ruff: noqa: RUF001
"""Whether a message asks to be taught, walked through or given a learning plan."""

from __future__ import annotations

import re
from typing import Literal

from app.modules.turn_reading.stuck import stuck_on_a_topic
from app.services.text_normalize import collapse_ws, straighten_apostrophes

# Asking to be taught, in the shipped UI languages. A task ("teach me how to
# install Docker") keeps its how-to steps; see ``_PROCEDURE``.
_TEACH_TURN = re.compile(
    r"(?:"
    r"\bteach\s+(?:me|us)\b|"
    r"\b(?:can|could|would|will)\s+you\s+teach\b|"
    r"\bhelp\s+me\s+(?:learn|study)\b|"
    r"\bi\s*(?:'d|’d|\s+would)?\s+(?:want|like|love|need)\s+to\s+learn\b|"
    r"\bi\s+wanna\s+learn\b|"
    # "I want to know American history": a subject, not a fact ("if it rains",
    # "my balance", "the price") and not news ("the new iPhone").
    r"\bi\s*(?:'d|’d|\s+would)?\s+(?:want|like|love|need)\s+to\s+(?:know|understand)\s+"
    r"(?:(?:more\s+)?about\s+)?"
    r"(?!(?:about|more|if|whether|what|when|where|why|how|who|whom|which|your|you|my|me|it|"
    r"this|that|"
    r"the\s+(?:price|time|weather|score|status|result|answer|cost|news|new|newest|latest|"
    r"current|date)|(?:the\s+)?(?:new|newest|latest|current))\b)[^\W\d_]|"
    r"\btutor\s+me\b|"
    r"\b(?:be|become|act\s+as)\s+my\s+(?:tutor|teacher)\b|"
    r"\b(?:give\s+me\s+)?an?\s+(?:lesson|crash\s+course)\s+(?:on|in|about)\b|"
    # es / pt
    r"\bens[eé]ñ(?:ame|anos|arme)\b|\bquiero\s+aprender\b|\bay[uú]dame\s+a\s+aprender\b|"
    r"\bme\s+ensin[ae]\b|\bensina[- ]me\b|\bquero\s+aprender\b|"
    # fr
    r"\bapprends[- ]moi\b|\benseigne[- ]moi\b|\bje\s+(?:veux|voudrais)\s+apprendre\b|"
    # de
    r"\bbring\s+mir\b[^.?!]{0,60}\bbei\b|"
    r"\bich\s+(?:möchte|will|würde\s+gerne?)\b[^.?!]{0,60}\blernen\b|"
    # it
    r"\binsegnami\b|\b(?:voglio|vorrei)\s+imparare\b|"
    # ru
    r"\bнаучи\s+меня\b|\bобучи\s+меня\b|\bхочу\s+(?:научиться|выучить|изучить)\b|"
    # tr
    r"\böğret(?:ir\s+misin|ebilir\s+misin)?\b|\böğrenmek\s+istiyorum\b|"
    # am
    r"አስተምረኝ|መማር\s*እፈልጋለሁ"
    r")",
    re.IGNORECASE,
)


# A task keeps the how-to layout: the user wants it done, not a lesson.
_PROCEDURE = re.compile(
    r"\b(?:install|uninstall|set\s*up|setup|configure|deploy|download|troubleshoot|"
    r"fix|repair|reset|log\s*in|sign\s*up)\b",
    re.IGNORECASE,
)


# "Teach me (how) to bake bread" asks for a procedure; "teach me how to code"
# asks to learn a skill. The verb after "to" tells them apart.
_TO_VERB = re.compile(
    r"\b(?:(?:teach|help)\s+(?:me|us)\s+(?:how\s+)?to|learn\s+(?:how\s+)?to)\s+([a-z]+)",
    re.IGNORECASE,
)


_LEARNING_VERBS = frozenset(
    {
        "add",
        "analyse",
        "analyze",
        "budget",
        "calculate",
        "code",
        "compute",
        "conjugate",
        "count",
        "debug",
        "differentiate",
        "divide",
        "draw",
        "factor",
        "graph",
        "integrate",
        "invest",
        "learn",
        "multiply",
        "play",
        "program",
        "pronounce",
        "read",
        "reason",
        "say",
        "simplify",
        "sing",
        "solve",
        "speak",
        "spell",
        "study",
        "subtract",
        "think",
        "type",
        "understand",
        "use",
        "write",
    }
)


# A bounded roadmap/course request is different from an interactive teach-me
# session. Keep the pieces separate so common word orders remain readable and
# elapsed-time statements can be rejected before they become accidental plans.
_DURATION_TEXT = r"\b\d{1,3}[\s-]?(?:day|days|week|weeks|month|months)\b"


_DURATION = re.compile(_DURATION_TEXT, re.IGNORECASE)


_EXPLICIT_LEARNING_PLAN = re.compile(
    r"(?:"
    r"\b(?:learning|study|mastery|training)\s+(?:plan|roadmap|curriculum|schedule)\b|"
    r"\b(?:plan|roadmap)\s+(?:to|for)\s+(?:learn|learning|master|mastering|study|studying)\b|"
    r"\b(?:plan|roadmap)\b[^.?!]{0,45}\b(?:to\s+)?(?:learn|master|study)\b|"
    r"\b(?:curriculum|syllabus|course\s+plan)\b"
    r")",
    re.IGNORECASE,
)


# "Training" alone is a marathon's or a team's as often as a learner's: a training plan
# is caught by name above, and a marathon one there is a plan that does not teach.
_LEARNING_CUE = re.compile(
    r"\b(?:learn|learning|master|mastering|mastery|study|studying|"
    r"beginner|intermediate|advanced|senior|course|curriculum|syllabus|skill)\b",
    re.IGNORECASE,
)


_PLAN_CUE = re.compile(r"\b(?:plan|roadmap|curriculum|syllabus|course)\b", re.IGNORECASE)


_TEACH_WITH_DURATION = re.compile(
    rf"\b(?:teach\s+(?:me|us)|help\s+me\s+learn|i\s+(?:want|need|would\s+like)\s+to\s+learn)"
    rf"\b[^.?!]{{0,140}}{_DURATION_TEXT}",
    re.IGNORECASE,
)


_REQUESTED_DURATION_PLAN = re.compile(
    rf"\b(?:give|create|make|build|write|design|show|want|need)\b[^.?!]{{0,80}}"
    rf"{_DURATION_TEXT}[^.?!]{{0,60}}\b(?:plan|roadmap|curriculum|syllabus)\b",
    re.IGNORECASE,
)


_ELAPSED_LEARNING = re.compile(
    rf"(?:"
    rf"\b(?:started|finished|completed|spent)\b[^.?!]{{0,100}}{_DURATION_TEXT}|"
    rf"\b(?:i(?:'ve|\s+have)|we(?:'ve|\s+have)|has|had)\s+(?:already\s+)?(?:been\s+)?"
    rf"(?:learning|studying|practicing|training|working)\b[^.?!]{{0,100}}{_DURATION_TEXT}|"
    rf"\b(?:learned|studied|practiced|trained|worked)\b[^.?!]{{0,100}}\bfor\s+{_DURATION_TEXT}|"
    rf"{_DURATION_TEXT}\s+(?:ago|so\s+far)\b"
    rf")",
    re.IGNORECASE,
)


# Plans for doing, not learning, by kind: work, travel, events, health, home and money.
# "Plan a 3 day trip to Rome" was a study roadmap ("Learn the Forum's layout → … → Done
# when", 2026-10-29): the list named travel and vacation but not the trip.
_NON_LEARNING_PLAN_CUE = re.compile(
    r"\b(?:business|launch|marketing|content|social\s+media|product|project|campaign|sales|"
    r"travel|vacation|trip|itinerary|holiday|honeymoon|road\s+trip|visit|tour|"
    r"wedding|party|birthday|event|"
    r"workout|fitness|exercise|gym|marathon|running|race|weight\s+loss|lose\s+weight|"
    r"meal|diet|detox|fasting|sleep|"
    r"move|moving|cleaning|declutter|renovation|garden|"
    r"budget|savings|debt|finance)\b",
    re.IGNORECASE,
)


_INTERNATIONAL_LEARNING_PLAN = re.compile(
    r"(?:"
    r"\bplan\s+de\s+\d{1,3}[\s-]?(?:d[ií]as|dias|semanas|meses|semaines|mois)\b"
    r"[^.?!]{0,80}\b(?:aprender|apprendre|estudiar|étudier|estudar)\b|"
    r"\b\d{1,3}[\s-]?(?:tage|wochen|monate)\b[^.?!]{0,80}\blernplan\b"
    r")",
    re.IGNORECASE,
)


_PROGRAMMING_TAGS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpython\b", re.IGNORECASE), "python"),
    (re.compile(r"\b(?:javascript|js)\b", re.IGNORECASE), "javascript"),
    (re.compile(r"\b(?:typescript|ts)\b", re.IGNORECASE), "typescript"),
    (re.compile(r"\bjava\b", re.IGNORECASE), "java"),
    (re.compile(r"\b(?:c\+\+|cpp)\b", re.IGNORECASE), "cpp"),
    (re.compile(r"\bc#\b", re.IGNORECASE), "csharp"),
    (re.compile(r"\b(?:shell|bash)\b", re.IGNORECASE), "bash"),
    (re.compile(r"\b(?:sql|postgres(?:ql)?)\b", re.IGNORECASE), "sql"),
    (re.compile(r"\bhtml\b", re.IGNORECASE), "html"),
    (re.compile(r"\bcss\b", re.IGNORECASE), "css"),
    (re.compile(r"\b(?:swift|swiftui)\b", re.IGNORECASE), "swift"),
    (re.compile(r"\b(?:kotlin|android)\b", re.IGNORECASE), "kotlin"),
    (re.compile(r"\bgo(?:lang)?\b", re.IGNORECASE), "go"),
    (re.compile(r"\brust\b", re.IGNORECASE), "rust"),
    (re.compile(r"\bruby\b", re.IGNORECASE), "ruby"),
    (re.compile(r"\bphp\b", re.IGNORECASE), "php"),
)


def programming_tag(text: str) -> str | None:
    """The fence tag of the programming topic ``text`` names (``python``), or None."""
    cleaned = collapse_ws(text)
    for pattern, tag in _PROGRAMMING_TAGS:
        if pattern.search(cleaned):
            return tag
    return None


def is_learning_plan_request(text: str) -> bool:
    """True for bounded roadmaps/courses that should be delivered in full."""
    cleaned = straighten_apostrophes(collapse_ws(text))
    if not cleaned or len(cleaned) > 800:
        return False
    if _INTERNATIONAL_LEARNING_PLAN.search(cleaned):
        return True
    explicit = _EXPLICIT_LEARNING_PLAN.search(cleaned)
    duration = _DURATION.search(cleaned)
    if explicit and (not _NON_LEARNING_PLAN_CUE.search(cleaned) or _LEARNING_CUE.search(cleaned)):
        return True
    if duration is None:
        return False
    if _ELAPSED_LEARNING.search(cleaned) and not _TEACH_WITH_DURATION.search(cleaned):
        return False
    if _NON_LEARNING_PLAN_CUE.search(cleaned) and not _LEARNING_CUE.search(cleaned):
        return False
    if _REQUESTED_DURATION_PLAN.search(cleaned) or _TEACH_WITH_DURATION.search(cleaned):
        return True
    around_duration = cleaned[max(0, duration.start() - 140) : duration.end() + 140]
    return bool(_LEARNING_CUE.search(around_duration) or _PLAN_CUE.search(around_duration))


# "Help me understand two sum", or stuck on a topic ("I don't understand recursion",
# stuck.py): one idea, explained in full now, building to the answer in one reply.
_WALKTHROUGH = re.compile(
    r"(?:\bhelp\s+me\s+understand|\bwalk\s+me\s+through|\bbreak\s+down)\s+"
    r"(?!(?:it|this|that|what\s+you|you|why\s+you)\b)[^\W\d_]"
    r"|\bexplain\b[^.?!\n]{1,80}\bstep[- ]by[- ]step\b",
    re.IGNORECASE,
)


# "Walk me through changing a tire" / "how to set up Docker step by step" is a
# task to do: it keeps the numbered how-to steps.
_TASK_OBJECT = re.compile(r"\b(?:how\s+(?:to|do\s+i|can\s+i)|[a-z]{3,}ing)\b", re.IGNORECASE)


def is_walkthrough_request(text: str) -> bool:
    """True for "help me understand X" / "walk me through X": a full explanation now."""
    cleaned = straighten_apostrophes(collapse_ws(text))
    if not cleaned or len(cleaned) > 400:
        return False
    match = _WALKTHROUGH.search(cleaned)
    if match is None:
        return stuck_on_a_topic(cleaned) and not _PROCEDURE.search(cleaned)
    rest = cleaned[match.start() :]
    first_object = rest.split()[3:4] if rest.lower().startswith("walk me through") else []
    if first_object and _TASK_OBJECT.fullmatch(first_object[0]):
        return False
    return not (_PROCEDURE.search(cleaned) or re.search(r"\bhow\s+(?:to|do\s+i)\b", rest, re.I))


# Why a message is a request to be taught or not, for the turn's trace line.
TeachingReason = Literal["teach", "no_cue", "too_long", "learning_plan", "preference", "procedure"]


def teaching_reason(text: str) -> TeachingReason:
    """Why ``text`` asks for interactive tutoring (``teach``) or not."""
    cleaned = straighten_apostrophes(collapse_ws(text))
    if not cleaned:
        return "no_cue"
    if len(cleaned) > 400:
        return "too_long"
    if not _TEACH_TURN.search(cleaned):
        return "no_cue"
    if is_learning_plan_request(cleaned):
        return "learning_plan"
    # "Teach me by asking questions" says how, not what: no lesson yet.
    if is_standing_preference(cleaned):
        return "preference"
    return "procedure" if _asks_for_a_procedure(cleaned) else "teach"


def is_teaching_request(text: str) -> bool:
    """True for interactive tutoring, not a procedure or full learning roadmap."""
    return teaching_reason(text) == "teach"


# How the user wants to be taught or answered from now on, with no question of
# its own yet: "When teaching me, explain one concept at a time…", "From now on,
# use examples", "I learn best by doing", "Don't give me the answer, give hints".
# Read sentence by sentence on the collapsed, lower-cased text.
_PREF_LEAD = (
    r"^(?:(?:ok(?:ay)?|hey|hi|hello|so|also|and|btw|one\s+more\s+thing|quick\s+note|note)"
    r"[,!:.]?\s+)?(?:please\s+)?"
)


# What an instruction about replies starts with.
_PREF_DO = (
    r"(?:(?:please|just|only)\s+)?(?:(?:always|never|don't|do\s+not)\s+)?"
    r"(?:explain|teach|tutor|give|show|use|ask|quiz|test|answer|reply|respond|keep|start|begin|"
    r"end|finish|break|walk|include|add|check|let\s+me|make|write|focus|avoid|stop|wait|pause|"
    r"stick|limit|define|summari[sz]e|repeat|correct|challenge|guide|offer|provide|format|skip|"
    r"number|label|cite|speak|talk|tell|go\s+(?:one|step|slow|slowly|through|over)|"
    r"be\s+(?:more|less|concise|brief|direct|honest|clear|patient|simple|short|detailed|blunt|"
    r"gentle|critical|thorough|specific|shorter|longer|simpler|clearer))\b"
)


_PREF_SENTENCE: tuple[re.Pattern[str], ...] = (
    # "When teaching me, …" / "When you explain things to me, …"
    re.compile(
        _PREF_LEAD
        + r"when(?:ever)?\s+(?:you(?:'re|\s+are)?\s+)?(?:teach|teaching|tutor|tutoring|explain|"
        r"explaining|help|helping|answer|answering|reply|replying|respond|responding|show|showing|"
        r"giv(?:e|ing))\s+(?:me|us|things|stuff|concepts|topics|something|anything)\b"
        r"(?:\s*,\s*|(?:\s+[\w']+){0,3}\s*,\s*|\s+)"
        r"(?:" + _PREF_DO + r"|i\s+(?:prefer|like|love|want|need|learn)\b|"
        r"you\s+(?:should|must|can|could)\b|(?:can|could|would|will)\s+you\b|try\s+to\b|"
        r"make\s+sure\b)"
    ),
    # "When I ask you for code, always add comments"
    re.compile(
        _PREF_LEAD + r"when(?:ever)?\s+i\s+ask\s+(?:you\s+)?(?:for|about|to|a|an|anything|"
        r"something|questions?)\b[^,.;?!]{0,60},\s*" + _PREF_DO
    ),
    # "From now on, …" / "Going forward, your answers should …"
    re.compile(
        _PREF_LEAD + r"(?:from\s+now\s+on|going\s+forward|moving\s+forward|from\s+here\s+on"
        r"(?:\s+out)?|in\s+(?:the\s+)?future|for\s+future\s+(?:answers|replies|lessons|chats|"
        r"questions))\s*,?\s+(?:(?:you(?:'ll|\s+will|\s+should|\s+must|\s+can)?|your\s+"
        r"(?:answers|replies|responses|explanations|lessons|examples)\s+(?:should|must|"
        r"need\s+to|will)|i\s+(?:want|need|'d\s+like|would\s+like)\s+you\s+to)\s+)?" + _PREF_DO
    ),
    # "Use simple words from now on."
    re.compile(
        _PREF_LEAD + _PREF_DO + r"[^.?!]{0,160}\b(?:from\s+now\s+on|going\s+forward|"
        r"from\s+here\s+on(?:\s+out)?|in\s+(?:the\s+)?future)\s*[.!]?$"
    ),
    # "Always explain …" / "Can you always give examples?"
    re.compile(
        _PREF_LEAD + r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need|'d\s+"
        r"like|would\s+like)\s+you\s+to\s+)?(?:always|never)\s+(?:please\s+)?(?:explain|teach|"
        r"give|show|use|ask|quiz|test|answer|reply|respond|include|start|begin|end|break|walk|"
        r"check|define|summari[sz]e|cite|add|keep|write|tell|go\s+(?:one|step|slow|slowly|"
        r"through|over)|be\s+(?:more|less|concise|brief|direct|honest|clear|patient|simple|"
        r"short|detailed|blunt|gentle|critical|thorough|specific|shorter|simpler|clearer))\b"
    ),
    # "I want you to explain one concept at a time"
    re.compile(
        _PREF_LEAD + r"i\s+(?:want|need|'d\s+like|would\s+like)\s+you\s+to\s+(?:always\s+|only\s+)?"
        r"(?:explain|teach)\s+(?:me\s+)?(?:things\s+|concepts\s+|everything\s+)?(?:one\s+"
        r"(?:concept|thing|step|idea|topic)\s+at\s+a\s+time|step\s+by\s+step|slowly|simply|"
        r"with\s+(?:examples|analogies)|using\s+examples|like\s+(?:a|i'm|im))\b"
    ),
    # "I learn best by doing" / "I'm a visual learner"
    re.compile(_PREF_LEAD + r"i\s+learn\s+(?:best|better|most|faster|more\s+easily|well)\b"),
    re.compile(
        _PREF_LEAD + r"i(?:'m|\s+am)\s+an?\s+(?:visual|hands[- ]on|auditory|kinesthetic|"
        r"practical|slow|fast|reading)\s+learner\b"
    ),
    re.compile(
        _PREF_LEAD + r"i\s+(?:prefer|like|love|want|need)\s+to\s+(?:learn|be\s+taught|study)\s+"
        r"(?:by|with|through|using|one|step|slowly|in\s+small|from\s+examples)\b"
    ),
    re.compile(
        _PREF_LEAD + r"i\s+(?:prefer|like|love|need|want)\s+(?:it\s+)?when\s+you\s+(?:explain|"
        r"teach|give|use|show|ask|quiz|test|keep|break|walk|go|start|include|check)\b"
    ),
    re.compile(
        _PREF_LEAD + r"i\s+(?:prefer|like|want|need)\s+(?:short|shorter|brief|briefer|concise|"
        r"detailed|simple|simpler|step[- ]by[- ]step|practical|real[- ]world|lots\s+of|more|"
        r"fewer|less|plain|clear)\s+(?:answers|replies|responses|explanations|examples|"
        r"exercises|lessons|steps|hints|analogies|language|words)\b(?!\s+(?:of|about|on)\b)"
    ),
    # "Teach me by asking questions" / "teach me one concept at a time"
    re.compile(
        _PREF_LEAD + r"(?:(?:can|could|would|will)\s+you\s+)?teach\s+me\s+(?:by|using|with|"
        r"through|via|one\s+(?:concept|thing|step|idea|topic|lesson)\s+at\s+a\s+time|step\s+by\s+"
        r"step|slowly|in\s+small\s+steps|like\s+(?:a|i'm|im|i\s+am))\b"
    ),
    # "Don't give me the answer, give hints" / "Only give me hints"
    re.compile(
        _PREF_LEAD + r"(?:just\s+)?(?:don't|do\s+not|never|stop)\s+(?:just\s+)?(?:give|giving|"
        r"tell|telling|show|showing)\s+me\s+(?:the\s+)?(?:full\s+|final\s+|whole\s+)?"
        r"(?:answers?|solutions?)\b"
    ),
    re.compile(
        _PREF_LEAD + r"(?:just\s+|only\s+)?give\s+me\s+(?:only\s+)?(?:hints|clues|a\s+hint|"
        r"nudges)\s+(?:instead|first|rather|not|only)\b"
    ),
    re.compile(_PREF_LEAD + r"(?:only\s+(?:give\s+me\s+)?hints|hints?\s+only)\b"),
)


# A reminder ("always remind me to drink water"), a memory command ("keep in
# mind that I'm vegetarian") or a problem to work on is not a preference about
# replies.
_PREF_NOT = re.compile(
    r"\b(?:remind|reminders?|alarm|notify|notifications?|wake\s+me|ping\s+me|alert\s+me|"
    r"remember|forget|keep\s+in\s+mind)\b|\d\s*[-+*/=^×÷]\s*\d|=|```",
    re.IGNORECASE,
)


# A second sentence that asks for the topic now: "Teach me Python." / "Let's start."
_PREF_TOPIC_NOW = re.compile(
    r"\blet'?s\s+(?:start|begin|learn|study|do|go|talk)\b|\bstart\s+with\s+(?!an?\s)"
    r"|\bi\s+(?:want|need|'d\s+like|would\s+like)\s+to\s+(?:learn|know|understand|study)\b"
    r"|\b(?:topic|subject)\s+is\b"
)


# "Teach me by examples about cooking" names a topic after all.
_PREF_NAMES_TOPIC = re.compile(r"\b(?:how\s+to|how\s+do|about|what\s+is|what\s+are)\b|:\s*\S")


def _preference_sentence(sentence: str) -> bool:
    if not any(pattern.search(sentence) for pattern in _PREF_SENTENCE):
        return False
    teach_by = re.search(r"\bteach\s+me\s+(?:by|using|with|through|via|like)\b", sentence)
    return not (teach_by and _PREF_NAMES_TOPIC.search(sentence[teach_by.end() :]))


def is_standing_preference(text: str) -> bool:
    """True when the user says how to teach or answer them from now on, and asks nothing yet.

    "When teaching me yesterday you…", "from now on I'll wake at 6" and "always
    remind me to drink water" are not: a memory, a plan of their own, a reminder.
    """
    cleaned = collapse_ws(text or "").replace("’", "'").casefold()
    if not cleaned or len(cleaned) > 400 or _PREF_NOT.search(cleaned):
        return False
    sentences = [part for part in re.split(r"(?<=[.!?])\s", cleaned) if part.strip()]
    found = False
    for sentence in sentences:
        if _preference_sentence(sentence):
            found = True
            continue
        # Any other sentence is context; a question or a topic makes it a request.
        if "?" in sentence or _PREF_TOPIC_NOW.search(sentence) or _TEACH_TURN.search(sentence):
            return False
    return found


def _asks_for_a_procedure(cleaned: str) -> bool:
    if _PROCEDURE.search(cleaned):
        return True
    verb = _TO_VERB.search(cleaned)
    if verb is None:
        return False
    action = verb.group(1).lower()
    # "Teach me how to pass an interview/exam" is preparation/tutoring, not a
    # one-off procedure like installing Docker or tying a knot.
    if action == "pass" and re.search(
        r"\b(?:interview|exam|test|assessment|coding\s+challenge)\b",
        cleaned,
        re.IGNORECASE,
    ):
        return False
    return action not in _LEARNING_VERBS
