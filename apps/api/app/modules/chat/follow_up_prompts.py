"""The system prompts that ask for follow-up questions under a reply.

Five candidates come back, best first; ``related_prompts`` keeps three.
"""

from __future__ import annotations

SHAPE = (
    "Each one is a single short question in the user's own voice, as they would "
    "type it, in the language they wrote in: 3 to 9 words, at most 60 characters, "
    "ending with ?. One sentence, no "
    "preamble, no number, no label, no quote marks. "
    "Do not ask what the reply already explained, and do not repeat the user's "
    "question or one they asked before. "
    'Return JSON {"questions": ["...", "...", "...", "...", "..."]}.'
)

SUBJECT_SYSTEM = (
    "You write five questions a student would tap to keep learning the problem "
    "they are working on, best first: "
    "1. Understand: why a step or the result works. "
    "2. What if: the same problem with one number or condition changed. "
    "3. Go further: the next idea this problem leads to. "
    "4 and 5: one more of any of those kinds. "
    "Name the quantity, never restate the whole problem: "
    '"Why convert km/h to m/s first?", "What if it took 10 s instead?", '
    '"How far does the car go in 5 s?". '
    "A what-if names what changes. For an equation write the new one: "
    '"What if $3x + 3 = 5$?", never "What if it was 5?". '
    "Write each equation in $...$ with spaces around =, as in $x^2 = 9$ or "
    "$\\sqrt{x} = 5$. A letter and a number stay separate: never $x5$, and "
    "never a number stuck to a radical like $^5\\sqrt{x}$. "
    f"{SHAPE}"
)

# "Up to five" got one question in about half the calls (2026-10-29), and three or none
# are shown: ask for five, or none.
GENERAL_SYSTEM = (
    "You write five follow-up questions the user is likely to tap next, best first, "
    "about exactly what they just asked. Each digs one step further into the same "
    "topic: a detail the reply only touched on, the usual next step, or a likely "
    '"what if". Stay on their topic. '
    "Return an empty list when nothing would help: small talk, a personal update, "
    "a message or text they asked you to write, a reminder or a setting. "
    f"{SHAPE}"
)
