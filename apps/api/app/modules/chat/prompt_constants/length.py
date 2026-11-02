"""How long a reply should be: what the user's own message asks for.

There is no account-wide length setting (FEATURES.md, Personalization): each message
sets its own ("in one sentence", "in detail"). ``reply_length`` reads one text; a plan
that splits a message into parts calls it once per part. ``STYLE_HINTS`` holds the
length line a turn's system prompt carries.
"""

BREVITY_REQUEST_HINT = (
    "The user set the length: a sentence, word or line count, or a brief answer. "
    "Ignore decorative table/heading layout and match the length they asked exactly. Preserve a "
    "draft/code/visual container only when that container is the requested deliverable. "
    "When shortening existing text, never drop or blur factual details such as units, "
    "quantities, dates, names, or commitments."
)


MIXED_LENGTH_HINT = (
    "The user set different lengths for different parts of this message (one sentence for "
    "one question, detail for another). Give each part exactly the length it asked for; a "
    "one-sentence part stays one sentence."
)

# The length line of the system prompt: SHORT on a greeting or an ack (the lightweight
# path), DETAILED when the message asked for depth, otherwise fit to the question.
STYLE_HINTS = {
    "short": (
        "Response length: SHORT. Answer in one to three sentences. No preamble, no recap of "
        "the question, no closing offer to help further. No sections, headings, tables, "
        "diagrams, or HTML unless the user asked for them."
    ),
    "balanced": (
        "Response length: fit the question. A simple question gets a short, direct answer; a "
        "hard, technical or multi-part one gets the depth it needs, without padding. Use short "
        "headings and bullets only when they help. Lead with the answer (a calculation "
        "leads with its working); explanation after."
    ),
    "detailed": (
        "Response length: DETAILED. The user asked for depth: explain fully, with the "
        "mechanism, reasoning, examples, edge cases and trade-offs that matter. Stay "
        "scannable, with headings and lists where they fit; a requested essay, story, letter "
        "or paragraph keeps its prose form."
    ),
}
