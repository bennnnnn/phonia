"""English "draw me a cat and also explain black holes": a second request after the picture.

The turn's plan cuts it off and answers it beside the picture, so the whole line is not
one picture. The cut is the plan's own (``chat.cuts_after_picture``: its clause and cut
rules): "… and also <request>", "…. Also, <request>", "… and suggest names", "… and give
me facts about cats" are cut; "… and tell me about dog breeds" after a dog, "… and show
the cat sleeping", "… then suggest names" and "… and tell me its name" stay with the
picture, as the plan keeps them, and draw whole as on main.
"""

from __future__ import annotations

SECOND_ASKS = frozenset({"explain", "tell", "write", "show", "help", "what", "how", "why", "who"})


def _is_picture(body: str) -> bool:
    """A request the plan reads as a picture: one the draw reader takes, not a photo lookup
    (any other kind after a picture cuts alike)."""
    from app.modules.images.gen_intent import extract_image_gen_prompt
    from app.modules.images.lookup_intent import extract_image_lookup_query

    return not extract_image_lookup_query(body) and bool(extract_image_gen_prompt(body))


def asks_separately(text: str) -> bool:
    """True for "draw me a cat and also explain black holes": the plan cuts the line after
    the picture and answers the rest apart, so the line is no single picture."""
    from app.modules.chat import cuts_after_picture

    return cuts_after_picture(text, _is_picture)
