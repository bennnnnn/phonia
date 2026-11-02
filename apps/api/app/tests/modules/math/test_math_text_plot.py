"""A graph drawn in text characters is removed on a graph turn.

Reported from the app: "Graph it" after the slopes of y = 3x + 2 and y = 2x + 3
got a sketch made of ``*``, ``|`` and ``_``, which the phone wraps into rows of
broken symbols, even with the verified graph attached below it.
"""

from __future__ import annotations

import pytest

from app.modules.math.text_plot import (
    is_graph_turn,
    strip_text_plots,
    strip_text_plots_on_graph_turn,
)

_LINES = """Here's a quick sketch of the two lines:

- **Blue line:** $y = 3x + 2$ (steeper)
- **Red line:** $y = 2x + 3$ (flatter)

y ^
  |        *
  |      *   *
  |    *   *
  |*
  *______________________> x
  0   1   2   3   4

The blue line passes through (0,2) and (1,5)."""

_LABELLED = """Here's a quick sketch:

y ^
12|           * (2x+3) line
  |         /
 9|       *
  |     /
 0+------------------------------ x"""

_FENCED = """Sketch:

```
y
|      *
|    *
|  *
+-------- x
```

Done."""


@pytest.mark.parametrize("reply", [_LINES, _LABELLED, _FENCED])
def test_a_sketch_in_characters_is_removed(reply: str) -> None:
    cleaned = strip_text_plots(reply)

    assert "*" not in cleaned.replace("**", "")
    assert "|" not in cleaned
    assert "___" not in cleaned and "-----" not in cleaned


def test_the_words_around_a_sketch_stay() -> None:
    cleaned = strip_text_plots(_LINES)

    assert "$y = 3x + 2$" in cleaned
    assert cleaned.endswith("The blue line passes through (0,2) and (1,5).")


@pytest.mark.parametrize(
    "reply",
    [
        "| x | y |\n|---|---|\n| 0 | 2 |\n| 1 | 5 |\n| 2 | 8 |",
        '```python\nprint("|  *  |")\nprint("|  *  |")\nprint("+-----+")\n```',
        "The slope is $3$.\n\n- $y = 3x + 2$\n- $y = 2x + 3$",
    ],
)
def test_tables_code_and_prose_are_left_alone(reply: str) -> None:
    assert strip_text_plots(reply) == reply


def test_an_ascii_drawing_the_learner_asked_for_is_left_alone() -> None:
    assert not is_graph_turn("draw a cat in ascii", None)
    assert strip_text_plots_on_graph_turn(_FENCED, "draw a cat in ascii", None) == _FENCED


@pytest.mark.parametrize("text", ["Graph it", "plot sin(x)", "graph y = 3x + 2 and explain"])
def test_a_graph_request_is_a_graph_turn(text: str) -> None:
    assert is_graph_turn(text, None)
    assert "|" not in strip_text_plots_on_graph_turn(_LINES, text, None)
