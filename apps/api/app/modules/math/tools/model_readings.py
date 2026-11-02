"""A model's reading of a problem: certified only as the user's own maths.

SymPy checks the arithmetic of the equations it is given, not that they say what the
problem says (2026-11-01: a remainder problem read as 9B = 3 gave a checked A = -61/3; a tax
that "continues without end" summed over three rounds gave a checked 3920 for 5000).

- A photo's equations are certified only when they are on the page as read
  (``image_intent_on_the_page``); the typed extraction is held to the user's text the same
  way in ``tools/prompt.py``.
- A word problem's translation is never a verified card: its setup and SymPy's solution go
  to the model as an unchecked setup to check against the words (``unchecked_setup``).
"""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.modules.math.schemas import MathImageExtract, MathIntent
from app.modules.math.schemas.word_problem import WordProblemSetup
from app.modules.math.tools.solve_timeouts import note as note_solve_timeout

logger = logging.getLogger(__name__)


def image_intent_on_the_page(intent: MathIntent, extract: MathImageExtract) -> bool:
    """A photo's equations, system, inequality or expression are on the page as read (its
    source text, compared with SymPy). Kinds the page states as numbers (a shape's sides, a
    data list), and an extract with no page reading, are audited as before."""
    from app.modules.math.tool_check import READ_KINDS, intent_in_user_text

    sources = [text for text in (extract.source_text, extract.alternate_source_text) if text]
    # No page reading to hold it to: the OCR path declines a vision read without one
    # (``ocr.py``), so only a hand-built extract has none, and it is audited as before.
    if intent.kind not in READ_KINDS or not sources:
        return True
    return any(intent_in_user_text(intent, text) for text in sources)


async def unchecked_setup(setup: WordProblemSetup, settings: Settings) -> str | None:
    """A model's translation of a word problem with SymPy's solution, for the model to check
    against the words; None when SymPy finds no one solution, runs out of time or its pool
    breaks (the turn keeps its honesty note and never fails)."""
    from app.core.sympy_executor import run_sympy
    from app.modules.math.tools.block.word import unchecked_setup_note

    try:
        note: str | None = await run_sympy(
            unchecked_setup_note, setup, timeout=settings.stem_solve_timeout_seconds
        )
    except TimeoutError:
        note_solve_timeout("word_problem")
        return None
    except Exception:
        # BrokenProcessPool and its kin.
        logger.warning("word problem setup note failed", exc_info=True)
        return None
    return note
