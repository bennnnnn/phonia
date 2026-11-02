"""Code the user pasted: explain it line by line, or say why it fails and fix it.

"Explain this code line by line" used to get a loose bullet list that mixed
`$2$` maths into the code's values, so the phone showed raw dollar signs. A
request to explain, trace or debug a pasted snippet now gets one scannable
shape: the code reformatted in a tagged fence, a bold ``Line N`` label per line
with short bullets, a trace when one is asked for, and the output.
"""

from __future__ import annotations

from app.modules.turn_reading.coding import code_question_kind

# Shared by both shapes. A programming answer writes values in code ink; the
# general maths rule (inline `$...$`) does not apply to it.
_CODE_INK = (
    "- Code ink: every identifier, value, keyword and short expression goes in `inline code` "
    "(`total`, `0`, `for`, `total + n`); ordinary words stay plain. This is a programming "
    "answer: never write `$...$` or LaTeX, not even for arithmetic or a single number. Short "
    "bullets, no paragraphs."
)

CODE_EXPLAIN_HINT = (
    "The user pasted code and wants it explained. Use this shape:\n"
    "- One lead sentence saying what follows, e.g. \"Here's what each line does, then how "
    '`total` changes on each pass."\n'
    "- `### 1. The code`: their code in a language-tagged fence (```python), with its real "
    "line breaks and indentation even if they pasted it on one line. Do not change what it "
    "does.\n"
    "- `### 2. Explain each line`: for every line, a label such as **Line 1:** `total = 0` on "
    "its own line, then 1-3 short bullets. A tiny tagged fence only for an equivalent form "
    "(`total += n` is shorthand for `total = total + n`) or a small example.\n"
    "- When they ask for a trace, values per iteration or a loop's result: `### 3. <what they "
    "asked, e.g. Value of total after each iteration>` as a ```steps card, one numbered line "
    "per iteration with a bold title (1. **Iteration 1: `n = 2`**) and a plain line under it "
    "with the new state (`total = 0 + 2 = 2`), or a small pipe table (Iteration | n | total).\n"
    "- End with `**Output:**` and what it prints in a ```text block.\n" + _CODE_INK
)

CODE_DEBUG_HINT = (
    "The user pasted code that fails, or asks what is wrong with it. Use this shape:\n"
    "- One sentence naming the error and the line it happens on (`IndexError` on line 2).\n"
    "- `### Why it fails`: 2-4 short bullets on the cause, with the real values from their "
    "code.\n"
    "- `### The fix`: the corrected code in a language-tagged fence (```python) with a short "
    "comment on the changed line. A second reasonable fix gets one bullet, only if it helps.\n"
    "- `**Output:**` and what the fixed code prints, in a ```text block, when it prints.\n"
    + _CODE_INK
)

# "Run this python code: print(1+1)" got a bare "2", as if Recall ran it. Recall
# never executes code (CLAUDE.md golden rule 5); it says so, then reads the code.
CODE_RUN_HINT = (
    "The user asked you to run code. You cannot run or execute code, and nothing ran. Start "
    "with one short sentence that says so plainly (\"I can't run code, but here's what it "
    'would print:"), then what the code would output in a ```text block, worked out by '
    "reading it. If the output depends on input, files, the network, time or randomness, say "
    'what it depends on instead of inventing a result. Never word it as if it ran ("Output:" '
    'alone, "I ran it", "Result:"). Add a line-by-line explanation only if they asked '
    "for one.\n" + _CODE_INK
)

# Repeated next to the user's message: small models drift back to `$2$`.
CODE_INK_REMINDER = (
    "Programming answer: code names, values and expressions go in `inline code` and the code "
    "in a language-tagged fence; no `$...$` math anywhere in this reply."
)


def code_question_hint(text: str) -> str | None:
    """The layout for a pasted-code question, or None."""
    kind = code_question_kind(text)
    if kind == "debug":
        return CODE_DEBUG_HINT
    if kind == "explain":
        return CODE_EXPLAIN_HINT
    if kind == "run":
        return CODE_RUN_HINT
    return None
