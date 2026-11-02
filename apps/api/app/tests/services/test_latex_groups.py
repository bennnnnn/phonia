"""One brace matcher for the readers of a reply's or a keyboard's TeX."""

import pytest

from app.services.latex_groups import closed_group_end, group_end


@pytest.mark.parametrize(
    ("latex", "brace", "closed", "end"),
    [
        (r"\text{m/s} + 1", 5, 10, 10),
        (r"\frac{a{b}c}{d}", 5, 12, 12),
        ("{}", 0, 2, 2),
        # Never closes: the reader stops at the text's end, the strict one finds no group.
        (r"\text{m/s", 5, None, 9),
        ("{{x}", 0, None, 4),
        # No group opens here: the strict one says so.
        ("a{b}", 0, None, None),
        ("ab", 5, None, None),
    ],
)
def test_group_end_finds_the_matching_brace(
    latex: str, brace: int, closed: int | None, end: int | None
) -> None:
    assert closed_group_end(latex, brace) == closed
    if end is not None:
        assert group_end(latex, brace) == end
