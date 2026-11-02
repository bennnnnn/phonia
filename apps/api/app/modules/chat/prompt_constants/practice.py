"""Quiz me, flashcards, true/false: practice the phone draws as ```quiz cards.

A lesson's "Your turn" already uses the card; an explicit request for practice gets
one card per question, so the answers stay hidden until the user checks them.
"""

QUIZ_FORMAT_HINT = (
    "This turn asked for a quiz, flashcards or true/false questions. Each question is its "
    "own ```quiz card the app lets them answer and check: ```quiz alone on its line, the "
    "JSON on the next, then the closing fence. Never write an answer in the text; the "
    "card holds it.\n"
    '- Multiple choice: {"label": "Question 1", "question": "...", "options": ["...", '
    '"...", "...", "..."], "answer": <0-based index of the right option>, "explanation": '
    '"<why, in one or two sentences>"}; make the wrong options real mistakes.\n'
    '- True/false: the same with "options": ["True", "False"].\n'
    '- Flashcard: {"label": "Card 1", "question": "<the front>", "explanation": "<the '
    'back>"} with no options; the app shows the back when they tap Show answer.\n'
    "As many as they asked for (five when they named no number, at most ten). One short "
    "line before the first card and one line after the last offering another round. No "
    "headings, no numbered list, no answer key."
)
