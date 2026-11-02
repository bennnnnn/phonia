"""Asking the user with a tap card instead of a paragraph of questions (docs/clarify.md).

``CLARIFY_CARD_HINT`` is the one asking rule: when to ask, how the reply around the card
reads, when never, and the ```clarify card's shape. The server checks the card the model
writes (``chat/clarify_card.py``) and reads the user's picks on the next turn
(``chat/clarify_turn.py``).
"""

import re

from app.modules.turn_reading.clarify import names_its_purpose

# A "best X for Y" question, answered without asking: the picks as a list, not paragraphs.
RANKING_FORMAT_HINT = (
    "This asks for the best picks for a purpose it names. Answer now and ask nothing: at "
    "most one short lead line, then a numbered list of the 5-8 strongest picks, best "
    "first, each opening with its **bold name**, then a dash and one or two short "
    "sentences on why it fits that purpose. Group the picks under 2-3 short ### headings "
    "only when they fall into clear kinds. Never paragraphs of picks. End with at most one "
    "short line offering to narrow it down (their budget, situation or place)."
)


CLARIFY_CARD_HINT = (
    "Asking the user: when the best answer depends on what they mean or want (what 'best' "
    "means to them, their goal, budget, level or situation) and neither memory nor this "
    "chat says it, ask with the tap card; never write those questions as prose, a list, or "
    "choices in parentheses. Ask only when their picks would change the answer in a real "
    "way: when a good general answer exists, give it in full and do not ask; a question "
    "that says what it is for ('the best countries for business', 'a laptop for coding', "
    "'a phone under $500') has one. Never ask what a plain word or phrase means ('clean "
    "food', 'healthy', 'cheap') when its everyday sense, or the one this chat gives it, is "
    "enough to answer, and read a typo as the word they meant. Never for a "
    "plain fact, a sum or a maths, physics or chemistry problem, a greeting, a reminder, a "
    "picture, a draft whose purpose they gave, or a question about an idea or project this "
    "chat is already about ('would users want this?'), which takes your view. A reply that "
    "asks has three parts. First "
    "a short useful start: the strongest few options, each its own paragraph with a bold "
    "line and a short why ('🇨🇭 **Switzerland — best for quality of life**'), or one short "
    "sentence when anything more would be a guess, as in 'plan my week'. Then a bold "
    "lead-in on its own line that fits the start and the card: after the start, **But let "
    "me ask you one thing.** for one question, **But let me ask you a couple of things.** "
    "for two or three; with no options before it, no 'But' (**Let me ask you one thing.**). "
    "Then one short line naming what you need (What do you mean by *best*?). Then the "
    "card, last: a "
    "```clarify fence holding one JSON object, for example "
    '{"request": "Recommend the best country for me.", "questions": [{"id": "priority", '
    '"label": "Main priority", "question": "What matters most to you?", "options": '
    '["💰 Making money", "🌿 Quality of life", "🛡️ Safety", "🎓 Education"]}, '
    '{"id": "region", "label": "Region", "question": "Which region are you considering?", '
    '"options": ["🌍 Anywhere", "🇪🇺 Europe", "🌎 The Americas", "🌏 Asia"]}], '
    '"closing": "Compare the strongest options with practical pros and cons.", '
    '"submit": "Find my best country"}. '
    "1 to 3 questions, 2 to 8 short options each, one pick per question; put the likeliest "
    "option first, because the card starts on it, and start each option with a fitting emoji "
    'when it helps them scan. "label" is 2 to 4 words naming the question. Tapping '
    'the button sends "request", each label with its pick, then "closing" as the user\'s '
    'next message: "request" is their ask as one first-person sentence, "closing" one '
    'sentence on what the answer should cover, and "submit" the button, 2 to 4 words '
    "saying what tapping does. All in the user's language. No Other or Skip option: they "
    "can type instead. A reply that asks is the exception to the emoji rule: a flag or "
    "fitting emoji may lead each start line and each option, no others. A question with no "
    "fixed choices (an email's purpose, their own numbers) is one short question in prose "
    "instead of a card."
)

# The turn after a card: the phone sends the card's request, "Label: pick." for each
# question, then its closing, as one message.
CLARIFY_PICKS_HINT = (
    "The user's message answers the clarify card your last reply ended on: their request, "
    "each question's label with what they picked, and what the answer should cover. Now "
    "give the full answer, built around those picks. Open with a direct recommendation in "
    "one or two sentences: the best fit for them and why, tied to their picks and to what "
    "memory says about them when it fits. Then the complete answer the message asks for, "
    "strongest options first; a flag or fitting emoji may lead each option, an exception to "
    "the emoji rule. Ask nothing more: no card, no questions, no 'tell me more'. Where "
    "something is still unknown, assume a sensible default and say it in one short line. "
    "Do not list their picks back."
)
# Anything typed instead of tapping: other words for the picks, "just answer", or a new question.
CLARIFY_UNANSWERED_HINT = (
    "Your last reply asked with a clarify card. If this message answers it in other words "
    "or says to skip or just answer, answer the request from before the card now. Ask "
    "nothing more: no card and no questions; for anything they did not say, assume a "
    "sensible default and say it in one short line. If it is a new question, answer that."
)


# A shape the user asked for wins over the ranked list: "in a table", "one paragraph".
_SHAPE_ASKED = re.compile(
    r"\b(?:tables?|charts?|graphs?|grid|paragraphs?|essay|bullet\s+points?|compar\w*|vs\.?"
    r"|versus|maps?|one\s+(?:line|sentence|word))\b",
    re.IGNORECASE,
)


def ranking_layout(text: str) -> str | None:
    """The ranked-picks layout for a "best X for Y" question that asks for no other shape."""
    if names_its_purpose(text) and _SHAPE_ASKED.search(text) is None:
        return RANKING_FORMAT_HINT
    return None
