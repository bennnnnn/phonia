"""One table of maths glyphs: every reader folds every operator glyph.

Eleven readers kept their own tables: an en dash was a minus to the solver and not to
the check of a reply's own arithmetic, and "⋅" folded in three of them (DUP-07).
"""

from __future__ import annotations

import pytest

from app.modules.chat.working_check import _plain
from app.modules.math.match.arithmetic import _to_ascii_arith
from app.modules.math.solve.latex_normalize import normalize_latex_to_sympy
from app.modules.math.tool_check import _normalize as tool_check_normalize
from app.services.glyphs import OPERATOR_GLYPHS, fold_operator_glyphs


@pytest.mark.parametrize(("glyph", "ascii_op"), sorted(OPERATOR_GLYPHS.items()))
def test_every_reader_folds_the_glyph(glyph: str, ascii_op: str) -> None:
    text = f"6 {glyph} 3"
    expected = f"6 {ascii_op} 3"
    assert fold_operator_glyphs(text) == expected
    assert _to_ascii_arith(text) == expected
    assert glyph not in tool_check_normalize(text)
    assert glyph not in normalize_latex_to_sympy(text)
    plain = _plain(text)
    assert plain is not None and glyph not in plain
