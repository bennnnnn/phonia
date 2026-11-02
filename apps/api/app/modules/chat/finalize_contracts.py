"""What a finalize pass declares about itself (ST-06): its kind, and the passes it must
follow or precede. Every pass in ``finalize_passes.FINALIZE_PASSES`` declares them, and
``test_finalize_passes`` holds the order to them."""

from __future__ import annotations

from typing import Literal

# "text": the pass only returns the reply (SymPy pool work included). "effect": it writes
# anything outside the text it returns: ctx/outcome fields, the committed text, usage
# counters, the status callback, Redis or the database, or a model call.
PassKind = Literal["text", "effect"]
TEXT: PassKind = "text"
EFFECT: PassKind = "effect"
# In ``before``: ahead of every other pass.
EVERY_OTHER = frozenset({"*"})

# The passes that land a subject's answer card under the reply's Answer heading.
CARD_PASSES = frozenset({"chemistry_fences", "physics_fences", "math_fences", "working_check"})
# The passes that read the model's fences as it wrote them.
FENCE_READERS = (CARD_PASSES - {"working_check"}) | {"formula_charts", "chemistry_enrich"}
# The server's own pictures and chips: added after the model's media is neutralized.
SERVER_MEDIA = frozenset({"answer_photo", "reply_picture", "search_sources"})

# After the user's Stop the reply is what they saw: only the passes that remove
# or neutralize model text (forged checks, untrusted media, scaffolding) or lay it
# out run. A pass that adds server text (a verified card, a note, source chips, a
# 3D model, a clock) would grow a stopped answer, and a new pass is left out
# until it is listed here.
STOPPED_REPLY_PASSES = frozenset(
    {
        "control_tokens",
        "drop_cut_reminder_fence",
        "prepare_model_reply",
        "answer_labels",
        "untrusted_media",
        "meta_notes",
        "prompt_leaks",
        "emoji_use",
        "answer_photo",
        "server_answer_cards",
        "text_plots",
        "solve_markers",
        "instant_usage",
        "close_fences",
        "clarify_card",
        "recipient_placeholders",
        "prose",
        "mermaid_and_places",
        "proper_case",
        "request_sections",
        "presentation",
    }
)
