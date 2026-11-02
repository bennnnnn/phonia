"""How a turn relates to the conversation: an opener, a correction, a request to go on.

- "good morning!" or "how are you?" asks for nothing, so it gets the compact prompt and no
  photo offer. The lightweight path stays the exact greetings (``routing.py`` forbids
  growing that list), and "good morning, what's the capital of Peru?" is a question.
- "no, I said I'm vegetarian" corrects what the last reply assumed: ``CORRECTION_HINT``.
- "continue" picks up where the last reply stopped: ``CONTINUE_HINT``, on the turns
  ``continuation_subject.is_resume_request`` names.
- "yes" after the last reply asked them to confirm something ("Could you confirm both
  figures?") confirms it: ``CONFIRMED_HINT``, beside the follow-through hint every short yes
  gets. Live (2026-10-25): $100k monthly take-home and $50k essentials, "Could you confirm
  both figures?", "Yes", and the reply asked to double-check them again.

Patterns read text passed through ``collapse_ws`` (one space) and lowercased.
"""

# "hi" after "hi" got a fresh "Hey bini! How's your Friday going?" each time, as if the
# chat had just begun; told only to "notice it", a model said "Hey bini! What's up?"
# twice. It now gets the count and its own last reply.
REPEATED_GREETING_HINT = (
    "The user greeted you again right after your last greeting. Open by noticing it, the "
    'way a friend texts back ("Hi again!", "Hello, hello!", "Another hi!"), then '
    "one short question: what's up, or are they just saying hi or testing you. One short "
    "line in all. Do not greet them as if the chat had just begun, and do not ask about "
    "their day."
)
_ORDINALS = {2: "second", 3: "third", 4: "fourth", 5: "fifth"}


def repeated_greeting_hint(run: int, last_reply: str | None) -> str:
    """The repeated-greeting rule with this run's count and the reply it must not repeat."""
    count = _ORDINALS.get(run, f"number {run}")
    parts = [REPEATED_GREETING_HINT, f"This is their {count} greeting in a row."]
    if run >= 3:
        parts.append(f'You may count them with a smile ("That\'s {run} now!").')
    if last_reply:
        said = " ".join(last_reply.split())[:160]
        parts.append(f'Your last reply was "{said}": open differently and use other words.')
    return " ".join(parts)


CORRECTION_HINT = (
    "The user is correcting something you said or assumed earlier. Apply the correction to "
    "this answer and to the rest of the chat, and do not repeat the mistaken assumption. "
    "Acknowledge it in a few words at most, without a long apology, then give the corrected "
    "answer."
)

CONTINUE_HINT = (
    "The user asked you to continue. Pick up exactly where your last reply stopped: the next "
    "sentence, step or line of code, in the same format (reopen the same code fence if it was "
    "cut mid-code). Do not restart, recap, or repeat what you already wrote."
)

# Said on every short yes (``routing.is_short_confirmation``): conditional, so it needs no
# reading of the last reply, and a yes to an offer is still that offer's.
CONFIRMED_HINT = (
    "If your last reply asked them to confirm something (figures, details, a plan or what "
    "they meant), this yes confirms it exactly as stated, even a figure that looks unusual. "
    "Treat it as settled and give the answer it was for now, using those values. Never ask "
    "them to confirm, double-check or restate it again."
)
